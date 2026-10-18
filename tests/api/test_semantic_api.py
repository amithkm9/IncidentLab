"""A transport-successful partial repair must never authorize promotion."""

from dataclasses import replace

import pytest

from incidentlab.domain.models import Action, Cause, Evidence, Finding
from incidentlab.investigation.agents import validate_finding
from incidentlab.recovery.adaptive import run_adaptive_rehearsal


def test_http_200_partial_repair_is_rejected_and_complete_plan_is_auditable(client):
    client.post("/api/inject", json={"scenario_id": "route_and_price_drift"})
    finding = client.post("/api/investigate", json={"mode": "baseline"}).json()
    before = client.get("/api/status").json()
    partial = client.post(
        "/api/rehearse", json={"strategy": "adaptive", "max_experiments": 1}
    ).json()
    plan = partial["report"]["experiments"][0]
    assert plan["verification"]["statuses"] == [200] * 3
    assert plan["verification"]["all_http_healthy"] is True
    assert plan["verification"]["semantic_passed"] is False
    assert partial["report"]["recommended_plan_id"] is None
    assert (
        client.post(
            "/api/promote", json={"rehearsal_id": partial["id"], "plan_id": plan["id"]}
        ).status_code
        == 409
    )
    assert client.get("/api/status").json() == before

    full = client.post("/api/rehearse", json={"strategy": "adaptive", "max_experiments": 4}).json()
    steps = full["report"]["decision_trace"]
    assert [step["statuses"] for step in steps] == [[200] * 3, [200] * 3]
    assert [step["semantic_passed"] for step in steps] == [False, True]
    result = client.post(
        "/api/promote",
        json={"rehearsal_id": full["id"], "plan_id": full["report"]["recommended_plan_id"]},
    )
    assert result.status_code == 200
    verification = result.json()["verification"]
    assert verification["all_healthy"] and verification["semantic_passed"]
    assert len(verification["semantic_checks"]) == 5
    assert {check["sku"] for check in verification["semantic_checks"]} == {
        "notebook",
        "lamp",
        "mug",
    }
    assert all(
        check["expected_total_cents"] == check["observed_total_cents"]
        for check in verification["semantic_checks"]
    )
    document = client.get(f"/api/postmortems/{finding['id']}").text
    assert "Business contract" in document and "price\\_mismatch" in document
    assert verification["contract"]["sha256"] in document
    assert "business contract passed" in document


@pytest.mark.parametrize("strategy", ["adaptive", "exhaustive"])
def test_silent_price_failure_is_never_a_healthy_control(client, strategy):
    status = client.post("/api/inject", json={"scenario_id": "silent_price_drift"}).json()
    assert status["http_errors"] == 0 and status["semantic_failures"] == 4
    diagnosis = client.post("/api/investigate", json={"mode": "baseline"}).json()
    assert diagnosis["result"]["finding"]["action"] == Action.rollback.value
    record = client.post("/api/rehearse", json={"strategy": strategy}).json()
    report = record["report"]
    assert not report["summary"]["control_healthy"]
    assert report["control"]["verification"]["all_http_healthy"]
    assert report["recommended_plan_id"] is not None


def test_changing_business_contract_invalidates_rehearsed_plan(client):
    client.post("/api/inject", json={"scenario_id": "silent_price_drift"})
    record = client.post("/api/rehearse", json={"strategy": "adaptive"}).json()
    lab = client.app.state.service.lab
    lab.contract = replace(lab.contract, version="2.0.0")
    response = client.post(
        "/api/promote",
        json={"rehearsal_id": record["id"], "plan_id": record["report"]["recommended_plan_id"]},
    )
    assert response.status_code == 409


def test_planner_receives_cited_business_failure_instead_of_false_success(lab):
    lab.inject("route_and_price_drift")
    contexts = []

    class Planner:
        def propose(self, context):
            contexts.append(context)
            evidence = context["latest_trial"]["evidence"]
            if len(contexts) == 1:
                entry = next(
                    item for item in evidence if item["data"].get("upstream_status") == 404
                )
                actions = [Action.route.value]
            else:
                entry = next(
                    item for item in evidence if item["data"].get("error_type") == "price_mismatch"
                )
                assert (
                    entry["data"]["expected_total_cents"] != entry["data"]["observed_total_cents"]
                )
                assert context["latest_trial"]["verification"]["all_http_healthy"]
                assert not context["latest_trial"]["verification"]["semantic_passed"]
                assert Action.rollback.value in context["action_catalog"]
                actions = [Action.route.value, Action.rollback.value]
            return {
                "tool": "rehearse_plan",
                "actions": actions,
                "hypothesis": "Test a revised plan against the business contract.",
                "evidence_ids": [entry["id"]],
            }

    report = run_adaptive_rehearsal(lab, strategy="mistral", planner=Planner())
    assert report["recommended_plan_id"] is not None and len(contexts) == 2
    assert lab.status()["errors"] == 4


def test_model_cannot_label_known_business_failure_healthy():
    observation = Evidence(
        id="metrics-current",
        source="metrics",
        summary="HTTP is healthy; totals are wrong",
        data={"requests": 3, "http_errors": 0, "errors": 3, "semantic_failures": 3},
    )
    finding = Finding(
        cause=Cause.healthy,
        action=Action.none,
        title="Everything passed",
        explanation="HTTP 200 proves recovery.",
        evidence_ids=[observation.id],
        verification="No action.",
        limitations="Local lab.",
    )
    with pytest.raises(ValueError, match="contradicts observed"):
        validate_finding(finding, {observation.id: observation})
