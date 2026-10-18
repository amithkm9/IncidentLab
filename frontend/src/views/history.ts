import { artifactPath } from "../api/paths";
import type {
  History,
  InvestigationSummary,
  RehearsalHistory,
} from "../domain";
import { $, el, button, link } from "../dom";
import { state } from "../state";
import { modeNames } from "../constants";
import { dateTime } from "../format";

function emptyHistory(title: string, description: string) {
  const box = el("div", "history-empty");
  box.append(el("strong", "", title), el("p", "", description));
  return box;
}

export function renderHistory(
  history: History | null,
  openArchive: (id: string) => void | Promise<void>,
) {
  state.history = history;
  const query = $("history-search").value.trim().toLocaleLowerCase();
  const matches = (item: InvestigationSummary | RehearsalHistory) => {
    const scenario =
      state.scenarios.find((scenario) => scenario.id === item.scenario_id)
        ?.name || "";
    return (
      !query ||
      [
        item.id,
        item.episode_id,
        item.scenario_id,
        scenario,
        ...("mode" in item
          ? [item.title, item.mode, modeNames[item.mode], item.cause]
          : [item.strategy]),
      ]
        .join(" ")
        .toLocaleLowerCase()
        .includes(query)
    );
  };
  const investigations = (history?.investigations || []).filter(matches);
  const rehearsals = (history?.rehearsals || []).filter(matches);
  $("history-investigations").replaceChildren(
    ...investigations.map((item) => {
      const row = el("article", "history-row");
      const main = el("div", "history-row-main");
      const heading = el("div", "history-row-heading");
      heading.append(
        button(item.title || "Saved investigation", "history-row-title", () =>
          openArchive(item.id),
        ),
      );
      const remediationLabel = item.verified
        ? "EPISODE RECOVERED"
        : item.remediated
          ? "ACTION APPLIED"
          : "READ-ONLY FINDING";
      heading.append(
        el("span", `tag${item.verified ? " good" : ""}`, remediationLabel),
      );
      const scenario =
        state.scenarios.find((scenario) => scenario.id === item.scenario_id)
          ?.name ||
        item.scenario_id ||
        "Lab snapshot";
      main.append(
        heading,
        el(
          "div",
          "history-row-meta",
          `${dateTime(item.created_at)} · ${scenario} · ${modeNames[item.mode] || item.mode || "Investigation"}`,
        ),
      );
      const actions = el("div", "history-row-actions");
      actions.append(
        button("Inspect →", "button secondary small", () =>
          openArchive(item.id),
        ),
        link(artifactPath("postmortems", item.id), "Postmortem ↗"),
      );
      row.append(main, actions);
      return row;
    }),
  );
  if (!investigations.length)
    $("history-investigations").append(
      emptyHistory(
        query
          ? "No matching investigations."
          : "Your incident record starts here.",
        query
          ? "Try another scenario, finding, or episode ID."
          : "Run an investigation to save its finding, tool calls, and evidence.",
      ),
    );
  $("history-rehearsals").replaceChildren(
    ...rehearsals.map((item) => {
      const row = el("article", "history-row");
      const main = el("div", "history-row-main");
      const heading = el("div", "history-row-heading");
      const scenario =
        state.scenarios.find((scenario) => scenario.id === item.scenario_id)
          ?.name ||
        item.scenario_id ||
        "Lab snapshot";
      heading.append(el("strong", "history-row-title", scenario));
      heading.append(
        el("span", "tag", item.promoted ? "PLAN PROMOTED" : "EXPERIMENT SAVED"),
      );
      const tested = item.summary?.tested_plans;
      main.append(
        heading,
        el(
          "div",
          "history-row-meta",
          `${dateTime(item.created_at)}${tested !== undefined ? ` · ${tested} plans tested` : ""} · Episode ${item.episode_id}`,
        ),
      );
      const actions = el("div", "history-row-actions");
      actions.append(
        link(artifactPath("rehearsals", item.id), "Experiment JSON ↗"),
      );
      row.append(main, actions);
      return row;
    }),
  );
  if (!rehearsals.length)
    $("history-rehearsals").append(
      emptyHistory(
        query ? "No matching experiments." : "No recovery experiments yet.",
        query
          ? "Try another scenario or episode ID."
          : "Run a fix rehearsal to save the control, candidate plans, and measured outcomes.",
      ),
    );
}
