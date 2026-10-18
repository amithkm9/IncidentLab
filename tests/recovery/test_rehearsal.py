import urllib.error
import urllib.request

import pytest

from incidentlab.domain.models import Action
from incidentlab.lab import Lab
from incidentlab.lab.scenarios import SCENARIO_BY_ID
from incidentlab.recovery.rehearsal import run_rehearsal


@pytest.mark.parametrize(
    "scenario_id", ["route_and_release", "database_and_inventory", "timeout_and_release"]
)
def test_rehearsal_finds_minimal_pair_without_changing_source(lab, scenario_id):
    lab.inject(scenario_id, seed=107)
    before = lab.status()
    fingerprint = lab.fingerprint()
    report = run_rehearsal(lab, probe_count=1)
    assert report["control"]["actions"] == []
    assert not report["control"]["verification"]["all_healthy"]
    assert report["summary"]["tested_plans"] == 15
    assert report["summary"]["minimal_action_count"] == 2
    assert all(
        not trial["verification"]["all_healthy"]
        for trial in report["experiments"]
        if len(trial["actions"]) == 1
    )
    recommended = next(
        trial for trial in report["experiments"] if trial["id"] == report["recommended_plan_id"]
    )
    assert set(recommended["actions"]) == {
        action.value for action in SCENARIO_BY_ID[scenario_id].expected_actions
    }
    assert recommended["verification"]["all_healthy"]
    assert lab.status() == before
    assert lab.fingerprint() == fingerprint == report["source_fingerprint"]


def test_insufficient_search_budget_does_not_claim_recovery(lab):
    lab.inject("route_and_release")
    report = run_rehearsal(lab, max_actions=1, probe_count=1)
    assert report["summary"]["tested_plans"] == 5
    assert report["summary"]["successful_plans"] == 0
    assert report["recommended_plan_id"] is None
    assert report["summary"]["abstention_reason"] == "no_successful_plan"


def test_rehearsal_uses_actual_repaired_state_and_ignores_scenario_label(lab):
    lab.inject("route_and_release")
    lab.apply(Action.route)
    # A deliberately false operator label must not guide experiment search.
    lab.scenario_id = "healthy"
    report = run_rehearsal(lab, max_actions=1, probe_count=1)
    recommended = next(
        trial for trial in report["experiments"] if trial["id"] == report["recommended_plan_id"]
    )
    assert recommended["actions"] == [Action.rollback.value]
    assert report["summary"]["minimal_action_count"] == 1
    assert lab.config["release"] == "checkout-1.1"


@pytest.mark.parametrize(
    "scenario_id,reason,plans",
    [("healthy", "control_healthy", 5), ("telemetry_gap", "missing_telemetry", 0)],
)
def test_controls_never_recommend_mutations(lab, scenario_id, reason, plans):
    lab.inject(scenario_id)
    report = run_rehearsal(lab, max_actions=1, probe_count=1)
    assert report["recommended_plan_id"] is None
    assert report["summary"]["minimal_action_count"] is None
    assert report["summary"]["abstention_reason"] == reason
    assert report["summary"]["tested_plans"] == plans


def test_trial_failure_closes_servers_and_removes_temporary_database(lab, monkeypatch):
    lab.inject("wrong_route")
    opened = []
    original = Lab.from_snapshot.__func__

    def track_clone(cls, snapshot, directory):
        clone = original(cls, snapshot, directory)
        opened.append((clone, clone.checkout_url, clone.directory))
        return clone

    def fail_probe(self, count=4):
        raise RuntimeError("Synthetic probe failure")

    monkeypatch.setattr(Lab, "from_snapshot", classmethod(track_clone))
    monkeypatch.setattr(Lab, "probe", fail_probe)
    with pytest.raises(RuntimeError, match="Synthetic probe failure"):
        run_rehearsal(lab, max_actions=1, probe_count=1)
    assert len(opened) == 1
    clone, endpoint, directory = opened[0]
    assert clone.servers == []
    assert clone.threads == []
    assert not directory.exists()
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(endpoint + "/health", timeout=0.2)
    assert lab.status()["errors"] == 4


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_actions": 0},
        {"max_actions": 3},
        {"max_actions": True},
        {"probe_count": 0},
        {"probe_count": 21},
        {"probe_count": True},
    ],
)
def test_invalid_budget_fails_before_spawning_trials(lab, kwargs):
    before = lab.status()
    with pytest.raises(ValueError):
        run_rehearsal(lab, **kwargs)
    assert lab.status() == before
