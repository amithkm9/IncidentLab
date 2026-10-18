import json
import sqlite3

import pytest

from incidentlab.application import IncidentService
from incidentlab.storage import RecordStore


def record(identifier="a" * 32):
    return {
        "id": identifier,
        "episode_id": "episode",
        "created_at": "2026-10-17T12:00:00Z",
        "revision": 0,
        "observation": {"requests": 4, "errors": 4, "scenario_id": "wrong_route"},
        "result": {
            "mode": "baseline",
            "elapsed_ms": 1.0,
            "traces": [],
            "finding": {
                "cause": "configuration_error",
                "title": "Inventory route failed",
                "explanation": "The observed request returned HTTP 404.",
                "evidence_ids": [],
                "action": "restore_inventory_route",
                "verification": "Issue fresh requests.",
                "limitations": "Controlled local lab.",
            },
        },
        "remediation": None,
    }


def test_legacy_exports_import_once_and_survive_restart(tmp_path):
    exports = tmp_path / "investigations"
    exports.mkdir()
    original = record()
    (exports / "old.json").write_text(json.dumps(original))
    (exports / "broken.json").write_text("incomplete")
    store = RecordStore(tmp_path)
    assert store.read("investigation", original["id"]) == original
    updated = {**original, "revision": 1}
    store.save_many([("investigation", updated)])
    reopened = RecordStore(tmp_path)
    assert reopened.read("investigation", original["id"]) == updated
    assert reopened.summary() == {"investigations": 1, "rehearsals": 0, "verified_recoveries": 0}
    assert reopened.events("episode") == []


def test_record_and_event_are_committed_atomically(tmp_path):
    store = RecordStore(tmp_path)
    item = record()
    event = {
        "id": "event",
        "episode_id": "episode",
        "created_at": "today",
        "type": "recovery_verified",
    }
    store.save_many([("investigation", item)], event)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_many([("investigation", {**item, "revision": 2})], event)
    assert store.read("investigation", item["id"])["revision"] == 0
    assert store.summary()["verified_recoveries"] == 1
    assert store.events("episode") == [event]
    assert store.events("other") == []


@pytest.mark.parametrize("identifier", ["../history.sqlite", "x" * 32, "a" * 31, "a" * 33])
def test_invalid_record_ids_never_address_paths(tmp_path, identifier):
    with pytest.raises(FileNotFoundError):
        RecordStore(tmp_path).read("investigation", identifier)


def test_legacy_verified_recovery_is_counted_once_across_restarts(tmp_path):
    exports = tmp_path / "investigations"
    exports.mkdir()
    original = {
        **record(),
        "remediation": {"verification": {"all_healthy": True, "statuses": [200] * 5}},
    }
    (exports / "old.json").write_text(json.dumps(original))
    for _ in range(2):
        store = RecordStore(tmp_path)
        assert store.summary()["verified_recoveries"] == 1
        assert len(store.events("episode")) == 1
        assert store.latest_recovery("episode")["data"]["legacy_import"]


@pytest.mark.parametrize("flag", ["false", "true", 1, 0, [], {}, None])
def test_legacy_verification_requires_a_boolean_flag(tmp_path, flag):
    exports = tmp_path / "investigations"
    exports.mkdir()
    original = {
        **record(),
        "remediation": {"verification": {"all_healthy": flag, "statuses": [200] * 5}},
    }
    (exports / "old.json").write_text(json.dumps(original))
    store = RecordStore(tmp_path)
    assert store.summary()["verified_recoveries"] == 0
    assert store.summary()["investigations"] == 0
    assert store.latest_recovery("episode") is None


@pytest.mark.parametrize(
    "verification",
    [
        {"all_healthy": True, "statuses": [500]},
        {"all_healthy": True, "statuses": [200], "semantic_passed": False},
        {"all_healthy": True, "statuses": [200], "semantic_passed": "false"},
        {"all_healthy": True, "statuses": [200], "all_http_healthy": False},
        {"all_healthy": True, "statuses": [True]},
        {"all_healthy": True, "statuses": []},
    ],
)
def test_legacy_contradictory_recovery_flags_are_not_imported(tmp_path, verification):
    exports = tmp_path / "investigations"
    exports.mkdir()
    original = {**record(), "remediation": {"verification": verification}}
    (exports / "old.json").write_text(json.dumps(original))
    assert RecordStore(tmp_path).summary()["investigations"] == 0


