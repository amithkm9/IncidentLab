"""Counterfactual evidence for a specific measured remediation plan.

Every trial receives the same private snapshot. This module neither chooses
actions from scenario labels nor calls a model or mutates the active lab.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .lab import Lab, LabSnapshot
from .models import Action

PROOF_PROBE_COUNT = 9
MAX_PROOF_TRIALS = 4


def content_digest(artifact: dict) -> str:
    content = {key: value for key, value in artifact.items() if key != "digest"}
    encoded = json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def seal_proof(artifact: dict) -> dict:
    artifact["digest"] = {
        "algorithm": "sha256",
        "value": content_digest(artifact),
        "signed": False,
        "scope": "Canonical UTF-8 JSON of this proof, sorted keys and compact separators, excluding the digest field.",
    }
    return artifact


def verify_proof_integrity(artifact: dict) -> bool:
    try:
        digest = artifact["digest"]
        return (
            digest["algorithm"] == "sha256"
            and digest["signed"] is False
            and isinstance(digest["value"], str)
            and hmac.compare_digest(digest["value"], content_digest(artifact))
        )
    except (KeyError, TypeError, ValueError):
        return False


def _valid_measurement(verification: dict, contract: dict) -> bool:
    """Reject incomplete/contradictory observations instead of trusting a flag."""
    try:
        json.dumps(verification, allow_nan=False)
        statuses, checks = verification["statuses"], verification["semantic_checks"]
        expected = contract["expected_totals_cents"]
        if (
            verification["contract"] != contract
            or type(verification["requests"]) is not int
            or verification["requests"] != PROOF_PROBE_COUNT
            or len(statuses) != PROOF_PROBE_COUNT
            or len(checks) != PROOF_PROBE_COUNT
            or any(type(status) is not int or not 100 <= status <= 599 for status in statuses)
        ):
            return False
        counts = Counter(check["sku"] for check in checks)
        if set(counts) != set(expected) or min(counts.values()) < 3:
            return False
        passed_checks = []
        for status, check in zip(statuses, checks):
            if (
                check["http_status"] != status
                or check["evaluated"] is not (status == 200)
                or type(check["expected_total_cents"]) is not int
                or check["expected_total_cents"] != expected[check["sku"]]
                or not isinstance(check["violations"], list)
                or not all(isinstance(item, str) for item in check["violations"])
            ):
                return False
            passed = (
                status == 200
                and check["observed_sku"] == check["sku"]
                and type(check["observed_total_cents"]) is int
                and check["observed_total_cents"] == expected[check["sku"]]
                and isinstance(check["request_id"], str)
                and 1 <= len(check["request_id"]) <= 64
                and not check["violations"]
            )
            if check["passed"] is not passed:
                return False
            passed_checks.append(passed)
        http_ok, semantic_ok = all(status == 200 for status in statuses), all(passed_checks)
        return (
            verification["all_http_healthy"] is http_ok
            and verification["semantic_passed"] is semantic_ok
            and verification["all_healthy"] is (http_ok and semantic_ok)
        )
    except (KeyError, TypeError, ValueError):
        return False


def _measure(snapshot: LabSnapshot, directory: Path, actions: list[str]) -> dict:
    clone = Lab.from_snapshot(snapshot, directory)
    try:
        return (
            clone.apply_plan([Action(action) for action in actions], probe_count=PROOF_PROBE_COUNT)[
                "verification"
            ]
            if actions
            else clone.probe(PROOF_PROBE_COUNT)
        )
    finally:
        clone.close()


def _trial_specs(actions: list[str]) -> list[dict]:
    trials = [
        {"id": "control", "kind": "control", "actions": [], "removed_action": None},
        {"id": "full-plan", "kind": "full_plan", "actions": actions, "removed_action": None},
    ]
    if len(actions) == 2:
        trials.extend(
            {
                "id": f"without-{index:02d}",
                "kind": "ablation",
                "actions": [other for other in actions if other != action],
                "removed_action": action,
            }
            for index, action in enumerate(actions, start=1)
        )
    return trials


def run_recovery_proof(
    snapshot: LabSnapshot,
    actions: list[str],
    *,
    rehearsal_id: str,
    plan_id: str,
    episode_id: str,
    revision: int,
) -> dict:
    """Re-measure a full plan and leave-one-action-out alternatives, at most four trials."""
    normalized = [Action(action).value for action in actions]
    if (
        not 1 <= len(normalized) <= 2
        or len(set(normalized)) != len(normalized)
        or Action.none.value in normalized
    ):
        raise ValueError("Recovery proof requires one or two unique executable actions")
    started = time.perf_counter()
    contract = snapshot.contract.metadata()
    specs = _trial_specs(normalized)
    artifact = {
        "id": uuid.uuid4().hex,
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rehearsal_id": rehearsal_id,
        "plan_id": plan_id,
        "episode_id": episode_id,
        "revision": revision,
        "source_fingerprint": snapshot.fingerprint(),
        "contract": contract,
        "actions": normalized,
        "probe_count": PROOF_PROBE_COUNT,
        "trials": [],
        "error": None,
        "limitations": [
            "This is measured counterfactual evidence for this local snapshot and plan, not a signed certificate or a production safety guarantee.",
            "Necessity means that removing one action from this particular passing plan failed the sampled checkout contract. It does not establish global minimality or identify a unique root cause.",
            "Nine requests per trial cover each of the three declared SKUs three times. Unspecified business rules, traffic distributions and long-term reliability are not established.",
            "All trials begin from the same snapshot; fixes do not carry between trials. A one-action plan reuses the no-action control as its removal trial.",
            "The content digest detects changed content when compared with a trusted digest. It authenticates neither the author nor the claims; it is not signed.",
            "This artifact is historical evidence. Current promotion authority also requires matching episode, revision, fingerprint, contract and an unpromoted current rehearsal.",
        ],
    }
    try:
        with tempfile.TemporaryDirectory(prefix="incidentlab-proof-") as temporary:
            for spec in specs:
                trial_started = time.perf_counter()
                trial = {**copy.deepcopy(spec), "verification": None, "error": None}
                try:
                    verification = _measure(snapshot, Path(temporary) / spec["id"], spec["actions"])
                    if not _valid_measurement(verification, contract):
                        trial["error"] = {
                            "code": "invalid_verification",
                            "message": "The trial returned incomplete or contradictory contract observations.",
                        }
                    else:
                        trial["verification"] = verification
                except Exception:
                    trial["error"] = {
                        "code": "trial_failed",
                        "message": "The isolated trial did not complete. No promotion is authorized by this proof.",
                    }
                trial["elapsed_ms"] = round((time.perf_counter() - trial_started) * 1000, 2)
                artifact["trials"].append(trial)
                if trial["error"]:
                    artifact["error"] = {**trial["error"], "trial_id": spec["id"]}
                    break
    except Exception:
        artifact["error"] = {
            "code": "proof_failed",
            "message": "The proof could not complete its isolated experiments. No promotion is authorized.",
        }
    measured = {
        trial["id"]: trial for trial in artifact["trials"] if trial["verification"] is not None
    }
    full_passed = measured.get("full-plan", {}).get("verification", {}).get("all_healthy")
    control_passed = measured.get("control", {}).get("verification", {}).get("all_healthy")
    necessity = []
    for index, action in enumerate(normalized, start=1):
        trial_id = "control" if len(normalized) == 1 else f"without-{index:02d}"
        ablation_passed = measured.get(trial_id, {}).get("verification", {}).get("all_healthy")
        necessary = (
            not ablation_passed if full_passed is True and ablation_passed is not None else None
        )
        necessity.append(
            {
                "action": action,
                "trial_id": trial_id,
                "necessary": necessary,
                "conclusion": "inconclusive"
                if necessary is None
                else "necessary_in_measured_plan"
                if necessary
                else "not_necessary_in_measured_plan",
            }
        )
    all_necessary = (
        all(item["necessary"] for item in necessity)
        if all(item["necessary"] is not None for item in necessity)
        else None
    )
    complete = len(measured) == len(specs) and artifact["error"] is None
    eligible = complete and full_passed is True and control_passed is False
    conclusion = (
        "inconclusive"
        if not complete
        else "full_plan_failed"
        if full_passed is not True
        else "control_healthy"
        if control_passed is True
        else "supported"
        if all_necessary
        else "redundant_action"
    )
    artifact.update(
        necessity=necessity,
        summary={
            "planned_trials": len(specs),
            "completed_trials": len(measured),
            "full_plan_passed": full_passed,
            "control_failed": not control_passed if control_passed is not None else None,
            "all_actions_necessary": all_necessary,
            "conclusion": conclusion,
            "promotion_eligible": eligible,
        },
        budget={
            "max_trials": MAX_PROOF_TRIALS,
            "planned_trials": len(specs),
            "started_trials": len(artifact["trials"]),
            "completed_trials": len(measured),
            "probe_count_per_trial": PROOF_PROBE_COUNT,
            "max_requests": MAX_PROOF_TRIALS * PROOF_PROBE_COUNT,
            "planned_requests": len(specs) * PROOF_PROBE_COUNT,
            "completed_trial_requests": len(measured) * PROOF_PROBE_COUNT,
            "provider_calls": 0,
            "accounting_note": "Completed-request count covers completed trials; failed trials may have issued partial traffic within the overall request budget.",
        },
        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return seal_proof(artifact)
