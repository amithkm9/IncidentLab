import { artifactPath } from "../api/paths";
import type { RehearsalRecord, RehearsalReport } from "../domain";
import { $, el, text, required } from "../dom";
import { state, recommendedPlan, isCurrent } from "../state";
import {
  strategyNames,
  stopReasonNames,
  rehearsalFailures,
} from "../constants";
import { actionLabel, duration, number } from "../format";
import {
  semanticState,
  providerFailureLabel,
  httpHealthy,
} from "../verification";
import { renderProof } from "./proof";
import { proofBlocksPromotion } from "../recovery";
import { appendContractDetails, verificationNotice } from "./contracts";

export function renderRehearsal(record: RehearsalRecord | null) {
  state.rehearsal = record;
  const report = record?.report;
  renderProof(record);
  $("rehearsal-empty").hidden = !!report;
  $("rehearsal-result").hidden = !report;
  $("rehearsal-dot").hidden = !report;
  $("promotion-result").hidden = true;
  $("rehearsal-run-meta").replaceChildren();
  $("decision-trail").replaceChildren();
  $("decision-trail-section").hidden = true;
  if (!record || !report) return;
  const plan = recommendedPlan();
  const controlHealthy = report.control.verification.all_healthy;
  const controlSemantic = semanticState(report.control?.verification);
  const planSemantic = semanticState(plan?.verification);
  const redundant = record.proof?.summary.conclusion === "redundant_action";
  const missingTelemetry =
    report.summary?.abstention_reason === "missing_telemetry";
  const planningFailure = rehearsalFailures[report.budget?.stop_reason ?? ""];
  const recommendation = $("recommendation");
  recommendation.className = `recommendation${!plan && !controlHealthy ? " warning" : ""}`;
  recommendation.replaceChildren(
    el("span", "recommendation-icon", plan || controlHealthy ? "✓" : "!"),
  );
  const message = el("div");
  message.append(
    el(
      "h3",
      "",
      planningFailure
        ? planningFailure.title
        : missingTelemetry
          ? "Rehearsal withheld: diagnostic telemetry unavailable."
          : controlHealthy
            ? controlSemantic.known
              ? "The control passed availability and business checks."
              : "The control passed the recorded HTTP checks."
            : plan
              ? planSemantic.passed
                ? `${plan.actions.length === 1 ? "One action" : `${plan.actions.length} actions`} recovered this snapshot.`
                : "A plan passed the recorded HTTP checks."
              : "No tested plan recovered checkout.",
    ),
  );
  message.append(
    el(
      "p",
      "",
      planningFailure
        ? planningFailure.description
        : missingTelemetry
          ? "No candidate fixes were tested or authorized. Restore diagnostic evidence before selecting a recovery action."
          : controlHealthy
            ? controlSemantic.known
              ? "Fresh requests matched the expected price and SKU without changes. No remediation is recommended."
              : "Business correctness was not recorded in this older report. Run a new rehearsal to check response contracts."
            : plan
              ? planSemantic.known
                ? `${actionLabel(plan.actions)}. Fresh responses passed HTTP, price, and SKU checks. ${redundant ? "The recovery proof found that a smaller variant also passes; inspect the omission results." : "This is the smallest passing tested plan in the rehearsal."}`
                : `${actionLabel(plan.actions)}. Business correctness was not recorded. Run a new rehearsal before promoting a change.`
              : "Review the evidence and experiment outcomes. A larger plan or a different intervention may be needed.",
    ),
  );
  const providerDetail = providerFailureLabel(report.error?.provider_failure);
  if (providerDetail)
    message.append(el("p", "provider-failure-detail", providerDetail));
  recommendation.append(message);
  text(
    "plans-tested",
    number(report.summary?.tested_plans ?? report.experiments?.length),
  );
  text(
    "plans-passed",
    number(
      report.summary?.successful_plans ??
        report.experiments?.filter((item) => item.verification.all_healthy)
          .length,
    ),
  );
  text("minimal-actions", controlHealthy ? "0" : (plan?.actions.length ?? "—"));
  text("rehearsal-duration", duration(report.elapsed_ms));
  renderRehearsalRun(report);
  renderExperiments();
  $("promotion").hidden = !plan || !!record.promotion || state.archive;
  const promotionDescription = required($("promotion").querySelector("p"));
  promotionDescription.textContent = proofBlocksPromotion(record)
    ? "The recovery proof does not authorize promotion. Review its results and run a new proof or rehearsal before applying a change."
    : !planSemantic.known
      ? "This older report has no business contract checks. Run a new rehearsal before promoting a plan."
      : isCurrent(record)
        ? redundant
          ? "A smaller variant also passed the proof. Review those results before applying this rehearsed plan and verifying fresh traffic."
          : "Apply the smallest passing tested plan, then verify fresh HTTP responses, prices, and product IDs in the active lab."
        : "The lab has changed since this experiment. Run a new rehearsal before promoting a plan.";
  $("rehearsal-limitations").replaceChildren(
    ...(report.limitations || []).map((limitation) => el("li", "", limitation)),
  );
  $("rehearsal-download").href = artifactPath("rehearsals", record.id);
  $("rehearsal-download").download = `incidentlab-rehearsal-${record.id}.json`;
  if (record.promotion)
    verificationNotice(
      $("promotion-result"),
      record.promotion,
      "Tested plan applied. Recovery verified.",
    );
}

