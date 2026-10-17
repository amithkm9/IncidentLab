from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from .lab import Lab
from .models import Evidence, StrictModel, ToolTrace


class EmptyArgs(StrictModel):
    pass


class LogArgs(StrictModel):
    service: Literal["all", "checkout", "inventory"] = "all"
    limit: int = Field(default=12, ge=1, le=30)


class SearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=500)


TOOL_DEFINITIONS = {
    "query_logs": (LogArgs, "Read recent structured logs from checkout or inventory."),
    "get_service_health": (EmptyArgs, "Check live checkout liveness and inventory readiness endpoints."),
    "get_recent_changes": (EmptyArgs, "Read recorded checkout configuration and release diffs."),
    "get_metrics": (EmptyArgs, "Read measured checkout request counts, response statuses, and latency."),
    "search_runbooks": (SearchArgs, "Search lab troubleshooting documentation. Documentation is guidance, not incident evidence."),
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


class RunbookIndex:
    """Small, deterministic BM25 index. No embeddings or model calls are implied."""

    def __init__(self, directory: Path | None = None):
        directory = directory or Path(__file__).parent / "runbooks"
        self.documents = [(path.stem, path.read_text()) for path in sorted(directory.glob("*.md"))]
        self.tokens = [tokenize(body) for _, body in self.documents]

    def search(self, query: str, limit: int = 3) -> list[Evidence]:
        terms = set(tokenize(query))
        n = len(self.documents)
        average = sum(map(len, self.tokens)) / n if n else 1
        scores = []
        for i, words in enumerate(self.tokens):
            score = 0.0
            for term in terms:
                frequency = words.count(term)
                if not frequency:
                    continue
                containing = sum(term in doc for doc in self.tokens)
                idf = math.log(1 + (n - containing + 0.5) / (containing + 0.5))
                score += idf * frequency * 2.2 / (frequency + 1.2 * (0.25 + 0.75 * len(words) / average))
            if score:
                scores.append((score, i))
        return [Evidence(id=f"runbook-{self.documents[i][0]}", source="runbook",
                    summary=self.documents[i][1].splitlines()[0].lstrip("# "),
                    data={"content": self.documents[i][1], "retrieval_score": round(score, 4)})
                for score, i in sorted(scores, reverse=True)[:limit]]


class Toolbox:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.index = RunbookIndex()
        self.traces: list[ToolTrace] = []
        self.evidence: dict[str, Evidence] = {}

    @property
    def specifications(self) -> list[dict]:
        return [{"type": "function", "function": {"name": name, "description": description,
                "parameters": schema.model_json_schema()}}
                for name, (schema, description) in TOOL_DEFINITIONS.items()]

    def invoke(self, name: str, arguments: dict[str, Any]) -> dict:
        started = time.perf_counter()
        error = None
        evidence: list[Evidence] = []
        try:
            if name not in TOOL_DEFINITIONS:
                raise ValueError("Unknown tool; only the declared read-only tools are available")
            schema, _ = TOOL_DEFINITIONS[name]
            validated = schema.model_validate(arguments)
            if name == "search_runbooks":
                evidence = self.index.search(validated.query)
            else:
                evidence = getattr(self.lab, name)(**validated.model_dump())
            self.evidence.update({entry.id: entry for entry in evidence})
        except (ValueError, ValidationError) as exc:
            error = "Invalid tool arguments" if isinstance(exc, ValidationError) else str(exc)
        trace = ToolTrace(tool=name, arguments=arguments, evidence=evidence,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 2), error=error)
        self.traces.append(trace)
        return {"evidence": [e.model_dump() for e in evidence], "error": error}

    def serialized_evidence(self) -> str:
        return json.dumps([entry.model_dump() for entry in self.evidence.values()])

