from types import SimpleNamespace

import pytest

from incidentlab import evaluate_rehearsal as evaluation
from incidentlab.models import Action


class FakeLab:
    def __init__(self, directory):
        self.directory = directory
        self.injections = []
        self.applied = []
        self.closed = False

    def inject(self, scenario_id, seed):
        self.case = next(case for case in evaluation.MANIFEST["scenarios"] if case["id"] == scenario_id)
        self.injections.append((scenario_id, seed))
        self.actions = []
        return {"scenario_id": scenario_id, "seed": seed}

    def apply_plan(self, actions):
        self.actions = [action.value for action in actions]
        self.applied.append(self.actions)
        return {"actions": self.actions, "verification": self.probe(5)}

    def probe(self, count):
        healthy = self.case["id"] == "healthy" or (
            bool(self.case["expected_actions"]) and set(self.case["expected_actions"]).issubset(self.actions)
        )
        return {"requests": count, "statuses": [200 if healthy else 500] * count,
                "all_healthy": healthy, "median_latency_ms": 1}

    def close(self):
        self.closed = True


def fake_investigate(lab, mode):
    actions = lab.case["expected_actions"]
    action = Action(actions[0]) if actions else Action.none
    return SimpleNamespace(finding=SimpleNamespace(action=action), model_dump=lambda **kwargs: {
        "finding": {"action": action.value}, "traces": [{"tool": "test observation"}], "elapsed_ms": 1,
    })


def plan(identifier, actions, healthy=False):
    return {"id": identifier, "actions": actions,
            "verification": {"requests": 3, "statuses": [200 if healthy else 500] * 3,
                             "all_healthy": healthy, "median_latency_ms": 1}, "elapsed_ms": 1}


def fake_rehearsal(lab, max_actions, probe_count):
    assert max_actions == 2 and probe_count == 3
    actions = lab.case["expected_actions"]
    return {"control": plan("control", [], lab.case["id"] == "healthy"),
            "experiments": [plan("candidate", actions, True)] if actions else [],
            "recommended_plan_id": "candidate" if actions else None,
            "summary": {"tested_plans": int(bool(actions)), "control_healthy": lab.case["id"] == "healthy"}}


@pytest.fixture
def fake_protocol(monkeypatch):
    labs = []

    def factory(directory):
        lab = FakeLab(directory)
        labs.append(lab)
        return lab

    monkeypatch.setattr(evaluation, "Lab", factory)
    monkeypatch.setattr(evaluation, "Toolbox", lambda lab: lab)
    monkeypatch.setattr(evaluation, "investigate", fake_investigate)
    monkeypatch.setattr(evaluation, "run_rehearsal", fake_rehearsal)
    return labs


def test_frozen_rehearsal_suite_has_known_case_denominators():
    manifest = evaluation.MANIFEST
    assert len(manifest["scenarios"]) == 10
    assert len(manifest["scenarios"]) * len(manifest["splits"]["test"]) == 30
    assert set(manifest["splits"]["smoke"]).isdisjoint(manifest["splits"]["test"])
    assert sum(len(case["expected_actions"]) == 1 for case in manifest["scenarios"]) == 5
    assert sum(len(case["expected_actions"]) == 2 for case in manifest["scenarios"]) == 3


