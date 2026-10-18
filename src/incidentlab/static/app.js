"use strict";
const $ = (id) => document.getElementById(id);
const state = { scenarios: [], config: null, status: null, record: null, rehearsal: null, workspace: null, history: null, busy: false, archive: false, view: "workbench", tab: "diagnosis" };
const modeNames = { baseline: "Offline baseline", mistral: "Mistral · tools + retrieval", retrieval: "Mistral · retrieval only", prompt: "Mistral · prompt only" };
const strategyNames = { exhaustive: "Compare all plans", adaptive: "Adaptive · offline policy", mistral: "Adaptive · Mistral agent" };
const stopReasonNames = { recovered: "A passing plan was found", recovery_found: "A passing plan was found", success: "A passing plan was found", budget_exhausted: "Experiment budget reached", healthy_control: "No-change control passed", control_healthy: "No-change control passed", missing_telemetry: "Diagnostic telemetry unavailable", no_candidates: "No further candidate plans", no_new_plan: "No new plan proposed", no_plan: "No further plan proposed", exhausted: "Candidate plans exhausted", completed: "Comparison completed", all_plans_tested: "All candidate plans tested", policy_abstained: "Policy abstained", agent_abstained: "Agent abstained", provider_error: "Provider request failed", invalid_plan: "Planner proposal rejected", experiment_error: "Isolated experiment failed to complete" };
const rehearsalFailures = {
  provider_error: { title: "Mistral experiment planning failed.", description: "The provider request did not complete successfully. No recovery plan was authorized; review any recorded outcomes and retry the rehearsal." },
  invalid_plan: { title: "The proposed experiment plan was rejected.", description: "The planner returned a proposal that failed validation. No recovery plan was authorized; review the record before retrying." },
  experiment_error: { title: "An isolated experiment could not complete.", description: "The lab could not finish measuring a candidate plan. No recovery plan was authorized; review any recorded outcomes before retrying." },
};
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
function semanticState(verification) {
  const checks = Array.isArray(verification?.semantic_checks) ? verification.semantic_checks : [];
  const known = typeof verification?.semantic_passed === "boolean";
  const evaluated = checks.filter((check) => check.evaluated);
  const failed = evaluated.filter((check) => !check.passed);
  return { known, checks, evaluated, failed, passed: known && verification.semantic_passed === true };
}
function httpHealthy(verification) {
  return typeof verification?.all_http_healthy === "boolean" ? verification.all_http_healthy
    : !!verification?.statuses?.length && verification.statuses.every((code) => code === 200);
}
function recoveryVerified(verification) {
  return !!verification?.all_healthy && httpHealthy(verification) && semanticState(verification).passed;
}
function totalLabel(cents, contract) {
  if (typeof cents !== "number" || !Number.isFinite(cents)) return "Not returned";
  if (contract?.currency) {
    try { return new Intl.NumberFormat(undefined, { style: "currency", currency: contract.currency }).format(cents / 100); } catch { /* Use explicit decimal amounts for older or invalid currency metadata. */ }
  }
  return `${(cents / 100).toFixed(2)}${contract?.currency ? ` ${contract.currency}` : ""}`;
}
function mismatchLabel(check, contract) {
  if (!check.evaluated) return `${check.sku}: business checks unavailable after HTTP ${check.http_status}.`;
  const price = `${check.sku}: expected ${totalLabel(check.expected_total_cents, contract)}, observed ${totalLabel(check.observed_total_cents, contract)}`;
  return check.observed_sku !== check.sku ? `${price}; expected SKU ${check.sku}, observed ${check.observed_sku ?? "not returned"}.` : `${price}.`;
}
function verificationSummary(verification) {
  const semantic = semanticState(verification);
  const requests = verification?.requests ?? verification?.statuses?.length ?? 0;
  if (!semantic.known) return `HTTP responses: ${(verification?.statuses || []).join(", ") || "not recorded"}. Business correctness was not recorded in this report.`;
  if (recoveryVerified(verification)) return `${requests} of ${requests} fresh requests passed HTTP, price, and SKU checks.`;
  if (httpHealthy(verification)) return `All ${requests} requests returned HTTP 200, but ${semantic.failed.length || "one or more"} response${semantic.failed.length === 1 ? "" : "s"} violated the business contract.`;
  return `HTTP responses: ${(verification?.statuses || []).join(", ") || "not recorded"}. ${semantic.evaluated.length} responses were evaluated for business correctness${semantic.failed.length ? `; ${semantic.failed.length} failed` : ""}.`;
}
function providerFailureLabel(failure) {
  const categories = {
    authentication: "Provider authentication failed", rate_limited: "Provider rate limit",
    provider_unavailable: "Provider unavailable", request_rejected: "Provider rejected the request",
    transport_timeout: "Provider request timed out", transport_error: "Provider connection failed",
    invalid_response: "Provider returned an invalid response", unknown_provider_error: "Provider request failed",
  };
  const label = categories[failure?.category];
  if (typeof label !== "string") return null;
  const status = failure.status_code;
  const retry = failure.retry_after_seconds;
  const validStatus = Number.isInteger(status) && status >= 100 && status <= 599;
  const validRetry = typeof retry === "number" && Number.isFinite(retry) && retry >= 0 && retry <= 3600;
  return `${label}${validStatus ? ` (HTTP ${status})` : ""}.${validRetry ? ` Retry after ${Math.ceil(retry)} seconds.` : ""}`;
}
function contractChecks(checks, contract) {
  return checks.map((check) => {
    const item = el("div", `contract-check${check.evaluated && !check.passed ? " failed" : ""}`);
    const heading = el("div", "contract-check-heading");
    heading.append(el("strong", "", check.sku), el("span", "", !check.evaluated ? `Not evaluated · HTTP ${check.http_status}` : check.passed ? `Contract passed · HTTP ${check.http_status}` : `Contract failed · HTTP ${check.http_status}`));
    const values = el("dl", "contract-values");
    for (const [label, value] of [["Expected total", totalLabel(check.expected_total_cents, contract)], ["Observed total", totalLabel(check.observed_total_cents, contract)], ["Expected SKU", check.sku], ["Observed SKU", check.observed_sku ?? "Not returned"]]) {
      const pair = el("div");
      pair.append(el("dt", "", label), el("dd", "", value));
      values.append(pair);
    }
    item.append(heading, values);
    if (check.evaluated && check.violations?.length) item.append(el("p", "contract-violations", check.violations.map((code) => code.replaceAll("_", " ")).join(" · ")));
    return item;
  });
}
function appendContractDetails(target, verification, preview = true) {
  const semantic = semanticState(verification);
  const label = !semantic.known ? "Business checks not recorded" : semantic.failed.length ? `${semantic.failed.length} business contract failure${semantic.failed.length === 1 ? "" : "s"}` : semantic.passed ? "Price & SKU contracts passed" : semantic.evaluated.length ? "Business checks incomplete" : "Business checks not evaluated";
  target.append(el("span", `contract-outcome${semantic.failed.length ? " failed" : semantic.passed ? " passed" : ""}`, label));
  if (preview && semantic.failed.length) target.append(el("p", "contract-inline-mismatch", mismatchLabel(semantic.failed[0], verification.contract)));
  if (semantic.checks.length) {
    const details = el("details", "contract-details compact");
    details.append(el("summary", "", `Inspect ${semantic.checks.length} response checks`));
    const list = el("div", "contract-check-list");
    list.append(...contractChecks(semantic.checks, verification.contract));
    details.append(list);
    target.append(details);
  }
}
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
    const error = new Error("Could not reach the lab. Check that the server is running, then use Refresh workspace to reconnect.");
    error.connectionLost = true;
    throw error;
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
  $("promote").disabled = locked || !isCurrent(state.rehearsal) || !recoveryVerified(plan?.verification) || !!state.rehearsal?.promotion;
  $("refresh-history").disabled = state.busy;
  $("refresh-workspace").disabled = state.busy;
  $("return-active").disabled = state.busy;
  $("main-content").setAttribute("aria-busy", String(state.busy));
  document.body.classList.toggle("is-busy", state.busy || !!state.status?.busy);
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
    if (error.connectionLost) {
      text("connection", "Connection interrupted");
      $("connection-dot").classList.add("offline");
    }
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
  const changed = state.view !== view;
  state.view = view;
  $("workbench-view").hidden = view !== "workbench";
  $("history-view").hidden = view !== "history";
  for (const name of ["workbench", "history"]) {
    $(`nav-${name}`).classList.toggle("active", view === name);
    if (view === name) $(`nav-${name}`).setAttribute("aria-current", "page");
    else $(`nav-${name}`).removeAttribute("aria-current");
  }
  text("breadcrumb-page", view === "workbench" ? "Recovery workbench" : "Incident history");
  if (changed) window.scrollTo({ top: 0, behavior: "auto" });
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
function rehearsalStrategyNote() {
  const strategy = $("rehearsal-strategy").value;
  const adaptive = strategy !== "exhaustive";
  $("experiment-budget-field").hidden = !adaptive;
  text("rehearsal-mode-note", strategy === "mistral"
    ? `The Mistral agent chooses the next plan from lab evidence and previous outcomes. Sanitized logs, metrics, service health, business contract checks, and experiment observations are sent to ${state.config?.model || "the configured Mistral model"} through the Mistral API. Calls can incur provider charges; usage is recorded.`
    : adaptive
      ? "A deterministic offline policy chooses the next plan using observed failures and earlier experiment results. No model API calls. It may leave plans untested when it stops."
      : "Compare every candidate within the selected plan size. No model API calls. The selected result is minimal within this tested set.");
  text("rehearsal-scope-note", adaptive
    ? "The budget limits candidate experiments; a no-change control is measured separately. The active lab stays unchanged."
    : `Up to ${$("max-actions").value === "1" ? "5" : "15"} candidate plans + a no-change control. Your active lab stays unchanged.`);
}
function renderStatus(status) {
  state.status = status;
  text("connection", status.busy ? "Lab operation in progress" : "Lab connected");
  $("connection-dot").classList.remove("offline");
  const transportErrors = status.http_errors ?? status.errors ?? 0;
  const semanticFailures = status.semantic_failures ?? 0;
  const contractsKnown = typeof status.semantic_checked_requests === "number";
  const failing = transportErrors > 0 || semanticFailures > 0;
  const noRequests = !status.requests;
  const scenario = state.scenarios.find((item) => item.id === status.scenario_id);
  text("active-scenario", scenario?.name || "Active incident");
  text("scenario-kind", scenario?.fault_count > 1 ? "COMPOUND FAULT" : scenario?.fault_count === 1 ? "SINGLE FAULT" : "CONTROL SCENARIO");
  $("scenario-kind").classList.toggle("amber", !!scenario?.fault_count);
  $("incident-status-dot").classList.toggle("failing", failing);
  $("error-metric").classList.toggle("failing", transportErrors > 0);
  const card = $("health-badge").closest(".health-card");
  card.classList.toggle("failing", failing);
  card.classList.toggle("unobserved", noRequests);
  text("health-badge", noRequests ? "Awaiting requests" : failing ? "Degraded" : contractsKnown ? "Healthy" : "HTTP healthy");
  text("health-caption", !status.telemetry_available ? "Diagnostic telemetry unavailable" : semanticFailures > 0 && transportErrors === 0 ? "HTTP 200 · business checks fail" : transportErrors > 0 ? "Checkout requests failing" : contractsKnown ? "Availability + contracts passed" : "Business checks not recorded");
  text("request-count", number(status.requests));
  text("error-count", number(transportErrors));
  text("error-rate", `${status.requests ? Math.round(transportErrors / status.requests * 100) : 0}%`);
  $("latency").replaceChildren(document.createTextNode(Number(status.median_latency_ms || 0).toFixed(1)), el("small", "", "ms"));
  text("window-label", `Observation window ${status.window}`);
  $("request-bars").replaceChildren(...(status.recent_statuses || []).map((code) => {
    const bar = el("span", `request-bar${code >= 400 ? " failed" : ""}`);
    bar.title = `HTTP ${code}`;
    bar.setAttribute("aria-label", `HTTP ${code}`);
    return bar;
  }));
  text("episode", `EPISODE ${status.episode_id} / SEED ${status.seed} / REV ${status.revision ?? 0}`);
  renderContractStatus(status);
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
function renderContractStatus(status) {
  const known = typeof status.semantic_checked_requests === "number";
  const checked = Number(status.semantic_checked_requests || 0);
  const failed = Number(status.semantic_failures || 0);
  const checks = Array.isArray(status.recent_semantic_checks) ? status.recent_semantic_checks : [];
  const passing = known && status.requests > 0 && checked === status.requests && failed === 0;
  $("contract-health").classList.toggle("failed", failed > 0);
  $("contract-health").classList.toggle("passed", passing);
  text("contract-health-title", failed ? "Successful responses contain incorrect checkout results." : passing ? "Correct prices. Correct products." : known ? "Business checks follow successful responses." : "Business correctness is not recorded.");
  text("contract-health-badge", failed ? `${number(failed)} CONTRACT FAILURE${failed === 1 ? "" : "S"}` : passing ? "CONTRACTS PASSED" : known ? "AWAITING VALID RESPONSES" : "HTTP-ONLY OBSERVATIONS");
  $("contract-health-badge").classList.toggle("amber", failed > 0);
  text("contract-health-summary", !known ? "This observation window only records transport health. HTTP 200 alone does not establish that checkout totals or product IDs are correct."
    : checked ? `${number(checked - failed)} of ${number(checked)} evaluated responses matched the expected price and SKU.${status.requests > checked ? ` ${number(status.requests - checked)} requests could not be evaluated after an HTTP failure.` : ""}`
      : "No successful checkout responses have been evaluated yet. HTTP failures must be resolved before prices and product IDs can be checked.");
  const mismatch = checks.find((check) => check.evaluated && !check.passed);
  $("contract-mismatch-preview").hidden = !mismatch;
  text("contract-mismatch-preview", mismatch ? mismatchLabel(mismatch, status.contract) : "");
  $("contract-health-details").hidden = !checks.length;
  $("contract-health-checks").replaceChildren(...contractChecks(checks, status.contract));
  $("contract-version").hidden = !status.contract;
  text("contract-version", status.contract ? `Contract ${status.contract.id} · version ${status.contract.version} · expected values are independent of the response.` : "");
}
function revealEvidence(id) {
  switchTab("evidence");
  $("evidence-search").value = "";
  filterEvidence();
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
  const semantic = semanticState(verification);
  const recovered = recoveryVerified(verification);
  target.className = `notice${!semantic.known && httpHealthy(verification) ? " neutral" : recovered ? "" : " error"}`;
  target.textContent = `${recovered ? successText : !semantic.known && httpHealthy(verification) ? "Availability was verified; full recovery was not established." : "Recovery not verified."} ${verificationSummary(verification)}`;
  appendContractDetails(target, verification);
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
  $("evidence-toolbar").hidden = !finding;
  $("evidence-no-matches").hidden = true;
  $("investigate-form").hidden = state.archive;
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
  filterEvidence();
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
  $("rehearsal-run-meta").replaceChildren();
  $("decision-trail").replaceChildren();
  $("decision-trail-section").hidden = true;
  if (!report) return;
  const plan = recommendedPlan();
  const controlHealthy = report.control?.verification?.all_healthy || report.summary?.control_healthy;
  const controlSemantic = semanticState(report.control?.verification);
  const planSemantic = semanticState(plan?.verification);
  const missingTelemetry = report.summary?.abstention_reason === "missing_telemetry";
  const planningFailure = rehearsalFailures[report.budget?.stop_reason];
  const recommendation = $("recommendation");
  recommendation.className = `recommendation${!plan && !controlHealthy ? " warning" : ""}`;
  recommendation.replaceChildren(el("span", "recommendation-icon", plan || controlHealthy ? "✓" : "!"));
  const message = el("div");
  message.append(el("h3", "", planningFailure ? planningFailure.title : missingTelemetry ? "Rehearsal withheld: diagnostic telemetry unavailable." : controlHealthy ? controlSemantic.known ? "The control passed availability and business checks." : "The control passed the recorded HTTP checks." : plan ? planSemantic.passed ? `${plan.actions.length === 1 ? "One action" : `${plan.actions.length} actions`} recovered this snapshot.` : "A plan passed the recorded HTTP checks." : "No tested plan recovered checkout."));
  message.append(el("p", "", planningFailure ? planningFailure.description : missingTelemetry ? "No candidate fixes were tested or authorized. Restore diagnostic evidence before selecting a recovery action." : controlHealthy
    ? controlSemantic.known ? "Fresh requests matched the expected price and SKU without changes. No remediation is recommended." : "Business correctness was not recorded in this older report. Run a new rehearsal to check response contracts."
    : plan ? planSemantic.known ? `${actionLabel(plan.actions)}. Fresh responses passed HTTP, price, and SKU checks. This is the smallest passing tested plan.` : `${actionLabel(plan.actions)}. Business correctness was not recorded. Run a new rehearsal before promoting a change.`
      : "Review the evidence and experiment outcomes. A larger plan or a different intervention may be needed."));
  const providerDetail = providerFailureLabel(report.error?.provider_failure);
  if (providerDetail) message.append(el("p", "provider-failure-detail", providerDetail));
  recommendation.append(message);
  text("plans-tested", number(report.summary?.tested_plans ?? report.experiments?.length));
  text("plans-passed", number(report.summary?.successful_plans ?? report.experiments?.filter((item) => item.verification.all_healthy).length));
  text("minimal-actions", controlHealthy ? "0" : report.summary?.minimal_action_count ?? plan?.actions.length ?? "—");
  text("rehearsal-duration", duration(report.elapsed_ms));
  renderRehearsalRun(report);
  renderExperiments();
  $("promotion").hidden = !plan || !!record.promotion || state.archive;
  const promotionDescription = $("promotion").querySelector("p");
  promotionDescription.textContent = !planSemantic.known ? "This older report has no business contract checks. Run a new rehearsal before promoting a plan." : isCurrent(record)
    ? "Apply the smallest passing tested plan, then verify fresh HTTP responses, prices, and product IDs in the active lab."
    : "The lab has changed since this experiment. Run a new rehearsal before promoting a plan.";
  $("rehearsal-limitations").replaceChildren(...(report.limitations || []).map((limitation) => el("li", "", limitation)));
  $("rehearsal-download").href = `/api/rehearsals/${record.id}`;
  $("rehearsal-download").download = `incidentlab-rehearsal-${record.id}.json`;
  if (record.promotion) verificationNotice($("promotion-result"), record.promotion, "Tested plan applied. Recovery verified.");
}
function renderRehearsalRun(report) {
  const strategy = report.strategy || "exhaustive";
  const meta = $("rehearsal-run-meta");
  const heading = el("div", "rehearsal-run-heading");
  heading.append(el("strong", "", strategyNames[strategy] || strategy.replaceAll("_", " ")));
  const budget = report.budget;
  if (budget) {
    const count = budget.used_experiments ?? report.summary?.tested_plans ?? 0;
    const cap = budget.max_experiments;
    heading.append(el("span", "tag", `${number(count)}${cap != null ? ` / ${number(cap)}` : ""} EXPERIMENTS`));
  }
  meta.append(heading);
  if (budget?.stop_reason) meta.append(el("p", "", `Stopped: ${stopReasonNames[budget.stop_reason] || budget.stop_reason.replaceAll("_", " ")}.`));
  const usage = report.provider_usage;
  if (strategy === "mistral" || usage?.model || usage?.api_calls > 0) {
    if (usage) {
      const parts = [usage.model || "Model not recorded"];
      if (usage.api_calls != null) parts.push(`${number(usage.api_calls)} API calls`);
      if (usage.input_tokens != null && usage.output_tokens != null) parts.push(`${number(usage.input_tokens)} input / ${number(usage.output_tokens)} output tokens`);
      meta.append(el("p", "", parts.join(" · ")));
      const hasCost = typeof usage.estimated_cost_usd === "number" && Number.isFinite(usage.estimated_cost_usd);
      meta.append(el("p", "", `${hasCost ? `$${usage.estimated_cost_usd.toFixed(6)} estimated API cost` : "API cost not estimated"}${usage.cost_note ? ` · ${usage.cost_note}` : ""}`));
    } else meta.append(el("p", "", "Provider usage was not recorded in this saved report."));
  } else meta.append(el("p", "", strategy === "adaptive" ? "Offline policy · no model API calls. Only the selected candidates were tested." : "Exhaustive comparison within the selected plan size · no model API calls."));
  const decisions = Array.isArray(report.decision_trace) ? report.decision_trace : [];
  $("decision-trail-section").hidden = !decisions.length;
  text("decision-count", `${decisions.length} ${decisions.length === 1 ? "STEP" : "STEPS"}`);
  $("decision-trail").replaceChildren(...decisions.map((decision, index) => {
    const item = el("li", "decision-item");
    const top = el("div", "decision-item-heading");
    const step = decision.step ?? index + 1;
    top.append(el("span", "decision-step", String(step)), el("strong", "", decision.actions?.length ? actionLabel(decision.actions) : "Planning stopped"));
    const outcome = typeof decision.outcome === "string" ? decision.outcome.replaceAll("_", " ") : "Outcome not recorded";
    top.append(el("span", "tag", outcome));
    item.append(top);
    if (decision.hypothesis) item.append(el("p", "decision-hypothesis", decision.hypothesis));
    const statuses = Array.isArray(decision.statuses) ? decision.statuses : [];
    if (statuses.length) {
      const observed = el("div", "decision-observations");
      observed.append(el("span", "", "Observed HTTP"));
      const codes = el("div", "http-codes");
      for (const code of statuses) {
        const codeNode = el("span", `http-code${code >= 400 ? " failed" : ""}`, String(code));
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
      for (const id of decision.evidence_ids) citations.append(el("code", "", id));
      item.append(citations);
    }
    return item;
  }));
}
function renderExperiments() {
  const report = state.rehearsal?.report;
  if (!report) return;
  const plan = recommendedPlan();
  const all = [report.control, plan, ...(report.experiments || []).filter((item) => item.id !== plan?.id)].filter(Boolean);
  const filter = $("plan-filter").value;
  const experiments = all.filter((item) => filter === "all" || (filter === "passed") === !!item.verification?.all_healthy);
  text("experiment-count", `${experiments.length} shown · ${all.length} total with control`);
  $("plans-empty").hidden = !!experiments.length;
  $("experiments").replaceChildren(...experiments.map((experiment) => {
    const recommended = experiment.id === report.recommended_plan_id;
    const row = el("tr", recommended ? "recommended" : "");
    const labelCell = el("td");
    labelCell.append(el("span", "plan-label", actionLabel(experiment.actions)));
    if (recommended) labelCell.append(el("small", "", "SMALLEST PASSING TESTED PLAN"));
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
    const semantic = semanticState(experiment.verification);
    resultCell.append(el("span", `result-pill${passed && semantic.passed ? "" : !semantic.known && passed ? " legacy" : " failed"}`, passed ? semantic.passed ? "Verified" : "HTTP only" : "Failed"));
    if (httpHealthy(experiment.verification) && semantic.known && !semantic.passed) resultCell.append(el("span", "false-recovery-label", "HTTP 200 ≠ recovery"));
    appendContractDetails(labelCell, experiment.verification);
    row.append(labelCell, responsesCell, el("td", "", `${Number(experiment.verification?.median_latency_ms || 0).toFixed(1)} ms`), resultCell);
    return row;
  }));
}
function updateEvidenceToggle() {
  const visible = [...$("traces").querySelectorAll("details")].filter((node) => !node.hidden);
  const allOpen = visible.length > 0 && visible.every((node) => node.open);
  text("expand-evidence", allOpen ? "Collapse all" : "Expand all");
  $("expand-evidence").disabled = !visible.length;
}
function filterEvidence() {
  const query = $("evidence-search").value.trim().toLocaleLowerCase();
  let matches = 0;
  for (const trace of $("traces").querySelectorAll("details")) {
    const toolMatch = trace.querySelector("summary").textContent.toLocaleLowerCase().includes(query);
    const cards = [...trace.querySelectorAll(".evidence-card")];
    for (const card of cards) card.hidden = !!query && !toolMatch && !card.textContent.toLocaleLowerCase().includes(query);
    trace.hidden = !!query && (cards.length ? cards.every((card) => card.hidden) : !trace.textContent.toLocaleLowerCase().includes(query));
    if (!trace.hidden) { matches++; if (query) trace.open = true; }
  }
  $("evidence-no-matches").hidden = !query || matches > 0 || !state.record;
  updateEvidenceToggle();
}
function renderNextStep() {
  const hasFinding = !!state.record;
  const hasRehearsal = !!state.rehearsal;
  const latestRecovery = state.record?.episode_recovery || state.rehearsal?.promotion || state.record?.remediation;
  const recovered = recoveryVerified(latestRecovery?.verification);
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
    description = "Fresh requests passed HTTP availability and matched expected prices and product IDs. Export the evidence or start another incident.";
  } else if (state.rehearsal?.report?.summary?.abstention_reason === "missing_telemetry") {
    title = "Restore the missing evidence";
    description = "Diagnostic telemetry is unavailable. No candidate changes were tested or authorized for this snapshot.";
  } else if (rehearsalFailures[state.rehearsal?.report?.budget?.stop_reason]) {
    title = state.rehearsal.report.budget.stop_reason === "experiment_error" ? "Review the experiment failure" : "Review the planning failure";
    description = "The rehearsal could not produce an authorized recovery plan. Inspect the saved outcome, then retry or choose another strategy.";
  } else if (hasRehearsal && recoveryVerified(recommendedPlan()?.verification) && isCurrent(state.rehearsal)) {
    title = "Promote a tested plan";
    description = "The comparison found a plan that passes HTTP and business contract checks. Apply it, then verify fresh responses in the active lab.";
  } else if (latestRecovery) {
    title = !semanticState(latestRecovery.verification).known ? "Availability-only recovery record" : httpHealthy(latestRecovery.verification) ? "HTTP 200 is not a full recovery" : "A fault may still remain";
    description = !semanticState(latestRecovery.verification).known ? "This record does not include business checks. Rehearse the current state to verify prices and product IDs." : httpHealthy(latestRecovery.verification) ? "Requests are reaching checkout, but the returned business data is still wrong. Rehearse the updated state to test a complete fix." : "The last fix did not restore healthy requests. Run a new rehearsal against the updated state to find the remaining intervention.";
  } else if (hasRehearsal && state.rehearsal.report?.control?.verification?.all_healthy) {
    title = semanticState(state.rehearsal.report.control.verification).known ? "Keep the healthy control" : "Recheck business correctness";
    description = semanticState(state.rehearsal.report.control.verification).known ? "The no-change control passed HTTP, price, and SKU checks. No fix is needed for this snapshot." : "This saved control only recorded HTTP availability. A new rehearsal can verify expected prices and product IDs.";
  } else if (hasFinding) {
    title = "Put the suggestion to a test";
    description = "Rehearse single fixes and combinations. A second fault can stay hidden until the first one is repaired.";
  } else if (state.status?.semantic_failures > 0 && !state.status?.http_errors) {
    title = "Look beyond the status code";
    description = "Checkout returns HTTP 200, but price or product checks are failing. Investigate the contract evidence before selecting a fix.";
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
  const query = $("history-search").value.trim().toLocaleLowerCase();
  const matches = (item) => {
    const scenario = state.scenarios.find((scenario) => scenario.id === item.scenario_id)?.name || "";
    return !query || [item.title, item.id, item.episode_id, item.scenario_id, scenario, item.mode, modeNames[item.mode], item.cause].join(" ").toLocaleLowerCase().includes(query);
  };
  const investigations = (history?.investigations || []).filter(matches);
  const rehearsals = (history?.rehearsals || []).filter(matches);
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
  if (!investigations.length) $("history-investigations").append(emptyHistory(query ? "No matching investigations." : "Your incident record starts here.", query ? "Try another scenario, finding, or episode ID." : "Run an investigation to save its finding, tool calls, and evidence."));
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
  if (!rehearsals.length) $("history-rehearsals").append(emptyHistory(query ? "No matching experiments." : "No recovery experiments yet.", query ? "Try another scenario or episode ID." : "Run a fix rehearsal to save the control, candidate plans, and measured outcomes."));
}
async function openArchive(id) {
  await operation("Opening the saved investigation and its evidence…", async () => {
    const record = await api(`/api/investigations/${id}`);
    const rehearsal = record.rehearsal_id ? await api(`/api/rehearsals/${record.rehearsal_id}`) : null;
    state.archive = true;
    $("archive-notice").hidden = false;
    renderFinding(record);
    renderRehearsal(rehearsal);
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
$("refresh-workspace").addEventListener("click", () => operation("Refreshing the recovery workspace…", async () => {
  if (!state.config) await loadConfiguration();
  if (state.view === "history") await refreshHistory();
  else await refreshWorkspace();
  text("activity", "Workspace refreshed from the active lab.");
}));
$("plan-filter").addEventListener("change", renderExperiments);
$("evidence-search").addEventListener("input", filterEvidence);
$("traces").addEventListener("toggle", updateEvidenceToggle, true);
$("expand-evidence").addEventListener("click", () => {
  const visible = [...$("traces").querySelectorAll("details")].filter((node) => !node.hidden);
  const shouldOpen = !visible.every((node) => node.open);
  for (const trace of visible) trace.open = shouldOpen;
  updateEvidenceToggle();
});
$("history-search").addEventListener("input", () => renderHistory(state.history));
$("demo").addEventListener("click", () => operation("Starting a route fault that masks silently incorrect checkout totals…", async () => {
  $("scenario").value = "route_and_price_drift";
  $("seed").value = 42;
  $("mode").value = "baseline";
  $("rehearsal-strategy").value = "adaptive";
  $("max-experiments").value = "4";
  $("max-actions").value = "2";
  $("question").value = "Investigate checkout availability and business correctness. Identify observed failures and propose an evidence-backed fix.";
  $("evidence-search").value = "";
  $("plan-filter").value = "all";
  scenarioDescription();
  modeNote();
  rehearsalStrategyNote();
  await api("/api/inject", { scenario_id: "route_and_price_drift", seed: 42 });
  await refreshWorkspace();
  await api("/api/investigate", { mode: "baseline", question: $("question").value });
  await refreshWorkspace();
  switchTab("diagnosis");
  text("activity", "Offline demo ready. A route fault masks incorrect totals. Rehearse with the offline adaptive policy to see why HTTP 200 alone is not recovery.");
  $("finding-title").tabIndex = -1;
  $("finding-title").focus({ preventScroll: true });
  $("finding").scrollIntoView({ block: "nearest", behavior: "auto" });
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
  text("activity", `Probe complete. ${verificationSummary(result.verification)}`);
}));
$("show-evidence").addEventListener("click", () => switchTab("evidence", true));
$("go-rehearse").addEventListener("click", () => switchTab("rehearsal", true));
$("rehearsal-strategy").addEventListener("change", rehearsalStrategyNote);
$("max-actions").addEventListener("change", rehearsalStrategyNote);
$("remediate").addEventListener("click", () => operation("Applying the single proposed fix and verifying fresh requests…", async () => {
  const result = await api("/api/remediate", { investigation_id: state.record.id, action: state.record.result.finding.action });
  await refreshWorkspace();
  text("activity", `Suggestion applied. ${verificationSummary(result.verification)}${recoveryVerified(result.verification) ? "" : " Rehearse the updated state before another change."}`);
}));
$("rehearse").addEventListener("click", () => {
  const strategy = $("rehearsal-strategy").value;
  if (strategy !== "exhaustive" && !$("max-experiments").reportValidity()) return;
  operation(strategy === "mistral" ? "Mistral is selecting experiments from lab observations. Isolated tests may take a few minutes; the active lab stays unchanged…" : "Testing recovery plans in isolated copies. The active lab stays unchanged; this may take a minute…", async () => {
  await api("/api/rehearse", { strategy, max_experiments: strategy === "exhaustive" ? 4 : Number($("max-experiments").value), max_actions: Number($("max-actions").value), probe_count: Number($("probe-count").value) });
  await refreshWorkspace();
  switchTab("rehearsal");
  const stopReason = state.rehearsal?.report?.budget?.stop_reason;
  text("activity", rehearsalFailures[stopReason] ? `Rehearsal stopped: ${stopReasonNames[stopReason].toLowerCase()}. No recovery plan was authorized; review the saved outcome.` : state.rehearsal?.report?.summary?.abstention_reason === "missing_telemetry" ? "Rehearsal withheld: diagnostic telemetry is unavailable. No candidate changes were tested or authorized." : recommendedPlan() ? "Rehearsal complete. Review the smallest passing tested plan before promoting it." : state.rehearsal?.report?.control?.verification?.all_healthy ? "Rehearsal complete. The no-change control is healthy; no fix is needed." : "Rehearsal complete. No tested plan recovered checkout; review the measured outcomes.");
  $("recommendation").tabIndex = -1;
  $("recommendation").focus({ preventScroll: true });
  $("recommendation").scrollIntoView({ block: "start", behavior: "auto" });
  });
});
$("promote").addEventListener("click", () => operation("Promoting the tested recovery plan and verifying fresh traffic in the active lab…", async () => {
  const result = await api("/api/promote", { rehearsal_id: state.rehearsal.id, plan_id: state.rehearsal.report.recommended_plan_id });
  await refreshWorkspace();
  text("activity", `Tested plan applied. ${verificationSummary(result.verification)}`);
}));

async function loadConfiguration() {
  const [config, scenarios] = await Promise.all([api("/api/config"), api("/api/scenarios")]);
  state.config = config;
  state.scenarios = scenarios;
  text("scenario-count", `${scenarios.length} SCENARIOS`);
  const groups = [
    ["Compound incidents · two faults", (scenario) => scenario.fault_count > 1],
    ["Single-fault incidents", (scenario) => scenario.fault_count === 1],
    ["Control scenarios", (scenario) => !scenario.fault_count],
  ];
  $("scenario").replaceChildren(...groups.map(([label, matches]) => {
    const group = el("optgroup");
    group.label = label;
    group.append(...scenarios.filter(matches).map((scenario) => {
      const option = el("option", "", scenario.name);
      option.value = scenario.id;
      return option;
    }));
    return group;
  }));
  for (const option of $("mode").options) {
    option.disabled = option.value !== "baseline" && !config.mistral_configured;
    option.textContent = `${modeNames[option.value] || option.value}${option.disabled ? " · API key required" : ""}`;
  }
  for (const option of $("rehearsal-strategy").options) {
    option.disabled = option.value === "mistral" && !config.mistral_configured;
    option.textContent = `${strategyNames[option.value] || option.value}${option.disabled ? " · API key required" : ""}`;
  }
  if ($("rehearsal-strategy").value === "mistral" && !config.mistral_configured) $("rehearsal-strategy").value = "exhaustive";
  text("app-version", `INCIDENTLAB ${config.version || ""} / LOCAL`);
  modeNote();
  rehearsalStrategyNote();
}
operation("Connecting to your recovery workspace…", async () => {
  await loadConfiguration();
  await refreshWorkspace();
  if (state.status?.scenario_id && state.scenarios.some((scenario) => scenario.id === state.status.scenario_id)) $("scenario").value = state.status.scenario_id;
  if (state.status?.seed !== undefined) $("seed").value = state.status.seed;
  scenarioDescription();
  text("activity", state.record || state.rehearsal ? "Workspace restored. Continue from the saved finding or experiment." : "Lab ready. Start a scenario, investigate the evidence, then test a recovery plan.");
});
