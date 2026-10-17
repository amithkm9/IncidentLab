"use strict";
const $ = (id) => document.getElementById(id);
const state = { scenarios: [], config: null, status: null, record: null, rehearsal: null, workspace: null, history: null, busy: false, archive: false, view: "workbench", tab: "diagnosis" };
const modeNames = { baseline: "Offline baseline", mistral: "Mistral · tools + retrieval", retrieval: "Mistral · retrieval only", prompt: "Mistral · prompt only" };
const toolNames = { get_metrics: "Request metrics", query_logs: "Application logs", get_service_health: "Service health", get_recent_changes: "Deployment changes", search_runbooks: "Runbook search" };
const actionNames = { no_action: "No changes proposed", restore_inventory_route: "Restore inventory route", restore_inventory_service: "Restore inventory service", restore_timeout_budget: "Restore timeout budget", restore_catalog_path: "Restore catalog path", rollback_checkout_release: "Roll back checkout release" };
const tabs = ["diagnosis", "rehearsal", "evidence"];
let busyRefreshTimer;
const duration = (ms) => ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Number(ms || 0).toFixed(1)} ms`;
const number = (value) => new Intl.NumberFormat().format(Number(value || 0));
const dateTime = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Saved record" : new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
};
const actionLabel = (actions) => actions?.length ? actions.map((action) => actionNames[action] || action.replaceAll("_", " ")).join(" + ") : "No changes · control";
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function text(id, value) { $(id).textContent = value; }
function link(href, label, className = "text-link") {
  const node = el("a", className, label);
  node.href = href;
  return node;
}
function button(label, className, handler) {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
}
async function api(path, body) {
  let response;
  try {
    response = await fetch(path, body === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Could not reach the lab. Check that the server is running, then retry.");
  }
  let payload;
  try { payload = await response.json(); } catch {
    throw new Error(`The server returned an unreadable response (${response.status}). Refresh the workspace and retry.`);
  }
  if (!response.ok) {
    const error = new Error(typeof payload.detail === "string" ? payload.detail : "The request could not be completed. Check the selected values and try again.");
    error.status = response.status;
    throw error;
  }
  return payload;
}
function isCurrent(record) {
  return !!record && record.episode_id === state.status?.episode_id && record.revision === state.status?.revision;
}
function recommendedPlan() {
  const report = state.rehearsal?.report;
  return report?.experiments?.find((plan) => plan.id === report.recommended_plan_id) || null;
}
function controls() {
  const locked = state.busy || !!state.status?.busy || state.archive || !state.status;
  document.querySelectorAll("[data-mutates]").forEach((node) => { node.disabled = locked; });
  const finding = state.record?.result?.finding;
  $("remediate").disabled = locked || !isCurrent(state.record) || !finding || finding.action === "no_action" || !!state.record?.remediation;
  const plan = recommendedPlan();
  $("promote").disabled = locked || !isCurrent(state.rehearsal) || !plan?.verification?.all_healthy || !!state.rehearsal?.promotion;
  $("refresh-history").disabled = state.busy;
  $("return-active").disabled = state.busy;
  $("main-content").setAttribute("aria-busy", String(state.busy));
}
async function operation(message, fn) {
  if (state.busy) return;
  state.busy = true;
  $("error").hidden = true;
  text("activity", message);
  $("activity").classList.add("busy");
  controls();
  try {
    await fn();
  } catch (error) {
    text("error", error.message || "The operation failed. Refresh the workspace and try again.");
    $("error").hidden = false;
    text("activity", "Operation stopped. Review the message above before retrying.");
    if (error.status === 409) {
      try { await refreshWorkspace(); } catch { /* Preserve the original actionable error. */ }
    }
  } finally {
    state.busy = false;
    $("activity").classList.remove("busy");
    controls();
  }
}
function switchTab(name, focus = false) {
  state.tab = name;
  for (const tab of tabs) {
    const selected = tab === name;
    $(`tab-${tab}`).classList.toggle("active", selected);
    $(`tab-${tab}`).setAttribute("aria-selected", String(selected));
    $(`tab-${tab}`).tabIndex = selected ? 0 : -1;
    $(`pane-${tab}`).hidden = !selected;
  }
  if (focus) $(`tab-${name}`).focus();
}
function switchView(view) {
  state.view = view;
  $("workbench-view").hidden = view !== "workbench";
  $("history-view").hidden = view !== "history";
  for (const name of ["workbench", "history"]) {
    $(`nav-${name}`).classList.toggle("active", view === name);
    if (view === name) $(`nav-${name}`).setAttribute("aria-current", "page");
    else $(`nav-${name}`).removeAttribute("aria-current");
  }
  text("breadcrumb-page", view === "workbench" ? "Recovery workbench" : "Incident history");
}
function scenarioDescription() {
  text("scenario-description", state.scenarios.find((item) => item.id === $("scenario").value)?.description || "");
}
function modeNote() {
  const mode = $("mode").value;
  text("mode-badge", mode === "baseline" ? "OFFLINE BASELINE" : "MISTRAL API");
  text("mode-note", mode === "baseline"
    ? "Fixed rules for known lab scenarios. This is not a Mistral model result."
    : `${state.config?.model || "Configured model"}. ${mode === "mistral" ? "Up to 16 read-only tool calls; token usage is recorded." : "Initial evidence snapshot; no model-directed tool calls."} No changes are applied by the investigator.`);
}
function renderStatus(status) {
  state.status = status;
  text("connection", status.busy ? "Lab operation in progress" : "Lab connected");
  $("connection-dot").classList.remove("offline");
  const failing = status.errors > 0;
  const noRequests = !status.requests;
  const card = $("health-badge").closest(".health-card");
  card.classList.toggle("failing", failing);
  card.classList.toggle("unobserved", noRequests);
  text("health-badge", noRequests ? "Awaiting requests" : failing ? "Degraded" : "Healthy");
  text("health-caption", !status.telemetry_available ? "Diagnostic telemetry unavailable" : failing ? "Checkout requests failing" : "Fresh request window");
  text("request-count", number(status.requests));
  text("error-count", number(status.errors));
  text("error-rate", `${Math.round(Number(status.error_rate || 0) * 100)}%`);
  $("latency").replaceChildren(document.createTextNode(Number(status.median_latency_ms || 0).toFixed(1)), el("small", "", "ms"));
  text("window-label", `Observation window ${status.window}`);
  $("request-bars").replaceChildren(...(status.recent_statuses || []).map((code) => {
    const bar = el("span", `request-bar${code >= 400 ? " failed" : ""}`);
    bar.title = `HTTP ${code}`;
    bar.setAttribute("aria-label", `HTTP ${code}`);
    return bar;
  }));
  text("episode", `EPISODE ${status.episode_id} / SEED ${status.seed} / REV ${status.revision ?? 0}`);
  clearTimeout(busyRefreshTimer);
  if (status.busy) busyRefreshTimer = setTimeout(async () => {
    if (state.busy) { renderStatus(state.status); return; }
    try { await refreshWorkspace(); } catch {
      text("connection", "Connection interrupted");
      $("connection-dot").classList.add("offline");
      text("error", "Could not refresh the active operation. Reload the page to reconnect.");
      $("error").hidden = false;
    }
  }, 2000);
}
function revealEvidence(id) {
  switchTab("evidence");
  const target = [...document.querySelectorAll(".evidence-card")].find((node) => node.dataset.evidenceId === id);
  if (!target) return;
  target.closest("details").open = true;
  target.focus({ preventScroll: true });
  target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
}
function verificationNotice(target, result, successText) {
  const verification = result?.verification;
  if (!verification) { target.hidden = true; return; }
  target.hidden = false;
  target.className = `notice${verification.all_healthy ? "" : " error"}`;
  target.textContent = verification.all_healthy
    ? `${successText} ${verification.statuses?.filter((code) => code === 200).length ?? verification.requests} of ${verification.requests} fresh requests returned HTTP 200.`
    : `Recovery not verified. Fresh responses: ${(verification.statuses || []).join(", ")}. Another fault may remain; investigate or rehearse again.`;
}
function renderFinding(record) {
  state.record = record;
  const result = record?.result;
  const finding = result?.finding;
  $("finding-empty").hidden = !!finding;
  $("finding").hidden = !finding;
  $("trace-empty").hidden = !!finding;
  $("diagnosis-dot").hidden = !finding;
  $("run-stats").hidden = !finding;
  $("recovery").hidden = true;
  $("traces").replaceChildren();
  text("tool-count", `${result?.traces?.length || 0} CALLS`);
  text("evidence-count", number(result?.traces?.length || 0));
  if (!finding) return;
  text("finding-cause", finding.cause.replaceAll("_", " ").toUpperCase());
  text("finding-time", dateTime(record.created_at));
  text("finding-title", finding.title);
  text("finding-explanation", finding.explanation);
  text("action-name", actionNames[finding.action] || finding.action);
  text("verification-plan", finding.verification);
  text("limitations", finding.limitations);
  $("remediate").hidden = finding.action === "no_action" || state.archive;
  $("go-rehearse").hidden = state.archive;
  const suggestionTag = document.querySelector(".suggestion-heading .tag");
  suggestionTag.textContent = record.remediation ? "APPLIED TO LAB" : finding.action === "no_action" ? "NO MUTATION" : "SINGLE ACTION";
  suggestionTag.classList.toggle("amber", !record.remediation && finding.action !== "no_action");
  text("suggestion-note", state.archive
    ? "Archived records are read-only. Return to the active incident to run new experiments."
    : record.remediation
      ? "This suggestion has been applied. Investigate again or compare recovery plans to test the current state."
      : !isCurrent(record)
        ? "The active lab has changed since this finding. Run a new investigation before applying its suggestion."
        : "A single fix may leave another fault hidden. Rehearsal compares fixes without changing this lab.");
  const evidenceById = new Map((result.traces || []).flatMap((trace) => trace.evidence || []).map((item) => [item.id, item]));
  $("citations").replaceChildren(...finding.evidence_ids.map((id, index) => {
    const evidence = evidenceById.get(id);
    const node = button("", "citation", () => revealEvidence(id));
    node.append(el("span", "citation-number", String(index + 1)), el("span", "", evidence?.source?.replaceAll("_", " ") || id));
    node.title = evidence ? `${evidence.summary} (${id})` : id;
    node.setAttribute("aria-label", `Open evidence ${index + 1}: ${evidence?.summary || id}`);
    return node;
  }));
  if (!finding.evidence_ids.length) $("citations").append(el("span", "subtle", "No diagnostic evidence was available."));
  $("download").href = `/api/investigations/${record.id}`;
  $("download").download = `incidentlab-${record.id}.json`;
  $("postmortem").href = `/api/postmortems/${record.id}`;
  $("postmortem").download = `incidentlab-${record.id}-postmortem.md`;
  $("traces").replaceChildren(...(result.traces || []).map((trace) => {
    const details = el("details", "trace");
    const summary = el("summary");
    summary.append(el("span", "trace-name", toolNames[trace.tool] || trace.tool), el("span", "trace-duration", duration(trace.elapsed_ms)));
    const body = el("div", "trace-body");
    body.append(el("pre", "trace-args", `${trace.tool}(${JSON.stringify(trace.arguments)})`));
    if (trace.error) body.append(el("p", "notice error", trace.error));
    if (!trace.evidence?.length && !trace.error) body.append(el("p", "subtle", "No matching observations."));
    for (const evidence of trace.evidence || []) {
      const card = el("div", "evidence-card");
      card.dataset.evidenceId = evidence.id;
      card.tabIndex = -1;
      card.append(el("span", "evidence-id", `${evidence.source} / ${evidence.id}`), el("h4", "", evidence.summary));
      card.append(el("pre", "", evidence.source === "runbook" && evidence.data?.content ? evidence.data.content : JSON.stringify(evidence.data, null, 2)));
      body.append(card);
    }
    details.append(summary, body);
    return details;
  }));
  const stats = $("run-stats");
  stats.replaceChildren(el("strong", "", `${modeNames[result.mode] || result.mode} · ${duration(result.elapsed_ms)}`));
  if (result.model) stats.append(el("div", "", `${result.model} · ${number(result.input_tokens)} input / ${number(result.output_tokens)} output tokens`));
  stats.append(el("div", "", result.estimated_cost_usd == null ? result.cost_note || "Estimated cost unavailable." : `$${Number(result.estimated_cost_usd).toFixed(6)} estimated · ${result.cost_note || ""}`));
  const recovery = record.episode_recovery || record.remediation;
  if (recovery) {
    verificationNotice($("recovery"), recovery, record.episode_recovery ? "Tested plan applied. Episode recovery verified." : "Suggestion applied. Recovery verified.");
    if (record.episode_recovery && record.remediation && !record.remediation.verification.all_healthy) {
      $("recovery").append(el("div", "", `The initial single-fix attempt failed (${record.remediation.verification.statuses.join(", ")}); the later rehearsed plan restored checkout.`));
    }
  }
}
function renderRehearsal(record) {
  state.rehearsal = record;
  const report = record?.report;
  $("rehearsal-empty").hidden = !!report;
  $("rehearsal-result").hidden = !report;
  $("rehearsal-dot").hidden = !report;
  $("promotion-result").hidden = true;
  if (!report) return;
  const plan = recommendedPlan();
  const controlHealthy = report.control?.verification?.all_healthy || report.summary?.control_healthy;
  const missingTelemetry = report.summary?.abstention_reason === "missing_telemetry";
  const recommendation = $("recommendation");
  recommendation.className = `recommendation${!plan && !controlHealthy ? " warning" : ""}`;
  recommendation.replaceChildren(el("span", "recommendation-icon", plan || controlHealthy ? "✓" : "!"));
  const message = el("div");
  message.append(el("h3", "", missingTelemetry ? "Rehearsal withheld: diagnostic telemetry unavailable." : controlHealthy ? "The control is already healthy." : plan ? `${plan.actions.length === 1 ? "One action" : `${plan.actions.length} actions`} recovered this snapshot.` : "No tested plan recovered checkout."));
  message.append(el("p", "", missingTelemetry ? "No candidate fixes were tested or authorized. Restore diagnostic evidence before selecting a recovery action." : controlHealthy
    ? "Fresh requests passed without changes. No remediation is recommended."
    : plan ? `${actionLabel(plan.actions)}. This is the smallest passing plan in the tested set.`
      : "Review the evidence and experiment outcomes. A larger plan or a different intervention may be needed."));
  recommendation.append(message);
  text("plans-tested", number(report.summary?.tested_plans ?? report.experiments?.length));
  text("plans-passed", number(report.summary?.successful_plans ?? report.experiments?.filter((item) => item.verification.all_healthy).length));
  text("minimal-actions", controlHealthy ? "0" : report.summary?.minimal_action_count ?? plan?.actions.length ?? "—");
  text("rehearsal-duration", duration(report.elapsed_ms));
  const experiments = [report.control, ...(report.experiments || [])].filter(Boolean);
  $("experiments").replaceChildren(...experiments.map((experiment) => {
    const recommended = experiment.id === report.recommended_plan_id;
    const row = el("tr", recommended ? "recommended" : "");
    const labelCell = el("td");
    labelCell.append(el("span", "plan-label", actionLabel(experiment.actions)));
    if (recommended) labelCell.append(el("small", "", "SMALLEST PASSING PLAN"));
    else if (!experiment.actions?.length) labelCell.append(el("small", "", "NO-CHANGE CONTROL"));
    const responsesCell = el("td");
    const codes = el("div", "http-codes");
    for (const code of experiment.verification?.statuses || []) {
      const codeNode = el("span", `http-code${code >= 400 ? " failed" : ""}`, String(code));
      codeNode.title = `HTTP ${code}`;
      codes.append(codeNode);
    }
    responsesCell.append(codes);
    const passed = !!experiment.verification?.all_healthy;
    const resultCell = el("td");
    resultCell.append(el("span", `result-pill${passed ? "" : " failed"}`, passed ? "Passed" : "Failed"));
    row.append(labelCell, responsesCell, el("td", "", `${Number(experiment.verification?.median_latency_ms || 0).toFixed(1)} ms`), resultCell);
    return row;
  }));
  $("promotion").hidden = !plan || !!record.promotion || state.archive;
  const promotionDescription = $("promotion").querySelector("p");
  promotionDescription.textContent = isCurrent(record)
    ? "Apply the smallest passing plan to the active lab, then verify it with fresh requests."
    : "The lab has changed since this experiment. Run a new rehearsal before promoting a plan.";
  $("rehearsal-limitations").replaceChildren(...(report.limitations || []).map((limitation) => el("li", "", limitation)));
  $("rehearsal-download").href = `/api/rehearsals/${record.id}`;
  $("rehearsal-download").download = `incidentlab-rehearsal-${record.id}.json`;
  if (record.promotion) verificationNotice($("promotion-result"), record.promotion, "Tested plan applied. Recovery verified.");
}
function renderNextStep() {
  const hasFinding = !!state.record;
  const hasRehearsal = !!state.rehearsal;
  const latestRecovery = state.record?.episode_recovery || state.rehearsal?.promotion || state.record?.remediation;
  const recovered = !!latestRecovery?.verification?.all_healthy;
  for (const [id, complete, index] of [["check-diagnosis", hasFinding, 1], ["check-rehearsal", hasRehearsal, 2], ["check-recovery", recovered, 3]]) {
    $(id).classList.toggle("complete", complete);
    $(id).querySelector("span").textContent = complete ? "✓" : String(index);
  }
  let title, description;
  if (state.archive) {
    title = "Inspect the saved evidence";
    description = "This investigation belongs to a saved lab snapshot. Explore its tool trail or download the postmortem.";
  } else if (recovered) {
    title = "Recovery, with proof";
    description = "Fresh checkout requests passed after the change. Export the evidence or start another incident to explore a different failure.";
  } else if (state.rehearsal?.report?.summary?.abstention_reason === "missing_telemetry") {
    title = "Restore the missing evidence";
    description = "Diagnostic telemetry is unavailable. No candidate changes were tested or authorized for this snapshot.";
  } else if (latestRecovery) {
    title = "A fault may still remain";
    description = "The last fix did not restore healthy requests. Run a new rehearsal against the updated state to find the remaining intervention.";
  } else if (hasRehearsal && recommendedPlan() && isCurrent(state.rehearsal)) {
    title = "Promote a tested plan";
    description = "The comparison found a passing plan. Review its outcomes, then apply it and verify new traffic in the active lab.";
  } else if (hasRehearsal && state.rehearsal.report?.control?.verification?.all_healthy) {
    title = "Keep the healthy control";
    description = "The no-change control passed. No fix is needed for this snapshot. Start a failure scenario to explore recovery.";
  } else if (hasFinding) {
    title = "Put the suggestion to a test";
    description = "Rehearse single fixes and combinations. A second fault can stay hidden until the first one is repaired.";
  } else if (state.status?.errors > 0) {
    title = "Follow the failure";
    description = "Checkout is returning errors. Run an investigation to connect the requests, recent changes, and service observations.";
  } else {
    title = "Introduce a failure";
    description = "Choose a scenario above to create a reproducible incident, or investigate the healthy control.";
  }
  text("next-title", title);
  text("next-description", description);
}
function renderTimeline(events) {
  const current = (events || []).filter((event) => !event.episode_id || event.episode_id === state.status?.episode_id);
  text("event-count", `${current.length} events`);
  if (!current.length) {
    $("timeline").replaceChildren(el("p", "field-help", "Start a scenario or investigation to build this incident’s timeline."));
    return;
  }
  const ordered = [...current].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 8);
  $("timeline").replaceChildren(...ordered.map((event) => {
    const item = el("div", `timeline-item${event.type?.includes("fail") ? " bad" : ""}`);
    item.append(el("strong", "", event.title || event.type?.replaceAll("_", " ") || "Lab event"));
    if (event.detail) item.append(el("p", "", event.detail));
    const time = el("time", "", dateTime(event.created_at));
    time.dateTime = event.created_at;
    item.append(time);
    return item;
  }));
}
function renderSummary(summary) {
  text("summary-investigations", number(summary?.investigations));
  text("summary-rehearsals", number(summary?.rehearsals));
  text("summary-recoveries", number(summary?.verified_recoveries));
  text("history-count", number(summary?.investigations));
}
function emptyHistory(title, description) {
  const box = el("div", "history-empty");
  box.append(el("strong", "", title), el("p", "", description));
  return box;
}
function renderHistory(history) {
  state.history = history;
  const investigations = history?.investigations || [];
  const rehearsals = history?.rehearsals || [];
  $("history-investigations").replaceChildren(...investigations.map((item) => {
    const row = el("article", "history-row");
    const main = el("div", "history-row-main");
    const heading = el("div", "history-row-heading");
    heading.append(button(item.title || "Saved investigation", "history-row-title", () => openArchive(item.id)));
    const remediationLabel = item.verified ? "EPISODE RECOVERED" : item.remediated ? "ACTION APPLIED" : "READ-ONLY FINDING";
    heading.append(el("span", `tag${item.verified ? " good" : ""}`, remediationLabel));
    const scenario = state.scenarios.find((scenario) => scenario.id === item.scenario_id)?.name || item.scenario_id || "Lab snapshot";
    main.append(heading, el("div", "history-row-meta", `${dateTime(item.created_at)} · ${scenario} · ${modeNames[item.mode] || item.mode || "Investigation"}`));
    const actions = el("div", "history-row-actions");
    actions.append(button("Inspect →", "button secondary small", () => openArchive(item.id)), link(`/api/postmortems/${item.id}`, "Postmortem ↗"));
    row.append(main, actions);
    return row;
  }));
  if (!investigations.length) $("history-investigations").append(emptyHistory("Your incident record starts here.", "Run an investigation to save its finding, tool calls, and evidence."));
  $("history-rehearsals").replaceChildren(...rehearsals.map((item) => {
    const row = el("article", "history-row");
    const main = el("div", "history-row-main");
    const heading = el("div", "history-row-heading");
    const scenario = state.scenarios.find((scenario) => scenario.id === item.scenario_id)?.name || item.scenario_id || "Lab snapshot";
    heading.append(el("strong", "history-row-title", scenario));
    heading.append(el("span", "tag", item.promoted || item.promotion ? "PLAN PROMOTED" : "EXPERIMENT SAVED"));
    const tested = item.tested_plans ?? item.summary?.tested_plans ?? item.report?.summary?.tested_plans;
    main.append(heading, el("div", "history-row-meta", `${dateTime(item.created_at)}${tested !== undefined ? ` · ${tested} plans tested` : ""} · Episode ${item.episode_id}`));
    const actions = el("div", "history-row-actions");
    actions.append(link(`/api/rehearsals/${item.id}`, "Experiment JSON ↗"));
    row.append(main, actions);
    return row;
  }));
  if (!rehearsals.length) $("history-rehearsals").append(emptyHistory("No recovery experiments yet.", "Run a fix rehearsal to save the control, candidate plans, and measured outcomes."));
}
async function openArchive(id) {
  await operation("Opening the saved investigation and its evidence…", async () => {
    const record = await api(`/api/investigations/${id}`);
    state.archive = true;
    $("archive-notice").hidden = false;
    renderFinding(record);
    renderRehearsal(null);
    renderNextStep();
    switchView("workbench");
    switchTab("diagnosis");
    text("activity", "Archived investigation opened. Mutating actions are disabled for this saved record.");
    $("archive-notice").scrollIntoView({ block: "start", behavior: "auto" });
  });
}
async function refreshWorkspace() {
  const workspace = await api("/api/workspace");
  state.workspace = workspace;
  renderStatus(workspace.status);
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
async function refreshHistory() {
  await refreshWorkspace();
  const history = await api("/api/history");
  renderHistory(history);
}

for (const name of tabs) {
  $(`tab-${name}`).addEventListener("click", () => switchTab(name));
  $(`tab-${name}`).addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (tabs.indexOf(name) + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (tabs.indexOf(name) + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); switchTab(tabs[next], true); }
  });
}
$("nav-workbench").setAttribute("aria-label", "Recovery workbench");
$("nav-history").setAttribute("aria-label", "Incident history");
$("nav-workbench").addEventListener("click", () => switchView("workbench"));
$("nav-history").addEventListener("click", () => {
  switchView("history");
  if (state.history) renderHistory(state.history);
  else renderHistory({ investigations: state.workspace?.history || [], rehearsals: [] });
  operation("Loading saved incident history…", async () => {
    await refreshHistory();
    text("activity", "History loaded. Saved records remain available across lab episodes.");
  });
});
$("refresh-history").addEventListener("click", () => operation("Refreshing saved records…", async () => {
  await refreshHistory();
  text("activity", "History refreshed.");
}));
$("return-active").addEventListener("click", () => operation("Restoring the active incident…", async () => {
  state.archive = false;
  $("archive-notice").hidden = true;
  await refreshWorkspace();
  text("activity", "Active incident restored. You can continue investigating and testing recovery plans.");
}));
$("scenario").addEventListener("change", scenarioDescription);
$("mode").addEventListener("change", modeNote);
$("scenario-form").addEventListener("submit", (event) => {
  event.preventDefault();
  operation("Starting the scenario and sending real checkout requests…", async () => {
    await api("/api/inject", { scenario_id: $("scenario").value, seed: Number($("seed").value) });
    state.archive = false;
    $("archive-notice").hidden = true;
    await refreshWorkspace();
    switchTab("diagnosis");
    text("activity", "Scenario ready. Investigate the observed failure, then rehearse a recovery plan.");
  });
});
$("investigate-form").addEventListener("submit", (event) => {
  event.preventDefault();
  operation($("mode").value === "baseline" ? "Inspecting logs, service health, changes, metrics, and runbooks…" : "Mistral is investigating. This bounded investigation can take a few minutes…", async () => {
    await api("/api/investigate", { mode: $("mode").value, question: $("question").value });
    await refreshWorkspace();
    switchTab("diagnosis");
    text("activity", "Investigation complete. Review the evidence, then compare recovery plans in an isolated rehearsal.");
    $("finding-title").tabIndex = -1;
    $("finding-title").focus({ preventScroll: true });
    $("finding").scrollIntoView({ block: "nearest", behavior: "auto" });
  });
});
$("probe").addEventListener("click", () => operation("Sending five fresh checkout requests…", async () => {
  const result = await api("/api/probe", { count: 5 });
  await refreshWorkspace();
  text("activity", `Probe complete: ${result.verification.statuses.join(", ")}. ${result.verification.all_healthy ? "All requests passed." : "Checkout is still returning errors."}`);
}));
$("show-evidence").addEventListener("click", () => switchTab("evidence", true));
$("go-rehearse").addEventListener("click", () => switchTab("rehearsal", true));
$("remediate").addEventListener("click", () => operation("Applying the single proposed fix and verifying fresh requests…", async () => {
  const result = await api("/api/remediate", { investigation_id: state.record.id, action: state.record.result.finding.action });
  await refreshWorkspace();
  text("activity", result.verification.all_healthy ? "Recovery verified against fresh traffic. The result is saved with the investigation." : "The suggestion was applied, but checkout is still failing. Rehearse the updated state to find the remaining fix.");
}));
$("rehearse").addEventListener("click", () => operation("Testing recovery plans in isolated copies. The active lab stays unchanged; this may take a minute…", async () => {
  await api("/api/rehearse", { max_actions: Number($("max-actions").value), probe_count: Number($("probe-count").value) });
  await refreshWorkspace();
  switchTab("rehearsal");
    text("activity", state.rehearsal?.report?.summary?.abstention_reason === "missing_telemetry" ? "Rehearsal withheld: diagnostic telemetry is unavailable. No candidate changes were tested or authorized." : recommendedPlan() ? "Rehearsal complete. Review the smallest passing plan before promoting it." : state.rehearsal?.report?.control?.verification?.all_healthy ? "Rehearsal complete. The no-change control is healthy; no fix is needed." : "Rehearsal complete. No tested plan recovered checkout; review the measured outcomes.");
  $("recommendation").tabIndex = -1;
  $("recommendation").focus({ preventScroll: true });
  $("recommendation").scrollIntoView({ block: "nearest", behavior: "auto" });
}));
$("promote").addEventListener("click", () => operation("Promoting the tested recovery plan and verifying fresh traffic in the active lab…", async () => {
  const result = await api("/api/promote", { rehearsal_id: state.rehearsal.id, plan_id: state.rehearsal.report.recommended_plan_id });
  await refreshWorkspace();
  text("activity", result.verification.all_healthy ? "Recovery verified. The tested plan passed fresh requests in the active lab." : "Plan applied, but fresh verification failed. Review the new observations before another change.");
}));

operation("Connecting to your recovery workspace…", async () => {
  const [config, scenarios] = await Promise.all([api("/api/config"), api("/api/scenarios")]);
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
  text("app-version", `INCIDENTLAB ${config.version || ""} / LOCAL`);
  modeNote();
  await refreshWorkspace();
  if (state.status?.scenario_id && scenarios.some((scenario) => scenario.id === state.status.scenario_id)) $("scenario").value = state.status.scenario_id;
  if (state.status?.seed !== undefined) $("seed").value = state.status.seed;
  scenarioDescription();
  text("activity", state.record || state.rehearsal ? "Workspace restored. Continue from the saved finding or experiment." : "Lab ready. Start a scenario, investigate the evidence, then test a recovery plan.");
});
