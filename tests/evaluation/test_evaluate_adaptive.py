import json
from types import SimpleNamespace

import pytest

from incidentlab.evaluation import adaptive as evaluation
from incidentlab.models import Action


def verification(healthy, count=3):
    return {
        "requests": count,
        "statuses": [200 if healthy else 500] * count,
        "all_healthy": healthy,
        "median_latency_ms": 1,
    }


def experiment(identifier, actions=(), healthy=False, count=3):
    return {
        "id": identifier,
        "actions": list(actions),
        "verification": verification(healthy, count),
        "elapsed_ms": 1,
    }


class FakeLab:
    instances = []

    def __init__(self, directory):
        self.directory = directory
        self.actions, self.applied, self.probes = [], [], []
        self.closed = False
        self.instances.append(self)

    def inject(self, scenario_id, seed):
        self.case = next(item for item in evaluation.SCENARIOS if item["id"] == scenario_id)
        self.seed = seed
        return {"scenario_id": scenario_id, "seed": seed}

    def apply_plan(self, actions, probe_count=5):
        self.actions = [action.value for action in actions]
        self.applied.append(self.actions)
        return {"actions": self.actions, "verification": self.probe(probe_count)}

    def probe(self, count):
        self.probes.append(count)
        healthy = self.case["id"] == "healthy" or (
            bool(self.case["expected_actions"])
            and set(self.case["expected_actions"]).issubset(self.actions)
        )
        return verification(healthy, count)

    def close(self):
        self.closed = True


def fake_strategy(lab, strategy, max_experiments, max_actions, probe_count, planner=None):
    """Test oracle used only to isolate scoring, lifecycle, and guard behavior."""
    actions = lab.case["expected_actions"]
    selected = actions if strategy != "ordered" else actions[:1]
    success = bool(selected) and set(actions).issubset(selected)
    control_healthy = lab.case["id"] == "healthy"
    trials = [experiment("plan-01", selected, success, probe_count)] if selected else []
    return {
        "strategy": strategy,
        "control": experiment("control", healthy=control_healthy, count=probe_count),
        "experiments": trials,
        "recommended_plan_id": "plan-01" if success else None,
        "summary": {"telemetry_available": lab.case["id"] != "telemetry_gap"},
        "budget": {
            "max_experiments": max_experiments,
            "used_experiments": len(trials),
            "stop_reason": "verified_plan" if success else "candidate_budget_exhausted",
        },
        "decision_trace": [],
        "provider_usage": {
            "model": "mock-provider" if strategy == "mistral" else None,
            "api_calls": 1 if strategy == "mistral" else 0,
            "input_tokens": 20 if strategy == "mistral" else 0,
            "output_tokens": 10 if strategy == "mistral" else 0,
            "estimated_cost_usd": None if strategy == "mistral" else 0,
            "cost_note": "Prices unavailable" if strategy == "mistral" else "Offline policy",
        },
    }


@pytest.fixture
def fake_protocol(monkeypatch):
    FakeLab.instances = []
    monkeypatch.setattr(evaluation, "Lab", FakeLab)
    monkeypatch.setattr(evaluation, "_run_strategy", fake_strategy)
    return FakeLab.instances


def test_scoring_retains_all_known_cases_and_fresh_independent_source_labs(fake_protocol):
    report = evaluation.evaluate()
    summary = report["summary"]
    assert summary["episodes"] == 10
    assert (
        summary["fault_episodes"],
        summary["single_fault_episodes"],
        summary["compound_fault_episodes"],
        summary["control_episodes"],
    ) == (8, 5, 3, 2)
    assert summary["strategies"]["adaptive"]["verified_recoveries"] == 8
    assert summary["strategies"]["ordered"]["verified_recoveries"] == 5
    assert summary["offline_adaptive_vs_ordered_recovery_percentage_points"] == 37.5
    assert summary["strategies"]["adaptive"]["control_no_action_rate"] == 1
    assert len(fake_protocol) == 20
    assert len({str(lab.directory) for lab in fake_protocol}) == 20
    assert all(lab.closed and lab.probes == [5] for lab in fake_protocol)
    assert len(report["manifest_sha256"]) == 64
    assert report["manifest"]["max_experiments"] == 4
    assert report["model_strategy_selected"] is False
    assert "NOT Mistral model performance" in report["provenance"]
    assert "mistral" not in summary["strategies"]
    assert all(
        not arm["uses_model"] and arm["provider_usage"]["recorded_api_calls"] == 0
        for arm in summary["strategies"].values()
    )