function renderRehearsalRun(report: RehearsalReport) {
  const strategy = report.strategy || "exhaustive";
  const meta = $("rehearsal-run-meta");
  const heading = el("div", "rehearsal-run-heading");
  heading.append(
    el("strong", "", strategyNames[strategy] || strategy.replaceAll("_", " ")),
  );
  const budget = report.budget;
  if (budget) {
    const count = budget.used_experiments ?? report.summary?.tested_plans ?? 0;
    const cap = budget.max_experiments;
    heading.append(
      el(
        "span",
        "tag",
        `${number(count)}${cap != null ? ` / ${number(cap)}` : ""} EXPERIMENTS`,
      ),
    );
  }
  meta.append(heading);
  if (budget?.stop_reason)
    meta.append(
      el(
        "p",
        "",
        `Stopped: ${stopReasonNames[budget.stop_reason] || budget.stop_reason.replaceAll("_", " ")}.`,
      ),
    );
  const usage = report.provider_usage;
  if (strategy === "mistral" || usage?.model || (usage?.api_calls ?? 0) > 0) {
    if (usage) {
      const parts = [usage.model || "Model not recorded"];
      if (usage.api_calls != null)
        parts.push(`${number(usage.api_calls)} API calls`);
      if (usage.input_tokens != null && usage.output_tokens != null)
        parts.push(
          `${number(usage.input_tokens)} input / ${number(usage.output_tokens)} output tokens`,
        );
      meta.append(el("p", "", parts.join(" · ")));
      const cost = usage.estimated_cost_usd;
      const hasCost = typeof cost === "number" && Number.isFinite(cost);
      meta.append(
        el(
          "p",
          "",
          `${hasCost ? `$${cost.toFixed(6)} estimated API cost` : "API cost not estimated"}${usage.cost_note ? ` · ${usage.cost_note}` : ""}`,
        ),
      );
    } else
      meta.append(
        el("p", "", "Provider usage was not recorded in this saved report."),
      );
  } else
    meta.append(
      el(
        "p",
        "",
        strategy === "adaptive"
          ? "Offline policy · no model API calls. Only the selected candidates were tested."
          : "Exhaustive comparison within the selected plan size · no model API calls.",
      ),
    );
  const decisions = Array.isArray(report.decision_trace)
    ? report.decision_trace
    : [];
  $("decision-trail-section").hidden = !decisions.length;
  text(
    "decision-count",
    `${decisions.length} ${decisions.length === 1 ? "STEP" : "STEPS"}`,
  );
  $("decision-trail").replaceChildren(
    ...decisions.map((decision, index) => {
      const item = el("li", "decision-item");
      const top = el("div", "decision-item-heading");
      const step = decision.step ?? index + 1;
      top.append(
        el("span", "decision-step", String(step)),
        el(
          "strong",
          "",
          decision.actions?.length
            ? actionLabel(decision.actions)
            : "Planning stopped",
        ),
      );
      const outcome =
        typeof decision.outcome === "string"
          ? decision.outcome.replaceAll("_", " ")
          : "Outcome not recorded";
      top.append(el("span", "tag", outcome));
      item.append(top);
      if (decision.hypothesis)
        item.append(el("p", "decision-hypothesis", decision.hypothesis));
      const statuses = Array.isArray(decision.statuses)
        ? decision.statuses
        : [];
      if (statuses.length) {
        const observed = el("div", "decision-observations");
        observed.append(el("span", "", "Observed HTTP"));
        const codes = el("div", "http-codes");
        for (const code of statuses) {
          const codeNode = el(
            "span",
            `http-code${code >= 400 ? " failed" : ""}`,
            String(code),
          );
          codeNode.title = `HTTP ${code}`;
          codes.append(codeNode);
        }
        observed.append(codes);
        item.append(observed);
        appendContractDetails(item, decision);
      }
      if (decision.evidence_ids?.length) {
        const citations = el("div", "decision-citations");
        citations.append(el("span", "", "Input evidence"));
        for (const id of decision.evidence_ids)
          citations.append(el("code", "", id));
        item.append(citations);
      }
      return item;
    }),
  );
}

