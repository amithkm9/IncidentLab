import json
import sqlite3
import urllib.error
import urllib.request

import pytest

from incidentlab.investigator import baseline
from incidentlab.lab import Lab, SCENARIOS
from incidentlab.models import Action, Cause
from incidentlab.tools import Toolbox


@pytest.mark.parametrize("scenario", [scenario for scenario in SCENARIOS if scenario.fault_count < 2], ids=lambda scenario: scenario.id)
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


@pytest.mark.parametrize("scenario", [scenario for scenario in SCENARIOS if scenario.fault_count == 2], ids=lambda scenario: scenario.id)
def test_compound_failure_masks_a_second_fault(lab, scenario):
    lab.inject(scenario.id)
    finding = baseline(Toolbox(lab)).finding
    assert finding.cause == scenario.cause
    assert finding.action == scenario.action
    assert not lab.apply(finding.action)["verification"]["all_healthy"]
    remaining = next(action for action in scenario.expected_actions if action != finding.action)
    assert baseline(Toolbox(lab)).finding.action == remaining
    assert lab.apply(remaining)["verification"]["all_healthy"]


def test_atomic_plan_uses_one_fresh_observation_window(lab):
    lab.inject("route_and_release")
    previous_window = lab.window
    result = lab.apply_plan([Action.route, Action.rollback], probe_count=3)
    assert result["actions"] == [Action.route.value, Action.rollback.value]
    assert result["verification"]["statuses"] == [200, 200, 200]
    assert lab.window == previous_window + 1
    assert lab.status()["requests"] == 3


@pytest.mark.parametrize("actions", [[], [Action.none], [Action.route, Action.route],
    [Action.route, Action.database, Action.rollback], [Action.route, "arbitrary_shell_command"]])
def test_invalid_plan_does_not_partially_change_state(lab, actions):
    lab.inject("route_and_release")
    fingerprint = lab.fingerprint()
    before = lab.status()
    with pytest.raises(ValueError):
        lab.apply_plan(actions)
    assert lab.fingerprint() == fingerprint
    assert lab.status() == before


def test_clone_copies_database_and_uses_independent_endpoints(lab, tmp_path):
    lab.inject("healthy")
    with sqlite3.connect(lab.database) as database:
        database.execute("UPDATE products SET price = 71 WHERE sku = 'notebook'")
    clone = lab.clone(tmp_path / "clone")
    try:
        assert clone.inventory_url != lab.inventory_url
        assert clone.checkout_url != lab.checkout_url
        assert clone.database != lab.database
        assert clone.config["inventory_url"].startswith(clone.inventory_url)
        assert clone.config["catalog_path"] == str(clone.database)
        with urllib.request.urlopen(clone.checkout_url + "/checkout?sku=notebook") as response:
            assert json.load(response)["total"] == 71
        with sqlite3.connect(clone.database) as database:
            database.execute("UPDATE products SET price = 9 WHERE sku = 'notebook'")
        with sqlite3.connect(lab.database) as database:
            assert database.execute("SELECT price FROM products WHERE sku = 'notebook'").fetchone()[0] == 71
        assert lab.status()["requests"] == 4
    finally:
        clone.close()


def test_snapshot_preserves_a_partial_repair_instead_of_reinjecting(lab, tmp_path):
    lab.inject("route_and_release")
    lab.apply(Action.route)
    snapshot = lab.snapshot()
    clone = Lab.from_snapshot(snapshot, tmp_path / "clone")
    try:
        assert clone.scenario_id == "snapshot"
        assert clone.config["inventory_url"] == clone.inventory_url + "/v1/stock"
        assert clone.config["release"] == "checkout-1.1"
        assert clone.probe(1)["statuses"] == [500]
        assert clone.apply(Action.rollback)["verification"]["all_healthy"]
        assert lab.config["release"] == "checkout-1.1"
    finally:
        clone.close()


def test_missing_catalog_stays_missing_in_the_clone(lab, tmp_path):
    lab.inject("missing_database")
    clone = lab.clone(tmp_path / "clone")
    try:
        assert not clone.probe(1)["all_healthy"]
        assert clone.config["catalog_path"] != lab.config["catalog_path"]
        assert clone.apply(Action.database)["verification"]["all_healthy"]
        assert lab.probe(1)["statuses"] == [500]
    finally:
        clone.close()


def test_clone_refuses_to_overwrite_existing_directory(lab):
    fingerprint = lab.fingerprint()
    with pytest.raises(ValueError, match="empty directory"):
        lab.clone(lab.directory)
    assert lab.fingerprint() == fingerprint


def test_fingerprint_tracks_state_but_not_observations(lab):
    original = lab.fingerprint()
    lab.probe(2)
    assert lab.fingerprint() == original
    with sqlite3.connect(lab.database) as database:
        database.execute("UPDATE products SET price = 13 WHERE sku = 'notebook'")
    changed = lab.fingerprint()
    assert changed != original
    lab.inventory_ready = False
    assert lab.fingerprint() != changed