def test_candidate_and_probe_limits_reach_both_strategies_identically(fake_protocol, monkeypatch):
    calls = []

    def observe(lab, strategy, max_experiments, max_actions, probe_count, planner=None):
        calls.append((strategy, max_experiments, max_actions, probe_count))
        return fake_strategy(lab, strategy, max_experiments, max_actions, probe_count)

    monkeypatch.setattr(evaluation, "_run_strategy", observe)
    report = evaluation.evaluate(seeds=(11, 23), max_experiments=2, probe_count=5)
    assert set(calls) == {("adaptive", 2, 2, 5), ("ordered", 2, 2, 5)}
    assert report["summary"]["episodes"] == 20
    assert len(fake_protocol) == 40


def test_one_failed_arm_does_not_skip_the_other_or_disappear_from_denominators(
    fake_protocol, monkeypatch
):
    def failing(lab, strategy, *args):
        if strategy == "adaptive" and lab.case["id"] == "wrong_route":
            raise RuntimeError("policy failed")
        return fake_strategy(lab, strategy, *args)

    monkeypatch.setattr(evaluation, "_run_strategy", failing)
    report = evaluation.evaluate()
    arm = report["summary"]["strategies"]["adaptive"]
    assert (arm["completed"], arm["errors"], arm["verified_recoveries"], arm["recovery_rate"]) == (
        9,
        1,
        7,
        0.875,
    )
    assert report["summary"]["episode_errors"] == 1
    assert report["episodes"][0]["strategies"]["ordered"]["completed"]
    assert all(lab.closed for lab in fake_protocol)


def test_reported_provider_errors_preserve_evidence_and_do_not_count_as_abstention(
    fake_protocol, monkeypatch
):
    def failed_report(lab, strategy, *args):
        report = fake_strategy(lab, strategy, *args)
        report["budget"]["stop_reason"] = "provider_error"
        report["error"] = {"code": "provider_error", "message": "Safe failure"}
        return report

    monkeypatch.setattr(evaluation, "_run_strategy", failed_report)
    report = evaluation.evaluate(strategies=("adaptive",))
    arm = report["summary"]["strategies"]["adaptive"]
    assert arm["errors"] == 10 and arm["completed"] == 0
    assert arm["control_no_action_rate"] == 0
    assert arm["telemetry_gap_abstention_rate"] == 0
    assert arm["candidate_experiments"] == 8
    assert all(item["strategies"]["adaptive"]["result"]["error"] for item in report["episodes"])
    assert all(not lab.applied for lab in fake_protocol)


@pytest.mark.parametrize(
    "mutation, error_fragment",
    [
        (lambda report: report.update(recommended_plan_id="unmeasured"), "missing from measured"),
        (
            lambda report: report["experiments"].extend(
                [experiment(f"extra-{i}", [Action.route.value]) for i in range(4)]
            ),
            "experiment budget",
        ),
        (
            lambda report: report["experiments"][0]["verification"].update(
                statuses=[500, 200, 200]
            ),
            "eligible measured success",
        ),
        (lambda report: report["experiments"][0]["verification"].update(requests=2), "probe count"),
        (
            lambda report: report["control"]["verification"].update(verification(True)),
            "eligible measured success",
        ),
        (
            lambda report: report["experiments"][0].update(actions=[Action.none.value]),
            "action budget",
        ),
    ],
)
def test_invalid_recommendations_never_apply_an_evaluator_substituted_fix(
    fake_protocol, monkeypatch, tmp_path, mutation, error_fragment
):
    def invalid(lab, strategy, *args):
        report = fake_strategy(lab, strategy, *args)
        mutation(report)
        return report

    monkeypatch.setattr(evaluation, "_run_strategy", invalid)
    outcome = evaluation._run_arm(tmp_path, "adaptive", "wrong_route", 42, 4, 2, 3)
    assert outcome["completed"] is False and outcome["recovered"] is False
    assert error_fragment in outcome["error"]
    assert FakeLab.instances[-1].applied == []


