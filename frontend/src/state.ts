import type {
  BoundRecord,
  Config,
  History,
  InvestigationRecord,
  RehearsalRecord,
  Scenario,
  Status,
  Tab,
  View,
  Workspace,
} from "./domain";

import { matchesSnapshot } from "./recovery";

interface AppState {
  scenarios: Scenario[];
  config: Config | null;
  status: Status | null;
  record: InvestigationRecord | null;
  rehearsal: RehearsalRecord | null;
  workspace: Workspace | null;
  workspaceFresh: boolean;
  history: History | null;
  busy: boolean;
  archive: boolean;
  view: View;
  tab: Tab;
}
export const state: AppState = {
  scenarios: [],
  config: null,
  status: null,
  record: null,
  rehearsal: null,
  workspace: null,
  workspaceFresh: false,
  history: null,
  busy: false,
  archive: false,
  view: "workbench",
  tab: "diagnosis",
};

export function isCurrent(record?: BoundRecord | null) {
  return matchesSnapshot(record, state.status);
}

export function recommendedPlan() {
  const report = state.rehearsal?.report;
  return (
    report?.experiments?.find(
      (plan) => plan.id === report.recommended_plan_id,
    ) || null
  );
}