def test_legacy_failure_remains_readable_without_modern_contract_fields(tmp_path):
    exports = tmp_path / "investigations"
    exports.mkdir()
    original = {
        **record(),
        "remediation": {"verification": {"all_healthy": False, "statuses": [502] * 5}},
    }
    (exports / "old.json").write_text(json.dumps(original))
    store = RecordStore(tmp_path)
    service = IncidentService.__new__(IncidentService)
    service.store = store
    assert store.read("investigation", original["id"]) == original
    assert service.history()["investigations"][0]["scenario_id"] == "wrong_route"
    assert service.history()["investigations"][0]["investigation_verified"] is False
    assert "This attempt did not restore checkout" in service.postmortem(original["id"])


@pytest.mark.parametrize(
    "change",
    [
        {"result": {}},
        {"result": []},
        {"observation": None},
        {"revision": "0"},
        {"remediation": []},
        {"remediation": {"verification": {}}},
        {
            "remediation": {
                "verification": {"all_healthy": True, "statuses": [200]},
                "created_at": {},
            }
        },
    ],
)
def test_malformed_legacy_shapes_cannot_break_history(tmp_path, change):
    exports = tmp_path / "investigations"
    exports.mkdir()
    (exports / "bad.json").write_text(json.dumps({**record(), **change}))
    (exports / "good.json").write_text(json.dumps(record("b" * 32)))
    store = RecordStore(tmp_path)
    service = IncidentService.__new__(IncidentService)
    service.store = store
    assert [item["id"] for item in service.history()["investigations"]] == ["b" * 32]


def test_deeply_nested_legacy_json_does_not_abort_startup(tmp_path):
    exports = tmp_path / "investigations"
    exports.mkdir()
    (exports / "deep.json").write_text("[" * 2000 + "0" + "]" * 2000)
    (exports / "good.json").write_text(json.dumps(record()))
    assert RecordStore(tmp_path).summary()["investigations"] == 1


def test_history_skips_malformed_records_imported_before_validation(tmp_path):
    store = RecordStore(tmp_path)
    original = record()
    store.save_many([("investigation", original)])
    with store.connection() as database:
        for identifier, payload in [
            ("b" * 32, "[" * 2000 + "0" + "]" * 2000),
            ("c" * 32, "not json"),
            ("d" * 32, "[]"),
            ("e" * 32, json.dumps({"id": "e" * 32})),
        ]:
            database.execute(
                "INSERT INTO records VALUES (?, 'investigation', 'episode', 'today', ?)",
                (identifier, payload),
            )
    service = IncidentService.__new__(IncidentService)
    service.store = store
    assert [item["id"] for item in service.history()["investigations"]] == [original["id"]]
    for identifier in ("b" * 32, "c" * 32, "d" * 32):
        with pytest.raises(FileNotFoundError):
            store.read("investigation", identifier)


def test_postmortem_never_coerces_a_stored_false_string_to_recovery(tmp_path):
    store = RecordStore(tmp_path)
    original = {
        **record(),
        "remediation": {"verification": {"all_healthy": "false", "statuses": [502]}},
    }
    store.save_many([("investigation", original)])
    service = IncidentService.__new__(IncidentService)
    service.store = store
    assert "Recovery verified by this attempt." not in service.postmortem(original["id"])
    assert "This attempt did not restore checkout" in service.postmortem(original["id"])


def test_skipped_legacy_record_cannot_add_a_recovery_event(tmp_path):
    store = RecordStore(tmp_path)
    current = {
        **record(),
        "revision": 1,
        "remediation": {"verification": {"all_healthy": False, "statuses": [502]}},
    }
    store.save_many([("investigation", current)])
    exports = tmp_path / "investigations"
    exports.mkdir()
    legacy = {
        **record(),
        "remediation": {"verification": {"all_healthy": True, "statuses": [200]}},
    }
    (exports / "old.json").write_text(json.dumps(legacy))
    reopened = RecordStore(tmp_path)
    assert reopened.read("investigation", current["id"]) == current
    assert reopened.latest_recovery(current["episode_id"]) is None
    assert reopened.summary()["verified_recoveries"] == 0
