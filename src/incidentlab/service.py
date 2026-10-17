"""Single-lab orchestration; model tools cannot reach mutation operations."""
from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .investigator import investigate
from .lab import Lab
from .models import Action, InvestigateRequest
from .tools import Toolbox


class ConflictError(Exception):
    pass


class IncidentService:
    def __init__(self, directory: Path):
        self.lab = Lab(directory / "lab")
        self.artifacts = directory / "investigations"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self._operation = threading.Lock()
        self.latest: dict | None = None
        self.revision = 0
        self.lab.inject("healthy")

    @contextmanager
    def operation(self):
        if not self._operation.acquire(blocking=False):
            raise ConflictError("The lab is busy. Wait for the current operation to finish.")
        try:
            yield
        finally:
            self._operation.release()

    def status(self) -> dict:
        return {**self.lab.status(), "busy": self._operation.locked()}

    def inject(self, scenario_id: str, seed: int) -> dict:
        with self.operation():
            result = self.lab.inject(scenario_id, seed)
            self.revision += 1
            self.latest = None
            return result

    def probe(self, count: int) -> dict:
        with self.operation():
            return {"verification": self.lab.probe(count), "status": self.lab.status()}

    def investigate(self, request: InvestigateRequest) -> dict:
        with self.operation():
            result = investigate(Toolbox(self.lab), request.mode, request.question)
            record = {
                "id": uuid.uuid4().hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "episode_id": self.lab.episode_id,
                "revision": self.revision,
                "question": request.question,
                "observation": self.lab.status(),
                "result": result.model_dump(mode="json"),
                "remediation": None,
            }
            self._save(record)
            self.latest = record
            return record

    def remediate(self, investigation_id: str, action: Action) -> dict:
        with self.operation():
            record = self.latest
            if (not record or record["id"] != investigation_id
                    or record["episode_id"] != self.lab.episode_id
                    or record["revision"] != self.revision):
                raise ConflictError("This finding is stale. Investigate the current incident before applying a fix.")
            if record["remediation"] is not None:
                raise ConflictError("This remediation was already attempted. Run a new investigation.")
            if action == Action.none or action.value != record["result"]["finding"]["action"]:
                raise ConflictError("Only the action proposed by the current finding can be applied.")
            result = self.lab.apply(action)
            self.revision += 1
            record["remediation"] = result
            self._save(record)
            return {**result, "status": self.lab.status()}

    def _save(self, record: dict) -> None:
        target = self.artifacts / f"{record['id']}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)

    def read(self, investigation_id: str) -> dict:
        # Artifact IDs, never caller-controlled filesystem paths.
        if len(investigation_id) != 32 or any(c not in "0123456789abcdef" for c in investigation_id):
            raise FileNotFoundError("Investigation not found")
        return json.loads((self.artifacts / f"{investigation_id}.json").read_text(encoding="utf-8"))

    def close(self) -> None:
        self.lab.close()
