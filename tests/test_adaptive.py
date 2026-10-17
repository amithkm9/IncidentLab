import copy
import json

import httpx
import pytest

from incidentlab import adaptive
from incidentlab.models import Action


class ScriptedPlanner:
    def __init__(self, proposals):
        self.proposals = iter(proposals)
        self.contexts = []
        self.closed = False

    def propose(self, context):
        self.contexts.append(copy.deepcopy(context))
        proposal = next(self.proposals)
        if isinstance(proposal, Exception):
            raise proposal
        return proposal(context) if callable(proposal) else proposal

    def close(self):
        self.closed = True


def choose(actions):
    return lambda context: {"tool": "rehearse_plan", "actions": actions,
                            "hypothesis": "Test the observed fault.",
                            "evidence_ids": [context["latest_trial"]["evidence"][0]["id"]]}


@pytest.mark.parametrize("scenario,expected", [
    ("route_and_release", [Action.route.value, Action.rollback.value]),
    ("database_and_inventory", [Action.database.value, Action.dependency.value]),
    ("timeout_and_release", [Action.timeout.value, Action.rollback.value]),
])
def test_adaptive_uses_new_errors_to_repair_masked_compound_fault(lab, scenario, expected):
    lab.inject(scenario)
    fingerprint, before = lab.fingerprint(), lab.status()
    report = adaptive.run_adaptive_rehearsal(lab)
    assert lab.fingerprint() == fingerprint and lab.status() == before
    assert report["strategy"] == "adaptive"
    assert [trial["actions"] for trial in report["experiments"]] == [expected[:1], expected]
    assert [step["outcome"] for step in report["decision_trace"]] == ["failed", "passed"]
    assert report["recommended_plan_id"] == report["experiments"][-1]["id"]
    assert report["experiments"][-1]["verification"]["statuses"] == [200] * 3
    assert report["budget"]["used_experiments"] == 2
    assert report["provider_usage"]["api_calls"] == 0
    initial_ids = {entry["id"] for entry in report["control"]["evidence"]}
    fresh_ids = {entry["id"] for entry in report["experiments"][0]["evidence"]}
    assert fresh_ids.isdisjoint(initial_ids)
    assert fresh_ids.intersection(report["decision_trace"][1]["evidence_ids"])


@pytest.mark.parametrize("scenario,reason", [("healthy", "control_healthy"), ("telemetry_gap", "missing_telemetry")])
def test_controls_bypass_provider_and_credentials(lab, monkeypatch, scenario, reason):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    lab.inject(scenario)
    planner = ScriptedPlanner([AssertionError("must not call")])
    report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert planner.contexts == [] and planner.closed
    assert report["recommended_plan_id"] is None and report["experiments"] == []
    assert report["budget"]["stop_reason"] == reason
    assert report["provider_usage"]["api_calls"] == 0
    assert adaptive.run_adaptive_rehearsal(lab, strategy="mistral")["recommended_plan_id"] is None


@pytest.mark.parametrize("options", [{"max_experiments": 1}, {"max_actions": 1}])
def test_budgets_stop_before_unverified_compound_promotion(lab, options):
    lab.inject("route_and_release")
    report = adaptive.run_adaptive_rehearsal(lab, **options)
    assert len(report["experiments"]) == 1
    assert report["recommended_plan_id"] is None
    assert report["budget"]["stop_reason"] in {"experiment_budget_exhausted", "planner_abstained"}


def test_false_scenario_label_is_not_an_input_to_policy(lab):
    lab.inject("route_and_release")
    lab.scenario_id = "healthy"
    report = adaptive.run_adaptive_rehearsal(lab)
    assert report["summary"]["minimal_action_count"] == 2
    assert report["recommended_plan_id"] is not None


def test_mistral_planner_gets_sanitized_fresh_evidence_and_no_hidden_state(lab):
    lab.inject("route_and_release")
    planner = ScriptedPlanner([choose([Action.route.value]), choose([Action.route.value, Action.rollback.value])])
    report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert report["recommended_plan_id"] is not None and planner.closed
    context_text = json.dumps(planner.contexts)
    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert not {"scenario_id", "expected_actions", "catalog_path", "inventory_url", "config"}.intersection(keys(planner.contexts))
    for forbidden in ("route_and_release", str(lab.directory), str(lab.database), lab.inventory_url):
        assert forbidden not in context_text
    assert any(entry["data"].get("error_type") == "TypeError" for entry in planner.contexts[1]["latest_trial"]["evidence"])
    assert planner.contexts[1]["tested_actions"] == [[Action.route.value]]


