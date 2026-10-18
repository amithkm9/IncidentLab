"""Measure false HTTP-only recovery decisions and contract-verified remediation.

Acceptance gates score the same saved responses, not separate traffic. Policy
recovery is a separate comparison requiring five fresh verification requests.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import tempfile
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from incidentlab import __version__
from incidentlab.domain.contracts import CHECKOUT_CONTRACT
from incidentlab.domain.models import Action
from incidentlab.evaluation import adaptive as policy_evaluation
from incidentlab.lab import Lab
from incidentlab.lab.scenarios import SCENARIO_BY_ID
from incidentlab.recovery.rehearsal import measure_plan

MANIFEST = {
    "name": "incidentlab-semantic-recovery-v1",
    "contract": CHECKOUT_CONTRACT.metadata(),
    "scenarios": [
        {
            "id": "silent_price_drift",
            "expected_actions": [Action.rollback.value],
            "silent_corruption": True,
        },
        {
            "id": "route_and_price_drift",
            "expected_actions": [Action.route.value, Action.rollback.value],
            "silent_corruption": True,
        },
        {"id": "bad_release", "expected_actions": [Action.rollback.value]},
        {
            "id": "route_and_release",
            "expected_actions": [Action.route.value, Action.rollback.value],
        },
        {"id": "healthy", "expected_actions": [], "control": "healthy"},
        {"id": "telemetry_gap", "expected_actions": [], "control": "telemetry_gap"},
    ],
    "splits": {"smoke": [42], "test": [11, 23, 37]},
    "acceptance_plans": [
        {"id": "control", "actions": []},
        {"id": "route", "actions": [Action.route.value]},
        {"id": "rollback", "actions": [Action.rollback.value]},
        {"id": "route-and-rollback", "actions": [Action.route.value, Action.rollback.value]},
    ],
    "final_verification_probe_count": 5,
}


def _acceptance(verification: dict, count: int) -> dict:
    """Check recorded response facts against the declared immutable contract.

    A missing or contradictory contract record is an error, not evidence of a
    semantic bug. No scenario label or expected remediation participates here.
    """
    statuses = verification.get("statuses")
    checks = verification.get("semantic_checks")
    contract = verification.get("contract") or {}
    expected = contract.get("expected_totals_cents")
    if (
        verification.get("requests") != count
        or not isinstance(statuses, list)
        or len(statuses) != count
        or not isinstance(checks, list)
        or len(checks) != count
        or contract != MANIFEST["contract"]
        or not isinstance(expected, dict)
        or not expected
        or any(not isinstance(value, int) or isinstance(value, bool) for value in expected.values())
        or not isinstance(contract.get("sha256"), str)
        or len(contract["sha256"]) != 64
    ):
        raise ValueError("Incomplete semantic verification record")
    http_passed = statuses == [200] * count
    verdicts = []
    for status, check in zip(statuses, checks):
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("violations"), list)
            or check.get("http_status") != status
            or check.get("sku") not in expected
            or check.get("expected_total_cents") != expected[check["sku"]]
        ):
            raise ValueError("Semantic check does not match its response or contract")
        if check.get("evaluated") is not (status == 200):
            raise ValueError("Semantic evaluation flag contradicts HTTP status")
        observed = check.get("observed_total_cents")
        request_id = check.get("request_id")
        passed = (
            status == 200
            and check.get("observed_sku") == check["sku"]
            and isinstance(observed, int)
            and not isinstance(observed, bool)
            and observed == expected[check["sku"]]
            and isinstance(request_id, str)
            and 1 <= len(request_id) <= 64
            and not check["violations"]
        )
        if check.get("passed") is not passed or (not passed and not check["violations"]):
            raise ValueError("Semantic verdict contradicts recorded response facts")
        verdicts.append(passed)
    semantic_passed = all(verdicts)
    if (
        verification.get("all_http_healthy") is not http_passed
        or verification.get("semantic_passed") is not semantic_passed
        or verification.get("all_healthy") is not (http_passed and semantic_passed)
    ):
        raise ValueError("Aggregate verification flags contradict recorded checks")
    return {
        "status_only_accepted": http_passed,
        "semantic_accepted": semantic_passed,
        "status_only_false_recovery": http_passed and not semantic_passed,
    }


def _paired_trials(directory: Path, scenario_id: str, seed: int, probe_count: int) -> dict:
    trials = [
        {
            **copy.deepcopy(plan),
            "completed": False,
            "verification": None,
            "status_only_accepted": False,
            "semantic_accepted": False,
            "status_only_false_recovery": False,
            "error": None,
        }
        for plan in MANIFEST["acceptance_plans"]
    ]
    result = {"source_fingerprint": None, "source_unchanged": None, "trials": trials, "error": None}
    source = None
    try:
        source = Lab(directory / "source")
        result["before"] = source.inject(scenario_id, seed)
        snapshot = source.snapshot()
        result["source_fingerprint"] = snapshot.fingerprint()
        for trial in trials:
            try:
                measured = measure_plan(
                    snapshot,
                    directory / trial["id"],
                    trial["id"],
                    tuple(Action(action) for action in trial["actions"]),
                    probe_count,
                )
                trial.update(measured)
                trial.update(_acceptance(trial["verification"], probe_count))
                trial["completed"] = True
            except Exception as exc:
                trial["error"] = (
                    f"{type(exc).__name__}: paired measurement or contract validation failed"
                )
        result["source_unchanged"] = source.fingerprint() == result["source_fingerprint"]
        if not result["source_unchanged"]:
            result["error"] = "The source changed during isolated acceptance measurements"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: paired acceptance setup failed"
    finally:
        if source is not None:
            try:
                source.close()
            except Exception as exc:
                result["error"] = f"{type(exc).__name__}: source cleanup failed"
    return result


def _policy_arm(
    directory: Path,
    strategy: str,
    scenario_id: str,
    seed: int,
    max_experiments: int,
    max_actions: int,
    probe_count: int,
    planner=None,
) -> dict:
    outcome = policy_evaluation._run_arm(
        directory, strategy, scenario_id, seed, max_experiments, max_actions, probe_count, planner
    )
    outcome["status_only_recovered"] = False
    if outcome["completed"]:
        try:
            acceptance = _acceptance(
                outcome["verification"], MANIFEST["final_verification_probe_count"]
            )
            outcome["final_acceptance"] = acceptance
            outcome["status_only_recovered"] = bool(
                outcome["actions"] and acceptance["status_only_accepted"]
            )
            outcome["recovered"] = bool(outcome["actions"] and acceptance["semantic_accepted"])
        except (ValueError, TypeError, KeyError):
            outcome.update(
                completed=False,
                recovered=False,
                no_action=False,
                error="Final verification did not contain consistent contract evidence",
            )
    return outcome


def summarize(episodes: list[dict], strategies: tuple[str, ...] = ("adaptive",)) -> dict:
    trials = [trial for episode in episodes for trial in episode["paired_acceptance"]["trials"]]
    completed = [
        trial
        for episode in episodes
        if episode["paired_acceptance"]["source_unchanged"] is True
        for trial in episode["paired_acceptance"]["trials"]
        if trial["completed"]
    ]
    status_accepts = sum(trial["status_only_accepted"] for trial in completed)
    semantic_accepts = sum(trial["semantic_accepted"] for trial in completed)
    false_accepts = sum(trial["status_only_false_recovery"] for trial in completed)

    def rate(numerator, denominator):
        return round(numerator / denominator, 4) if denominator else None

    policies = policy_evaluation.summarize(episodes, strategies)
    examples = [
        {
            "case_id": episode["case_id"],
            "trial_id": trial["id"],
            "actions": trial["actions"],
            "statuses": trial["verification"]["statuses"],
            "violating_checks": [
                check for check in trial["verification"]["semantic_checks"] if not check["passed"]
            ],
        }
        for episode in episodes
        if episode["paired_acceptance"]["source_unchanged"] is True
        for trial in episode["paired_acceptance"]["trials"]
        if trial["completed"] and trial["status_only_false_recovery"]
    ]
    return {
        "episodes": len(episodes),
        "episode_errors": sum(
            bool(
                episode["paired_acceptance"]["error"]
                or any(not trial["completed"] for trial in episode["paired_acceptance"]["trials"])
                or any(episode["strategies"][strategy]["error"] for strategy in strategies)
            )
            for episode in episodes
        ),
        "paired_acceptance": {
            "attempted_trials": len(trials),
            "completed_trials": len(completed),
            "failed_or_unverifiable_trials": len(trials) - len(completed),
            "status_only_acceptances": status_accepts,
            "semantic_acceptances": semantic_accepts,
            "status_only_acceptance_rate": rate(status_accepts, len(trials)),
            "semantic_acceptance_rate": rate(semantic_accepts, len(trials)),
            "status_only_false_recoveries": false_accepts,
            "false_recovery_fraction_of_status_acceptances": rate(false_accepts, status_accepts),
            "recorded_probe_requests": sum(
                (trial.get("verification") or {}).get("requests", 0) for trial in trials
            ),
            "counterexample_scope": "False recovery means HTTP-only acceptance of the exact same recorded responses that violate the declared checkout contract. It is not an independent test of contract correctness.",
            "denominator_scope": "Acceptance rates include every planned trial; failed or unverifiable trials are not accepted. The false-recovery fraction is conditional on completed HTTP-only acceptances.",
        },
        "false_recovery_examples": examples,
        "policy_recovery": policies,
    }


def evaluate(
    split: str = "smoke",
    strategies=("adaptive",),
    max_experiments: int = 4,
    max_actions: int = 2,
    probe_count: int = 3,
    allow_paid_api: bool = False,
    planner=None,
) -> dict:
    strategies = tuple(strategies)
    if split not in MANIFEST["splits"]:
        raise ValueError("Unknown semantic evaluation split")
    if any(strategy not in {"adaptive", "mistral"} for strategy in strategies):
        raise ValueError("Semantic policy strategies must be adaptive or mistral")
    seeds = tuple(MANIFEST["splits"][split])
    policy_evaluation._validate_options(
        strategies, seeds, max_experiments, max_actions, probe_count, allow_paid_api
    )
    for case in MANIFEST["scenarios"]:
        if set(case["expected_actions"]) != {
            action.value for action in SCENARIO_BY_ID[case["id"]].expected_actions
        }:
            raise ValueError(f"Frozen action labels drifted for {case['id']}")
    manifest = {
        **copy.deepcopy(MANIFEST),
        "split": split,
        "seeds": list(seeds),
        "strategies": list(strategies),
        "max_experiments": max_experiments,
        "max_actions": max_actions,
        "probe_count": probe_count,
    }
    started_at, started = datetime.now(timezone.utc).isoformat(), time.perf_counter()
    episodes = []
    with tempfile.TemporaryDirectory(prefix="incidentlab-semantic-eval-") as directory:
        for case in MANIFEST["scenarios"]:
            for seed in seeds:
                case_id = f"{case['id']}-{seed}"
                episode = {
                    "case_id": case_id,
                    "scenario_id": case["id"],
                    "seed": seed,
                    "expected_actions": list(case["expected_actions"]),
                    "control": case.get("control"),
                    "silent_corruption": case.get("silent_corruption", False),
                    "strategies": {},
                }
                episode["paired_acceptance"] = _paired_trials(
                    Path(directory) / case_id / "paired", case["id"], seed, probe_count
                )
                for strategy in strategies:
                    episode["strategies"][strategy] = _policy_arm(
                        Path(directory) / case_id / strategy,
                        strategy,
                        case["id"],
                        seed,
                        max_experiments,
                        max_actions,
                        probe_count,
                        planner,
                    )
                episodes.append(episode)
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": 1,
        "project_version": __version__,
        "split": split,
        "manifest": manifest,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "provenance": (
            "Paired contract-acceptance comparison with a separately identified live Mistral recovery arm."
            if "mistral" in strategies
            else "Offline contract-acceptance and deterministic policy comparison; NOT Mistral model performance."
        ),
        "model_strategy_selected": "mistral" in strategies,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": {name: version(name) for name in ("httpx", "pydantic", "fastapi")},
        },
        "limitations": [
            "Six known scenario families and repeated seeds are regression coverage, not independent production incidents or unseen-fault generalization.",
            "Both acceptance gates inspect identical saved response facts; the comparison does not run an HTTP-only planner or claim equal reasoning quality.",
            "The four fixed acceptance plans are declared in advance, not selected from ground truth or substituted for policy recommendations.",
            "The contract checks known SKU identity and expected price cents. It does not establish all business semantics, absence of side effects, or production safety.",
            "Policy recovery is separate from paired acceptance and requires five fresh contract-verified checkout requests after its own selected plan.",
            "Known expected remediation labels are used only for denominators and drift checks, never passed to policies or used to repair their choices.",
            "Failures stay in policy quality denominators; partial provider usage may undercount billable calls. Mistral requires explicit paid-API authorization.",
        ],
        "summary": summarize(episodes, strategies),
        "episodes": episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=tuple(MANIFEST["splits"]), default="smoke")
    parser.add_argument("--strategies", default="adaptive", help="Comma-separated adaptive,mistral")
    parser.add_argument("--max-experiments", type=int, default=4)
    parser.add_argument("--max-actions", type=int, choices=(1, 2), default=2)
    parser.add_argument("--probe-count", type=int, default=3)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(
            args.split,
            tuple(item.strip() for item in args.strategies.split(",")),
            args.max_experiments,
            args.max_actions,
            args.probe_count,
            args.allow_paid_api,
        )
        output = args.output or Path("artifacts") / f"semantic-{args.split}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    print(report["provenance"])
    print(json.dumps(report["summary"], indent=2))
    print(f"Saved complete report: {output}")
    if report["summary"]["episode_errors"]:
        parser.exit(1, "One or more semantic comparison arms failed; inspect the saved report.\n")


if __name__ == "__main__":
    main()
