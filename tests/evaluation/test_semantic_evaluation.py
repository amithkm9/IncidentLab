import copy
import json
from types import SimpleNamespace

import pytest

from incidentlab.domain.contracts import CHECKOUT_CONTRACT, validate_checkout_response
from incidentlab.domain.models import Action
from incidentlab.evaluation import semantic as evaluation


def verification(count=3, status=200, offset=0):
    skus = tuple(CHECKOUT_CONTRACT.expected_totals_cents)
    checks = []
    for index in range(count):
        sku = skus[index % len(skus)]
        body = json.dumps(
            {
                "sku": sku,
                "total": (CHECKOUT_CONTRACT.expected_totals_cents[sku] + offset) / 100,
                "request_id": f"request-{index}",
            }
        )
        checks.append(validate_checkout_response(body, status, sku))
    passed = all(check["passed"] for check in checks)
    return {
        "requests": count,
        "statuses": [status] * count,
        "all_http_healthy": status == 200,
        "semantic_passed": passed,
        "all_healthy": status == 200 and passed,
        "semantic_checks": checks,
        "contract": CHECKOUT_CONTRACT.metadata(),
        "median_latency_ms": 1,
    }


def test_identical_http_responses_expose_semantic_false_recovery():
    record = verification(offset=100)
    before = copy.deepcopy(record)
    acceptance = evaluation._acceptance(record, 3)
    assert record == before
    assert acceptance == {
        "status_only_accepted": True,
        "semantic_accepted": False,
        "status_only_false_recovery": True,
    }
    assert all(
        check["observed_total_cents"] - check["expected_total_cents"] == 100
        for check in record["semantic_checks"]
    )
    assert evaluation._acceptance(verification(), 3)["semantic_accepted"] is True
    assert (
        evaluation._acceptance(verification(status=500), 3)["status_only_false_recovery"] is False
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("contract"),
        lambda value: value.update(semantic_passed=False),
        lambda value: value["semantic_checks"].pop(),
        lambda value: value["contract"].update(sha256="0" * 64),
        lambda value: value["semantic_checks"][0].update(expected_total_cents=1),
        lambda value: value["semantic_checks"][0].update(http_status=500),
        lambda value: value["semantic_checks"][0].update(observed_total_cents=999),
    ],
)
def test_missing_or_contradictory_contract_records_are_errors_not_counterexamples(mutation):
    record = verification()
    mutation(record)
    with pytest.raises(ValueError):
        evaluation._acceptance(record, 3)


def test_other_contract_violations_remain_semantic_failures():
    record = verification(count=1)
    record["semantic_checks"][0].update(
        request_id=None, passed=False, violations=["missing_request_id"]
    )
    record.update(semantic_passed=False, all_healthy=False)
    assert evaluation._acceptance(record, 1)["status_only_false_recovery"] is True


class FakeLab:
    instances = []

    def __init__(self, directory):
        self.directory, self.closed = directory, False
        self.instances.append(self)

    def inject(self, scenario_id, seed):
        self.scenario_id, self.seed = scenario_id, seed
        return {"scenario_id": scenario_id, "seed": seed}

    def snapshot(self):
        return SimpleNamespace(scenario_id=self.scenario_id, fingerprint=lambda: self.fingerprint())

    def fingerprint(self):
        return "snapshot-" + self.scenario_id

    def close(self):
        self.closed = True


def measured(snapshot, directory, identifier, actions, count):
    actions = {action.value for action in actions}
    scenario = snapshot.scenario_id
    route_missing = (
        scenario in {"route_and_release", "route_and_price_drift"}
        and Action.route.value not in actions
    )
    release_bad = (
        scenario in {"bad_release", "route_and_release"} and Action.rollback.value not in actions
    )
    silent = (
        scenario in {"silent_price_drift", "route_and_price_drift"}
        and Action.rollback.value not in actions
    )
    status = 502 if route_missing or scenario == "telemetry_gap" else 500 if release_bad else 200
    return {
        "id": identifier,
        "actions": sorted(actions),
        "verification": verification(count, status, 100 if silent else 0),
        "elapsed_ms": 1,
    }


