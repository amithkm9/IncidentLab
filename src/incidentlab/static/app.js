"use strict";
const $ = (id) => document.getElementById(id);
const state = { scenarios: [], config: null, record: null, busy: false };
const modeNames = { baseline: "Offline baseline", mistral: "Mistral · tools + retrieval", retrieval: "Mistral · retrieval only", prompt: "Mistral · prompt only" };
const toolNames = { get_metrics: "Request metrics", query_logs: "Application logs", get_service_health: "Service health", get_recent_changes: "Deployment changes", search_runbooks: "Runbook search" };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "The request could not be completed. Check the form and try again.");
  return payload;
}
function controls() {
  document.querySelectorAll("button, input, select, textarea").forEach((node) => { node.disabled = state.busy; });
  const finding = state.record?.result.finding;
  $("remediate").disabled = state.busy || !finding || finding.action === "no_action" || !!state.record?.remediation;
}
async function operation(message, fn) {
  if (state.busy) return;
  state.busy = true;
  $("error").hidden = true;
  $("activity").textContent = message;
  $("activity").classList.add("busy");
  controls();
  try {
    await fn();
  } catch (error) {
    $("error").textContent = error.message || "Could not reach the lab. Check that the server is running.";
    $("error").hidden = false;
    $("activity").textContent = "Operation failed. Review the message above and retry.";
  } finally {
    state.busy = false;
    $("activity").classList.remove("busy");
    controls();
  }
}
function renderStatus(status) {
  $("connection").textContent = "Lab connected";
  const failing = status.errors > 0;
  $("health-badge").textContent = !status.requests ? "No requests observed" : failing ? "Checkout failing" : "Requests healthy";
  $("health-badge").classList.toggle("failing", failing);
  $("health-caption").textContent = !status.telemetry_available ? "Diagnostic telemetry unavailable" : `Observation window ${status.window}`;
  $("request-count").textContent = status.requests;
  $("error-rate").textContent = `${Math.round(status.error_rate * 100)}%`;
  $("latency").textContent = `${status.median_latency_ms.toFixed(1)} ms`;
  $("request-bars").replaceChildren(...status.recent_statuses.map((code) => {
    const bar = el("span", `request-bar${code >= 400 ? " failed" : ""}`);
    bar.title = `HTTP ${code}`;
    bar.setAttribute("aria-label", `HTTP ${code}`);
    return bar;
  }));
  $("episode").textContent = `EPISODE ${status.episode_id} · SEED ${status.seed}`;
}
function scenarioDescription() {
  $("scenario-description").textContent = state.scenarios.find((item) => item.id === $("scenario").value)?.description || "";
}
function modeNote() {
  const mode = $("mode").value;
  $("mode-badge").textContent = mode === "baseline" ? "OFFLINE BASELINE" : "MISTRAL API";
  $("mode-note").textContent = mode === "baseline"
    ? "The baseline uses fixed rules for these lab scenarios. It is not a Mistral model result."
    : `Uses ${state.config?.model || "the configured model"}. API token usage is recorded. ${mode === "mistral" ? "Up to 16 read-only tool calls; no automatic changes." : "Uses an initial evidence snapshot; no model-directed tool calls."}`;
}
function clearFinding() {
  state.record = null;
  $("finding").hidden = true;
  $("finding-empty").hidden = false;
  $("trace-empty").hidden = false;
  $("download").hidden = true;
  $("run-stats").hidden = true;
  $("recovery").hidden = true;
  $("traces").replaceChildren();
  $("tool-count").textContent = "0 calls";
}
function revealEvidence(id) {
  const target = [...document.querySelectorAll(".evidence-card")].find((node) => node.dataset.evidenceId === id);
  if (!target) return;
  target.closest("details").open = true;
  target.focus({ preventScroll: true });
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}
function renderFinding(record) {
  state.record = record;
  const result = record.result;
  const finding = result.finding;
  $("finding-empty").hidden = true;
  $("finding").hidden = false;
  $("trace-empty").hidden = true;
  $("recovery").hidden = true;
  $("finding-cause").textContent = finding.cause.replaceAll("_", " ").toUpperCase();
  $("finding-title").textContent = finding.title;
  $("finding-explanation").textContent = finding.explanation;
  $("action-name").textContent = finding.action;
  $("verification-plan").textContent = finding.verification;
  $("limitations").textContent = finding.limitations;
  $("remediate").hidden = finding.action === "no_action";
  $("remediate").nextElementSibling.hidden = finding.action === "no_action";
  $("citations").replaceChildren(...finding.evidence_ids.map((id) => {
    const button = el("button", "citation", id);
    button.type = "button";
    button.addEventListener("click", () => revealEvidence(id));
    return button;
  }));
  if (!finding.evidence_ids.length) $("citations").append(el("span", "subtle", "No diagnostic evidence was available."));
  $("download").href = `/api/investigations/${record.id}`;
  $("download").download = `incidentlab-${record.id}.json`;
  $("download").hidden = false;
  $("tool-count").textContent = `${result.traces.length} calls`;
  $("traces").replaceChildren(...result.traces.map((trace) => {
    const details = el("details", "trace");
    const summary = el("summary");
    summary.append(el("span", "trace-name", toolNames[trace.tool] || trace.tool), el("span", "trace-duration", `${trace.elapsed_ms.toFixed(1)} ms`));
    const body = el("div", "trace-body");
    body.append(el("pre", "trace-args", `${trace.tool}(${JSON.stringify(trace.arguments)})`));
    if (trace.error) body.append(el("p", "notice error", trace.error));
    if (!trace.evidence.length && !trace.error) body.append(el("p", "subtle", "No matching observations."));
    for (const evidence of trace.evidence) {
      const card = el("div", "evidence-card");
      card.dataset.evidenceId = evidence.id;
      card.tabIndex = -1;
      card.append(el("span", "evidence-id", evidence.id), el("h4", "", evidence.summary));
      card.append(el("pre", "", evidence.source === "runbook" ? evidence.data.content : JSON.stringify(evidence.data, null, 2)));
      body.append(card);
    }
    details.append(summary, body);
    return details;
  }));
  const stats = $("run-stats");
  stats.hidden = false;
  stats.replaceChildren(el("strong", "", `${modeNames[result.mode]} · ${(result.elapsed_ms / 1000).toFixed(2)} s`));
  if (result.model) stats.append(el("div", "", `${result.model} · ${result.input_tokens} input / ${result.output_tokens} output tokens`));
  stats.append(el("div", "", result.estimated_cost_usd === null ? result.cost_note : `$${result.estimated_cost_usd.toFixed(6)} estimated · ${result.cost_note}`));
}

