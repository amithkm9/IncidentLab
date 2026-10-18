import copy
from collections import Counter
from types import SimpleNamespace

import pytest

from incidentlab import proof
from incidentlab.contracts import CHECKOUT_CONTRACT
from incidentlab.lab import Lab
from incidentlab.models import Action


def run(snapshot, actions):
    return proof.run_recovery_proof(
        snapshot,
        actions,
        rehearsal_id="a" * 32,
        plan_id="plan-02",
        episode_id="episode",
        revision=2,
    )


def measurement(*, passed=False, status=200):
    checks = []
    for index in range(9):
        sku, cents = CHECKOUT_CONTRACT.prices[index % 3]
        checks.append(
            {
                "sku": sku,
                "expected_total_cents": cents,
                "observed_sku": sku if status == 200 else None,
                "observed_total_cents": (cents if passed else cents + 100)
                if status == 200
                else None,
                "request_id": str(index) if status == 200 else None,
                "http_status": status,
                "evaluated": status == 200,
                "passed": passed,
                "violations": []
                if passed
                else ["price_mismatch" if status == 200 else "http_status_not_ok"],
            }
        )
    return {
        "requests": 9,
        "statuses": [status] * 9,
        "all_http_healthy": status == 200,
        "semantic_passed": passed,
        "all_healthy": passed,
        "semantic_checks": checks,
        "contract": CHECKOUT_CONTRACT.metadata(),
        "median_latency_ms": 1,
    }


def fake_snapshot():
    return SimpleNamespace(contract=CHECKOUT_CONTRACT, fingerprint=lambda: "snapshot-fingerprint")


def test_digest_is_stable_under_key_order_and_detects_changed_content():
    original = proof.seal_proof(
        {"actions": [Action.route.value], "summary": {"passed": True}, "schema_version": 1}
    )
    reordered = {key: original[key] for key in reversed(original)}
    assert proof.verify_proof_integrity(reordered)
    assert original["digest"]["signed"] is False
    changed = copy.deepcopy(original)
    changed["summary"]["passed"] = False
    assert not proof.verify_proof_integrity(changed)
    assert proof.content_digest(original) != proof.content_digest(changed)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(all_healthy=True),
        lambda value: value.update(semantic_checks=value["semantic_checks"][:3]),
        lambda value: value["semantic_checks"][0].update(expected_total_cents=1),
        lambda value: value.update(contract={"id": "other"}),
        lambda value: value.update(statuses=[True] * 9),
    ],
)
def test_contradictory_or_incomplete_measurement_cannot_authorize_proof(monkeypatch, mutation):
    def measure(snapshot, directory, actions):
        value = measurement()
        mutation(value)
        return value

    monkeypatch.setattr(proof, "_measure", measure)
    result = run(fake_snapshot(), [Action.rollback.value])
    assert result["error"]["code"] == "invalid_verification"
    assert result["summary"]["promotion_eligible"] is False
    assert result["summary"]["completed_trials"] == 0
    assert result["budget"]["started_trials"] == 1
    assert proof.verify_proof_integrity(result)


def test_ablation_error_keeps_full_success_but_blocks_authority(monkeypatch):
    seen = []

    def measure(snapshot, directory, actions):
        seen.append(list(actions))
        if directory.name == "without-01":
            raise RuntimeError("SECRET-LOCAL-DETAIL")
        return measurement(passed=len(actions) == 2, status=200 if actions else 502)

    monkeypatch.setattr(proof, "_measure", measure)
    result = run(fake_snapshot(), [Action.route.value, Action.rollback.value])
    assert result["summary"]["full_plan_passed"] is True
    assert result["summary"]["promotion_eligible"] is False
    assert result["summary"]["conclusion"] == "inconclusive"
    assert result["summary"]["all_actions_necessary"] is None
    assert result["budget"]["started_trials"] == 3
    assert result["budget"]["completed_trial_requests"] == 18
    assert result["error"]["trial_id"] == "without-01"
    assert "SECRET" not in str(result)
    assert seen == [[], [Action.route.value, Action.rollback.value], [Action.rollback.value]]


