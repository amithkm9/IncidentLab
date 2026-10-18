import type { LabEvent, Status, WorkspaceSummary } from "../domain";
import { $, el, text, selected, required } from "../dom";
import { state, isCurrent, recommendedPlan } from "../state";
import { modeNames, strategyNames, rehearsalFailures } from "../constants";
import { number, dateTime } from "../format";
import { recoveryVerified, semanticState, httpHealthy } from "../verification";
import { proofBlocksPromotion } from "../recovery";
import { renderContractStatus } from "./contracts";

export function scenarioDescription() {
  text(
    "scenario-description",
    state.scenarios.find((item) => item.id === $("scenario").value)
      ?.description || "",
  );
}

export function modeNote() {
  const mode = selected("mode", modeNames);
  text("mode-badge", mode === "baseline" ? "OFFLINE BASELINE" : "MISTRAL API");
  text(
    "mode-note",
    mode === "baseline"
      ? "Fixed rules for known lab scenarios. This is not a Mistral model result."
      : `${state.config?.model || "Configured model"}. ${mode === "mistral" ? "Up to 16 read-only tool calls; token usage is recorded." : "Initial evidence snapshot; no model-directed tool calls."} No changes are applied by the investigator.`,
  );
}

export function rehearsalStrategyNote() {
  const strategy = selected("rehearsal-strategy", strategyNames);
  const adaptive = strategy !== "exhaustive";
  $("experiment-budget-field").hidden = !adaptive;
  text(
    "rehearsal-mode-note",
    strategy === "mistral"
      ? `The Mistral agent chooses the next plan from lab evidence and previous outcomes. Sanitized logs, metrics, service health, business contract checks, and experiment observations are sent to ${state.config?.model || "the configured Mistral model"} through the Mistral API. Calls can incur provider charges; usage is recorded.`
      : adaptive
        ? "A deterministic offline policy chooses the next plan using observed failures and earlier experiment results. No model API calls. It may leave plans untested when it stops."
        : "Compare every candidate within the selected plan size. No model API calls. The selected result is minimal within this tested set.",
  );
  text(
    "rehearsal-scope-note",
    adaptive
      ? "The budget limits candidate experiments; a no-change control is measured separately. The active lab stays unchanged."
      : `Up to ${$("max-actions").value === "1" ? "5" : "15"} candidate plans + a no-change control. Your active lab stays unchanged.`,
  );
}

export function renderStatus(status: Status) {
  state.status = status;
  text(
    "connection",
    status.busy ? "Lab operation in progress" : "Lab connected",
  );
  $("connection-dot").classList.remove("offline");
  const transportErrors = status.http_errors ?? status.errors ?? 0;
  const semanticFailures = status.semantic_failures ?? 0;
  const contractsKnown = typeof status.semantic_checked_requests === "number";
  const failing = transportErrors > 0 || semanticFailures > 0;
  const noRequests = !status.requests;
  const scenario = state.scenarios.find(
    (item) => item.id === status.scenario_id,
  );
  text("active-scenario", scenario?.name || "Active incident");
  text(
    "scenario-kind",
    (scenario?.fault_count ?? 0) > 1
      ? "COMPOUND FAULT"
      : scenario?.fault_count === 1
        ? "SINGLE FAULT"
        : "CONTROL SCENARIO",
  );
  $("scenario-kind").classList.toggle("amber", !!scenario?.fault_count);
  $("incident-status-dot").classList.toggle("failing", failing);
  $("error-metric").classList.toggle("failing", transportErrors > 0);
  const card = required($("health-badge").closest(".health-card"));
  card.classList.toggle("failing", failing);
  text(
    "health-badge",
    noRequests
      ? "Awaiting requests"
      : failing
        ? "Degraded"
        : contractsKnown
          ? "Healthy"
          : "HTTP healthy",
  );
  text(
    "health-caption",
    !status.telemetry_available
      ? "Diagnostic telemetry unavailable"
      : semanticFailures > 0 && transportErrors === 0
        ? "HTTP 200 · business checks fail"
        : transportErrors > 0
          ? "Checkout requests failing"
          : contractsKnown
            ? "Availability + contracts passed"
            : "Business checks not recorded",
  );
  text("request-count", number(status.requests));
  text("error-count", number(transportErrors));
  text(
    "error-rate",
    `${status.requests ? Math.round((transportErrors / status.requests) * 100) : 0}%`,
  );
  $("latency").replaceChildren(
    document.createTextNode(Number(status.median_latency_ms || 0).toFixed(1)),
    el("small", "", "ms"),
  );
  text("window-label", `Observation window ${status.window}`);
  $("request-bars").replaceChildren(
    ...(status.recent_statuses || []).map((code) => {
      const bar = el("span", `request-bar${code >= 400 ? " failed" : ""}`);
      bar.title = `HTTP ${code}`;
      bar.setAttribute("aria-label", `HTTP ${code}`);
      return bar;
    }),
  );
  text(
    "episode",
    `EPISODE ${status.episode_id} / SEED ${status.seed} / REV ${status.revision ?? 0}`,
  );
  renderContractStatus(status);
}