def policy_outcome(
    directory, strategy, scenario_id, seed, max_experiments, max_actions, probe_count, planner=None
):
    case = next(case for case in evaluation.MANIFEST["scenarios"] if case["id"] == scenario_id)
    actions = case["expected_actions"]
    final = verification(5, 502 if scenario_id == "telemetry_gap" else 200)
    trial = {"verification": verification(probe_count), "actions": actions}
    usage = {
        "model": "mock-provider" if strategy == "mistral" else None,
        "api_calls": 1 if strategy == "mistral" else 0,
        "input_tokens": 100 if strategy == "mistral" else 0,
        "output_tokens": 10 if strategy == "mistral" else 0,
        "estimated_cost_usd": None if strategy == "mistral" else 0,
        "cost_note": "Test fixture only",
    }
    return {
        "completed": True,
        "actions": list(actions),
        "no_action": not actions,
        "recovered": bool(actions),
        "verification": final,
        "remediation": {"verification": final} if actions else None,
        "elapsed_ms": 1,
        "error": None,
        "result": {
            "control": trial,
            "experiments": [trial] if actions else [],
            "provider_usage": usage,
            "budget": {"used_experiments": int(bool(actions))},
        },
    }


@pytest.fixture
def fake_protocol(monkeypatch):
    FakeLab.instances = []
    calls = []

    def measure(*args):
        calls.append(args)
        return measured(*args)

    monkeypatch.setattr(evaluation, "Lab", FakeLab)
    monkeypatch.setattr(evaluation, "measure_plan", measure)
    monkeypatch.setattr(evaluation.policy_evaluation, "_run_arm", policy_outcome)
    return calls


def test_frozen_suite_scores_paired_trials_and_separate_policy_recovery(fake_protocol):
    report = evaluation.evaluate("test")
    summary = report["summary"]
    assert summary["episodes"] == 18 and summary["episode_errors"] == 0
    pairs = summary["paired_acceptance"]
    assert pairs["attempted_trials"] == pairs["completed_trials"] == 72
    assert pairs["status_only_acceptances"] == 39
    assert pairs["semantic_acceptances"] == 30
    assert pairs["status_only_false_recoveries"] == 9
    assert pairs["recorded_probe_requests"] == 216
    recovery = summary["policy_recovery"]
    assert recovery["fault_episodes"] == 12 and recovery["control_episodes"] == 6
    assert recovery["strategies"]["adaptive"]["verified_recoveries"] == 12
    assert recovery["strategies"]["adaptive"]["control_no_action_rate"] == 1
    assert len(summary["false_recovery_examples"]) == 9
    assert "NOT Mistral" in report["provenance"]
    assert report["manifest"]["contract"] == CHECKOUT_CONTRACT.metadata()
    assert len(report["manifest_sha256"]) == 64
    assert all(lab.closed for lab in FakeLab.instances)


def test_each_fixed_plan_uses_one_identical_snapshot_and_known_probe_count(fake_protocol):
    evaluation.evaluate()
    assert len(fake_protocol) == 24
    for offset in range(0, len(fake_protocol), 4):
        group = fake_protocol[offset : offset + 4]
        assert all(call[0] is group[0][0] for call in group)
        assert [call[2] for call in group] == [
            plan["id"] for plan in evaluation.MANIFEST["acceptance_plans"]
        ]
        assert [[action.value for action in call[3]] for call in group] == [
            plan["actions"] for plan in evaluation.MANIFEST["acceptance_plans"]
        ]
        assert all(call[4] == 3 for call in group)


