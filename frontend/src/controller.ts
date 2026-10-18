import type { Status, Scenario, Mode, Strategy } from "./domain";
import { $, text, el } from "./dom";
import { state, isCurrent, recommendedPlan } from "./state";
import { modeNames, strategyNames } from "./constants";
import { proofBlocksPromotion } from "./recovery";
import { recoveryVerified } from "./verification";
import { api, ApiError } from "./api";
import { switchView, switchTab } from "./navigation";
import {
  renderStatus,
  renderTimeline,
  renderSummary,
  renderNextStep,
  modeNote,
  rehearsalStrategyNote,
} from "./views/workbench";
import { renderFinding } from "./views/investigation";
import { renderRehearsal } from "./views/rehearsal";
import { renderHistory } from "./views/history";

function controls() {
  const locked =
    state.busy || !!state.status?.busy || state.archive || !state.status;
  document
    .querySelectorAll<
      | HTMLButtonElement
      | HTMLInputElement
      | HTMLSelectElement
      | HTMLTextAreaElement
    >("[data-mutates]")
    .forEach((node) => {
      node.disabled = locked;
    });
  const finding = state.record?.result?.finding;
  $("remediate").disabled =
    locked ||
    !isCurrent(state.record) ||
    !finding ||
    finding.action === "no_action" ||
    !!state.record?.remediation;
  const plan = recommendedPlan();
  $("promote").disabled =
    locked ||
    !isCurrent(state.rehearsal) ||
    !recoveryVerified(plan?.verification) ||
    !!state.rehearsal?.promotion ||
    proofBlocksPromotion(state.rehearsal);
  $("prove").disabled =
    locked ||
    !isCurrent(state.rehearsal) ||
    !recoveryVerified(plan?.verification) ||
    !!state.rehearsal?.promotion;
  $("refresh-history").disabled = state.busy;
  $("refresh-workspace").disabled = state.busy;
  $("return-active").disabled = state.busy;
  $("main-content").setAttribute("aria-busy", String(state.busy));
  document.body.classList.toggle("is-busy", state.busy || !!state.status?.busy);
}

export async function operation(message: string, fn: () => Promise<void>) {
  if (state.busy) return;
  state.busy = true;
  $("error").hidden = true;
  text("activity", message);
  controls();
  try {
    await fn();
  } catch (error) {
    if (error instanceof ApiError && error.connectionLost) {
      text("connection", "Connection interrupted");
      $("connection-dot").classList.add("offline");
    }
    text(
      "error",
      error instanceof Error
        ? error.message
        : "The operation failed. Refresh the workspace and try again.",
    );
    $("error").hidden = false;
    text(
      "activity",
      "Operation stopped. Review the message above before retrying.",
    );
    if (error instanceof ApiError && error.status === 409) {
      try {
        await refreshWorkspace();
      } catch {
        /* Preserve the original actionable error. */
      }
    }
  } finally {
    state.busy = false;
    controls();
  }
}

export async function openArchive(id: string) {
  await operation(
    "Opening the saved investigation and its evidence…",
    async () => {
      const record = await api(`/api/investigations/${id}`);
      const rehearsal = record.rehearsal_id
        ? await api(`/api/rehearsals/${record.rehearsal_id}`)
        : null;
      state.archive = true;
      $("archive-notice").hidden = false;
      renderFinding(record);
      renderRehearsal(rehearsal);
      renderNextStep();
      switchView("workbench");
      switchTab("diagnosis");
      text(
        "activity",
        "Archived investigation opened. Mutating actions are disabled for this saved record.",
      );
      $("archive-notice").scrollIntoView({ block: "start", behavior: "auto" });
    },
  );
}

export async function refreshWorkspace() {
  const workspace = await api("/api/workspace");
  state.workspace = workspace;
  renderStatus(workspace.status);
  scheduleBusyRefresh(workspace.status);
  if (!state.archive) {
    renderFinding(workspace.latest_investigation || null);
    renderRehearsal(workspace.latest_rehearsal || null);
  }
  renderTimeline(workspace.events);
  renderSummary(workspace.summary);
  renderNextStep();
  controls();
  return workspace;
}

export async function refreshHistory() {
  await refreshWorkspace();
  const history = await api("/api/history");
  renderHistory(history);
}

export async function loadConfiguration() {
  const [config, scenarios] = await Promise.all([
    api("/api/config"),
    api("/api/scenarios"),
  ]);
  state.config = config;
  state.scenarios = scenarios;
  text("scenario-count", `${scenarios.length} SCENARIOS`);
  const groups: [string, (scenario: Scenario) => boolean][] = [
    ["Compound incidents · two faults", (scenario) => scenario.fault_count > 1],
    ["Single-fault incidents", (scenario) => scenario.fault_count === 1],
    ["Control scenarios", (scenario) => !scenario.fault_count],
  ];
  $("scenario").replaceChildren(
    ...groups.map(([label, matches]) => {
      const group = el("optgroup");
      group.label = label;
      group.append(
        ...scenarios.filter(matches).map((scenario) => {
          const option = el("option", "", scenario.name);
          option.value = scenario.id;
          return option;
        }),
      );
      return group;
    }),
  );
  for (const option of $("mode").options) {
    option.disabled = option.value !== "baseline" && !config.mistral_configured;
    option.textContent = `${modeNames[option.value as Mode] || option.value}${option.disabled ? " · API key required" : ""}`;
  }
  for (const option of $("rehearsal-strategy").options) {
    option.disabled = option.value === "mistral" && !config.mistral_configured;
    option.textContent = `${strategyNames[option.value as Strategy] || option.value}${option.disabled ? " · API key required" : ""}`;
  }
  if ($("rehearsal-strategy").value === "mistral" && !config.mistral_configured)
    $("rehearsal-strategy").value = "exhaustive";
  text("app-version", `INCIDENTLAB ${config.version || ""} / LOCAL`);
  modeNote();
  rehearsalStrategyNote();
}

let busyRefreshTimer: ReturnType<typeof setTimeout> | undefined;
function scheduleBusyRefresh(status: Status): void {
  clearTimeout(busyRefreshTimer);
  if (status.busy)
    busyRefreshTimer = setTimeout(async () => {
      if (state.busy) {
        scheduleBusyRefresh(status);
        return;
      }
      try {
        await refreshWorkspace();
      } catch {
        text("connection", "Connection interrupted");
        $("connection-dot").classList.add("offline");
        text(
          "error",
          "Could not refresh the active operation. Reload the page to reconnect.",
        );
        $("error").hidden = false;
      }
    }, 2000);
}
