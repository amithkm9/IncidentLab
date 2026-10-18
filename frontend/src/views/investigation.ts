import type { InvestigationRecord } from "../domain";
import { $, el, text, button, required } from "../dom";
import { state, isCurrent } from "../state";
import { toolNames, modeNames, actionNames } from "../constants";
import { dateTime, duration, number } from "../format";
import { switchTab } from "../navigation";
import { verificationNotice } from "./contracts";

function revealEvidence(id: string) {
  switchTab("evidence");
  $("evidence-search").value = "";
  filterEvidence();
  const target = [
    ...document.querySelectorAll<HTMLElement>(".evidence-card"),
  ].find((node) => node.dataset.evidenceId === id);
  if (!target) return;
  required(target.closest("details")).open = true;
  target.focus({ preventScroll: true });
  target.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
    block: "center",
  });
}

export function renderFinding(record: InvestigationRecord | null) {
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
  if (!record || !result || !finding) return;
  text("finding-cause", finding.cause.replaceAll("_", " ").toUpperCase());
  text("finding-time", dateTime(record.created_at));
  text("finding-title", finding.title);
  text("finding-explanation", finding.explanation);
  text("action-name", actionNames[finding.action] || finding.action);
  text("verification-plan", finding.verification);
  text("limitations", finding.limitations);
  $("remediate").hidden = finding.action === "no_action" || state.archive;
  $("go-rehearse").hidden = state.archive;
  const suggestionTag = required(
    document.querySelector(".suggestion-heading .tag"),
  );
  suggestionTag.textContent = record.remediation
    ? "APPLIED TO LAB"
    : finding.action === "no_action"
      ? "NO MUTATION"
      : "SINGLE ACTION";
  suggestionTag.classList.toggle(
    "amber",
    !record.remediation && finding.action !== "no_action",
  );
  text(
    "suggestion-note",
    state.archive
      ? "Archived records are read-only. Return to the active incident to run new experiments."
      : record.remediation
        ? "This suggestion has been applied. Investigate again or compare recovery plans to test the current state."
        : !isCurrent(record)
          ? "The active lab has changed since this finding. Run a new investigation before applying its suggestion."
          : "A single fix may leave another fault hidden. Rehearsal compares fixes without changing this lab.",
  );
  const evidenceById = new Map(
    (result.traces || [])
      .flatMap((trace) => trace.evidence || [])
      .map((item) => [item.id, item]),
  );
  $("citations").replaceChildren(
    ...finding.evidence_ids.map((id, index) => {
      const evidence = evidenceById.get(id);
      const node = button("", "citation", () => revealEvidence(id));
      node.append(
        el("span", "citation-number", String(index + 1)),
        el("span", "", evidence?.source?.replaceAll("_", " ") || id),
      );
      node.title = evidence ? `${evidence.summary} (${id})` : id;
      node.setAttribute(
        "aria-label",
        `Open evidence ${index + 1}: ${evidence?.summary || id}`,
      );
      return node;
    }),
  );
  if (!finding.evidence_ids.length)
    $("citations").append(
      el("span", "subtle", "No diagnostic evidence was available."),
    );
  $("download").href = `/api/investigations/${record.id}`;
  $("download").download = `incidentlab-${record.id}.json`;
  $("postmortem").href = `/api/postmortems/${record.id}`;
  $("postmortem").download = `incidentlab-${record.id}-postmortem.md`;
  $("traces").replaceChildren(
    ...(result.traces || []).map((trace) => {
      const details = el("details", "trace");
      const summary = el("summary");
      summary.append(
        el("span", "trace-name", toolNames[trace.tool] || trace.tool),
        el("span", "trace-duration", duration(trace.elapsed_ms)),
      );
      const body = el("div", "trace-body");
      body.append(
        el(
          "pre",
          "trace-args",
          `${trace.tool}(${JSON.stringify(trace.arguments)})`,
        ),
      );
      if (trace.error) body.append(el("p", "notice error", trace.error));
      if (!trace.evidence?.length && !trace.error)
        body.append(el("p", "subtle", "No matching observations."));
      for (const evidence of trace.evidence || []) {
        const card = el("div", "evidence-card");
        card.dataset.evidenceId = evidence.id;
        card.tabIndex = -1;
        card.append(
          el("span", "evidence-id", `${evidence.source} / ${evidence.id}`),
          el("h4", "", evidence.summary),
        );
        card.append(
          el(
            "pre",
            "",
            evidence.source === "runbook" && evidence.data?.content
              ? evidence.data.content
              : JSON.stringify(evidence.data, null, 2),
          ),
        );
        body.append(card);
      }
      details.append(summary, body);
      return details;
    }),
  );
  filterEvidence();
  const stats = $("run-stats");
  stats.replaceChildren(
    el(
      "strong",
      "",
      `${modeNames[result.mode] || result.mode} · ${duration(result.elapsed_ms)}`,
    ),
  );
  if (result.model)
    stats.append(
      el(
        "div",
        "",
        `${result.model} · ${number(result.input_tokens)} input / ${number(result.output_tokens)} output tokens`,
      ),
    );
  stats.append(
    el(
      "div",
      "",
      result.estimated_cost_usd == null
        ? result.cost_note || "Estimated cost unavailable."
        : `$${Number(result.estimated_cost_usd).toFixed(6)} estimated · ${result.cost_note || ""}`,
    ),
  );
  const recovery = record.episode_recovery || record.remediation;
  if (recovery) {
    verificationNotice(
      $("recovery"),
      recovery,
      record.episode_recovery
        ? "Tested plan applied. Episode recovery verified."
        : "Suggestion applied. Recovery verified.",
    );
    if (
      record.episode_recovery &&
      record.remediation &&
      !record.remediation.verification.all_healthy
    ) {
      $("recovery").append(
        el(
          "div",
          "",
          `The initial single-fix attempt failed (${record.remediation.verification.statuses.join(", ")}); the later rehearsed plan restored checkout.`,
        ),
      );
    }
  }
}

export function updateEvidenceToggle() {
  const visible = [...$("traces").querySelectorAll("details")].filter(
    (node) => !node.hidden,
  );
  const allOpen = visible.length > 0 && visible.every((node) => node.open);
  text("expand-evidence", allOpen ? "Collapse all" : "Expand all");
  $("expand-evidence").disabled = !visible.length;
}

export function filterEvidence() {
  const query = $("evidence-search").value.trim().toLocaleLowerCase();
  let matches = 0;
  for (const trace of $("traces").querySelectorAll("details")) {
    const toolMatch = required(trace.querySelector("summary"))
      .textContent.toLocaleLowerCase()
      .includes(query);
    const cards = [...trace.querySelectorAll<HTMLElement>(".evidence-card")];
    for (const card of cards)
      card.hidden =
        !!query &&
        !toolMatch &&
        !card.textContent.toLocaleLowerCase().includes(query);
    trace.hidden =
      !!query &&
      (cards.length
        ? cards.every((card) => card.hidden)
        : !trace.textContent.toLocaleLowerCase().includes(query));
    if (!trace.hidden) {
      matches++;
      if (query) trace.open = true;
    }
  }
  $("evidence-no-matches").hidden = !query || matches > 0 || !state.record;
  updateEvidenceToggle();
}