@pytest.mark.parametrize("proposal", [
    {"tool": "run_shell", "actions": [Action.route.value], "hypothesis": "bad", "evidence_ids": []},
    {"tool": "rehearse_plan", "actions": ["delete_database"], "hypothesis": "bad", "evidence_ids": []},
    {"tool": "rehearse_plan", "actions": [Action.route.value], "hypothesis": "bad", "evidence_ids": ["forged"]},
    {"tool": "rehearse_plan", "actions": [Action.route.value, Action.route.value], "hypothesis": "bad", "evidence_ids": []},
])
def test_invalid_decisions_never_execute_or_authorize(lab, proposal):
    lab.inject("wrong_route")
    before = lab.status()
    planner = ScriptedPlanner([proposal])
    report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert report["error"]["code"] == "invalid_plan"
    assert report["decision_trace"][0]["outcome"] == "invalid_plan"
    assert report["experiments"] == [] and report["recommended_plan_id"] is None
    assert lab.status() == before and planner.closed


def test_duplicate_plans_are_not_repeated(lab):
    lab.inject("route_and_release")
    planner = ScriptedPlanner([choose([Action.route.value]), choose([Action.route.value])])
    report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert len(report["experiments"]) == 1
    assert report["budget"]["stop_reason"] == "duplicate_plan"
    assert report["decision_trace"][-1]["outcome"] == "duplicate_plan"
    assert report["recommended_plan_id"] is None


def test_model_error_preserves_measured_failure_and_closes_clones(lab, monkeypatch):
    lab.inject("route_and_release")
    clones = []
    original = adaptive.Lab.from_snapshot

    def tracked(snapshot, directory):
        clone = original(snapshot, directory)
        clones.append(clone)
        return clone

    monkeypatch.setattr(adaptive.Lab, "from_snapshot", tracked)
    planner = ScriptedPlanner([choose([Action.route.value]), RuntimeError("SECRET-PROVIDER-BODY")])
    report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert report["error"]["code"] == "provider_error"
    assert len(report["experiments"]) == 1 and report["budget"]["used_experiments"] == 1
    assert report["recommended_plan_id"] is None and planner.closed
    assert "SECRET-PROVIDER-BODY" not in json.dumps(report)
    assert len(clones) == 2 and all(clone.servers == [] and clone.threads == [] for clone in clones)


def test_failed_experiment_preserves_prior_trials_and_attempt_budget(lab, monkeypatch):
    lab.inject("route_and_release")
    measure = adaptive._measure

    def fail_second(snapshot, directory, identifier, actions, probe_count):
        if identifier == "plan-02":
            raise OSError("SECRET-LOCAL-PATH")
        return measure(snapshot, directory, identifier, actions, probe_count)

    monkeypatch.setattr(adaptive, "_measure", fail_second)
    report = adaptive.run_adaptive_rehearsal(lab)
    assert report["error"]["code"] == "experiment_error"
    assert report["recommended_plan_id"] is None
    assert len(report["experiments"]) == 1
    assert report["budget"]["used_experiments"] == 2
    assert report["budget"]["completed_experiments"] == 1
    assert report["decision_trace"][-1]["outcome"] == "experiment_error"
    assert "SECRET-LOCAL-PATH" not in json.dumps(report)


def test_expired_deadline_never_starts_a_model_selected_experiment(lab, monkeypatch):
    lab.inject("wrong_route")

    def late_proposal(context):
        monkeypatch.setattr(adaptive, "MAX_REHEARSAL_SECONDS", 0)
        return choose([Action.route.value])(context)

    planner = ScriptedPlanner([late_proposal])
    report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert report["budget"]["stop_reason"] == "deadline_exhausted"
    assert report["experiments"] == [] and report["recommended_plan_id"] is None
    assert planner.closed


@pytest.mark.parametrize("options", [{"strategy": "fake"}, {"max_experiments": 0}, {"max_experiments": 9},
                                      {"max_experiments": True}, {"max_actions": 3}, {"probe_count": 21}])
def test_invalid_limits_fail_before_snapshot(options):
    with pytest.raises(ValueError):
        adaptive.run_adaptive_rehearsal(None, **options)


def provider_context(error="upstream_http_error", identifier="observed-1", actions=None):
    entry = {"id": identifier, "source": "checkout", "summary": "Observed failure",
             "data": {"error_type": error, "upstream_status": 404}}
    return {"allowed_actions": list(adaptive.ALLOWED_ACTIONS), "max_actions": 2, "remaining_experiments": 4,
            "remaining_seconds": 100, "latest_trial": {"id": "control", "actions": actions or [], "evidence": [entry],
                "verification": {"statuses": [500], "all_healthy": False}},
            "evidence": [entry], "tested_actions": [], "decisions": []}


def provider_response(arguments, name="rehearse_plan", call_id="call-1", usage=None):
    return {"outputs": [{"type": "function.call", "name": name, "tool_call_id": call_id,
                         "arguments": json.dumps(arguments)}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20} if usage is None else usage}


