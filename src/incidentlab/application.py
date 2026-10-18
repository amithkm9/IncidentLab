"""Single-lab orchestration, durable audit records, and guarded plan promotion."""

from __future__ import annotations

import copy
import json
import re
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from incidentlab.domain.models import Action, InvestigateRequest
from incidentlab.investigation.agents import investigate
from incidentlab.investigation.tools import Toolbox
from incidentlab.lab import Lab
from incidentlab.recovery.adaptive import run_adaptive_rehearsal
from incidentlab.recovery.proof import run_recovery_proof, seal_proof, verify_proof_integrity
from incidentlab.recovery.rehearsal import run_rehearsal
from incidentlab.storage import RecordStore, valid_investigation_record


class ConflictError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def markdown(value: object) -> str:
    # Export model/user text as text, never executable HTML or Markdown links.
    text = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]", " ", str(value))
    return re.sub(r"([\\`*_{}\[\]()<>#+!|])", r"\\\1", text)


class IncidentService:
    def __init__(self, directory: Path):
        self.store = RecordStore(directory)
        self.lab = Lab(directory / "lab")
        self._operation = threading.Lock()
        self.latest: dict | None = None
        self.latest_rehearsal: dict | None = None
        self.revision = 0
        self.lab.inject("healthy")
        self.store.event(
            self._event(
                "lab_started",
                "Lab ready",
                "A fresh healthy episode is available. Previous records remain read-only.",
            )
        )

    @contextmanager
    def operation(self):
        if not self._operation.acquire(blocking=False):
            raise ConflictError("The lab is busy. Wait for the current operation to finish.")
        try:
            yield
        finally:
            self._operation.release()

    def _event(self, kind: str, title: str, detail: str, data: dict | None = None) -> dict:
        return {
            "id": uuid.uuid4().hex,
            "created_at": now(),
            "type": kind,
            "title": title,
            "detail": detail,
            "episode_id": self.lab.episode_id,
            "data": data or {},
        }

    def status(self) -> dict:
        return {**self.lab.status(), "revision": self.revision, "busy": self._operation.locked()}

    def _observation(self) -> dict:
        return {**self.lab.status(), "revision": self.revision}

    def inject(self, scenario_id: str, seed: int) -> dict:
        with self.operation():
            self.lab.inject(scenario_id, seed)
            self.revision += 1
            self.latest = self.latest_rehearsal = None
            result = self._observation()
            self.store.event(
                self._event(
                    "scenario_injected", "Scenario injected", f"{scenario_id} · seed {seed}", result
                )
            )
            return result

    def probe(self, count: int) -> dict:
        with self.operation():
            verification = self.lab.probe(count)
            self.store.event(
                self._event(
                    "traffic_probed",
                    "Fresh traffic observed",
                    f"{count} checkout requests completed.",
                    verification,
                )
            )
            return {"verification": verification, "status": self._observation()}

    def investigate(self, request: InvestigateRequest) -> dict:
        with self.operation():
            result = investigate(Toolbox(self.lab), request.mode, request.question)
            record = {
                "id": uuid.uuid4().hex,
                "created_at": now(),
                "episode_id": self.lab.episode_id,
                "revision": self.revision,
                "scenario_id": self.lab.scenario_id,
                "question": request.question,
                "observation": self._observation(),
                "result": result.model_dump(mode="json"),
                "remediation": None,
            }
            event = self._event(
                "investigation_completed",
                result.finding.title,
                f"{request.mode} diagnosis recorded with {len(result.finding.evidence_ids)} citations.",
                {"investigation_id": record["id"], "action": result.finding.action.value},
            )
            self.store.save_many([("investigation", record)], event)
            self.latest = record
            return copy.deepcopy(record)

    def _assert_current(self, record: dict | None, identifier: str, label: str) -> dict:
        if (
            not record
            or record["id"] != identifier
            or record["episode_id"] != self.lab.episode_id
            or record["revision"] != self.revision
        ):
            raise ConflictError(
                f"This {label} is stale. Run a new {label} for the current incident."
            )
        return record

    def remediate(self, investigation_id: str, action: Action) -> dict:
        with self.operation():
            record = self._assert_current(self.latest, investigation_id, "investigation")
            if record["remediation"] is not None:
                raise ConflictError(
                    "This remediation was already attempted. Run a new investigation."
                )
            if action == Action.none or action.value != record["result"]["finding"]["action"]:
                raise ConflictError(
                    "Only the action proposed by the current finding can be applied."
                )
            self.store.event(
                self._event(
                    "remediation_requested",
                    "Single fix requested",
                    action.value,
                    {"investigation_id": investigation_id},
                )
            )
            result = self.lab.apply(action)
            self.revision += 1
            record["remediation"] = {**result, "created_at": now(), "method": "single_fix"}
            self.store.save_many(
                [("investigation", record)],
                self._recovery_event(result, "Single fix", {"investigation_id": investigation_id}),
            )
            return {**result, "status": self._observation()}

    def rehearse(
        self,
        max_actions: int = 2,
        probe_count: int = 3,
        strategy: str = "exhaustive",
        max_experiments: int = 4,
    ) -> dict:
        with self.operation():
            self.store.event(
                self._event(
                    "rehearsal_started",
                    "Fix rehearsal started",
                    "Testing isolated copies; the active lab remains unchanged.",
                    {
                        "strategy": strategy,
                        "max_experiments": max_experiments if strategy != "exhaustive" else None,
                    },
                )
            )
            try:
                if strategy == "exhaustive":
                    report = run_rehearsal(
                        self.lab, max_actions=max_actions, probe_count=probe_count
                    )
                    report["strategy"] = "exhaustive"
                else:
                    report = run_adaptive_rehearsal(
                        self.lab,
                        strategy=strategy,
                        max_experiments=max_experiments,
                        max_actions=max_actions,
                        probe_count=probe_count,
                    )
            except Exception:
                self.store.event(
                    self._event(
                        "rehearsal_failed",
                        "Rehearsal did not complete",
                        "No new plan was authorized. Retry the rehearsal.",
                    )
                )
                raise
            record = {
                "id": uuid.uuid4().hex,
                "created_at": now(),
                "episode_id": self.lab.episode_id,
                "revision": self.revision,
                "scenario_id": self.lab.scenario_id,
                "observation": self._observation(),
                "report": report,
                "promotion": None,
                "proof": None,
                "proof_history": [],
                "proof_failure": None,
            }
            records = [("rehearsal", record)]
            if self.latest and self.latest["episode_id"] == self.lab.episode_id:
                self.latest["rehearsal_id"] = record["id"]
                records.append(("investigation", self.latest))
            self.store.save_many(
                records,
                self._event(
                    "rehearsal_completed",
                    "Fix rehearsal completed",
                    f"{report['summary']['tested_plans']} plans tested; {report['summary']['successful_plans']} restored checkout in isolation.",
                    {
                        "rehearsal_id": record["id"],
                        "recommended_plan_id": report["recommended_plan_id"],
                    },
                ),
            )
            self.latest_rehearsal = record
            return copy.deepcopy(record)

    def _proof_authority(self, record: dict, proof: dict) -> dict:
        reason = "current_snapshot"
        if not verify_proof_integrity(proof):
            reason = "integrity_mismatch"
        elif record.get("proof_failure"):
            reason = "latest_proof_failed"
        elif not self.latest_rehearsal or self.latest_rehearsal["id"] != record["id"]:
            reason = "stale_rehearsal"
        elif record.get("promotion") is not None:
            reason = "already_promoted"
        elif record["episode_id"] != self.lab.episode_id or record["revision"] != self.revision:
            reason = "stale_episode_or_revision"
        elif (
            proof.get("rehearsal_id") != record["id"]
            or proof.get("episode_id") != record["episode_id"]
            or proof.get("revision") != record["revision"]
            or proof.get("plan_id") != record["report"].get("recommended_plan_id")
        ):
            reason = "binding_mismatch"
        elif proof.get("contract") != self.lab.contract.metadata():
            reason = "contract_changed"
        else:
            try:
                if (
                    proof.get("source_unchanged") is not True
                    or proof.get("source_fingerprint") != record["report"].get("source_fingerprint")
                    or proof.get("source_fingerprint") != self.lab.fingerprint()
                ):
                    reason = "source_changed"
            except Exception:
                reason = "source_unavailable"
        return {"is_current": reason == "current_snapshot", "reason": reason}

    def prove(self, rehearsal_id: str) -> dict:
        """Attach a bounded, unsigned counterfactual proof to a current rehearsal."""
        with self.operation():
            record = self._assert_current(self.latest_rehearsal, rehearsal_id, "rehearsal")
            if record.get("promotion") is not None:
                raise ConflictError(
                    "This plan was already promoted. Rehearse the current state again."
                )
            report = record["report"]
            snapshot = self.lab.snapshot()
            if report.get("source_fingerprint") != snapshot.fingerprint():
                raise ConflictError(
                    "The lab changed after rehearsal. Rehearse the current state again."
                )
            plan = next(
                (
                    trial
                    for trial in report["experiments"]
                    if trial["id"] == report["recommended_plan_id"]
                ),
                None,
            )
            if (
                not plan
                or not plan["actions"]
                or plan["verification"].get("all_healthy") is not True
                or plan["verification"].get("semantic_passed") is not True
                or plan["verification"].get("contract") != snapshot.contract.metadata()
                or report["control"]["verification"].get("all_healthy") is not False
                or not snapshot.telemetry_available
            ):
                raise ConflictError(
                    "Recovery proof requires a current successful recommendation with the current business contract."
                )
            self.store.event(
                self._event(
                    "proof_started",
                    "Recovery proof started",
                    "Testing the full plan, no-action control and action removals in isolated copies; nine requests per trial.",
                    {"rehearsal_id": rehearsal_id, "plan_id": plan["id"]},
                )
            )
            try:
                proof = run_recovery_proof(
                    snapshot,
                    list(plan["actions"]),
                    rehearsal_id=rehearsal_id,
                    plan_id=plan["id"],
                    episode_id=record["episode_id"],
                    revision=record["revision"],
                )
            except Exception:
                record["proof_failure"] = {
                    "code": "proof_failed",
                    "created_at": now(),
                    "message": "The proof did not complete. Run a new proof or rehearsal before promotion.",
                }
                self.store.save_many(
                    [("rehearsal", record)],
                    self._event(
                        "proof_failed",
                        "Recovery proof failed",
                        record["proof_failure"]["message"],
                        {"rehearsal_id": rehearsal_id},
                    ),
                )
                raise RuntimeError(
                    "Recovery proof did not complete. No promotion is authorized by this attempt."
                ) from None
            try:
                unchanged = (
                    record["episode_id"] == self.lab.episode_id
                    and record["revision"] == self.revision
                    and snapshot.fingerprint() == self.lab.fingerprint()
                )
            except Exception:
                unchanged = False
            proof["source_unchanged"] = unchanged
            if not unchanged:
                proof["summary"]["promotion_eligible"] = False
                proof["error"] = {
                    "code": "source_changed",
                    "message": "The source changed during measurement. This proof is historical evidence only.",
                }
            seal_proof(proof)
            if record.get("proof"):
                record.setdefault("proof_history", []).append(record["proof"])
            record["proof"], record["proof_failure"] = proof, None
            eligible = proof["summary"]["promotion_eligible"]
            self.store.save_many(
                [("rehearsal", record)],
                self._event(
                    "proof_completed" if eligible else "proof_failed",
                    "Recovery proof completed"
                    if eligible
                    else "Recovery proof did not support promotion",
                    f"{proof['summary']['completed_trials']}/{proof['summary']['planned_trials']} trials completed; {proof['summary']['conclusion']}.",
                    {
                        "rehearsal_id": rehearsal_id,
                        "proof_id": proof["id"],
                        "digest": proof["digest"]["value"],
                        "promotion_eligible": eligible,
                    },
                ),
            )
            return {
                "proof": copy.deepcopy(proof),
                "authority": self._proof_authority(record, proof),
            }

    def read_proof(self, rehearsal_id: str) -> dict:
        record = self.read_rehearsal(rehearsal_id)
        proof = record.get("proof")
        if not proof:
            raise FileNotFoundError("Recovery proof not found")
        return {"proof": proof, "authority": self._proof_authority(record, proof)}

    def promote(self, rehearsal_id: str, plan_id: str) -> dict:
        with self.operation():
            record = self._assert_current(self.latest_rehearsal, rehearsal_id, "rehearsal")
            if record["promotion"] is not None:
                raise ConflictError(
                    "This plan was already promoted. Rehearse the current state again."
                )
            report = record["report"]
            if report.get("source_fingerprint") != self.lab.fingerprint():
                raise ConflictError(
                    "The lab changed after rehearsal. Rehearse the current state again."
                )
            plan = next((p for p in report["experiments"] if p["id"] == plan_id), None)
            if (
                not plan
                or plan_id != report["recommended_plan_id"]
                or not plan["actions"]
                or plan["verification"].get("all_healthy") is not True
                or report["control"]["verification"].get("all_healthy") is not False
            ):
                raise ConflictError("Only the recommended successful plan can be promoted.")
            if record.get("proof_failure"):
                raise ConflictError(
                    "The latest recovery proof failed. Run a new proof or rehearsal before promotion."
                )
            if record.get("proof"):
                proof = record["proof"]
                if (
                    not self._proof_authority(record, proof)["is_current"]
                    or proof.get("actions") != plan["actions"]
                    or proof.get("summary", {}).get("promotion_eligible") is not True
                ):
                    raise ConflictError(
                        "The current recovery proof does not authorize promotion. Run a new proof or rehearsal."
                    )
            self.store.event(
                self._event(
                    "promotion_requested",
                    "Tested plan requested",
                    " + ".join(plan["actions"]),
                    {"rehearsal_id": rehearsal_id, "plan_id": plan_id},
                )
            )
            result = self.lab.apply_plan(
                [Action(action) for action in plan["actions"]], probe_count=5
            )
            self.revision += 1
            promotion = {
                **result,
                "created_at": now(),
                "method": "rehearsed_plan",
                "rehearsal_id": rehearsal_id,
                "plan_id": plan_id,
            }
            record["promotion"] = promotion
            records = [("rehearsal", record)]
            if self.latest and self.latest["episode_id"] == record["episode_id"]:
                if self.latest["revision"] == record["revision"]:
                    self.latest["remediation"] = promotion
                # Preserve a failed first attempt while recording the later outcome.
                self.latest["episode_recovery"] = promotion
                self.latest["rehearsal_id"] = rehearsal_id
                records.append(("investigation", self.latest))
            self.store.save_many(
                records,
                self._recovery_event(
                    result, "Rehearsed plan", {"rehearsal_id": rehearsal_id, "plan_id": plan_id}
                ),
            )
            return {**promotion, "status": self._observation()}

    def _recovery_event(self, result: dict, label: str, identifiers: dict) -> dict:
        verified = result["verification"].get("all_healthy") is True
        semantic = result["verification"].get("semantic_passed")
        contract = (
            "passed" if semantic is True else "failed" if semantic is False else "not recorded"
        )
        return self._event(
            "recovery_verified" if verified else "recovery_failed",
            "Recovery verified" if verified else "Checkout still failing",
            f"{label}: fresh responses {result['verification']['statuses']}; business contract {contract}.",
            {**identifiers, "verification": result["verification"]},
        )

    def read(self, investigation_id: str) -> dict:
        return self.store.read("investigation", investigation_id)

    def read_rehearsal(self, rehearsal_id: str) -> dict:
        return self.store.read("rehearsal", rehearsal_id)

    def history(self, limit: int = 50) -> dict:
        investigations = []
        for record in self.store.recent("investigation", limit):
            if not valid_investigation_record(record):
                continue
            finding = record["result"]["finding"]
            outcome = self.store.latest_recovery(record["episode_id"])
            investigations.append(
                {key: record[key] for key in ("id", "created_at", "episode_id", "revision")}
                | {
                    "scenario_id": record.get(
                        "scenario_id", record.get("observation", {}).get("scenario_id", "unknown")
                    ),
                    "mode": record["result"]["mode"],
                    "title": finding["title"],
                    "cause": finding["cause"],
                    "remediated": record.get("remediation") is not None,
                    "verified": bool(outcome and outcome["type"] == "recovery_verified"),
                    "investigation_verified": (
                        (record.get("remediation") or {}).get("verification", {}).get("all_healthy")
                        is True
                    ),
                    "verification_scope": "latest_episode_outcome",
                }
            )
        rehearsals = []
        for record in self.store.recent("rehearsal", limit):
            rehearsals.append(
                {
                    key: record[key]
                    for key in ("id", "created_at", "episode_id", "revision", "scenario_id")
                }
                | {
                    "summary": record["report"]["summary"],
                    "promoted": record["promotion"] is not None,
                    "strategy": record["report"].get("strategy", "exhaustive"),
                    "recommended_plan_id": record["report"]["recommended_plan_id"],
                    "proof_summary": record.get("proof", {}).get("summary")
                    if record.get("proof")
                    else None,
                }
            )
        return {"investigations": investigations, "rehearsals": rehearsals}

    def workspace(self) -> dict:
        return {
            "status": self.status(),
            "latest_investigation": copy.deepcopy(self.latest),
            "latest_rehearsal": copy.deepcopy(self.latest_rehearsal),
            "events": self.store.events(self.lab.episode_id),
            "history": self.history()["investigations"],
            "summary": self.store.summary(),
        }

    def postmortem(self, investigation_id: str) -> str:
        record = self.read(investigation_id)
        result, observation = record["result"], record["observation"]
        finding = result["finding"]
        lines = [
            "# IncidentLab incident report",
            "",
            f"## {markdown(finding['title'])}",
            "",
            f"- Record: {markdown(record['id'])}",
            f"- Episode: {markdown(record['episode_id'])}",
            f"- Captured: {markdown(record['created_at'])}",
            f"- Investigator: {markdown(result['mode'])}",
            f"- Observed requests: {markdown(observation['requests'])}; errors: {markdown(observation['errors'])}",
            "",
            "## Diagnosis",
            "",
            markdown(finding["explanation"]),
            "",
            f"Proposed single action: {markdown(finding['action'])}",
            "",
            "## Supporting observations",
            "",
        ]
        evidence = {e["id"]: e for trace in result["traces"] for e in trace["evidence"]}
        for identifier in finding["evidence_ids"]:
            item = evidence.get(identifier)
            if item:
                lines.extend(
                    [
                        f"### {markdown(item['id'])}",
                        "",
                        markdown(item["summary"]),
                        "",
                        *[
                            "    " + line
                            for line in json.dumps(item["data"], indent=2).splitlines()
                        ],
                        "",
                    ]
                )
        if record.get("rehearsal_id"):
            rehearsal = self.read_rehearsal(record["rehearsal_id"])
            report = rehearsal["report"]
            lines.extend(
                [
                    "## Isolated fix rehearsal",
                    "",
                    f"Strategy: {markdown(report.get('strategy', 'exhaustive'))}.",
                    "",
                    f"Tested {markdown(report['summary']['tested_plans'])} plans; recommended {markdown(report['recommended_plan_id'] or 'none')}.",
                    "",
                    "| Plan | Actions | HTTP responses | Business contract | Passed |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for plan in [report["control"], *report["experiments"]]:
                verification = plan["verification"]
                semantic = verification.get("semantic_passed")
                contract_result = (
                    "Passed"
                    if semantic is True
                    else "Failed"
                    if semantic is False
                    else "Not recorded"
                )
                lines.append(
                    f"| {markdown(plan['id'])} | {markdown(', '.join(plan['actions']) or 'No action')} | {markdown(verification['statuses'])} | {contract_result} | {markdown(verification['all_healthy'])} |"
                )
            if report["control"]["verification"].get("contract"):
                contract = report["control"]["verification"]["contract"]
                lines.extend(
                    [
                        "",
                        f"Business contract: {markdown(contract.get('id'))}, version {markdown(contract.get('version'))}, SHA-256 {markdown(contract.get('sha256'))}.",
                        "",
                        "| Trial | SKU | Expected cents | Observed cents | Violations |",
                        "| --- | --- | --- | --- | --- |",
                    ]
                )
                for plan in [report["control"], *report["experiments"]]:
                    for check in plan["verification"].get("semantic_checks", []):
                        if check.get("evaluated") and not check.get("passed"):
                            lines.append(
                                f"| {markdown(plan['id'])} | {markdown(check.get('sku'))} | {markdown(check.get('expected_total_cents'))} | {markdown(check.get('observed_total_cents'))} | {markdown(check.get('violations'))} |"
                            )
            lines.extend(["", *[markdown(note) for note in report["limitations"]], ""])
            if rehearsal.get("proof"):
                proof = rehearsal["proof"]
                lines.extend(
                    [
                        "### Counterfactual recovery proof",
                        "",
                        f"Proof: {markdown(proof['id'])}. Outcome: {markdown(proof['summary']['conclusion'])}.",
                        "",
                        f"Nine requests per trial; {markdown(proof['summary']['completed_trials'])} completed trials. "
                        "Each action was removed from the complete plan in an independent copy of the same snapshot.",
                        "",
                        "| Removed action | Comparison trial | Necessity in this measured plan |",
                        "| --- | --- | --- |",
                    ]
                )
                for item in proof["necessity"]:
                    lines.append(
                        f"| {markdown(item['action'])} | {markdown(item['trial_id'])} | {markdown(item['conclusion'])} |"
                    )
                lines.extend(
                    [
                        "",
                        f"Unsigned content SHA-256: {markdown(proof['digest']['value'])}.",
                        "",
                        "This is historical evidence for the recorded snapshot, not global minimality, a signed certificate, or current promotion authority.",
                        "",
                    ]
                )
            if report.get("decision_trace"):
                lines.extend(
                    [
                        "### Experiment decisions",
                        "",
                        "Short experiment hypotheses and measured outcomes; not private model reasoning.",
                        "",
                    ]
                )
                for decision in report["decision_trace"]:
                    lines.append(
                        f"- Step {markdown(decision['step'])}: {markdown(decision['hypothesis'])} "
                        f"Actions: {markdown(decision['actions'])}. Outcome: {markdown(decision['outcome'])}. "
                        f"Evidence: {markdown(decision.get('evidence_ids', []))}."
                    )
                lines.append("")
            if report.get("provider_usage"):
                usage = report["provider_usage"]
                lines.extend(
                    [
                        "### Planner usage",
                        "",
                        f"Model: {markdown(usage.get('model') or 'Offline policy; no model calls')}. "
                        f"API calls: {markdown(usage.get('api_calls', 0))}. "
                        f"Tokens: {markdown(usage.get('input_tokens', 0))} input / {markdown(usage.get('output_tokens', 0))} output.",
                        "",
                        markdown(usage.get("cost_note", "No cost estimate available.")),
                        "",
                    ]
                )
        remediation = record.get("remediation")
        lines.extend(["## This investigation's remediation attempt", ""])
        if remediation:
            verification = remediation["verification"]
            lines.extend(
                [
                    f"Method: {markdown(remediation.get('method', 'single_fix'))}.",
                    "",
                    f"Fresh HTTP responses: {markdown(verification['statuses'])}.",
                    "",
                    f"Business contract passed: {markdown(verification.get('semantic_passed', 'not recorded'))}.",
                    "",
                    "Recovery verified by this attempt."
                    if verification.get("all_healthy") is True
                    else "This attempt did not restore checkout. See the latest episode outcome below.",
                    "",
                ]
            )
        else:
            lines.extend(["No remediation was applied from this investigation.", ""])
        outcome = self.store.latest_recovery(record["episode_id"])
        lines.extend(["## Latest episode outcome", ""])
        if outcome:
            lines.extend(
                [
                    "Recovery verified."
                    if outcome["type"] == "recovery_verified"
                    else "Recovery not verified; checkout was still failing at the latest remediation attempt.",
                    "",
                    markdown(outcome["detail"]),
                    "",
                    f"Recorded: {markdown(outcome['created_at'])}.",
                    "",
                ]
            )
        else:
            lines.extend(["No remediation outcome recorded for this episode.", ""])
        lines.extend(["## Episode timeline", ""])
        for event in self.store.events(record["episode_id"], 1000):
            lines.append(
                f"- {markdown(event['created_at'])} — {markdown(event['title'])}: {markdown(event['detail'])}"
            )
        lines.extend(
            [
                "",
                "## Scope",
                "",
                markdown(finding["limitations"]),
                "",
                "This is a controlled local HTTP/SQLite lab, not production evidence. Citation validation checks identifiers, not semantic entailment. Offline baseline results are not Mistral performance.",
                "",
            ]
        )
        return "\n".join(lines)

    def close(self) -> None:
        self.lab.close()
