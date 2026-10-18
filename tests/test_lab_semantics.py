import sqlite3
from dataclasses import replace

from incidentlab.contracts import CHECKOUT_CONTRACT
from incidentlab.lab import Lab
from incidentlab.models import Action


def test_silent_price_drift_returns_200_but_fails_business_verification(lab):
    status = lab.inject("silent_price_drift")
    assert status["recent_statuses"] == [200] * 4
    assert status["http_errors"] == 0
    assert status["errors"] == status["semantic_failures"] == 4
    assert status["business_error_rate"] == status["error_rate"] == 1
    result = lab.probe(3)
    assert result["all_http_healthy"]
    assert not result["all_healthy"]
    assert not result["semantic_passed"]
    assert {check["sku"] for check in result["semantic_checks"]} == {"notebook", "lamp", "mug"}
    assert all(check["observed_total_cents"] == check["expected_total_cents"] + 100 for check in result["semantic_checks"])
    logs = [entry for entry in lab.query_logs("checkout", limit=30) if entry.data.get("error_type") == "price_mismatch"]
    assert logs
    assert logs[-1].data["contract_id"] == CHECKOUT_CONTRACT.id
    assert logs[-1].data["http_status"] == 200
    assert logs[-1].data["violations"] == ["price_mismatch"]
    assert lab.get_metrics()[0].data["semantic_failures"] == 7


def test_route_repair_exposes_silent_failure_then_rollback_restores_semantics(lab):
    lab.inject("route_and_price_drift")
    partial = lab.apply(Action.route)["verification"]
    assert partial["statuses"] == [200] * 5
    assert partial["all_http_healthy"]
    assert not partial["semantic_passed"]
    assert not partial["all_healthy"]
    assert lab.status()["http_errors"] == 0
    assert lab.status()["semantic_failures"] == 5
    final = lab.apply(Action.rollback)["verification"]
    assert final["all_healthy"] and final["semantic_passed"]
    assert all(check["observed_total_cents"] == check["expected_total_cents"] for check in final["semantic_checks"])
    assert lab.status()["errors"] == lab.status()["semantic_failures"] == 0


def test_semantic_rehearsal_clone_preserves_real_bug_and_isolates_repairs(lab, tmp_path):
    lab.inject("route_and_price_drift")
    lab.apply(Action.route)
    fingerprint = lab.fingerprint()
    before = lab.status()
    clone = lab.clone(tmp_path / "clone")
    try:
        result = clone.probe(3)
        assert result["all_http_healthy"] and not result["semantic_passed"]
        assert clone.apply(Action.rollback)["verification"]["semantic_passed"]
        assert clone.contract == lab.contract
        assert lab.status() == before
        assert lab.fingerprint() == fingerprint
        assert lab.config["release"] == "checkout-1.2"
    finally:
        clone.close()


def test_catalog_mutation_does_not_redefine_expected_price(lab):
    lab.inject("healthy")
    with sqlite3.connect(lab.database) as database:
        database.execute("UPDATE products SET price = 99 WHERE sku = 'notebook'")
    result = lab.probe(3)
    assert result["all_http_healthy"]
    assert not result["all_healthy"]
    check = next(item for item in result["semantic_checks"] if item["sku"] == "notebook")
    assert check["expected_total_cents"] == 1200
    assert check["observed_total_cents"] == 9900
    assert check["violations"] == ["price_mismatch"]
    # An allowlisted code rollback cannot silently repair corrupted catalog data.
    assert not lab.apply(Action.rollback)["verification"]["all_healthy"]


def test_probe_covers_every_product_before_repeating_and_is_seed_deterministic(lab):
    lab.inject("healthy", seed=107)
    first = lab.probe(6)
    second = lab.probe(6)
    first_skus = [check["sku"] for check in first["semantic_checks"]]
    assert first_skus == [check["sku"] for check in second["semantic_checks"]]
    assert set(first_skus[:3]) == {"notebook", "lamp", "mug"}
    assert first_skus[:3] == first_skus[3:]
    assert first["all_healthy"]


def test_snapshot_and_fingerprint_include_the_contract_version(lab, tmp_path):
    before = lab.fingerprint()
    lab.contract = replace(CHECKOUT_CONTRACT, version="2.0.0")
    assert lab.fingerprint() != before
    snapshot = lab.snapshot()
    clone = Lab.from_snapshot(snapshot, tmp_path / "clone")
    try:
        lab.contract = replace(CHECKOUT_CONTRACT, version="3.0.0")
        assert snapshot.contract.version == clone.contract.version == "2.0.0"
        assert clone.probe(3)["contract"]["sha256"] == snapshot.contract.sha256
    finally:
        clone.close()