export function renderExperiments() {
  const report = state.rehearsal?.report;
  if (!report) return;
  const plan = recommendedPlan();
  const all = [
    report.control,
    ...(plan ? [plan] : []),
    ...(report.experiments || []).filter((item) => item.id !== plan?.id),
  ];
  const filter = $("plan-filter").value;
  const experiments = all.filter(
    (item) =>
      filter === "all" ||
      (filter === "passed") === !!item.verification?.all_healthy,
  );
  text(
    "experiment-count",
    `${experiments.length} shown · ${all.length} total with control`,
  );
  $("plans-empty").hidden = !!experiments.length;
  $("experiments").replaceChildren(
    ...experiments.map((experiment) => {
      const recommended = experiment.id === report.recommended_plan_id;
      const row = el("tr", recommended ? "recommended" : "");
      const labelCell = el("td");
      labelCell.append(
        el("span", "plan-label", actionLabel(experiment.actions)),
      );
      if (recommended)
        labelCell.append(
          el(
            "small",
            "",
            state.rehearsal?.proof?.summary.conclusion === "redundant_action"
              ? "RECOMMENDED IN REHEARSAL"
              : "SMALLEST PASSING TESTED PLAN",
          ),
        );
      else if (!experiment.actions?.length)
        labelCell.append(el("small", "", "NO-CHANGE CONTROL"));
      const responsesCell = el("td");
      const codes = el("div", "http-codes");
      for (const code of experiment.verification?.statuses || []) {
        const codeNode = el(
          "span",
          `http-code${code >= 400 ? " failed" : ""}`,
          String(code),
        );
        codeNode.title = `HTTP ${code}`;
        codes.append(codeNode);
      }
      responsesCell.append(codes);
      const passed = !!experiment.verification?.all_healthy;
      const resultCell = el("td");
      const semantic = semanticState(experiment.verification);
      resultCell.append(
        el(
          "span",
          `result-pill${passed && semantic.passed ? "" : !semantic.known && passed ? " legacy" : " failed"}`,
          passed ? (semantic.passed ? "Verified" : "HTTP only") : "Failed",
        ),
      );
      if (
        httpHealthy(experiment.verification) &&
        semantic.known &&
        !semantic.passed
      )
        resultCell.append(
          el("span", "false-recovery-label", "HTTP 200 ≠ recovery"),
        );
      appendContractDetails(labelCell, experiment.verification);
      row.append(
        labelCell,
        responsesCell,
        el(
          "td",
          "",
          `${Number(experiment.verification?.median_latency_ms || 0).toFixed(1)} ms`,
        ),
        resultCell,
      );
      return row;
    }),
  );
}
