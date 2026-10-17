from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from incidentlab.api import create_app
from incidentlab.models import Action


def inject(client, scenario="route_and_release"):
    assert client.post("/api/inject", json={"scenario_id": scenario, "seed": 42}).status_code == 200


def rehearse(client, max_actions=2):
    response = client.post("/api/rehearse", json={"max_actions": max_actions, "probe_count": 1})
    assert response.status_code == 200, response.text
    return response.json()


def promote(client, record, plan_id=None):
    return client.post("/api/promote", json={"rehearsal_id": record["id"],
        "plan_id": plan_id or record["report"]["recommended_plan_id"] or "none"})


def test_compound_rehearsal_promotion_history_and_postmortem(client):
    inject(client)
    finding = client.post("/api/investigate", json={}).json()
    before = client.get("/api/status").json()
    record = rehearse(client)
    after = client.get("/api/status").json()
    assert after == before  # Clones did not send traffic to, or mutate, the source.
    assert record["report"]["summary"]["minimal_action_count"] == 2
    assert promote(client, record, "control").status_code == 409
    result = promote(client, record)
    assert result.status_code == 200
    assert result.json()["verification"]["statuses"] == [200] * 5
    assert set(result.json()["actions"]) == {Action.route.value, Action.rollback.value}
    assert promote(client, record).status_code == 409
    workspace = client.get("/api/workspace").json()
    assert workspace["summary"] == {"investigations": 1, "rehearsals": 1, "verified_recoveries": 1}
    assert workspace["latest_investigation"]["remediation"]["method"] == "rehearsed_plan"
    assert workspace["latest_rehearsal"]["promotion"]["verification"]["all_healthy"]
    assert workspace["events"][-1]["type"] == "recovery_verified"
    assert client.get("/api/history").json()["investigations"][0]["verified"]
    assert client.get(f"/api/rehearsals/{record['id']}").json()["promotion"] is not None
    report = client.get(f"/api/postmortems/{finding['id']}")
    assert report.status_code == 200
    assert "attachment" in report.headers["content-disposition"]
    assert "Isolated fix rehearsal" in report.text
    assert "Recovery verified" in report.text
    assert "not production evidence" in report.text


def test_rehearsal_rejects_changed_episode_and_out_of_band_drift(client):
    inject(client, "wrong_route")
    record = rehearse(client, 1)
    client.app.state.service.lab.config["release"] = "checkout-1.1"
    assert promote(client, record).status_code == 409
    assert client.get("/api/status").json()["revision"] == record["revision"]
    inject(client, "wrong_route")
    assert promote(client, record).status_code == 409


def test_single_fix_invalidates_old_rehearsal(client):
    inject(client, "wrong_route")
    finding = client.post("/api/investigate", json={}).json()
    record = rehearse(client, 1)
    assert client.post("/api/remediate", json={"investigation_id": finding["id"],
        "action": finding["result"]["finding"]["action"]}).status_code == 200
    assert promote(client, record).status_code == 409


@pytest.mark.parametrize("scenario", ["healthy", "telemetry_gap"])
def test_controls_never_authorize_promotion(client, scenario):
    inject(client, scenario)
    record = rehearse(client, 1)
    assert record["report"]["recommended_plan_id"] is None
    assert promote(client, record).status_code == 409
    assert client.get("/api/workspace").json()["summary"]["verified_recoveries"] == 0


def test_rehearsal_contract_and_busy_gate(client):
    for body in ({"max_actions": 3}, {"probe_count": 0}, {"max_actions": 0}, {"extra": True}):
        assert client.post("/api/rehearse", json=body).status_code == 422
    assert client.post("/api/promote", json={"rehearsal_id": "../bad", "plan_id": "plan-01"}).status_code == 422
    assert client.get("/api/history?limit=101").status_code == 422
    assert client.get("/api/rehearsals/" + "f" * 32).status_code == 404
    assert client.get("/api/postmortems/" + "f" * 32).status_code == 404
    with client.app.state.service.operation():
        assert client.post("/api/rehearse", json={}).status_code == 409
        assert client.post("/api/promote", json={"rehearsal_id": "a" * 32, "plan_id": "plan-01"}).status_code == 409


def test_restart_preserves_history_but_not_remediation_authority(tmp_path: Path):
    directory = tmp_path / "restart"
    with TestClient(create_app(directory)) as client:
        inject(client, "wrong_route")
        finding = client.post("/api/investigate", json={}).json()
        record = rehearse(client, 1)
    with TestClient(create_app(directory)) as client:
        workspace = client.get("/api/workspace").json()
        assert workspace["status"]["episode_id"] != record["episode_id"]
        assert workspace["latest_investigation"] is None
        assert workspace["latest_rehearsal"] is None
        assert workspace["history"][0]["id"] == finding["id"]
        assert client.get(f"/api/rehearsals/{record['id']}").status_code == 200
        assert promote(client, record).status_code == 409


def test_failed_single_fix_then_rehearsal_preserves_attempt_and_reports_final_recovery(client):
    inject(client)
    finding = client.post("/api/investigate", json={}).json()
    attempted = client.post("/api/remediate", json={"investigation_id": finding["id"],
        "action": finding["result"]["finding"]["action"]})
    assert attempted.status_code == 200
    assert not attempted.json()["verification"]["all_healthy"]
    record = rehearse(client, 1)
    assert record["report"]["summary"]["minimal_action_count"] == 1
    assert promote(client, record).json()["verification"]["all_healthy"]
    updated = client.get(f"/api/investigations/{finding['id']}").json()
    assert not updated["remediation"]["verification"]["all_healthy"]
    assert updated["episode_recovery"]["verification"]["all_healthy"]
    assert updated["rehearsal_id"] == record["id"]
    history = client.get("/api/history").json()["investigations"][0]
    assert history["verified"] and not history["investigation_verified"]
    report = client.get(f"/api/postmortems/{finding['id']}").text
    assert "This attempt did not restore checkout" in report
    assert "## Latest episode outcome\n\nRecovery verified." in report
    assert "Isolated fix rehearsal" in report