def test_comparison_uses_independent_identical_injections_and_fresh_verification(fake_protocol):
    report = evaluation.evaluate("test")
    summary = report["summary"]
    assert len(fake_protocol) == 2
    assert fake_protocol[0].directory != fake_protocol[1].directory
    assert fake_protocol[0].injections == fake_protocol[1].injections
    assert len(fake_protocol[0].injections) == 30
    assert all(lab.closed for lab in fake_protocol)
    assert summary["episodes"] == 30 and summary["episode_errors"] == 0
    assert summary["fault_episodes"] == 24
    assert summary["baseline"]["verified_recoveries"] == 15
    assert summary["rehearsal"]["verified_recoveries"] == 24
    assert summary["baseline"]["compound_fault_recoveries"] == 0
    assert summary["rehearsal"]["compound_fault_recoveries"] == 9
    assert summary["recovery_improvement_percentage_points"] == 37.5
    assert summary["compound_recovery_improvement_percentage_points"] == 100
    assert summary["baseline"]["control_no_action_rate"] == 1
    assert summary["rehearsal"]["control_no_action_rate"] == 1
    assert summary["candidate_experiments"] == 24
    assert summary["rehearsal_control_experiments"] == 30
    assert summary["rehearsal_probe_requests"] == (24 + 30) * 3
    assert "NOT Mistral" in report["provenance"] and len(report["manifest_sha256"]) == 64
    assert all(episode[arm]["verification"]["requests"] == 5
               for episode in report["episodes"] for arm in ("baseline", "rehearsal"))


def test_baseline_failure_remains_in_denominator_and_does_not_skip_rehearsal(fake_protocol, monkeypatch):
    def broken_investigate(lab, mode):
        if lab.case["id"] == "wrong_route":
            raise RuntimeError("deliberate comparator failure")
        return fake_investigate(lab, mode)

    monkeypatch.setattr(evaluation, "investigate", broken_investigate)
    report = evaluation.evaluate()
    summary = report["summary"]
    assert summary["episode_errors"] == 1
    assert summary["baseline"]["errors"] == 1
    assert summary["baseline"]["recovery_rate"] == 4 / 8
    assert summary["rehearsal"]["recovery_rate"] == 1
    assert report["episodes"][0]["rehearsal"]["completed"] is True


def test_evaluator_executes_selected_plan_and_never_substitutes_expected_actions(fake_protocol, monkeypatch):
    def wrong_recommendation(lab, **kwargs):
        return {"control": plan("control", []),
                "experiments": [plan("wrong", [Action.rollback.value]),
                                plan("actually_successful", lab.case["expected_actions"], True)],
                "recommended_plan_id": "wrong"}

    monkeypatch.setattr(evaluation, "run_rehearsal", wrong_recommendation)
    lab = FakeLab("unused")
    outcome = evaluation._run_arm(lab, "rehearsal", "route_and_release", 42)
    assert outcome["completed"] is True
    assert outcome["actions"] == [Action.rollback.value]
    assert lab.applied == [[Action.rollback.value]]
    assert outcome["recovered"] is False


def test_unknown_recommendation_is_recorded_as_failure(fake_protocol, monkeypatch):
    monkeypatch.setattr(evaluation, "run_rehearsal", lambda *args, **kwargs: {
        "control": plan("control", []), "experiments": [], "recommended_plan_id": "unmeasured",
    })
    outcome = evaluation._run_arm(FakeLab("unused"), "rehearsal", "wrong_route", 42)
    assert "missing from measured experiments" in outcome["error"]
    assert outcome["completed"] is False and outcome["no_action"] is False


def test_failed_control_is_not_counted_as_successful_abstention(fake_protocol, monkeypatch):
    monkeypatch.setattr(evaluation, "run_rehearsal", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failure")))
    report = evaluation.evaluate()
    assert report["summary"]["rehearsal"]["control_no_action_rate"] == 0
    assert report["summary"]["rehearsal"]["telemetry_gap_abstention_rate"] == 0


def test_empty_summary_does_not_invent_rates():
    summary = evaluation.summarize([])
    assert summary["fault_episodes"] == 0
    assert summary["recovery_improvement_percentage_points"] is None
    assert summary["baseline"]["recovery_rate"] is None
    assert summary["rehearsal"]["control_no_action_rate"] is None


def test_invalid_split_fails_before_starting_lab(fake_protocol):
    with pytest.raises(ValueError, match="Unknown rehearsal"):
        evaluation.evaluate("unknown")
    assert fake_protocol == []