export function renderNextStep() {
  const hasFinding = !!state.record;
  const hasRehearsal = !!state.rehearsal;
  const latestRecovery =
    state.record?.episode_recovery ||
    state.rehearsal?.promotion ||
    state.record?.remediation;
  const recovered = recoveryVerified(latestRecovery?.verification);
  for (const [id, complete, index] of [
    ["check-diagnosis", hasFinding, 1],
    ["check-rehearsal", hasRehearsal, 2],
    ["check-recovery", recovered, 3],
  ] as const) {
    $(id).classList.toggle("complete", complete);
    required($(id).querySelector("span")).textContent = complete
      ? "✓"
      : String(index);
  }
  let title, description;
  if (state.archive) {
    title = "Inspect the saved evidence";
    description =
      "This investigation belongs to a saved lab snapshot. Explore its tool trail or download the postmortem.";
  } else if (recovered) {
    title = "Recovery, with proof";
    description =
      "Fresh requests passed HTTP availability and matched expected prices and product IDs. Export the evidence or start another incident.";
  } else if (
    state.rehearsal?.report?.summary?.abstention_reason === "missing_telemetry"
  ) {
    title = "Restore the missing evidence";
    description =
      "Diagnostic telemetry is unavailable. No candidate changes were tested or authorized for this snapshot.";
  } else if (
    rehearsalFailures[state.rehearsal?.report?.budget?.stop_reason ?? ""]
  ) {
    title =
      state.rehearsal?.report.budget?.stop_reason === "experiment_error"
        ? "Review the experiment failure"
        : "Review the planning failure";
    description =
      "The rehearsal could not produce an authorized recovery plan. Inspect the saved outcome, then retry or choose another strategy.";
  } else if (
    (state.rehearsal?.proof || state.rehearsal?.proof_failure) &&
    proofBlocksPromotion(state.rehearsal)
  ) {
    title = "Resolve the proof before promotion";
    description =
      "The recovery proof did not establish an eligible plan for this snapshot. Inspect its trials, then run a new proof or rehearsal.";
  } else if (
    hasRehearsal &&
    recoveryVerified(recommendedPlan()?.verification) &&
    isCurrent(state.rehearsal)
  ) {
    title = "Promote a tested plan";
    description =
      "The comparison found a plan that passes HTTP and business contract checks. Apply it, then verify fresh responses in the active lab.";
  } else if (latestRecovery) {
    title = !semanticState(latestRecovery.verification).known
      ? "Availability-only recovery record"
      : httpHealthy(latestRecovery.verification)
        ? "HTTP 200 is not a full recovery"
        : "A fault may still remain";
    description = !semanticState(latestRecovery.verification).known
      ? "This record does not include business checks. Rehearse the current state to verify prices and product IDs."
      : httpHealthy(latestRecovery.verification)
        ? "Requests are reaching checkout, but the returned business data is still wrong. Rehearse the updated state to test a complete fix."
        : "The last fix did not restore healthy requests. Run a new rehearsal against the updated state to find the remaining intervention.";
  } else if (
    state.rehearsal &&
    state.rehearsal.report?.control?.verification?.all_healthy
  ) {
    title = semanticState(state.rehearsal.report.control.verification).known
      ? "Keep the healthy control"
      : "Recheck business correctness";
    description = semanticState(state.rehearsal.report.control.verification)
      .known
      ? "The no-change control passed HTTP, price, and SKU checks. No fix is needed for this snapshot."
      : "This saved control only recorded HTTP availability. A new rehearsal can verify expected prices and product IDs.";
  } else if (hasFinding) {
    title = "Put the suggestion to a test";
    description =
      "Rehearse single fixes and combinations. A second fault can stay hidden until the first one is repaired.";
  } else if (
    (state.status?.semantic_failures ?? 0) > 0 &&
    !state.status?.http_errors
  ) {
    title = "Look beyond the status code";
    description =
      "Checkout returns HTTP 200, but price or product checks are failing. Investigate the contract evidence before selecting a fix.";
  } else if ((state.status?.errors ?? 0) > 0) {
    title = "Follow the failure";
    description =
      "Checkout is returning errors. Run an investigation to connect the requests, recent changes, and service observations.";
  } else {
    title = "Introduce a failure";
    description =
      "Choose a scenario above to create a reproducible incident, or investigate the healthy control.";
  }
  text("next-title", title);
  text("next-description", description);
}

export function renderTimeline(events: LabEvent[]) {
  const current = (events || []).filter(
    (event) =>
      !event.episode_id || event.episode_id === state.status?.episode_id,
  );
  text("event-count", `${current.length} events`);
  if (!current.length) {
    $("timeline").replaceChildren(
      el(
        "p",
        "field-help",
        "Start a scenario or investigation to build this incident’s timeline.",
      ),
    );
    return;
  }
  const ordered = [...current]
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    .slice(0, 8);
  $("timeline").replaceChildren(
    ...ordered.map((event) => {
      const item = el(
        "div",
        `timeline-item${event.type?.includes("fail") ? " bad" : ""}`,
      );
      item.append(
        el(
          "strong",
          "",
          event.title || event.type?.replaceAll("_", " ") || "Lab event",
        ),
      );
      if (event.detail) item.append(el("p", "", event.detail));
      const time = el("time", "", dateTime(event.created_at));
      time.dateTime = event.created_at;
      item.append(time);
      return item;
    }),
  );
}

export function renderSummary(summary?: WorkspaceSummary) {
  text("summary-investigations", number(summary?.investigations));
  text("summary-rehearsals", number(summary?.rehearsals));
  text("summary-recoveries", number(summary?.verified_recoveries));
  text("history-count", number(summary?.investigations));
}
