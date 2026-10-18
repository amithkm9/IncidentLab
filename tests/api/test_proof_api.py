from dataclasses import replace

from fastapi.testclient import TestClient

from incidentlab import application as service
from incidentlab.api import create_app
from incidentlab.recovery import proof


def rehearse(client, scenario="route_and_price_drift"):
    assert client.post("/api/inject", json={"scenario_id": scenario}).status_code == 200
    response = client.post("/api/rehearse", json={"strategy": "adaptive"})
    assert response.status_code == 200
    return response.json()


def promote(client, record):
    return client.post(
        "/api/promote",
        json={"rehearsal_id": record["id"], "plan_id": record["report"]["recommended_plan_id"]},
    )


def test_proof_is_exportable_bound_to_current_state_and_invalid_after_promotion(client):
    record = rehearse(client)
    before = client.get("/api/status").json()
    response = client.post(f"/api/rehearsals/{record['id']}/proof")
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["authority"] == {"is_current": True, "reason": "current_snapshot"}
    artifact = envelope["proof"]
    assert artifact["source_unchanged"] is True and proof.verify_proof_integrity(artifact)
    assert artifact["summary"]["all_actions_necessary"] is True
    assert client.get("/api/status").json() == before
    workspace = client.get("/api/workspace").json()
    assert workspace["latest_rehearsal"]["proof"]["id"] == artifact["id"]
    assert any(event["type"] == "proof_completed" for event in workspace["events"])
    exported = client.get(f"/api/rehearsals/{record['id']}/proof")
    assert "attachment" in exported.headers["content-disposition"]
    assert exported.json()["proof"] == artifact
    assert promote(client, record).status_code == 200
    historical = client.get(f"/api/rehearsals/{record['id']}/proof").json()
    assert historical["proof"] == artifact
    assert historical["authority"] == {"is_current": False, "reason": "already_promoted"}
    assert client.post(f"/api/rehearsals/{record['id']}/proof").status_code == 409


def test_failed_full_plan_proof_blocks_previously_successful_recommendation_and_retains_history(
    client, monkeypatch
):
    record = rehearse(client)
    original = proof._measure

    def fail_full(snapshot, directory, actions):
        value = original(snapshot, directory, actions)
        if directory.name == "full-plan":
            value["all_healthy"] = value["semantic_passed"] = False
            for check in value["semantic_checks"]:
                check["observed_total_cents"] += 100
                check["passed"], check["violations"] = False, ["price_mismatch"]
        return value

    monkeypatch.setattr(proof, "_measure", fail_full)
    failed = client.post(f"/api/rehearsals/{record['id']}/proof").json()["proof"]
    assert failed["summary"]["conclusion"] == "full_plan_failed"
    assert failed["summary"]["promotion_eligible"] is False
    assert promote(client, record).status_code == 409
    assert client.get("/api/status").json()["errors"] == 4
    monkeypatch.setattr(proof, "_measure", original)
    passed = client.post(f"/api/rehearsals/{record['id']}/proof").json()["proof"]
    assert passed["summary"]["promotion_eligible"]
    stored = client.get(f"/api/rehearsals/{record['id']}").json()
    assert stored["proof_history"][0]["id"] == failed["id"]
    assert stored["proof"]["id"] == passed["id"]


def test_unexpected_proof_failure_is_audited_and_cannot_reuse_prior_proof(client, monkeypatch):
    record = rehearse(client, "silent_price_drift")
    assert client.post(f"/api/rehearsals/{record['id']}/proof").status_code == 200

    def fail(*args, **kwargs):
        raise OSError("SECRET-PATH")

    monkeypatch.setattr(service, "run_recovery_proof", fail)
    response = client.post(f"/api/rehearsals/{record['id']}/proof")
    assert response.status_code == 502 and "SECRET" not in response.text
    assert promote(client, record).status_code == 409
    stored = client.get(f"/api/rehearsals/{record['id']}").json()
    assert stored["proof_failure"]["code"] == "proof_failed"
    assert (
        client.get(f"/api/rehearsals/{record['id']}/proof").json()["authority"]["reason"]
        == "latest_proof_failed"
    )


def test_changed_contract_or_stale_rehearsal_cannot_use_proof_as_authority(client):
    record = rehearse(client, "silent_price_drift")
    assert client.post(f"/api/rehearsals/{record['id']}/proof").status_code == 200
    lab = client.app.state.service.lab
    lab.contract = replace(lab.contract, version="2.0.0")
    assert (
        client.get(f"/api/rehearsals/{record['id']}/proof").json()["authority"]["reason"]
        == "contract_changed"
    )
    assert promote(client, record).status_code == 409
    assert client.post(f"/api/rehearsals/{record['id']}/proof").status_code == 409
    lab.contract = replace(lab.contract, version="1.0.0")
    newer = client.post("/api/rehearse", json={"strategy": "adaptive"}).json()
    assert newer["id"] != record["id"]
    assert (
        client.get(f"/api/rehearsals/{record['id']}/proof").json()["authority"]["reason"]
        == "stale_rehearsal"
    )
    assert client.post(f"/api/rehearsals/{record['id']}/proof").status_code == 409


def test_tampered_proof_digest_blocks_promotion(client):
    record = rehearse(client, "silent_price_drift")
    client.post(f"/api/rehearsals/{record['id']}/proof")
    current = client.app.state.service.latest_rehearsal
    current["proof"]["summary"]["conclusion"] = "tampered"
    assert promote(client, record).status_code == 409
    assert client.get("/api/status").json()["semantic_failures"] == 4


def test_proof_survives_restart_as_historical_evidence_without_authority(tmp_path):
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        record = rehearse(client, "silent_price_drift")
        original = client.post(f"/api/rehearsals/{record['id']}/proof").json()["proof"]
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.get(f"/api/rehearsals/{record['id']}/proof")
        assert response.status_code == 200
        assert response.json()["proof"] == original
        assert response.json()["authority"]["is_current"] is False
        assert promote(client, record).status_code == 409


def test_proof_route_rejects_cross_origin_writes_and_missing_exports(client):
    record = rehearse(client, "silent_price_drift")
    assert client.get(f"/api/rehearsals/{record['id']}/proof").status_code == 404
    assert (
        client.post(
            f"/api/rehearsals/{record['id']}/proof", headers={"sec-fetch-site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.get("/api/rehearsals/not-an-id/proof").status_code == 404
