import { proofPath } from "../api/paths";
import type { ProofTrial, RehearsalRecord } from "../domain";
import { $, el, text } from "../dom";
import { state, isCurrent, recommendedPlan } from "../state";
import { actionLabel, duration } from "../format";
import { httpHealthy, recoveryVerified, semanticState } from "../verification";
import { proofConclusion } from "../recovery";
import { appendContractDetails } from "./contracts";

function trialCard(trial: ProofTrial): HTMLElement {
  const verification = trial.verification;
  const passed = recoveryVerified(verification);
  const card = el(
    "article",
    `proof-trial${trial.error ? " incomplete" : passed ? " passed" : " failed"}`,
  );
  const heading = el("div", "proof-trial-heading");
  const title =
    trial.kind === "control"
      ? "Without any fixes"
      : trial.kind === "full_plan"
        ? "With the full plan"
        : `Without: ${actionLabel(trial.removed_action ? [trial.removed_action] : [])}`;
  heading.append(
    el("h4", "", title),
    el(
      "span",
      `result-pill${passed ? "" : " failed"}`,
      trial.error || !verification
        ? "Incomplete"
        : passed
          ? "Verified"
          : "Failed",
    ),
  );
  card.append(
    heading,
    el("p", "proof-trial-actions", actionLabel(trial.actions)),
  );
  if (verification) {
    const http = el("div", "proof-http");
    http.append(el("span", "", "HTTP responses"));
    const codes = el("div", "http-codes");
    for (const code of verification.statuses)
      codes.append(
        el("span", `http-code${code === 200 ? "" : " failed"}`, code),
      );
    http.append(codes);
    card.append(http);
    if (
      httpHealthy(verification) &&
      semanticState(verification).known &&
      !semanticState(verification).passed
    )
      card.append(el("strong", "false-recovery-label", "HTTP 200 ≠ recovery"));
    appendContractDetails(card, verification);
  }
  if (trial.error)
    card.append(
      el(
        "p",
        "proof-trial-error",
        typeof trial.error === "string"
          ? trial.error
          : trial.error.message || "This trial did not complete.",
      ),
    );
  card.append(
    el(
      "p",
      "proof-trial-meta",
      `${verification?.requests ?? 0} measured responses · ${duration(trial.elapsed_ms)}`,
    ),
  );
  return card;
}

export function renderProof(record: RehearsalRecord | null): void {
  const proof = record?.proof;
  const canMeasure =
    !!record &&
    !state.archive &&
    isCurrent(record) &&
    !record.promotion &&
    recoveryVerified(recommendedPlan()?.verification);
  $("recovery-proof").hidden = !proof && !record?.proof_failure && !canMeasure;
  $("proof-intro").hidden = !canMeasure;
  $("proof-result").hidden = !proof;
  $("proof-failure").hidden = !record?.proof_failure;
  text("proof-failure", record?.proof_failure?.message || "");
  $("proof-trials").replaceChildren();
  $("proof-necessity").replaceChildren();
  $("proof-summary").replaceChildren();
  text(
    "prove",
    proof ? "Run the proof again →" : "Explain why each fix is needed →",
  );
  if (!record || !proof) return;
  const result = proofConclusion(proof);
  $("proof-summary").className =
    `proof-summary${proof.summary.conclusion === "supported" && !record.proof_failure ? " supported" : " caution"}`;
  $("proof-summary").append(
    el("strong", "", result.title),
    el("p", "", result.description),
  );
  if (proof.error)
    $("proof-summary").append(
      el("p", "proof-trial-error", proof.error.message),
    );
  text(
    "proof-context",
    record.proof_failure
      ? "A later proof attempt failed. The artifact below is historical evidence; it does not authorize promotion."
      : state.archive || !isCurrent(record) || record.promotion
        ? "Saved proof · read-only. These measurements describe the recorded snapshot; they do not authorize a new change."
        : proof.source_unchanged !== true
          ? "The source snapshot changed during measurement. This proof is historical evidence only."
          : `Measured on this snapshot · ${proof.summary.completed_trials} of ${proof.summary.planned_trials} trials completed. The server rechecks current authority before any promotion.`,
  );
  $("proof-trials").append(...proof.trials.map(trialCard));
  for (const item of proof.necessity) {
    const row = el(
      "div",
      `necessity-row${item.necessary === true ? " supported" : ""}`,
    );
    const trial = proof.trials.find(
      (candidate) => candidate.id === item.trial_id,
    );
    row.append(
      el("strong", "", actionLabel([item.action])),
      el(
        "span",
        "",
        item.necessary === true
          ? "Needed in this measured plan"
          : item.necessary === false
            ? "Removal also passed"
            : "Necessity not established",
      ),
    );
    if (trial?.kind === "control")
      row.append(
        el(
          "small",
          "",
          "Single-action plan: removing this action reuses the no-change control.",
        ),
      );
    $("proof-necessity").append(row);
  }
  text(
    "proof-budget",
    `${proof.budget.completed_trial_requests} responses in completed trials; ${proof.budget.planned_requests} planned; at most ${proof.budget.max_requests} requests. ${proof.budget.provider_calls} provider calls. ${proof.budget.accounting_note}`,
  );
  $("proof-limitations").replaceChildren(
    ...proof.limitations.map((limitation) => el("li", "", limitation)),
  );
  text("proof-digest", proof.digest.value);
  $("proof-download").href = proofPath(record.id);
  $("proof-download").download = `incidentlab-proof-${proof.id}.json`;
}
