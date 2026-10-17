"""Compare one-shot remediation with bounded fix rehearsal on real local HTTP traffic."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .investigator import investigate
from .lab import Lab, SCENARIO_BY_ID
from .models import Action
from .rehearsal import run_rehearsal
from .tools import Toolbox


# This manifest is evaluator-owned ground truth. It is never supplied to either
# decision procedure. Keep case identities fixed when comparing report artifacts.
MANIFEST = {
    "name": "incidentlab-fix-rehearsal-v1",
    "scenarios": [
        {"id": "wrong_route", "expected_actions": [Action.route.value]},
        {"id": "inventory_down", "expected_actions": [Action.dependency.value]},
        {"id": "tight_timeout", "expected_actions": [Action.timeout.value]},
        {"id": "missing_database", "expected_actions": [Action.database.value]},
        {"id": "bad_release", "expected_actions": [Action.rollback.value]},
        {"id": "route_and_release", "expected_actions": [Action.route.value, Action.rollback.value]},
        {"id": "database_and_inventory", "expected_actions": [Action.database.value, Action.dependency.value]},
        {"id": "timeout_and_release", "expected_actions": [Action.timeout.value, Action.rollback.value]},
        {"id": "healthy", "expected_actions": [], "control": "healthy"},
        {"id": "telemetry_gap", "expected_actions": [], "control": "telemetry_gap"},
    ],
    "splits": {"smoke": [42], "test": [11, 23, 37]},
    "max_actions_per_plan": 2,
    "rehearsal_probe_count": 3,
    "final_verification_probe_count": 5,
}


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(episodes: list[dict]) -> dict:
    """Include failed arms in every applicable quality denominator."""
    faults = [episode for episode in episodes if episode["expected_actions"]]
    singles = [episode for episode in faults if len(episode["expected_actions"]) == 1]
    compounds = [episode for episode in faults if len(episode["expected_actions"]) > 1]
    controls = [episode for episode in episodes if not episode["expected_actions"]]
    healthy = [episode for episode in controls if episode.get("control") == "healthy"]
    gaps = [episode for episode in controls if episode.get("control") == "telemetry_gap"]
    arms = {}
    for arm in ("baseline", "rehearsal"):
        outcomes = [episode[arm] for episode in episodes]
        elapsed = [outcome["elapsed_ms"] for outcome in outcomes if outcome.get("completed")]
        recovered = lambda group: sum(bool(episode[arm].get("completed") and episode[arm].get("recovered")) for episode in group)
        no_action = lambda group: sum(bool(episode[arm].get("completed") and episode[arm].get("no_action")) for episode in group)
        arms[arm] = {
            "completed": sum(bool(outcome.get("completed")) for outcome in outcomes),
            "errors": sum(outcome.get("error") is not None for outcome in outcomes),
            "verified_recoveries": recovered(faults),
            "recovery_rate": _rate(recovered(faults), len(faults)),
            "single_fault_recoveries": recovered(singles),
            "single_fault_recovery_rate": _rate(recovered(singles), len(singles)),
            "compound_fault_recoveries": recovered(compounds),
            "compound_fault_recovery_rate": _rate(recovered(compounds), len(compounds)),
            "controls_with_no_action": no_action(controls),
            "control_no_action_rate": _rate(no_action(controls), len(controls)),
            "healthy_no_action_rate": _rate(no_action(healthy), len(healthy)),
            "telemetry_gap_abstention_rate": _rate(no_action(gaps), len(gaps)),
            "median_episode_ms": round(statistics.median(elapsed), 2) if elapsed else None,
            "total_episode_ms": round(sum(outcome.get("elapsed_ms", 0) for outcome in outcomes), 2),
        }
    baseline_rate, rehearsal_rate = (arms[key]["recovery_rate"] for key in ("baseline", "rehearsal"))
    baseline_compound, rehearsal_compound = (arms[key]["compound_fault_recovery_rate"] for key in ("baseline", "rehearsal"))
    experiments = [experiment for episode in episodes
                   for experiment in (episode["rehearsal"].get("result") or {}).get("experiments", [])]
    controls_run = [episode["rehearsal"]["result"]["control"] for episode in episodes
                    if (episode["rehearsal"].get("result") or {}).get("control")]
    return {
        "episodes": len(episodes),
        "episode_errors": sum(any(episode[arm].get("error") is not None for arm in arms) for episode in episodes),
        "fault_episodes": len(faults),
        "single_fault_episodes": len(singles),
        "compound_fault_episodes": len(compounds),
        "control_episodes": len(controls),
        "healthy_controls": len(healthy),
        "telemetry_gap_controls": len(gaps),
        **arms,
        "recovery_improvement_percentage_points": round((rehearsal_rate - baseline_rate) * 100, 2) if baseline_rate is not None and rehearsal_rate is not None else None,
        "compound_recovery_improvement_percentage_points": round((rehearsal_compound - baseline_compound) * 100, 2) if baseline_compound is not None and rehearsal_compound is not None else None,
        "candidate_experiments": len(experiments),
        "successful_candidate_experiments": sum(experiment.get("verification", {}).get("all_healthy", False) for experiment in experiments),
        "rehearsal_control_experiments": len(controls_run),
        "rehearsal_probe_requests": sum(experiment.get("verification", {}).get("requests", 0) for experiment in experiments + controls_run),
        "model_api_calls": 0,
        "timing_scope": "Each arm includes fault injection, decision procedure, action execution if selected, and final fresh verification; excludes lab construction. All attempts count toward total time; median covers completed arms.",
    }


def _outcome() -> dict:
    return {"completed": False, "result": None, "actions": [], "no_action": False,
            "recovered": False, "verification": None, "remediation": None,
            "elapsed_ms": 0, "error": None}


def _run_arm(lab: Lab, arm: str, scenario_id: str, seed: int) -> dict:
    outcome = _outcome()
    started = time.perf_counter()
    try:
        outcome["before"] = lab.inject(scenario_id, seed)
        if arm == "baseline":
            result = investigate(Toolbox(lab), "baseline")
            outcome["result"] = result.model_dump(mode="json")
            actions = [] if result.finding.action == Action.none else [result.finding.action]
        else:
            result = run_rehearsal(lab, max_actions=MANIFEST["max_actions_per_plan"],
                                   probe_count=MANIFEST["rehearsal_probe_count"])
            outcome["result"] = result
            selected_id = result["recommended_plan_id"]
            candidates = [result["control"], *result["experiments"]]
            selected = next((candidate for candidate in candidates if candidate["id"] == selected_id), None)
            if selected_id is not None and selected is None:
                raise ValueError("Rehearsal recommended a plan missing from measured experiments")
            actions = [Action(action) for action in selected["actions"]] if selected else []
        outcome["actions"] = [action.value for action in actions]
        if actions:
            # Execute only the procedure's chosen plan; evaluator truth is never
            # used to replace an incorrect or unsuccessful recommendation.
            outcome["remediation"] = lab.apply_plan(actions)
        outcome["verification"] = lab.probe(MANIFEST["final_verification_probe_count"])
        outcome["recovered"] = bool(actions and outcome["verification"]["all_healthy"])
        outcome["no_action"] = not actions
        outcome["completed"] = True
    except Exception as exc:
        # Keep unexpected arm failures visible, continue the independent arm,
        # and retain the failed case in every applicable metric denominator.
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    outcome["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return outcome


def evaluate(split: str = "smoke") -> dict:
    if split not in MANIFEST["splits"]:
        raise ValueError("Unknown rehearsal evaluation split")
    for case in MANIFEST["scenarios"]:
        scenario = SCENARIO_BY_ID[case["id"]]
        if set(case["expected_actions"]) != {action.value for action in scenario.expected_actions}:
            raise ValueError(f"Frozen expected actions no longer match scenario {scenario.id}")
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    episodes = []
    with tempfile.TemporaryDirectory(prefix="incidentlab-rehearsal-eval-") as directory:
        baseline_lab = Lab(Path(directory) / "baseline")
        try:
            rehearsal_lab = Lab(Path(directory) / "rehearsal")
            try:
                for case in MANIFEST["scenarios"]:
                    for seed in MANIFEST["splits"][split]:
                        episode = {"case_id": f"{case['id']}-{seed}", "scenario_id": case["id"],
                                   "seed": seed, "expected_actions": list(case["expected_actions"]),
                                   "fault_count": len(case["expected_actions"]), "control": case.get("control")}
                        episode["baseline"] = _run_arm(baseline_lab, "baseline", case["id"], seed)
                        episode["rehearsal"] = _run_arm(rehearsal_lab, "rehearsal", case["id"], seed)
                        episodes.append(episode)
            finally:
                rehearsal_lab.close()
        finally:
            baseline_lab.close()
    manifest_bytes = json.dumps(MANIFEST, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1, "project_version": __version__, "split": split,
        "provenance": "Offline deterministic engineering comparison; NOT Mistral model performance.",
        "started_at": started_at, "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "manifest": MANIFEST, "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "packages": {name: version(name) for name in ("httpx", "pydantic", "fastapi")}},
        "limitations": [
            "Known finite fault families and an allowlist of five lab actions; exhaustive search is bounded to at most two actions.",
            "The comparator performs one deterministic diagnosis and one action; it does not retry or receive the rehearsal's larger experiment budget.",
            "Repeated seeds exercise the same mechanisms; they are regression cases, not independent incidents or a held-out generalization study.",
            "Rehearsal clones this purpose-built HTTP/SQLite application; production service cloning and production-safe changes are not implemented.",
            "Health means a small batch of HTTP 200 checkout responses; long-term reliability, semantic correctness, and nonfunctional regressions are not established.",
            "Telemetry-gap cases intentionally require no recommendation, even though a hidden dependency fault exists.",
            "Live request timings vary; benchmark throughput and incident-resolution time are not production performance claims.",
        ],
        "summary": summarize(episodes), "episodes": episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=list(MANIFEST["splits"]), default="smoke")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(args.split)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    output = args.output or Path("artifacts") / f"rehearsal-{args.split}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["provenance"])
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved complete report: {output}")
    if report["summary"]["episode_errors"]:
        parser.exit(1, "One or more comparison arms failed; inspect the saved report.\n")


if __name__ == "__main__":
    main()