def test_failed_measurement_and_policy_remain_in_denominators(fake_protocol, monkeypatch):
    def failed_trial(snapshot, directory, identifier, actions, count):
        if snapshot.scenario_id == "silent_price_drift" and identifier == "control":
            raise OSError("SECRET-LOCAL-DETAIL")
        return measured(snapshot, directory, identifier, actions, count)

    def failed_policy(*args):
        outcome = policy_outcome(*args)
        if args[2] == "silent_price_drift":
            outcome.update(
                completed=False,
                recovered=False,
                no_action=False,
                verification=None,
                error="provider_error",
            )
        return outcome

    monkeypatch.setattr(evaluation, "measure_plan", failed_trial)
    monkeypatch.setattr(evaluation.policy_evaluation, "_run_arm", failed_policy)
    report = evaluation.evaluate()
    assert report["summary"]["episode_errors"] == 1
    pairs = report["summary"]["paired_acceptance"]
    assert pairs["attempted_trials"] == 24 and pairs["completed_trials"] == 23
    assert pairs["failed_or_unverifiable_trials"] == 1
    assert pairs["status_only_acceptance_rate"] == 0.5
    assert report["summary"]["policy_recovery"]["strategies"]["adaptive"]["recovery_rate"] == 0.75
    assert "SECRET-LOCAL-DETAIL" not in json.dumps(report)
    assert all(lab.closed for lab in FakeLab.instances)


def test_policy_result_is_not_repaired_using_expected_actions(fake_protocol, monkeypatch, tmp_path):
    def wrong_policy(*args):
        outcome = policy_outcome(*args)
        outcome["actions"] = [Action.route.value]
        outcome["verification"] = verification(5, offset=100)
        return outcome

    monkeypatch.setattr(evaluation.policy_evaluation, "_run_arm", wrong_policy)
    outcome = evaluation._policy_arm(tmp_path, "adaptive", "silent_price_drift", 42, 4, 2, 3)
    assert outcome["actions"] == [Action.route.value]
    assert outcome["completed"] is True and outcome["recovered"] is False
    assert outcome["status_only_recovered"] is True


def test_policy_final_verification_must_be_five_consistent_checks(
    fake_protocol, monkeypatch, tmp_path
):
    def short_verification(*args):
        outcome = policy_outcome(*args)
        outcome["verification"] = verification(1)
        return outcome

    monkeypatch.setattr(evaluation.policy_evaluation, "_run_arm", short_verification)
    outcome = evaluation._policy_arm(tmp_path, "adaptive", "silent_price_drift", 42, 4, 2, 3)
    assert outcome["completed"] is False and outcome["recovered"] is False
    assert outcome["error"] is not None


@pytest.mark.parametrize(
    "options",
    [
        {"strategies": ("mistral",)},
        {"strategies": ("mistral",), "allow_paid_api": True},
        {"split": "unknown"},
        {"max_experiments": 9},
        {"strategies": ("ordered",)},
    ],
)
def test_preflight_rejects_unauthorized_paid_calls_and_bad_options(
    fake_protocol, monkeypatch, options
):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ValueError):
        evaluation.evaluate(**options)
    assert FakeLab.instances == [] and fake_protocol == []


def test_optional_mistral_usage_is_separate_and_preserved_in_summary(fake_protocol, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "mock-only-no-network")
    report = evaluation.evaluate(strategies=("adaptive", "mistral"), allow_paid_api=True)
    arms = report["summary"]["policy_recovery"]["strategies"]
    assert arms["adaptive"]["provider_usage"]["recorded_api_calls"] == 0
    assert arms["mistral"]["provider_usage"]["recorded_api_calls"] == 6
    assert arms["mistral"]["provider_usage"]["recorded_input_tokens"] == 600
    assert arms["mistral"]["provider_usage"]["estimated_cost_usd"] is None
    assert report["model_strategy_selected"] is True


def test_empty_summary_does_not_invent_acceptance_rates():
    result = evaluation.summarize([])
    assert result["paired_acceptance"]["attempted_trials"] == 0
    assert result["paired_acceptance"]["false_recovery_fraction_of_status_acceptances"] is None
    assert result["policy_recovery"]["strategies"]["adaptive"]["recovery_rate"] is None


def test_real_silent_corruption_exposes_same_response_counterexample(tmp_path):
    result = evaluation._paired_trials(tmp_path / "real", "silent_price_drift", 42, 3)
    assert result["error"] is None and result["source_unchanged"] is True
    control = next(trial for trial in result["trials"] if trial["id"] == "control")
    rollback = next(trial for trial in result["trials"] if trial["id"] == "rollback")
    assert control["verification"]["statuses"] == [200] * 3
    assert control["status_only_false_recovery"] is True
    assert rollback["semantic_accepted"] is True
