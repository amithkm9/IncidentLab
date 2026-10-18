"""Measure bounded remediation plans against isolated copies of actual state.

This is exhaustive intervention testing in a disposable simulator, not a model
prediction or a proof that a plan is safe in a production environment.
"""

from __future__ import annotations

import itertools
import tempfile
import time
from pathlib import Path

from incidentlab.domain.models import Action
from incidentlab.lab import Lab, LabSnapshot

EXECUTABLE_ACTIONS = tuple(action for action in Action if action != Action.none)


def measure_plan(
    snapshot: LabSnapshot,
    directory: Path,
    plan_id: str,
    actions: tuple[Action, ...],
    probe_count: int,
) -> dict:
    """Measure one plan on a fresh clone and release its HTTP resources."""
    started = time.perf_counter()
    clone = Lab.from_snapshot(snapshot, directory)
    try:
        verification = (
            clone.apply_plan(actions, probe_count=probe_count)["verification"]
            if actions
            else clone.probe(probe_count)
        )
        return {
            "id": plan_id,
            "actions": [action.value for action in actions],
            "verification": verification,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    finally:
        clone.close()


def run_rehearsal(lab: Lab, max_actions: int = 2, probe_count: int = 3) -> dict:
    """Compare a no-change control with every allowed one/two-action plan.

    All trials start from the same snapshot. A plan is eligible only when every
    fresh request returns HTTP 200 and passes the declared checkout contract;
    deterministic ordering breaks equal-size
    ties. Neither scenario IDs nor expected fault labels enter the search.
    """
    if (
        not isinstance(max_actions, int)
        or isinstance(max_actions, bool)
        or max_actions not in (1, 2)
    ):
        raise ValueError("Rehearsal supports one or two actions per plan")
    if (
        not isinstance(probe_count, int)
        or isinstance(probe_count, bool)
        or not 1 <= probe_count <= 20
    ):
        raise ValueError("Probe count must be between 1 and 20")
    started = time.perf_counter()
    snapshot = lab.snapshot()
    experiments = []
    with tempfile.TemporaryDirectory(prefix="incidentlab-rehearsal-") as temporary:
        directory = Path(temporary)
        control = measure_plan(snapshot, directory / "control", "control", (), probe_count)
        if snapshot.telemetry_available:
            plans = itertools.chain.from_iterable(
                itertools.combinations(EXECUTABLE_ACTIONS, size)
                for size in range(1, max_actions + 1)
            )
            for index, actions in enumerate(plans, start=1):
                plan_id = f"plan-{index:02d}"
                experiments.append(
                    measure_plan(snapshot, directory / plan_id, plan_id, actions, probe_count)
                )
    successes = [trial for trial in experiments if trial["verification"]["all_healthy"]]
    control_healthy = control["verification"]["all_healthy"]
    recommended = (
        successes[0] if successes and not control_healthy and snapshot.telemetry_available else None
    )
    abstention = (
        "missing_telemetry"
        if not snapshot.telemetry_available
        else "control_healthy"
        if control_healthy
        else "no_successful_plan"
        if recommended is None
        else None
    )
    return {
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "source_fingerprint": snapshot.fingerprint(),
        "probe_count": probe_count,
        "max_actions": max_actions,
        "control": control,
        "experiments": experiments,
        "recommended_plan_id": recommended["id"] if recommended else None,
        "summary": {
            "tested_plans": len(experiments),
            "successful_plans": len(successes),
            "minimal_action_count": len(recommended["actions"]) if recommended else None,
            "control_healthy": control_healthy,
            "telemetry_available": snapshot.telemetry_available,
            "abstention_reason": abstention,
        },
        "limitations": [
            "Tests a snapshot of a disposable HTTP/SQLite lab; it does not simulate a production fleet.",
            "Success requires HTTP 200 and the declared checkout contract for every sampled response; untested business rules and long-term reliability are not established.",
            "Search is exhaustive only over the five allowlisted actions and the configured one/two-action budget.",
            "Plans are ranked by fewest actions, with a fixed tie-break order; latency is measured but not used as a safety or cost score.",
            "A healthy control or unavailable diagnostic telemetry prevents recommending a change.",
        ],
    }