$("scenario").addEventListener("change", scenarioDescription);
$("mode").addEventListener("change", modeNote);
$("scenario-form").addEventListener("submit", (event) => {
  event.preventDefault();
  operation("Introducing the scenario and sending real checkout requests…", async () => {
    const status = await api("/api/inject", { scenario_id: $("scenario").value, seed: Number($("seed").value) });
    clearFinding();
    renderStatus(status);
    $("activity").textContent = "Scenario ready. Run an investigation to find the cause.";
  });
});
$("investigate-form").addEventListener("submit", (event) => {
  event.preventDefault();
  operation($("mode").value === "baseline" ? "Inspecting logs, health, changes, metrics, and runbooks…" : "Mistral is investigating. A bounded investigation may take a few minutes…", async () => {
    const record = await api("/api/investigate", { mode: $("mode").value, question: $("question").value });
    renderFinding(record);
    renderStatus(await api("/api/status"));
    $("activity").textContent = "Investigation complete. Review the finding and its evidence before applying a fix.";
  });
});
$("probe").addEventListener("click", () => operation("Sending five fresh checkout requests…", async () => {
  const result = await api("/api/probe", { count: 5 });
  renderStatus(result.status);
  $("activity").textContent = `Probe complete: ${result.verification.statuses.join(", ")}.`;
}));
$("remediate").addEventListener("click", () => operation("Applying the proposed lab fix and verifying five new requests…", async () => {
  const result = await api("/api/remediate", { investigation_id: state.record.id, action: state.record.result.finding.action });
  state.record.remediation = result;
  renderStatus(result.status);
  const recovered = result.verification.all_healthy;
  $("recovery").hidden = false;
  $("recovery").className = `notice${recovered ? "" : " error"}`;
  $("recovery").textContent = recovered ? "Recovery verified. 5 of 5 fresh checkout requests returned HTTP 200. You can investigate again to check the healthy state." : `Recovery not verified. Fresh responses: ${result.verification.statuses.join(", ")}. Run a new investigation.`;
  $("activity").textContent = recovered ? "Fix applied. Recovery verified against fresh traffic." : "Fix applied, but checkout is still failing.";
}));

operation("Connecting to the disposable lab…", async () => {
  const [config, scenarios, status] = await Promise.all([api("/api/config"), api("/api/scenarios"), api("/api/status")]);
  state.config = config;
  state.scenarios = scenarios;
  $("scenario").replaceChildren(...scenarios.map((scenario) => {
    const option = el("option", "", scenario.name);
    option.value = scenario.id;
    return option;
  }));
  for (const option of $("mode").options) {
    if (option.value !== "baseline" && !config.mistral_configured) {
      option.disabled = true;
      option.textContent += " · API key required";
    }
  }
  scenarioDescription();
  modeNote();
  renderStatus(status);
  $("activity").textContent = "Lab ready. Choose a scenario to begin, or investigate the healthy control.";
});
