import "./style.css";
import { $, text, selected } from "./dom";
import { state } from "./state";
import {
  modeNames,
  strategyNames,
  tabs,
  stopReasonNames,
  rehearsalFailures,
} from "./constants";
import { api, requestRecoveryProof } from "./api";
import { verificationSummary, recoveryVerified } from "./verification";
import { switchView, switchTab } from "./navigation";
import {
  operation,
  refreshHistory,
  refreshWorkspace,
  loadConfiguration,
} from "./controller";
import { renderHistory } from "./views/history";
import {
  scenarioDescription,
  modeNote,
  rehearsalStrategyNote,
} from "./views/workbench";
import { filterEvidence, updateEvidenceToggle } from "./views/investigation";
import { renderExperiments } from "./views/rehearsal";
import { recommendedPlan } from "./state";

for (const name of tabs) {
  $(`tab-${name}`).addEventListener("click", () => switchTab(name));
  $(`tab-${name}`).addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight")
      next = (tabs.indexOf(name) + 1) % tabs.length;
    if (event.key === "ArrowLeft")
      next = (tabs.indexOf(name) + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      switchTab(tabs[next], true);
    }
  });
}
$("nav-workbench").setAttribute("aria-label", "Recovery workbench");
$("nav-history").setAttribute("aria-label", "Incident history");
$("nav-workbench").addEventListener("click", () => switchView("workbench"));
$("nav-history").addEventListener("click", () => {
  switchView("history");
  if (state.history) renderHistory(state.history);
  else
    renderHistory({
      investigations: state.workspace?.history || [],
      rehearsals: [],
    });
  operation("Loading saved incident history…", async () => {
    await refreshHistory();
    text(
      "activity",
      "History loaded. Saved records remain available across lab episodes.",
    );
  });
});
$("refresh-history").addEventListener("click", () =>
  operation("Refreshing saved records…", async () => {
    await refreshHistory();
    text("activity", "History refreshed.");
  }),
);
$("refresh-workspace").addEventListener("click", () =>
  operation("Refreshing the recovery workspace…", async () => {
    if (!state.config) await loadConfiguration();
    if (state.view === "history") await refreshHistory();
    else await refreshWorkspace();
    text("activity", "Workspace refreshed from the active lab.");
  }),
);
$("plan-filter").addEventListener("change", renderExperiments);
$("evidence-search").addEventListener("input", filterEvidence);
$("traces").addEventListener("toggle", updateEvidenceToggle, true);
$("expand-evidence").addEventListener("click", () => {
  const visible = [...$("traces").querySelectorAll("details")].filter(
    (node) => !node.hidden,
  );
  const shouldOpen = !visible.every((node) => node.open);
  for (const trace of visible) trace.open = shouldOpen;
  updateEvidenceToggle();
});
$("history-search").addEventListener("input", () =>
  renderHistory(state.history),
);
$("demo").addEventListener("click", () =>
  operation(
    "Starting a route fault that masks silently incorrect checkout totals…",
    async () => {
      $("scenario").value = "route_and_price_drift";
      $("seed").value = "42";
      $("mode").value = "baseline";
      $("rehearsal-strategy").value = "adaptive";
      $("max-experiments").value = "4";
      $("max-actions").value = "2";
      $("question").value =
        "Investigate checkout availability and business correctness. Identify observed failures and propose an evidence-backed fix.";
      $("evidence-search").value = "";
      $("plan-filter").value = "all";
      scenarioDescription();
      modeNote();
      rehearsalStrategyNote();
      await api("/api/inject", {
        scenario_id: "route_and_price_drift",
        seed: 42,
      });
      await refreshWorkspace();
      await api("/api/investigate", {
        mode: "baseline",
        question: $("question").value,
      });
      await refreshWorkspace();
      switchTab("diagnosis");
      text(
        "activity",
        "Offline demo ready. A route fault masks incorrect totals. Rehearse with the offline adaptive policy to see why HTTP 200 alone is not recovery.",
      );
      $("finding-title").tabIndex = -1;
      $("finding-title").focus({ preventScroll: true });
      $("finding").scrollIntoView({ block: "nearest", behavior: "auto" });
    },
  ),
);
$("return-active").addEventListener("click", () =>
  operation("Restoring the active incident…", async () => {
    state.archive = false;
    $("archive-notice").hidden = true;
    await refreshWorkspace();
    text(
      "activity",
      "Active incident restored. You can continue investigating and testing recovery plans.",
    );
  }),
);
$("scenario").addEventListener("change", scenarioDescription);
$("mode").addEventListener("change", modeNote);
$("scenario-form").addEventListener("submit", (event) => {
  event.preventDefault();
  operation(
    "Starting the scenario and sending real checkout requests…",
    async () => {
      await api("/api/inject", {
        scenario_id: $("scenario").value,
        seed: Number($("seed").value),
      });
      state.archive = false;
      $("archive-notice").hidden = true;
      await refreshWorkspace();
      switchTab("diagnosis");
      text(
        "activity",
        "Scenario ready. Investigate the observed failure, then rehearse a recovery plan.",
      );
    },
  );
});
$("investigate-form").addEventListener("submit", (event) => {
  event.preventDefault();
  operation(
    $("mode").value === "baseline"
      ? "Inspecting logs, service health, changes, metrics, and runbooks…"
      : "Mistral is investigating. This bounded investigation can take a few minutes…",
    async () => {
      await api("/api/investigate", {
        mode: selected("mode", modeNames),
        question: $("question").value,
      });
      await refreshWorkspace();
      switchTab("diagnosis");
      text(
        "activity",
        "Investigation complete. Review the evidence, then compare recovery plans in an isolated rehearsal.",
      );
      $("finding-title").tabIndex = -1;
      $("finding-title").focus({ preventScroll: true });
      $("finding").scrollIntoView({ block: "nearest", behavior: "auto" });
    },
  );
});
$("probe").addEventListener("click", () =>
  operation("Sending five fresh checkout requests…", async () => {
    const result = await api("/api/probe", { count: 5 });
    await refreshWorkspace();
    text(
      "activity",
      `Probe complete. ${verificationSummary(result.verification)}`,
    );
  }),
);
$("show-evidence").addEventListener("click", () => switchTab("evidence", true));
$("go-rehearse").addEventListener("click", () => switchTab("rehearsal", true));
$("rehearsal-strategy").addEventListener("change", rehearsalStrategyNote);
$("max-actions").addEventListener("change", rehearsalStrategyNote);
$("remediate").addEventListener("click", () =>
  operation(
    "Applying the single proposed fix and verifying fresh requests…",
    async () => {
      const record = state.record;
      if (!record)
        throw new Error("Run an investigation before applying a suggestion.");
      const result = await api("/api/remediate", {
        investigation_id: record.id,
        action: record.result.finding.action,
      });
      await refreshWorkspace();
      text(
        "activity",
        `Suggestion applied. ${verificationSummary(result.verification)}${recoveryVerified(result.verification) ? "" : " Rehearse the updated state before another change."}`,
      );
    },
  ),
);
$("rehearse").addEventListener("click", () => {
  const strategy = selected("rehearsal-strategy", strategyNames);
  if (strategy !== "exhaustive" && !$("max-experiments").reportValidity())
    return;
  operation(
    strategy === "mistral"
      ? "Mistral is selecting experiments from lab observations. Isolated tests may take a few minutes; the active lab stays unchanged…"
      : "Testing recovery plans in isolated copies. The active lab stays unchanged; this may take a minute…",
    async () => {
      await api("/api/rehearse", {
        strategy,
        max_experiments:
          strategy === "exhaustive" ? 4 : Number($("max-experiments").value),
        max_actions: Number($("max-actions").value),
        probe_count: Number($("probe-count").value),
      });
      await refreshWorkspace();
      switchTab("rehearsal");
      const stopReason = state.rehearsal?.report?.budget?.stop_reason ?? "";
      text(
        "activity",
        rehearsalFailures[stopReason]
          ? `Rehearsal stopped: ${stopReasonNames[stopReason].toLowerCase()}. No recovery plan was authorized; review the saved outcome.`
          : state.rehearsal?.report?.summary?.abstention_reason ===
              "missing_telemetry"
            ? "Rehearsal withheld: diagnostic telemetry is unavailable. No candidate changes were tested or authorized."
            : recommendedPlan()
              ? "Rehearsal complete. Review the smallest passing tested plan before promoting it."
              : state.rehearsal?.report?.control?.verification?.all_healthy
                ? "Rehearsal complete. The no-change control is healthy; no fix is needed."
                : "Rehearsal complete. No tested plan recovered checkout; review the measured outcomes.",
      );
      $("recommendation").tabIndex = -1;
      $("recommendation").focus({ preventScroll: true });
      $("recommendation").scrollIntoView({ block: "start", behavior: "auto" });
    },
  );
});
$("prove").addEventListener("click", () =>
  operation(
    "Testing the full plan and removing each fix in isolated copies. Up to 36 requests; no model calls…",
    async () => {
      const record = state.rehearsal;
      if (!record)
        throw new Error(
          "Run a rehearsal with a passing plan before requesting a proof.",
        );
      try {
        const result = await requestRecoveryProof(record.id);
        await refreshWorkspace();
        text(
          "activity",
          result.authority.is_current && result.proof.summary.promotion_eligible
            ? "Recovery proof complete. Inspect what happened when each fix was removed before promoting the plan."
            : "Recovery proof saved, but it does not authorize promotion. Review the measured outcome before continuing.",
        );
        $("proof-summary").tabIndex = -1;
        $("proof-summary").focus({ preventScroll: true });
        $("proof-summary").scrollIntoView({
          block: "nearest",
          behavior: "auto",
        });
      } catch (error) {
        try {
          await refreshWorkspace();
        } catch {
          /* Keep the original proof error visible. */
        }
        throw error;
      }
    },
  ),
);
$("promote").addEventListener("click", () =>
  operation(
    "Promoting the tested recovery plan and verifying fresh traffic in the active lab…",
    async () => {
      const record = state.rehearsal;
      const planId = record?.report.recommended_plan_id;
      if (!record || !planId)
        throw new Error(
          "Run a rehearsal with a passing plan before promotion.",
        );
      const result = await api("/api/promote", {
        rehearsal_id: record.id,
        plan_id: planId,
      });
      await refreshWorkspace();
      text(
        "activity",
        `Tested plan applied. ${verificationSummary(result.verification)}`,
      );
    },
  ),
);

operation("Connecting to your recovery workspace…", async () => {
  await loadConfiguration();
  await refreshWorkspace();
  const status = state.status;
  if (
    status?.scenario_id &&
    state.scenarios.some((scenario) => scenario.id === status.scenario_id)
  )
    $("scenario").value = status.scenario_id;
  if (status?.seed !== undefined) $("seed").value = String(status.seed);
  scenarioDescription();
  text(
    "activity",
    state.record || state.rehearsal
      ? "Workspace restored. Continue from the saved finding or experiment."
      : "Lab ready. Start a scenario, investigate the evidence, then test a recovery plan.",
  );
});
