import json

import pytest

from incidentlab import service


def find(client, scenario="wrong_route"):
    assert client.post("/api/inject", json={"scenario_id": scenario}).status_code == 200
    response = client.post("/api/investigate", json={"mode": "baseline"})
    assert response.status_code == 200
    return response.json()


def test_complete_workflow_and_export(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}
    assert len(client.get("/api/scenarios").json()) == 7
    record = find(client)
    assert record["result"]["finding"]["cause"] == "configuration_error"
    response = client.post("/api/remediate", json={"investigation_id": record["id"], "action": "restore_inventory_route"})
    assert response.status_code == 200
    assert response.json()["verification"]["statuses"] == [200] * 5
    artifact = client.get(f"/api/investigations/{record['id']}")
    assert "attachment;" in artifact.headers["content-disposition"]
    assert artifact.json()["remediation"]["verification"]["all_healthy"]
    healthy = client.post("/api/investigate", json={}).json()
    assert healthy["result"]["finding"]["cause"] == "healthy"
    assert client.post("/api/remediate", json={"investigation_id": record["id"], "action": "restore_inventory_route"}).status_code == 409


def test_stale_finding_cannot_modify_new_episode(client):
    record = find(client)
    client.post("/api/inject", json={"scenario_id": "bad_release"})
    response = client.post("/api/remediate", json={"investigation_id": record["id"], "action": "restore_inventory_route"})
    assert response.status_code == 409
    assert client.get("/api/status").json()["errors"] == 4


def test_action_must_match_current_finding_and_only_run_once(client):
    record = find(client)
    assert client.post("/api/remediate", json={"investigation_id": record["id"], "action": "rollback_checkout_release"}).status_code == 409
    request = {"investigation_id": record["id"], "action": "restore_inventory_route"}
    assert client.post("/api/remediate", json=request).status_code == 200
    assert client.post("/api/remediate", json=request).status_code == 409


@pytest.mark.parametrize("scenario", ["healthy", "telemetry_gap"])
def test_controls_have_no_executable_action(client, scenario):
    record = find(client, scenario)
    assert client.post("/api/remediate", json={"investigation_id": record["id"], "action": "no_action"}).status_code == 409


def test_concurrent_mutation_is_rejected(client):
    with client.app.state.service.operation():
        assert client.get("/api/status").json()["busy"]
        assert client.post("/api/inject", json={"scenario_id": "healthy"}).status_code == 409
        assert client.post("/api/investigate", json={}).status_code == 409
        assert client.post("/api/probe", json={}).status_code == 409


def test_invalid_requests_and_cross_origin_mutations(client):
    for body in ({"scenario_id": "bogus"}, {"scenario_id": "healthy", "seed": -1}, {"scenario_id": "healthy", "extra": 1}):
        assert client.post("/api/inject", json=body).status_code == 422
    assert client.post("/api/probe", json={"count": 0}).status_code == 422
    assert client.post("/api/probe", json={"count": 21}).status_code == 422
    assert client.post("/api/investigate", json={"mode": "bogus"}).status_code == 422
    assert client.post("/api/inject", json={"scenario_id": "healthy"}, headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert client.get("/api/investigations/not-an-artifact").status_code == 404
    assert client.get("/api/investigations/" + "a" * 32).status_code == 404


def test_missing_key_is_explicit_and_no_fallback_occurs(client):
    assert not client.get("/api/config").json()["mistral_configured"]
    response = client.post("/api/investigate", json={"mode": "mistral"})
    assert response.status_code == 503
    assert client.app.state.service.latest is None


def test_api_returns_clean_errors_for_failed_model(client, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    def fail(*args):
        raise RuntimeError("Mistral API returned HTTP 429; check model access, credentials, and quota.")
    monkeypatch.setattr(service, "investigate", fail)
    response = client.post("/api/investigate", json={"mode": "mistral"})
    assert response.status_code == 502
    assert "429" in response.json()["detail"]
    assert "test-key" not in json.dumps(response.json())
    assert client.app.state.service.latest is None
