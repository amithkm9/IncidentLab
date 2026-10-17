import json

import httpx
import pytest

from incidentlab.investigator import MistralInvestigator, validate_finding
from incidentlab.models import Action, Cause, Evidence, Finding
from incidentlab.tools import RunbookIndex, Toolbox


def finding(**changes):
    values = dict(cause=Cause.healthy, title="Observed requests succeeded", explanation="The available checkout logs show HTTP 200 responses.",
        evidence_ids=["test-log"], action=Action.none, verification="Collect additional representative traffic.",
        limitations="A small lab observation window does not establish production health.")
    return Finding(**{**values, **changes})


def test_finding_rejects_invented_citations_and_incompatible_actions():
    evidence = {"test-log": Evidence(id="test-log", source="checkout", summary="Completed", data={"status": 200})}
    assert validate_finding(finding(), evidence)
    with pytest.raises(ValueError, match="not observed"):
        validate_finding(finding(evidence_ids=["invented"]), evidence)
    with pytest.raises(ValueError, match="inconsistent"):
        validate_finding(finding(action=Action.rollback), evidence)
    with pytest.raises(ValueError, match="observed incident evidence"):
        validate_finding(finding(evidence_ids=[]), evidence)


def test_runbook_is_guidance_not_incident_evidence():
    evidence = {"test-log": Evidence(id="test-log", source="runbook", summary="Healthy recipe")}
    with pytest.raises(ValueError, match="observed incident evidence"):
        validate_finding(finding(), evidence)


def test_retrieval_returns_relevant_runbook_and_handles_no_match():
    index = RunbookIndex()
    assert index.search("catalog SQLite database unable open path")[0].id == "runbook-catalog-path"
    assert index.search("zzznomatchxxx") == []


@pytest.fixture
def model_key(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key-not-live")
    monkeypatch.delenv("MISTRAL_INPUT_USD_PER_MILLION", raising=False)
    monkeypatch.delenv("MISTRAL_OUTPUT_USD_PER_MILLION", raising=False)


def test_mocked_mistral_tool_round_trip(lab, model_key):
    lab.inject("healthy")
    toolbox = Toolbox(lab)
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert "scenario_id" not in request.content.decode()
        assert request.headers["authorization"] == "Bearer test-key-not-live"
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call00001", "type": "function", "function": {"name": "get_service_health", "arguments": "{}"}}]}
        else:
            assert body["messages"][-1]["role"] == "tool"
            assert body["messages"][-1]["tool_call_id"] == "call00001"
            citation = next(e.id for e in toolbox.evidence.values() if e.source == "metrics")
            message = {"role": "assistant", "content": finding(evidence_ids=[citation]).model_dump_json()}
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": {"prompt_tokens": 120, "completion_tokens": 30}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = MistralInvestigator(client).investigate(toolbox, "mistral", "Investigate checkout health.")
    assert result.mode == "mistral"
    assert result.input_tokens == 240 and result.output_tokens == 60
    assert [trace.tool for trace in result.traces] == ["query_logs", "get_metrics", "get_service_health"]
    assert result.estimated_cost_usd is None
    assert "tools" in requests[0]


@pytest.mark.parametrize("mode,runbook", [("prompt", False), ("retrieval", True)])
def test_ablation_modes_do_not_offer_model_tools(lab, model_key, mode, runbook):
    lab.inject("healthy")
    toolbox = Toolbox(lab)
    def handle(request):
        body = json.loads(request.content)
        assert "tools" not in body
        citation = next(e.id for e in toolbox.evidence.values() if e.source == "metrics")
        return httpx.Response(200, json={"choices": [{"message": {"content": finding(evidence_ids=[citation]).model_dump_json()}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = MistralInvestigator(client).investigate(toolbox, mode, "Investigate checkout health.")
    assert ("search_runbooks" in [t.tool for t in result.traces]) == runbook


@pytest.mark.parametrize("kind", ["http_error", "invalid_json", "bad_message"])
def test_model_failures_never_become_baseline_results(model_key, kind):
    def handle(request):
        if kind == "http_error":
            return httpx.Response(429, text="provider error")
        if kind == "invalid_json":
            return httpx.Response(200, text="not json")
        return httpx.Response(200, json={"choices": [{"message": None}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(RuntimeError, match="Mistral"):
            MistralInvestigator(client)._complete([], None)


def test_model_cannot_exceed_call_budget(lab, model_key):
    lab.inject("healthy")
    toolbox = Toolbox(lab)
    def handle(request):
        message = {"tool_calls": [{"id": f"call{i:05}", "function": {"name": "get_metrics", "arguments": "{}"}} for i in range(17)]}
        return httpx.Response(200, json={"choices": [{"message": message}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(RuntimeError, match="16-call"):
            MistralInvestigator(client).investigate(toolbox, "mistral", "Investigate")
    assert len(toolbox.traces) == 2


def test_unknown_tool_is_reported_without_mutation(lab, model_key):
    lab.inject("healthy")
    toolbox = Toolbox(lab)
    calls = 0
    def handle(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            message = {"tool_calls": [{"id": "call00001", "function": {"name": "apply", "arguments": "{}"}}]}
        else:
            payload = json.loads(request.content)
            assert "only the declared read-only tools" in payload["messages"][-1]["content"]
            message = {"content": finding(cause=Cause.unknown, evidence_ids=[]).model_dump_json()}
        return httpx.Response(200, json={"choices": [{"message": message}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = MistralInvestigator(client).investigate(toolbox, "mistral", "Investigate")
    assert result.finding.action == Action.none
    assert lab.window == 1


def test_cost_requires_finite_operator_prices(model_key, monkeypatch):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        model = MistralInvestigator(client)
        model.input_tokens, model.output_tokens = 1000, 500
        monkeypatch.setenv("MISTRAL_INPUT_USD_PER_MILLION", "1")
        monkeypatch.setenv("MISTRAL_OUTPUT_USD_PER_MILLION", "2")
        assert model._cost()[0] == .002
        monkeypatch.setenv("MISTRAL_INPUT_USD_PER_MILLION", "NaN")
        assert model._cost()[0] is None
