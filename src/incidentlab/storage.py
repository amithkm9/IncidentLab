"""Durable, indexed local records and append-only operation events.

Each call uses a short SQLite transaction and a separate connection. A restart
preserves evidence, never authority to mutate the new in-memory lab.
"""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .domain.models import Investigation

MAX_LEGACY_RECORD_BYTES = 4 * 1024 * 1024


def _record_id(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)
    )


def valid_investigation_record(record: object) -> bool:
    """Check historical shape without granting the record mutation authority.

    The original v0.1 format has no scenario_id or business contract fields.
    Keep those records readable, but never coerce strings into recovery flags.
    """
    try:
        if (
            not isinstance(record, dict)
            or not _record_id(record.get("id"))
            or not isinstance(record.get("episode_id"), str)
            or not 1 <= len(record["episode_id"]) <= 128
            or not isinstance(record.get("created_at"), str)
            or not 1 <= len(record["created_at"]) <= 80
            or type(record.get("revision")) is not int
            or record["revision"] < 0
        ):
            return False
        observation = record["observation"]
        if not isinstance(observation, dict) or any(
            type(observation.get(key)) is not int or observation[key] < 0
            for key in ("requests", "errors")
        ):
            return False
        Investigation.model_validate(record["result"])
        remediation = record.get("remediation")
        if remediation is not None:
            if not isinstance(remediation, dict):
                return False
            verification = remediation["verification"]
            if (
                not isinstance(verification, dict)
                or type(verification.get("all_healthy")) is not bool
                or not isinstance(verification.get("statuses"), list)
                or not 1 <= len(verification["statuses"]) <= 20
                or any(
                    type(status) is not int or not 100 <= status <= 599
                    for status in verification["statuses"]
                )
                or any(
                    type(verification[key]) is not bool
                    for key in ("semantic_passed", "all_http_healthy")
                    if key in verification
                )
            ):
                return False
            if verification["all_healthy"] is True and (
                any(status != 200 for status in verification["statuses"])
                or verification.get("semantic_passed", True) is not True
                or verification.get("all_http_healthy", True) is not True
            ):
                return False
            timestamp = remediation.get("created_at", record["created_at"])
            if not isinstance(timestamp, str) or not 1 <= len(timestamp) <= 80:
                return False
        return True
    except (KeyError, TypeError, ValueError, RecursionError):
        return False


def _decode_record(payload: str) -> dict | None:
    try:
        record = json.loads(payload)
        return record if isinstance(record, dict) else None
    except (ValueError, TypeError, RecursionError):
        return None


class RecordStore:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.database = directory / "history.sqlite"
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                    episode_id TEXT NOT NULL, created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_kind_created
                    ON records(kind, created_at DESC);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT UNIQUE NOT NULL, episode_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, type TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_episode_sequence
                    ON events(episode_id, sequence);
            """)
        self._import_legacy(directory / "investigations")

    def _import_legacy(self, directory: Path) -> None:
        """Import bounded regular exports; corrupt historical data cannot stop startup."""
        if directory.is_symlink():
            return
        # Preserve exports produced by v0.1. Import is idempotent; newer records win.
        for path in directory.glob("*.json"):
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                descriptor = os.open(
                    path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK
                )
                with os.fdopen(descriptor, "rb") as source:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        continue
                    raw = source.read(MAX_LEGACY_RECORD_BYTES + 1)
                if len(raw) > MAX_LEGACY_RECORD_BYTES:
                    continue
                record = json.loads(raw)
                if not valid_investigation_record(record):
                    continue
                remediation = record.get("remediation") or {}
                event = None
                if remediation.get("verification", {}).get("all_healthy") is True:
                    event = {
                        "id": f"legacy-recovery-{record['id']}",
                        "episode_id": record["episode_id"],
                        "created_at": remediation.get("created_at", record["created_at"]),
                        "type": "recovery_verified",
                        "title": "Imported verified recovery",
                        "detail": "Imported from a v0.1 record; timestamp may be the investigation time.",
                        "data": {
                            "investigation_id": record["id"],
                            "legacy_import": True,
                            "verification": remediation["verification"],
                        },
                    }
                self.save_many([("investigation", record)], event, ignore_existing=True)
            except (OSError, ValueError, KeyError, TypeError, RecursionError):
                continue

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_many(
        self,
        records: list[tuple[str, dict]],
        event: dict | None = None,
        *,
        ignore_existing: bool = False,
    ) -> None:
        with self.connection() as db:
            records_written = False
            for kind, record in records:
                insert = "INSERT OR IGNORE" if ignore_existing else "INSERT OR REPLACE"
                cursor = db.execute(
                    f"{insert} INTO records VALUES (?, ?, ?, ?, ?)",
                    (
                        record["id"],
                        kind,
                        record["episode_id"],
                        record["created_at"],
                        json.dumps(record, allow_nan=False),
                    ),
                )
                records_written |= cursor.rowcount > 0
            # A skipped legacy export cannot add a recovery event for a newer
            # record. Keep record and event acceptance in the same transaction.
            if event and (not ignore_existing or records_written):
                insert_event = "INSERT OR IGNORE" if ignore_existing else "INSERT"
                db.execute(
                    f"{insert_event} INTO events(id,episode_id,created_at,type,payload) VALUES (?,?,?,?,?)",
                    (
                        event["id"],
                        event["episode_id"],
                        event["created_at"],
                        event["type"],
                        json.dumps(event, allow_nan=False),
                    ),
                )

    def event(self, event: dict) -> None:
        self.save_many([], event)

    def read(self, kind: str, record_id: str) -> dict:
        if not _record_id(record_id):
            raise FileNotFoundError("Record not found")
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM records WHERE id=? AND kind=?", (record_id, kind)
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Record not found")
        record = _decode_record(row[0])
        if record is None:
            raise FileNotFoundError("Record not found")
        return record

    def recent(self, kind: str, limit: int = 50) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                (kind, max(1, min(limit, 100))),
            ).fetchall()
        return [record for row in rows if (record := _decode_record(row[0])) is not None]

    def events(self, episode_id: str, limit: int = 100) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM events WHERE episode_id=? ORDER BY sequence DESC LIMIT ?",
                (episode_id, max(1, min(limit, 1000))),
            ).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def summary(self) -> dict:
        with self.connection() as db:
            counts = dict(db.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind").fetchall())
            recovered = db.execute(
                "SELECT COUNT(*) FROM events WHERE type='recovery_verified'"
            ).fetchone()[0]
        return {
            "investigations": counts.get("investigation", 0),
            "rehearsals": counts.get("rehearsal", 0),
            "verified_recoveries": recovered,
        }

    def latest_recovery(self, episode_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM events WHERE episode_id=? AND type IN "
                "('recovery_verified','recovery_failed') ORDER BY sequence DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None