def test_provider_stateless_conversations_function_loop_and_usage(monkeypatch):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert str(request.url) == "https://api.mistral.ai/v1/conversations"
        assert body["store"] is False and body["completion_args"]["tool_choice"] == "any"
        assert request.extensions["timeout"]["read"] <= 30
        context = json.loads(body["inputs"][-1].get("result") or body["inputs"][-1]["content"])
        return httpx.Response(200, json=provider_response({"actions": [Action.route.value],
            "hypothesis": "Test the route.", "evidence_ids": [context["evidence"][0]["id"]]}, call_id=f"call-{len(requests)}"))

    monkeypatch.setenv("MISTRAL_INPUT_USD_PER_MILLION", "2")
    monkeypatch.setenv("MISTRAL_OUTPUT_USD_PER_MILLION", "4")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        planner = adaptive.MistralConversationPlanner(client=client, api_key="test-key")
        planner.propose(provider_context())
        planner.propose(provider_context("TypeError", "observed-2", [Action.route.value]))
        usage = planner.usage()
    assert len(requests) == 2
    assert requests[1]["inputs"][-2]["type"] == "function.call"
    assert requests[1]["inputs"][-1]["type"] == "function.result"
    assert requests[1]["inputs"][-1]["tool_call_id"] == "call-1"
    assert "TypeError" in requests[1]["inputs"][-1]["result"]
    assert usage["input_tokens"] == 200 and usage["output_tokens"] == 40
    assert usage["api_calls"] == 2 and usage["estimated_cost_usd"] == .00056


@pytest.mark.parametrize("kind", ["http_error", "malformed", "invalid_json", "unknown_tool", "forged_evidence", "unknown_action", "multiple_calls"])
def test_provider_rejects_protocol_failures_without_raw_response_leakage(kind):
    def handler(request):
        if kind == "http_error":
            return httpx.Response(401, text="SECRET-PROVIDER-BODY")
        if kind == "malformed":
            return httpx.Response(200, json={"outputs": "SECRET-PROVIDER-BODY"})
        if kind == "invalid_json":
            return httpx.Response(200, text="SECRET-PROVIDER-BODY")
        arguments = {"actions": ["unknown" if kind == "unknown_action" else Action.route.value],
                     "hypothesis": "Test.", "evidence_ids": ["forged" if kind == "forged_evidence" else "observed-1"]}
        payload = provider_response(arguments, name="run_shell" if kind == "unknown_tool" else "rehearse_plan")
        if kind == "multiple_calls":
            payload["outputs"] *= 2
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        planner = adaptive.MistralConversationPlanner(client=client, api_key="test-key")
        expected_error = adaptive.InvalidDecisionError if kind in {"unknown_tool", "forged_evidence", "unknown_action"} else RuntimeError
        with pytest.raises(expected_error) as error:
            planner.propose(provider_context())
        assert "SECRET-PROVIDER-BODY" not in str(error.value)
        assert planner.usage()["api_calls"] == 1
        if kind in {"http_error", "malformed", "invalid_json"}:
            assert planner.usage()["estimated_cost_usd"] is None
            assert "incomplete" in planner.usage()["cost_note"]


@pytest.mark.parametrize("kind", ["unknown_tool", "forged_evidence", "unknown_action"])
def test_provider_rejected_decision_keeps_invalid_plan_outcome(lab, kind):
    lab.inject("wrong_route")

    def handler(request):
        context = json.loads(json.loads(request.content)["inputs"][-1]["content"])
        arguments = {"actions": ["unknown" if kind == "unknown_action" else Action.route.value],
                     "hypothesis": "Test the observed failure.",
                     "evidence_ids": ["forged" if kind == "forged_evidence" else context["evidence"][0]["id"]]}
        return httpx.Response(200, json=provider_response(arguments,
            name="run_shell" if kind == "unknown_tool" else "rehearse_plan"))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        planner = adaptive.MistralConversationPlanner(client=client, api_key="test-key")
        report = adaptive.run_adaptive_rehearsal(lab, strategy="mistral", planner=planner)
    assert report["error"]["code"] == "invalid_plan"
    assert report["budget"]["stop_reason"] == "invalid_plan"
    assert report["decision_trace"][-1]["outcome"] == "invalid_plan"
    assert report["provider_usage"]["api_calls"] == 1
    assert report["provider_usage"]["input_tokens"] == 100
    assert report["experiments"] == [] and report["recommended_plan_id"] is None


def test_provider_transport_timeout_counts_attempt_and_closes_owned_client(monkeypatch):
    def fail(request):
        raise httpx.ReadTimeout("SECRET-TIMEOUT", request=request)

    client = httpx.Client(transport=httpx.MockTransport(fail))
    monkeypatch.setattr(adaptive.httpx, "Client", lambda **kwargs: client)
    planner = adaptive.MistralConversationPlanner(api_key="test-key")
    with pytest.raises(RuntimeError):
        planner.propose(provider_context())
    planner.close()
    assert client.is_closed
    assert planner.usage()["api_calls"] == 1
    assert planner.usage()["input_tokens"] == 0
    assert planner.usage()["estimated_cost_usd"] is None


def test_provider_credentials_are_required_without_fallback(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="no offline planner"):
        adaptive.MistralConversationPlanner()
