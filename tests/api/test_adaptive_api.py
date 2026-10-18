"""Adaptive plans must pass the same persistence and promotion boundary."""

import pytest


def test_adaptive_compound_flow_is_persisted_and_guarded(client):
    client.post("/api/inject", json={"scenario_id": "route_and_release", "seed": 42})
    finding = client.post("/api/investigate", json={"mode": "baseline"}).json()
    before = client.get("/api/status").json()
    response = client.post(
        "/api/rehearse", json={"strategy": "adaptive", "max_experiments": 4, "probe_count": 1}
    )
    assert response.status_code == 200, response.text
    record = response.json()
    report = record["report"]
    assert report["strategy"] == "adaptive"
    assert report["summary"]["tested_plans"] == 2
    assert report["provider_usage"]["api_calls"] == 0
    assert report["decision_trace"]
    assert client.get("/api/status").json() == before
    assert client.get(f"/api/rehearsals/{record['id']}").json() == record
    assert client.get("/api/history").json()["rehearsals"][0]["strategy"] == "adaptive"
    result = client.post(
        "/api/promote",
        json={"rehearsal_id": record["id"], "plan_id": report["recommended_plan_id"]},
    )
    assert result.status_code == 200
    assert result.json()["verification"]["statuses"] == [200] * 5
    assert (
        client.post(
            "/api/promote",
            json={"rehearsal_id": record["id"], "plan_id": report["recommended_plan_id"]},
        ).status_code
        == 409
    )
    postmortem = client.get(f"/api/postmortems/{finding['id']}").text
    assert "Strategy: adaptive" in postmortem
    assert "Experiment decisions" in postmortem
    assert "Offline policy; no model calls" in postmortem


def test_adaptive_budget_exhaustion_never_authorizes_a_partial_fix(client):
    client.post("/api/inject", json={"scenario_id": "route_and_release"})
    response = client.post(
        "/api/rehearse", json={"strategy": "adaptive", "max_experiments": 1, "probe_count": 1}
    )
    assert response.status_code == 200
    record = response.json()
    assert record["report"]["summary"]["tested_plans"] == 1
    assert record["report"]["recommended_plan_id"] is None
    plan = record["report"]["experiments"][0]
    assert not plan["verification"]["all_healthy"]
    assert (
        client.post(
            "/api/promote", json={"rehearsal_id": record["id"], "plan_id": plan["id"]}
        ).status_code
        == 409
    )


def test_mistral_planner_requires_key_without_offline_substitution(client):
    response = client.post("/api/rehearse", json={"strategy": "mistral"})
    assert response.status_code == 503
    assert "MISTRAL_API_KEY" in response.json()["detail"]
    assert client.get("/api/workspace").json()["latest_rehearsal"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"strategy": "unknown"},
        {"max_experiments": 0},
        {"max_experiments": 9},
        {"strategy": "adaptive", "allow_shell": True},
    ],
)
def test_adaptive_invalid_requests_are_rejected(client, body):
    assert client.post("/api/rehearse", json=body).status_code == 422
    assert client.get("/api/workspace").json()["latest_rehearsal"] is None


def test_adaptive_plan_rejects_new_episode(client):
    client.post("/api/inject", json={"scenario_id": "wrong_route"})
    record = client.post("/api/rehearse", json={"strategy": "adaptive", "probe_count": 1}).json()
    client.post("/api/inject", json={"scenario_id": "wrong_route"})
    assert (
        client.post(
            "/api/promote",
            json={"rehearsal_id": record["id"], "plan_id": record["report"]["recommended_plan_id"]},
        ).status_code
        == 409
    )
