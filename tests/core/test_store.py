import json
import sqlite3

import pytest

from incidentlab.store import RecordStore


def record(identifier="a" * 32):
    return {
        "id": identifier,
        "episode_id": "episode",
        "created_at": "2026-10-17T12:00:00Z",
        "revision": 0,
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
