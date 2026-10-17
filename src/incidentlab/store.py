"""Durable, indexed local records and append-only operation events.

Each call uses a short SQLite transaction and a separate connection. A restart
preserves evidence, never authority to mutate the new in-memory lab.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


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
        # Preserve exports produced by v0.1. Import is idempotent; newer records win.
        for path in (directory / "investigations").glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                remediation = record.get("remediation") or {}
                event = None
                if remediation.get("verification", {}).get("all_healthy"):
                    event = {"id": f"legacy-recovery-{record['id']}", "episode_id": record["episode_id"],
                        "created_at": remediation.get("created_at", record["created_at"]),
                        "type": "recovery_verified", "title": "Imported verified recovery",
                        "detail": "Imported from a v0.1 record; timestamp may be the investigation time.",
                        "data": {"investigation_id": record["id"], "legacy_import": True,
                                 "verification": remediation["verification"]}}
                self.save_many([("investigation", record)], event, ignore_existing=True)
            except (ValueError, KeyError, TypeError):
                continue

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_many(self, records: list[tuple[str, dict]], event: dict | None = None,
                  *, ignore_existing: bool = False) -> None:
        with self.connection() as db:
            for kind, record in records:
                insert = "INSERT OR IGNORE" if ignore_existing else "INSERT OR REPLACE"
                db.execute(f"{insert} INTO records VALUES (?, ?, ?, ?, ?)", (
                    record["id"], kind, record["episode_id"], record["created_at"],
                    json.dumps(record, allow_nan=False),
                ))
            if event:
                insert_event = "INSERT OR IGNORE" if ignore_existing else "INSERT"
                db.execute(f"{insert_event} INTO events(id,episode_id,created_at,type,payload) VALUES (?,?,?,?,?)", (
                    event["id"], event["episode_id"], event["created_at"], event["type"],
                    json.dumps(event, allow_nan=False),
                ))

    def event(self, event: dict) -> None:
        self.save_many([], event)

    def read(self, kind: str, record_id: str) -> dict:
        if len(record_id) != 32 or any(c not in "0123456789abcdef" for c in record_id):
            raise FileNotFoundError("Record not found")
        with self.connection() as db:
            row = db.execute("SELECT payload FROM records WHERE id=? AND kind=?", (record_id, kind)).fetchone()
        if row is None:
            raise FileNotFoundError("Record not found")
        return json.loads(row[0])

    def recent(self, kind: str, limit: int = 50) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM records WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                              (kind, max(1, min(limit, 100)))).fetchall()
        return [json.loads(row[0]) for row in rows]

    def events(self, episode_id: str, limit: int = 100) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT payload FROM events WHERE episode_id=? ORDER BY sequence DESC LIMIT ?",
                              (episode_id, max(1, min(limit, 1000)))).fetchall()
        return [json.loads(row[0]) for row in reversed(rows)]

    def summary(self) -> dict:
        with self.connection() as db:
            counts = dict(db.execute("SELECT kind, COUNT(*) FROM records GROUP BY kind").fetchall())
            recovered = db.execute("SELECT COUNT(*) FROM events WHERE type='recovery_verified'").fetchone()[0]
        return {"investigations": counts.get("investigation", 0),
                "rehearsals": counts.get("rehearsal", 0), "verified_recoveries": recovered}

    def latest_recovery(self, episode_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM events WHERE episode_id=? AND type IN "
                "('recovery_verified','recovery_failed') ORDER BY sequence DESC LIMIT 1", (episode_id,)).fetchone()
        return json.loads(row[0]) if row else None
