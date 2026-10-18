import type { Tab, View } from "./domain";
import { $, text } from "./dom";
import { state } from "./state";
import { tabs } from "./constants";

export function switchTab(name: Tab, focus = false) {
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

export function switchView(view: View) {
  const changed = state.view !== view;
  state.view = view;
  $("workbench-view").hidden = view !== "workbench";
  $("history-view").hidden = view !== "history";
  for (const name of ["workbench", "history"] as const) {
    $(`nav-${name}`).classList.toggle("active", view === name);
    if (view === name) $(`nav-${name}`).setAttribute("aria-current", "page");
    else $(`nav-${name}`).removeAttribute("aria-current");
  }
  text(
    "breadcrumb-page",
    view === "workbench" ? "Recovery workbench" : "Incident history",
  );
  if (changed) window.scrollTo({ top: 0, behavior: "auto" });
}
