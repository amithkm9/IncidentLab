/** Every static ID is tied to its actual HTML element type. */
export interface Elements {
  "recovery-proof": HTMLElementTagNameMap["section"];
  "proof-title": HTMLElementTagNameMap["h3"];
  "proof-intro": HTMLElementTagNameMap["div"];
  prove: HTMLElementTagNameMap["button"];
  "proof-failure": HTMLElementTagNameMap["div"];
  "proof-result": HTMLElementTagNameMap["div"];
  "proof-summary": HTMLElementTagNameMap["div"];
  "proof-context": HTMLElementTagNameMap["p"];
  "proof-trials": HTMLElementTagNameMap["div"];
  "proof-necessity": HTMLElementTagNameMap["div"];
  "proof-budget": HTMLElementTagNameMap["p"];
  "proof-limitations": HTMLElementTagNameMap["ul"];
  "proof-digest": HTMLElementTagNameMap["code"];
  "proof-download": HTMLElementTagNameMap["a"];

  "nav-workbench": HTMLElementTagNameMap["button"];
  "nav-history": HTMLElementTagNameMap["button"];
  "history-count": HTMLElementTagNameMap["span"];
  "connection-dot": HTMLElementTagNameMap["span"];
  connection: HTMLElementTagNameMap["span"];
  "app-version": HTMLElementTagNameMap["small"];
  "main-content": HTMLElementTagNameMap["main"];
  "breadcrumb-page": HTMLElementTagNameMap["strong"];
  "refresh-workspace": HTMLElementTagNameMap["button"];
  error: HTMLElementTagNameMap["div"];
  "workbench-view": HTMLElementTagNameMap["section"];
  "page-title": HTMLElementTagNameMap["h1"];
  demo: HTMLElementTagNameMap["button"];
  "archive-notice": HTMLElementTagNameMap["div"];
  "return-active": HTMLElementTagNameMap["button"];
  "incident-status-dot": HTMLElementTagNameMap["span"];
  "active-scenario": HTMLElementTagNameMap["strong"];
  "scenario-kind": HTMLElementTagNameMap["span"];
  probe: HTMLElementTagNameMap["button"];
  "health-icon": HTMLElementTagNameMap["span"];
  "health-badge": HTMLElementTagNameMap["strong"];
  "health-caption": HTMLElementTagNameMap["span"];
  "request-bars": HTMLElementTagNameMap["div"];
  "error-metric": HTMLElementTagNameMap["div"];
  "error-rate": HTMLElementTagNameMap["strong"];
  "error-count": HTMLElementTagNameMap["span"];
  latency: HTMLElementTagNameMap["strong"];
  "request-count": HTMLElementTagNameMap["strong"];
  "window-label": HTMLElementTagNameMap["span"];
  "contract-health": HTMLElementTagNameMap["section"];
  "contract-health-title": HTMLElementTagNameMap["h2"];
  "contract-health-summary": HTMLElementTagNameMap["p"];
  "contract-health-badge": HTMLElementTagNameMap["span"];
  "contract-mismatch-preview": HTMLElementTagNameMap["div"];
  "contract-health-details": HTMLElementTagNameMap["details"];
  "contract-health-checks": HTMLElementTagNameMap["div"];
  "contract-version": HTMLElementTagNameMap["p"];
  "scenario-title": HTMLElementTagNameMap["h2"];
  "scenario-count": HTMLElementTagNameMap["span"];
  "scenario-form": HTMLElementTagNameMap["form"];
  scenario: HTMLElementTagNameMap["select"];
  seed: HTMLElementTagNameMap["input"];
  inject: HTMLElementTagNameMap["button"];
  "scenario-description": HTMLElementTagNameMap["p"];
  "topology-title": HTMLElementTagNameMap["h2"];
  "tab-diagnosis": HTMLElementTagNameMap["button"];
  "diagnosis-dot": HTMLElementTagNameMap["span"];
  "tab-rehearsal": HTMLElementTagNameMap["button"];
  "rehearsal-dot": HTMLElementTagNameMap["span"];
  "tab-evidence": HTMLElementTagNameMap["button"];
  "evidence-count": HTMLElementTagNameMap["span"];
  "pane-diagnosis": HTMLElementTagNameMap["div"];
  "investigate-form": HTMLElementTagNameMap["form"];
  "mode-badge": HTMLElementTagNameMap["span"];
  question: HTMLElementTagNameMap["textarea"];
  mode: HTMLElementTagNameMap["select"];
  investigate: HTMLElementTagNameMap["button"];
  "mode-note": HTMLElementTagNameMap["p"];
  "finding-empty": HTMLElementTagNameMap["div"];
  finding: HTMLElementTagNameMap["article"];
  "finding-cause": HTMLElementTagNameMap["span"];
  "finding-time": HTMLElementTagNameMap["span"];
  "finding-title": HTMLElementTagNameMap["h3"];
  "finding-explanation": HTMLElementTagNameMap["p"];
  "show-evidence": HTMLElementTagNameMap["button"];
  citations: HTMLElementTagNameMap["div"];
  "action-name": HTMLElementTagNameMap["strong"];
  "verification-plan": HTMLElementTagNameMap["p"];
  "go-rehearse": HTMLElementTagNameMap["button"];
  remediate: HTMLElementTagNameMap["button"];
  "suggestion-note": HTMLElementTagNameMap["p"];
  recovery: HTMLElementTagNameMap["div"];
  limitations: HTMLElementTagNameMap["p"];
  download: HTMLElementTagNameMap["a"];
  postmortem: HTMLElementTagNameMap["a"];
  "pane-rehearsal": HTMLElementTagNameMap["div"];
  "rehearsal-strategy": HTMLElementTagNameMap["select"];
  "experiment-budget-field": HTMLElementTagNameMap["div"];
  "max-experiments": HTMLElementTagNameMap["input"];
  "rehearsal-mode-note": HTMLElementTagNameMap["p"];
  "max-actions": HTMLElementTagNameMap["select"];
  "probe-count": HTMLElementTagNameMap["select"];
  rehearse: HTMLElementTagNameMap["button"];
  "rehearsal-scope-note": HTMLElementTagNameMap["p"];
  "rehearsal-empty": HTMLElementTagNameMap["div"];
  "rehearsal-result": HTMLElementTagNameMap["div"];
  recommendation: HTMLElementTagNameMap["div"];
  "rehearsal-run-meta": HTMLElementTagNameMap["div"];
  "plans-tested": HTMLElementTagNameMap["strong"];
  "plans-passed": HTMLElementTagNameMap["strong"];
  "minimal-actions": HTMLElementTagNameMap["strong"];
  "rehearsal-duration": HTMLElementTagNameMap["strong"];
  promotion: HTMLElementTagNameMap["div"];
  promote: HTMLElementTagNameMap["button"];
  "promotion-result": HTMLElementTagNameMap["div"];
  "experiment-count": HTMLElementTagNameMap["span"];
  "plan-filter": HTMLElementTagNameMap["select"];
  experiments: HTMLElementTagNameMap["tbody"];
  "plans-empty": HTMLElementTagNameMap["p"];
  "decision-trail-section": HTMLElementTagNameMap["section"];
  "decision-trail-title": HTMLElementTagNameMap["h3"];
  "decision-count": HTMLElementTagNameMap["span"];
  "decision-trail": HTMLElementTagNameMap["ol"];
  "rehearsal-limitations": HTMLElementTagNameMap["ul"];
  "rehearsal-download": HTMLElementTagNameMap["a"];
  "pane-evidence": HTMLElementTagNameMap["div"];
  "tool-count": HTMLElementTagNameMap["span"];
  "evidence-toolbar": HTMLElementTagNameMap["div"];
  "evidence-search": HTMLElementTagNameMap["input"];
  "expand-evidence": HTMLElementTagNameMap["button"];
  "trace-empty": HTMLElementTagNameMap["div"];
  "evidence-no-matches": HTMLElementTagNameMap["p"];
  traces: HTMLElementTagNameMap["div"];
  "run-stats": HTMLElementTagNameMap["div"];
  "next-title": HTMLElementTagNameMap["h2"];
  "next-description": HTMLElementTagNameMap["p"];
  "check-diagnosis": HTMLElementTagNameMap["li"];
  "check-rehearsal": HTMLElementTagNameMap["li"];
  "check-recovery": HTMLElementTagNameMap["li"];
  "event-count": HTMLElementTagNameMap["span"];
  timeline: HTMLElementTagNameMap["div"];
  "history-view": HTMLElementTagNameMap["section"];
  "history-title": HTMLElementTagNameMap["h1"];
  "refresh-history": HTMLElementTagNameMap["button"];
  "summary-investigations": HTMLElementTagNameMap["strong"];
  "summary-rehearsals": HTMLElementTagNameMap["strong"];
  "summary-recoveries": HTMLElementTagNameMap["strong"];
  "history-search": HTMLElementTagNameMap["input"];
  "history-investigations": HTMLElementTagNameMap["div"];
  "history-rehearsals": HTMLElementTagNameMap["div"];
  episode: HTMLElementTagNameMap["span"];
  activity: HTMLElementTagNameMap["div"];
}
export function $<K extends keyof Elements>(id: K): Elements[K] {
  const node = document.getElementById(id);
  if (!node) throw new Error(`Missing interface element: ${id}`);
  return node as Elements[K];
}
export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = "",
  value?: unknown,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = String(value);
  return node;
}
export function text(id: keyof Elements, value: unknown): void {
  $(id).textContent = String(value);
}
export function link(
  href: string,
  label: string,
  className = "text-link",
): HTMLAnchorElement {
  const node = el("a", className, label);
  node.href = href;
  return node;
}
export function button(
  label: string,
  className: string,
  handler: () => void | Promise<void>,
): HTMLButtonElement {
  const node = el("button", className, label);
  node.type = "button";
  node.addEventListener("click", handler);
  return node;
}
export function selected<K extends string>(
  id: keyof Elements,
  choices: Record<K, string>,
): K {
  const node = $(id);
  if (!(node instanceof HTMLSelectElement) || !(node.value in choices))
    throw new Error("Invalid selected option");
  return node.value as K;
}
export function required<E extends Element>(node: E | null): E {
  if (!node) throw new Error("Required interface element was not found");
  return node;
}
