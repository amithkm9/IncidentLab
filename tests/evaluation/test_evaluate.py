import json

import pytest

from incidentlab.evaluation.baseline import MANIFEST, evaluate, summarize


def test_frozen_suite_has_disjoint_seed_splits():
    manifest = json.loads(MANIFEST.read_text())
    assert set(manifest["splits"]["dev"]).isdisjoint(manifest["splits"]["test"])
    assert len(manifest["scenarios"]) * len(manifest["splits"]["test"]) == 105


def test_smoke_evaluation_records_real_recoveries_and_provenance():
    report = evaluate()
    assert report["mode"] == "baseline"
    assert "NOT Mistral" in report["provenance"]
    assert report["summary"]["episodes"] == 7
    assert report["summary"]["errors"] == 0
    assert report["summary"]["diagnosis_accuracy"] == 1
    assert report["summary"]["remediation_success_rate"] == 1
    assert report["summary"]["appropriate_abstention_rate"] == 1
    assert report["summary"]["input_tokens"] == 0
    assert len(report["manifest_sha256"]) == 64
    assert all(e["result"]["traces"] for e in report["episodes"])


def test_model_eval_without_credentials_fails_before_starting_lab(monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ValueError, match="No baseline will be substituted"):
        evaluate("mistral")


def test_failed_episodes_remain_in_accuracy_denominator():
    failed = {
        "expected_cause": "configuration_error",
        "expected_action": "restore_inventory_route",
        "diagnosis_correct": False,
        "action_correct": False,
        "recovered": False,
        "result": None,
        "error": "API failure",
    }
    summary = summarize([failed])
    assert summary["episodes"] == 1 and summary["errors"] == 1
    assert summary["diagnosis_accuracy"] == 0
    assert summary["remediation_success_rate"] == 0
    assert summary["estimated_cost_usd"] is None