def test_fresh_verification_checks_statuses_instead_of_trusting_boolean(
    fake_protocol, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        FakeLab,
        "probe",
        lambda self, count: {"requests": count, "statuses": [500] * count, "all_healthy": True},
    )
    outcome = evaluation._run_arm(tmp_path, "adaptive", "wrong_route", 42, 4, 2, 3)
    assert outcome["completed"] and not outcome["recovered"]
    assert outcome["actions"] == [Action.route.value]


def test_source_construction_failures_are_recorded_per_arm(fake_protocol, monkeypatch):
    monkeypatch.setattr(
        evaluation, "Lab", lambda directory: (_ for _ in ()).throw(OSError("Cannot create lab"))
    )
    report = evaluation.evaluate()
    assert report["summary"]["episode_errors"] == 10
    assert all(
        arm["errors"] == 10 and arm["recovery_rate"] == 0
        for arm in report["summary"]["strategies"].values()
    )


@pytest.mark.parametrize(
    "options",
    [
        {"strategies": ()},
        {"strategies": ("unknown",)},
        {"strategies": ("adaptive", "adaptive")},
        {"seeds": ()},
        {"seeds": (42, 42)},
        {"seeds": (-1,)},
        {"seeds": (True,)},
        {"max_experiments": 0},
        {"max_experiments": 9},
        {"max_experiments": True},
        {"max_actions": 3},
        {"probe_count": 0},
        {"probe_count": 21},
    ],
)
def test_invalid_options_fail_before_any_lab_is_created(fake_protocol, options):
    with pytest.raises(ValueError):
        evaluation.evaluate(**options)
    assert fake_protocol == []


