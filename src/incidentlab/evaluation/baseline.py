"""Replay frozen cases with real HTTP traffic and save all findings and traces."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from incidentlab import __version__
from incidentlab.domain.models import Action, Cause
from incidentlab.investigation.agents import investigate
from incidentlab.investigation.tools import Toolbox
from incidentlab.lab import Lab
from incidentlab.lab.scenarios import SCENARIO_BY_ID

MANIFEST = Path(__file__).parent / "manifests" / "baseline.json"


def summarize(episodes: list[dict]) -> dict:
    total = len(episodes)
    actionable = [e for e in episodes if e["expected_action"] != Action.none.value]
    gaps = [e for e in episodes if e["expected_cause"] == Cause.unknown.value]
    controls = [e for e in episodes if e["expected_action"] == Action.none.value]
    times = sorted(e["result"]["elapsed_ms"] for e in episodes if e.get("result"))
    costs = [e["result"].get("estimated_cost_usd") for e in episodes if e.get("result")]

    def rate(count, denominator):
        return round(count / denominator, 4) if denominator else None

    return {
        "episodes": total,
        "completed": sum(e.get("result") is not None for e in episodes),
        "errors": sum(e.get("error") is not None for e in episodes),
        "diagnosis_accuracy": rate(sum(e["diagnosis_correct"] for e in episodes), total),
        "action_accuracy": rate(sum(e["action_correct"] for e in episodes), total),
        "actionable_episodes": len(actionable),
        "remediation_success_rate": rate(sum(e["recovered"] for e in actionable), len(actionable)),
        "appropriate_abstention_rate": rate(
            sum(e["diagnosis_correct"] and e["action_correct"] for e in gaps), len(gaps)
        ),
        "control_no_action_rate": rate(sum(e["action_correct"] for e in controls), len(controls)),
        "median_latency_ms": round(statistics.median(times), 2) if times else None,
        "p95_latency_ms": times[math.ceil(len(times) * 0.95) - 1] if times else None,
        "input_tokens": sum(e["result"]["input_tokens"] for e in episodes if e.get("result")),
        "output_tokens": sum(e["result"]["output_tokens"] for e in episodes if e.get("result")),
        "estimated_cost_usd": round(sum(costs), 8)
        if costs and all(c is not None for c in costs) and not any(e.get("error") for e in episodes)
        else None,
        "usage_scope": "Completed findings only; failed API responses may also incur charges.",
        "semantic_evidence_support": "Not measured. Reference validation is not claim entailment; review saved traces manually.",
    }


def evaluate(mode: str = "baseline", split: str = "smoke", manifest_path: Path = MANIFEST) -> dict:
    if mode not in {"baseline", "mistral", "prompt", "retrieval"}:
        raise ValueError("Unknown evaluation mode")
    if mode != "baseline" and not os.environ.get("MISTRAL_API_KEY", "").strip():
        raise ValueError(
            "MISTRAL_API_KEY is required for model evaluation. No baseline will be substituted."
        )
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    seeds = manifest["splits"][split]
    started = datetime.now(timezone.utc).isoformat()
    episodes = []
    with tempfile.TemporaryDirectory(prefix="incidentlab-eval-") as directory:
        lab = Lab(Path(directory))
        try:
            for scenario_id in manifest["scenarios"]:
                scenario = SCENARIO_BY_ID[scenario_id]
                for seed in seeds:
                    episode = {
                        "case_id": f"{scenario.id}-{seed}",
                        "scenario_id": scenario.id,
                        "seed": seed,
                        "expected_cause": scenario.cause.value,
                        "expected_action": scenario.action.value,
                        "diagnosis_correct": False,
                        "action_correct": False,
                        "recovered": False,
                        "result": None,
                        "remediation": None,
                        "error": None,
                    }
                    try:
                        episode["before"] = lab.inject(scenario.id, seed)
                        result = investigate(Toolbox(lab), mode)
                        episode["result"] = result.model_dump(mode="json")
                        episode["diagnosis_correct"] = result.finding.cause == scenario.cause
                        episode["action_correct"] = result.finding.action == scenario.action
                        if result.finding.action != Action.none:
                            episode["remediation"] = lab.apply(result.finding.action)
                            episode["recovered"] = episode["remediation"]["verification"][
                                "all_healthy"
                            ]
                    except (ValueError, RuntimeError, OSError) as exc:
                        # Never replace a failed model run with the baseline.
                        episode["error"] = f"{type(exc).__name__}: {exc}"
                    episodes.append(episode)
        finally:
            lab.close()
    return {
        "schema_version": 1,
        "project_version": __version__,
        "mode": mode,
        "split": split,
        "provenance": "Deterministic offline baseline; NOT Mistral model performance."
        if mode == "baseline"
        else "Live Mistral API evaluation; failed calls remain failures.",
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {name: version(name) for name in ("httpx", "pydantic", "fastapi")},
        },
        "limitations": [
            "Known single-fault lab cases; no production accuracy or unseen-family claim.",
            "Repeated seeds are regression coverage, not independent statistical samples.",
            "Telemetry and timing are measured live and can vary between runs.",
            "Model aliases can change; pin a provider model version for longitudinal comparisons.",
        ],
        "summary": summarize(episodes),
        "episodes": episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["baseline", "mistral", "prompt", "retrieval"], default="baseline"
    )
    parser.add_argument("--split", choices=["smoke", "dev", "test"], default="smoke")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(args.mode, args.split, args.manifest)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    output = args.output or Path("artifacts") / f"{args.mode}-{args.split}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["provenance"])
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved complete report: {output}")
    if report["summary"]["errors"]:
        parser.exit(1, "One or more episodes failed; inspect the saved report.\n")


if __name__ == "__main__":
    main()