@pytest.mark.parametrize(
    "actions",
    [
        [],
        [Action.none.value],
        [Action.route.value, Action.route.value],
        [Action.route.value, Action.rollback.value, Action.database.value],
        ["run_shell"],
    ],
)
def test_invalid_proof_plan_fails_before_measurement(monkeypatch, actions):
    def forbidden(*args):
        raise AssertionError("No experiment should start")

    monkeypatch.setattr(proof, "_measure", forbidden)
    with pytest.raises(ValueError):
        run(fake_snapshot(), actions)


def test_real_compound_proof_distinguishes_transport_and_business_necessity(lab):
    lab.inject("route_and_price_drift")
    before, fingerprint = lab.status(), lab.fingerprint()
    result = run(lab.snapshot(), [Action.route.value, Action.rollback.value])
    assert result["summary"]["conclusion"] == "supported"
    assert result["summary"]["all_actions_necessary"] is True
    assert result["summary"]["promotion_eligible"] is True
    assert result["budget"]["completed_trial_requests"] == 36
    assert result["budget"]["provider_calls"] == 0
    by_id = {trial["id"]: trial for trial in result["trials"]}
    assert by_id["full-plan"]["verification"]["all_healthy"]
    assert by_id["without-01"]["verification"]["all_http_healthy"] is False
    assert by_id["without-02"]["verification"]["all_http_healthy"] is True
    assert by_id["without-02"]["verification"]["semantic_passed"] is False
    for trial in result["trials"]:
        assert Counter(check["sku"] for check in trial["verification"]["semantic_checks"]) == {
            "notebook": 3,
            "lamp": 3,
            "mug": 3,
        }
    assert lab.status() == before and lab.fingerprint() == fingerprint
    assert proof.verify_proof_integrity(result)


def test_single_action_proof_reuses_control_and_ignores_scenario_label(lab):
    lab.inject("route_and_price_drift")
    lab.apply(Action.route)
    lab.scenario_id = "healthy"
    result = run(lab.snapshot(), [Action.rollback.value])
    assert result["summary"]["promotion_eligible"]
    assert result["summary"]["planned_trials"] == result["summary"]["completed_trials"] == 2
    assert [trial["id"] for trial in result["trials"]] == ["control", "full-plan"]
    assert result["necessity"] == [
        {
            "action": Action.rollback.value,
            "trial_id": "control",
            "necessary": True,
            "conclusion": "necessary_in_measured_plan",
        }
    ]
    assert result["budget"]["completed_trial_requests"] == 18


def test_redundant_action_is_not_falsely_claimed_necessary(lab):
    lab.inject("wrong_route")
    result = run(lab.snapshot(), [Action.route.value, Action.rollback.value])
    assert result["summary"]["conclusion"] == "redundant_action"
    assert result["summary"]["all_actions_necessary"] is False
    assert result["summary"]["promotion_eligible"] is True
    by_action = {item["action"]: item for item in result["necessity"]}
    assert by_action[Action.route.value]["necessary"] is True
    assert by_action[Action.rollback.value]["necessary"] is False


def test_http_successful_full_plan_with_wrong_prices_fails_proof(lab):
    lab.inject("route_and_price_drift")
    result = run(lab.snapshot(), [Action.route.value])
    assert result["trials"][1]["verification"]["all_http_healthy"]
    assert result["summary"]["full_plan_passed"] is False
    assert result["summary"]["conclusion"] == "full_plan_failed"
    assert result["summary"]["promotion_eligible"] is False
    assert result["necessity"][0]["necessary"] is None


def test_trial_failure_closes_clones_and_preserves_failed_artifact(lab, monkeypatch):
    lab.inject("silent_price_drift")
    snapshot = lab.snapshot()
    clones = []
    original = Lab.from_snapshot

    def tracked(snapshot, directory):
        clone = original(snapshot, directory)
        clones.append(clone)
        return clone

    def failed_probe(self, count=4):
        raise RuntimeError("SECRET-FAILURE")

    monkeypatch.setattr(Lab, "from_snapshot", tracked)
    monkeypatch.setattr(Lab, "probe", failed_probe)
    result = run(snapshot, [Action.rollback.value])
    assert result["error"]["code"] == "trial_failed"
    assert result["summary"]["promotion_eligible"] is False
    assert len(clones) == 1
    assert clones[0].servers == clones[0].threads == []
    assert not clones[0].directory.exists()
    assert "SECRET" not in str(result)
    assert lab.status()["semantic_failures"] == 4
