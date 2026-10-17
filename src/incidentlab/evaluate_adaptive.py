"""Compare evidence-adaptive and fixed-order recovery under equal candidate ceilings.

The default comparison is entirely offline. Mistral is a separate, explicitly
enabled arm; deterministic results are never represented as model performance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import os
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .evaluate_rehearsal import MANIFEST as REHEARSAL_MANIFEST
from .lab import Lab, SCENARIO_BY_ID
from .models import Action
from .rehearsal import EXECUTABLE_ACTIONS, _experiment


STRATEGIES = ("adaptive", "ordered", "mistral")
SCENARIOS = copy.deepcopy(REHEARSAL_MANIFEST["scenarios"])
FINAL_PROBE_COUNT = 5
STRATEGY_LABELS = {
    "adaptive": "Offline evidence-adaptive deterministic policy",
    "ordered": "Offline fixed-order candidate search",
    "mistral": "Live Mistral evidence-adaptive policy",
}


def _validate_options(strategies, seeds, max_experiments, max_actions, probe_count, allow_paid_api):
    if not strategies or len(set(strategies)) != len(strategies) or any(item not in STRATEGIES for item in strategies):
        raise ValueError("Choose distinct strategies from adaptive, ordered, mistral")
    if (not seeds or any(not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 1_000_000 for seed in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError("Seeds must be distinct integers between 0 and 1000000")
    for name, value, low, high in (("max_experiments", max_experiments, 1, 8),
                                   ("max_actions", max_actions, 1, 2), ("probe_count", probe_count, 1, 20)):
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer between {low} and {high}")
    if "mistral" in strategies:
        if not allow_paid_api:
            raise ValueError("Mistral makes paid API calls; explicitly pass --allow-paid-api")
        if not os.environ.get("MISTRAL_API_KEY", "").strip():
            raise ValueError("MISTRAL_API_KEY must be configured before evaluating Mistral")


def _passed(verification: dict | None, count: int) -> bool:
    return bool(verification and verification.get("all_healthy") is True
                and verification.get("requests") == count and verification.get("statuses") == [200] * count)


def run_ordered_rehearsal(lab: Lab, max_experiments: int = 4, max_actions: int = 2, probe_count: int = 3) -> dict:
    """Test a fixed prefix of the action combinations without consulting labels.

    Both policies receive the same candidate/probe ceilings and stop on a
    measured success. Equality of these ceilings is not equality of reasoning
    cost, evidence access, total HTTP traffic, or the number of candidates used.
    """
    _validate_options(("ordered",), (0,), max_experiments, max_actions, probe_count, False)
    started = time.perf_counter()
    snapshot = lab.snapshot()
    experiments, decisions = [], []
    recommended, control, error, attempted = None, None, None, 0
    try:
        with tempfile.TemporaryDirectory(prefix="incidentlab-ordered-") as directory:
            control = _experiment(snapshot, Path(directory) / "control", "control", (), probe_count)
            if not snapshot.telemetry_available:
                stop_reason = "missing_telemetry"
            elif _passed(control["verification"], probe_count):
                stop_reason = "control_healthy"
            else:
                stop_reason = "candidate_budget_exhausted"
                candidates = itertools.chain.from_iterable(
                    itertools.combinations(EXECUTABLE_ACTIONS, size) for size in range(1, max_actions + 1))
                for index, actions in enumerate(itertools.islice(candidates, max_experiments), start=1):
                    plan_id = f"plan-{index:02d}"
                    attempted += 1
                    trial = _experiment(snapshot, Path(directory) / plan_id, plan_id, actions, probe_count)
                    experiments.append(trial)
                    decisions.append({"step": index, "tool": "rehearse_plan", "actions": list(trial["actions"]),
                                      "hypothesis": "Next plan in the fixed action-combination order.",
                                      "plan_id": plan_id, "evidence_ids": []})
                    if _passed(trial["verification"], probe_count):
                        recommended = trial
                        stop_reason = "verified_plan"
                        break
                if recommended is None and len(experiments) < max_experiments:
                    stop_reason = "candidate_space_exhausted"
    except Exception:
        recommended, stop_reason = None, "experiment_error"
        error = {"code": stop_reason, "message": "An isolated experiment failed before completion; prior measured outcomes are retained."}
        decisions.append({"step": len(experiments) + 1, "outcome": stop_reason, "actions": [], "evidence_ids": []})
    control_healthy = _passed((control or {}).get("verification"), probe_count)
    return {
        "strategy": "ordered", "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "source_fingerprint": snapshot.fingerprint(), "max_actions": max_actions, "probe_count": probe_count,
        "control": control, "experiments": experiments,
        "recommended_plan_id": recommended["id"] if recommended else None,
        "summary": {"tested_plans": len(experiments),
                    "successful_plans": sum(_passed(item["verification"], probe_count) for item in experiments),
                    "minimal_action_count": len(recommended["actions"]) if recommended else None,
                    "control_healthy": control_healthy, "telemetry_available": snapshot.telemetry_available,
                    "abstention_reason": None if recommended else stop_reason},
        "decision_trace": decisions,
        "budget": {"max_experiments": max_experiments, "used_experiments": attempted,
                   "completed_experiments": len(experiments), "stop_reason": stop_reason},
        "error": error,
        "provider_usage": {"model": None, "input_tokens": 0, "output_tokens": 0, "api_calls": 0,
                           "estimated_cost_usd": 0, "cost_note": "Offline policy; no model API calls."},
        "limitations": ["Fixed-order prefix search over known allowlisted actions; it is not an iterative diagnosis baseline.",
                        "A passing plan establishes only sampled HTTP 200 checkout responses in this disposable lab."],
    }


def _run_strategy(lab, strategy, max_experiments, max_actions, probe_count, planner=None):
    if strategy == "ordered":
        return run_ordered_rehearsal(lab, max_experiments, max_actions, probe_count)
    from .adaptive import run_adaptive_rehearsal
    return run_adaptive_rehearsal(lab, strategy=strategy, max_experiments=max_experiments,
                                 max_actions=max_actions, probe_count=probe_count,
                                 planner=planner if strategy == "mistral" else None)


def _selected_actions(report: dict, max_experiments: int, max_actions: int, probe_count: int) -> list[Action]:
    experiments = report.get("experiments", [])
    if len(experiments) > max_experiments or report.get("budget", {}).get("used_experiments", len(experiments)) > max_experiments:
        raise ValueError("Strategy exceeded the candidate experiment budget")
    candidates = [report["control"], *experiments]
    identifiers = [item["id"] for item in candidates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Measured experiment IDs must be unique")
    if report["control"].get("actions"):
        raise ValueError("The no-action control must not apply interventions")
    for item in experiments:
        actions = [Action(action) for action in item["actions"]]
        if not 1 <= len(actions) <= max_actions or len(set(actions)) != len(actions) or Action.none in actions:
            raise ValueError("Measured candidate violates the action budget or allowlist")
    for item in candidates:
        verification = item["verification"]
        if verification.get("requests") != probe_count or len(verification.get("statuses", [])) != probe_count:
            raise ValueError("Strategy did not use the configured probe count")
    selected_id = report.get("recommended_plan_id")
    if selected_id is None:
        return []
    selected = next((item for item in experiments if item["id"] == selected_id), None)
    if selected is None:
        raise ValueError("Recommended plan is missing from measured candidate experiments")
    actions = [Action(action) for action in selected["actions"]]
    if not 1 <= len(actions) <= max_actions or len(set(actions)) != len(actions) or Action.none in actions:
        raise ValueError("Recommended plan violates the action budget or allowlist")
    if (not _passed(selected["verification"], probe_count) or _passed(report["control"]["verification"], probe_count)
            or not report.get("summary", {}).get("telemetry_available", False)):
        raise ValueError("Recommended plan lacks an eligible measured success")
    return actions


def _run_arm(directory: Path, strategy: str, scenario_id: str, seed: int,
             max_experiments: int, max_actions: int, probe_count: int, planner=None) -> dict:
    outcome = {"completed": False, "result": None, "actions": [], "no_action": False,
               "recovered": False, "verification": None, "remediation": None,
               "elapsed_ms": 0, "error": None}
    started, lab = time.perf_counter(), None
    try:
        # Fresh source instances prevent one strategy's mutations from changing
        # the other strategy's observations. Ground truth is used only below by
        # the evaluator's summary, never passed into a policy or substituted.
        lab = Lab(directory)
        outcome["before"] = lab.inject(scenario_id, seed)
        report = _run_strategy(lab, strategy, max_experiments, max_actions, probe_count, planner)
        outcome["result"] = report
        if report.get("error") or report.get("budget", {}).get("stop_reason") in {"provider_error", "invalid_plan"}:
            error = report.get("error") or {}
            raise RuntimeError(f"Strategy stopped: {error.get('code') or report['budget']['stop_reason']}")
        actions = _selected_actions(report, max_experiments, max_actions, probe_count)
        outcome["actions"] = [action.value for action in actions]
        if actions:
            outcome["remediation"] = lab.apply_plan(actions, probe_count=FINAL_PROBE_COUNT)
            outcome["verification"] = outcome["remediation"]["verification"]
        else:
            outcome["verification"] = lab.probe(FINAL_PROBE_COUNT)
        outcome["recovered"] = bool(actions and _passed(outcome["verification"], FINAL_PROBE_COUNT))
        outcome["no_action"] = not actions
        outcome["completed"] = True
    except Exception as exc:
        # Model provider errors already carry safe report metadata. Do not copy
        # arbitrary exception bodies that may contain request data or secrets.
        outcome["error"] = (f"{type(exc).__name__}: model comparison arm failed; inspect safe report metadata"
                            if strategy == "mistral" else f"{type(exc).__name__}: {exc}")
    finally:
        if lab is not None:
            try:
                lab.close()
            except Exception as exc:
                outcome["completed"] = False
                outcome["error"] = outcome["error"] or f"{type(exc).__name__}: lab cleanup failed"
        outcome["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return outcome


def _rate(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def summarize(episodes: list[dict], strategies: tuple[str, ...] = ("adaptive", "ordered")) -> dict:
    faults = [item for item in episodes if item["expected_actions"]]
    singles = [item for item in faults if len(item["expected_actions"]) == 1]
    compounds = [item for item in faults if len(item["expected_actions"]) > 1]
    controls = [item for item in episodes if not item["expected_actions"]]
    gaps = [item for item in controls if item.get("control") == "telemetry_gap"]
    arms = {}
    for strategy in strategies:
        outcomes = [episode["strategies"][strategy] for episode in episodes]
        recovered = lambda group: sum(bool(item["strategies"][strategy].get("completed") and item["strategies"][strategy].get("recovered")) for item in group)
        no_action = lambda group: sum(bool(item["strategies"][strategy].get("completed") and item["strategies"][strategy].get("no_action")) for item in group)
        reports = [item["result"] for item in outcomes if item.get("result")]
        experiments = [experiment for report in reports for experiment in report.get("experiments", [])]
        control_runs = [report["control"] for report in reports if report.get("control")]
        usages = [report.get("provider_usage", {}) for report in reports]
        elapsed = [item["elapsed_ms"] for item in outcomes if item.get("completed")]
        usage_complete = (strategy != "mistral" or (len(usages) == len(outcomes)
            and all(item.get("completed") for item in outcomes)
            and all(usage.get("estimated_cost_usd") is not None for usage in usages)))
        arms[strategy] = {
            "label": STRATEGY_LABELS[strategy], "uses_model": strategy == "mistral",
            "completed": sum(bool(item.get("completed")) for item in outcomes),
            "errors": sum(item.get("error") is not None for item in outcomes),
            "verified_recoveries": recovered(faults), "recovery_rate": _rate(recovered(faults), len(faults)),
            "single_fault_recoveries": recovered(singles), "single_fault_recovery_rate": _rate(recovered(singles), len(singles)),
            "compound_fault_recoveries": recovered(compounds), "compound_fault_recovery_rate": _rate(recovered(compounds), len(compounds)),
            "controls_with_no_action": no_action(controls), "control_no_action_rate": _rate(no_action(controls), len(controls)),
            "telemetry_gap_abstention_rate": _rate(no_action(gaps), len(gaps)),
            "candidate_experiments": len(experiments),
            "completed_candidate_experiments": len(experiments),
            "recorded_started_candidate_experiments": sum(report.get("budget", {}).get("used_experiments", len(report.get("experiments", []))) for report in reports),
            "control_experiments": len(control_runs),
            "recorded_experiment_requests": sum(item.get("verification", {}).get("requests", 0) for item in experiments + control_runs),
            "final_verification_requests": sum((item.get("verification") or {}).get("requests", 0) for item in outcomes),
            "median_episode_ms": round(statistics.median(elapsed), 2) if elapsed else None,
            "total_episode_ms": round(sum(item.get("elapsed_ms", 0) for item in outcomes), 2),
            "provider_usage": {
                "models": sorted({usage["model"] for usage in usages if usage.get("model")}),
                "recorded_api_calls": sum(usage.get("api_calls", 0) for usage in usages),
                "recorded_input_tokens": sum(usage.get("input_tokens", 0) for usage in usages),
                "recorded_output_tokens": sum(usage.get("output_tokens", 0) for usage in usages),
                "estimated_cost_usd": round(sum(usage.get("estimated_cost_usd") or 0 for usage in usages), 8) if usage_complete else None,
                "cost_complete": usage_complete,
                "notes": sorted({usage.get("cost_note") for usage in usages if usage.get("cost_note")}),
                "accounting_scope": "Recorded provider attempts and reported tokens only; failed or unreported responses may have unobserved billable usage.",
            },
        }
    comparison = None
    if "adaptive" in arms and "ordered" in arms and faults:
        comparison = round(100 * (arms["adaptive"]["verified_recoveries"] - arms["ordered"]["verified_recoveries"]) / len(faults), 2)
    return {"episodes": len(episodes), "episode_errors": sum(any(item["strategies"][strategy].get("error") for strategy in strategies) for item in episodes),
            "fault_episodes": len(faults), "single_fault_episodes": len(singles), "compound_fault_episodes": len(compounds),
            "control_episodes": len(controls), "telemetry_gap_controls": len(gaps), "strategies": arms,
            "offline_adaptive_vs_ordered_recovery_percentage_points": comparison,
            "timing_scope": "Per arm: fresh lab construction, injection, policy, application/five fresh verification requests, and cleanup. Failed attempts remain in totals; medians cover completed arms."}


def evaluate(strategies=("adaptive", "ordered"), seeds=(42,), max_experiments=4,
             max_actions=2, probe_count=3, allow_paid_api=False, planner=None) -> dict:
    strategies, seeds = tuple(strategies), tuple(seeds)
    _validate_options(strategies, seeds, max_experiments, max_actions, probe_count, allow_paid_api)
    for case in SCENARIOS:
        expected = {action.value for action in SCENARIO_BY_ID[case["id"]].expected_actions}
        if set(case["expected_actions"]) != expected:
            raise ValueError(f"Frozen expected actions no longer match scenario {case['id']}")
    manifest = {"name": "incidentlab-equal-candidate-budget-v1", "scenarios": copy.deepcopy(SCENARIOS),
                "seeds": list(seeds), "strategies": list(strategies), "max_experiments": max_experiments,
                "max_actions": max_actions, "probe_count": probe_count, "final_verification_probe_count": FINAL_PROBE_COUNT,
                "ordered_action_order": [action.value for action in EXECUTABLE_ACTIONS]}
    started_at, started = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    episodes = []
    with tempfile.TemporaryDirectory(prefix="incidentlab-adaptive-eval-") as directory:
        for case in SCENARIOS:
            for seed in seeds:
                episode = {"case_id": f"{case['id']}-{seed}", "scenario_id": case["id"], "seed": seed,
                           "expected_actions": list(case["expected_actions"]), "control": case.get("control"), "strategies": {}}
                for strategy in strategies:
                    episode["strategies"][strategy] = _run_arm(Path(directory) / episode["case_id"] / strategy,
                        strategy, case["id"], seed, max_experiments, max_actions, probe_count, planner)
                episodes.append(episode)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return {"schema_version": 1, "project_version": __version__, "manifest": manifest,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "provenance": ("Controlled lab policy comparison with a separately identified live Mistral arm."
                           if "mistral" in strategies else "Offline deterministic policy comparison; NOT Mistral model performance. No model API calls."),
            "model_strategy_selected": "mistral" in strategies,
            "started_at": started_at, "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "packages": {name: version(name) for name in ("httpx", "pydantic", "fastapi")}},
            "limitations": [
                "Equal candidate ceilings and requests per experiment do not imply equal total compute, evidence calls, tokens, or candidates actually used.",
                "Fixed-order prefix search is a simple comparator, not an equal-quality iterative incident investigator.",
                "The deterministic adaptive policy is engineered for the known fault mechanisms; its results are not model reasoning scores.",
                "Repeated seeds cover ten known scenarios, not independent production incidents or unseen-fault generalization.",
                "Recovery means five fresh HTTP 200 responses in this purpose-built local lab; semantics, side effects, and production safety are not established.",
                "Recorded experiment requests exclude injection and diagnostic evidence traffic; final verification is counted separately.",
                "Started candidate attempts may exceed completed measured experiments after execution failure; partial failed-request counts are unknown and are not invented.",
                "Failed attempts remain in recovery/control denominators; unavailable provider usage may undercount billable usage.",
            ], "summary": summarize(episodes, strategies), "episodes": episodes}


def _parse_seeds(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Seeds must be comma-separated integers") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategies", default="adaptive,ordered", help="Comma-separated adaptive,ordered,mistral")
    parser.add_argument("--seeds", type=_parse_seeds, default=(42,), help="Comma-separated integer seeds; default 42")
    parser.add_argument("--max-experiments", type=int, default=4)
    parser.add_argument("--max-actions", type=int, choices=(1, 2), default=2)
    parser.add_argument("--probe-count", type=int, default=3)
    parser.add_argument("--allow-paid-api", action="store_true", help="Explicitly authorize paid calls for the Mistral arm")
    parser.add_argument("--output", type=Path, default=Path("artifacts/adaptive-comparison.json"))
    args = parser.parse_args()
    try:
        report = evaluate(tuple(item.strip() for item in args.strategies.split(",")), args.seeds,
                          args.max_experiments, args.max_actions, args.probe_count, args.allow_paid_api)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    print(report["provenance"])
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved complete report: {args.output}")
    if report["summary"]["episode_errors"]:
        parser.exit(1, "One or more policy arms failed; inspect the saved report.\n")


if __name__ == "__main__":
    main()