def test_mistral_requires_explicit_paid_opt_in_even_with_a_key(fake_protocol, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-only-key")
    with pytest.raises(ValueError, match="allow-paid-api"):
        evaluation.evaluate(strategies=("mistral",))
    assert fake_protocol == []


def test_mistral_requires_key_before_any_lab_is_created(fake_protocol, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        evaluation.evaluate(strategies=("mistral",), allow_paid_api=True)
    assert fake_protocol == []


def test_mistral_usage_and_scores_are_separate_and_missing_cost_stays_unknown(
    fake_protocol, monkeypatch
):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-only-key")
    report = evaluation.evaluate(strategies=("adaptive", "mistral"), allow_paid_api=True)
    arms = report["summary"]["strategies"]
    usage = arms["mistral"]["provider_usage"]
    assert report["model_strategy_selected"] is True
    assert arms["mistral"]["uses_model"] is True and arms["adaptive"]["uses_model"] is False
    assert usage["recorded_api_calls"] == 10
    assert usage["recorded_input_tokens"] == 200
    assert usage["estimated_cost_usd"] is None and not usage["cost_complete"]
    assert arms["adaptive"]["provider_usage"]["recorded_api_calls"] == 0
    assert "test-only-key" not in json.dumps(report)


def test_model_failure_exception_body_is_not_written_to_report(fake_protocol, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "secret-token")
    monkeypatch.setattr(
        evaluation,
        "_run_strategy",
        lambda *args: (_ for _ in ()).throw(RuntimeError("Bearer secret-token")),
    )
    report = evaluation.evaluate(strategies=("mistral",), allow_paid_api=True)
    assert "secret-token" not in json.dumps(report)
    assert (
        report["summary"]["strategies"]["mistral"]["provider_usage"]["estimated_cost_usd"] is None
    )


def test_fixed_order_is_bounded_and_does_not_inspect_scenario_metadata(monkeypatch):
    snapshot = SimpleNamespace(telemetry_available=True, fingerprint=lambda: "fingerprint")
    # This source exposes only snapshot(): no scenario label or expected answer.
    source = SimpleNamespace(snapshot=lambda: snapshot)
    calls = []

    def measured(state, directory, plan_id, actions, probe_count):
        assert state is snapshot
        calls.append((tuple(actions), probe_count))
        return experiment(plan_id, [action.value for action in actions], False, probe_count)

    monkeypatch.setattr(evaluation, "_experiment", measured)
    report = evaluation.run_ordered_rehearsal(source, max_experiments=4, probe_count=5)
    assert calls == [((), 5), *((((action,), 5)) for action in evaluation.EXECUTABLE_ACTIONS[:4])]
    assert report["budget"]["used_experiments"] == 4
    assert report["recommended_plan_id"] is None
    assert report["provider_usage"]["api_calls"] == 0


@pytest.mark.parametrize(
    "telemetry, healthy, expected",
    [(False, False, "missing_telemetry"), (True, True, "control_healthy")],
)
def test_ordered_controls_do_not_spend_candidate_budget(monkeypatch, telemetry, healthy, expected):
    snapshot = SimpleNamespace(telemetry_available=telemetry, fingerprint=lambda: "fingerprint")
    calls = []

    def measured(state, directory, plan_id, actions, probe_count):
        calls.append(plan_id)
        return experiment(plan_id, healthy=healthy, count=probe_count)

    monkeypatch.setattr(evaluation, "_experiment", measured)
    report = evaluation.run_ordered_rehearsal(SimpleNamespace(snapshot=lambda: snapshot))
    assert calls == ["control"]
    assert report["budget"]["stop_reason"] == expected
    assert report["recommended_plan_id"] is None


def test_ordered_search_stops_after_first_measured_success(monkeypatch):
    snapshot = SimpleNamespace(telemetry_available=True, fingerprint=lambda: "fingerprint")
    calls = []

    def measured(state, directory, plan_id, actions, probe_count):
        calls.append(plan_id)
        return experiment(
            plan_id, [action.value for action in actions], plan_id == "plan-02", probe_count
        )

    monkeypatch.setattr(evaluation, "_experiment", measured)
    report = evaluation.run_ordered_rehearsal(SimpleNamespace(snapshot=lambda: snapshot))
    assert calls == ["control", "plan-01", "plan-02"]
    assert report["recommended_plan_id"] == "plan-02"
    assert report["budget"]["stop_reason"] == "verified_plan"


def test_ordered_experiment_failure_retains_prior_measured_outcomes(monkeypatch):
    snapshot = SimpleNamespace(telemetry_available=True, fingerprint=lambda: "fingerprint")

    def measured(state, directory, plan_id, actions, probe_count):
        if plan_id == "plan-02":
            raise RuntimeError("Experiment failed")
        return experiment(plan_id, [action.value for action in actions], False, probe_count)

    monkeypatch.setattr(evaluation, "_experiment", measured)
    report = evaluation.run_ordered_rehearsal(SimpleNamespace(snapshot=lambda: snapshot))
    assert report["error"]["code"] == "experiment_error"
    assert report["recommended_plan_id"] is None
    assert report["control"]["id"] == "control"
    assert len(report["experiments"]) == 1
    assert report["budget"]["used_experiments"] == 2
    assert report["budget"]["completed_experiments"] == 1


def test_empty_summary_has_no_invented_rates():
    summary = evaluation.summarize([])
    assert summary["fault_episodes"] == 0
    assert summary["offline_adaptive_vs_ordered_recovery_percentage_points"] is None
    assert summary["strategies"]["adaptive"]["recovery_rate"] is None


def test_cli_saves_failed_case_artifact_before_nonzero_exit(fake_protocol, monkeypatch, tmp_path):
    target = tmp_path / "comparison.json"
    monkeypatch.setattr(
        evaluation,
        "_run_strategy",
        lambda *args: (_ for _ in ()).throw(RuntimeError("failed policy")),
    )
    monkeypatch.setattr(
        "sys.argv", ["incidentlab-adaptive-eval", "--seeds", "11,23", "--output", str(target)]
    )
    with pytest.raises(SystemExit) as exc:
        evaluation.main()
    assert exc.value.code == 1
    saved = json.loads(target.read_text())
    assert saved["manifest"]["seeds"] == [11, 23]
    assert saved["summary"]["episode_errors"] == 20
    assert len(saved["episodes"]) == 20
