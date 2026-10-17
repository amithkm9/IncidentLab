import json
import urllib.error
import urllib.request

import pytest

from incidentlab.investigator import baseline
from incidentlab.lab import SCENARIOS
from incidentlab.models import Action, Cause
from incidentlab.tools import Toolbox


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.id)
def test_real_fault_diagnosis_and_recovery(lab, scenario):
    before = lab.inject(scenario.id, seed=107)
    assert before["requests"] == 4
    assert before["errors"] == (0 if scenario.cause == Cause.healthy else 4)
    result = baseline(Toolbox(lab))
    assert result.finding.cause == scenario.cause
    assert result.finding.action == scenario.action
    if scenario.action != Action.none:
        recovery = lab.apply(result.finding.action)
        assert recovery["verification"]["statuses"] == [200] * 5
        assert lab.status()["requests"] == 5
        assert lab.status()["errors"] == 0
        assert baseline(Toolbox(lab)).finding.cause == Cause.healthy


def test_http_liveness_does_not_establish_checkout_readiness(lab):
    lab.inject("inventory_down")
    with urllib.request.urlopen(lab.checkout_url + "/health") as response:
        assert response.status == 200
    with pytest.raises(urllib.error.HTTPError) as raised:
        urllib.request.urlopen(lab.checkout_url + "/checkout")
    assert raised.value.code == 502


def test_wrong_fix_does_not_claim_recovery(lab):
    lab.inject("wrong_route")
    assert not lab.apply(Action.dependency)["verification"]["all_healthy"]


def test_telemetry_gap_does_not_expose_ground_truth(lab):
    lab.inject("telemetry_gap")
    toolbox = Toolbox(lab)
    for name in ("query_logs", "get_service_health", "get_recent_changes", "get_metrics"):
        result = toolbox.invoke(name, {})
        assert {entry["source"] for entry in result["evidence"]} == {"collector"}
    observations = toolbox.serialized_evidence()
    assert "scenario_id" not in observations
    assert "inventory_ready" not in observations
    assert "dependency_unavailable" not in observations


def test_invalid_mutating_tool_is_rejected(lab):
    lab.inject("wrong_route")
    toolbox = Toolbox(lab)
    result = toolbox.invoke("apply", {"action": "restore_inventory_route"})
    assert result["error"]
    assert lab.status()["errors"] == 4
    assert toolbox.invoke("query_logs", {"limit": 1000})["error"] == "Invalid tool arguments"
    assert toolbox.invoke("get_metrics", {"scenario_id": "healthy"})["error"] == "Invalid tool arguments"


def test_prior_window_requests_cannot_contaminate_recovery(lab):
    lab.inject("tight_timeout")
    previous = lab.observation_id
    lab.apply(Action.timeout)
    count = len(lab.logs)
    lab._log(previous, "inventory", "Old request failed", status=503)
    assert len(lab.logs) == count
    assert previous != lab.observation_id


def test_missing_database_is_not_silently_created(lab):
    lab.inject("missing_database", seed=73)
    assert not (lab.directory / "missing-73.sqlite").exists()
    assert lab.status()["recent_statuses"] == [500] * 4


def test_observed_evidence_is_not_labeled_with_the_scenario(lab):
    for scenario in SCENARIOS:
        lab.inject(scenario.id)
        toolbox = Toolbox(lab)
        baseline(toolbox)
        data = json.loads(toolbox.serialized_evidence())
        assert all("scenario_id" not in e["data"] and "cause" not in e["data"] for e in data)
