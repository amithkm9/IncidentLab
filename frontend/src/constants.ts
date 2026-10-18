import type { Action, Mode, Strategy } from "./domain";

export const modeNames: Record<Mode, string> = {
  baseline: "Offline baseline",
  mistral: "Mistral · tools + retrieval",
  retrieval: "Mistral · retrieval only",
  prompt: "Mistral · prompt only",
};
export const strategyNames: Record<Strategy, string> = {
  exhaustive: "Compare all plans",
  adaptive: "Adaptive · offline policy",
  mistral: "Adaptive · Mistral agent",
};
export const stopReasonNames: Record<string, string> = {
  recovered: "A passing plan was found",
  recovery_found: "A passing plan was found",
  success: "A passing plan was found",
  budget_exhausted: "Experiment budget reached",
  healthy_control: "No-change control passed",
  control_healthy: "No-change control passed",
  missing_telemetry: "Diagnostic telemetry unavailable",
  no_candidates: "No further candidate plans",
  no_new_plan: "No new plan proposed",
  no_plan: "No further plan proposed",
  exhausted: "Candidate plans exhausted",
  completed: "Comparison completed",
  all_plans_tested: "All candidate plans tested",
  policy_abstained: "Policy abstained",
  agent_abstained: "Agent abstained",
  provider_error: "Provider request failed",
  invalid_plan: "Planner proposal rejected",
  experiment_error: "Isolated experiment failed to complete",
};
export const rehearsalFailures: Record<
  string,
  { title: string; description: string }
> = {
  provider_error: {
    title: "Mistral experiment planning failed.",
    description:
      "The provider request did not complete successfully. No recovery plan was authorized; review any recorded outcomes and retry the rehearsal.",
  },
  invalid_plan: {
    title: "The proposed experiment plan was rejected.",
    description:
      "The planner returned a proposal that failed validation. No recovery plan was authorized; review the record before retrying.",
  },
  experiment_error: {
    title: "An isolated experiment could not complete.",
    description:
      "The lab could not finish measuring a candidate plan. No recovery plan was authorized; review any recorded outcomes before retrying.",
  },
};
export const toolNames: Record<string, string> = {
  get_metrics: "Request metrics",
  query_logs: "Application logs",
  get_service_health: "Service health",
  get_recent_changes: "Deployment changes",
  search_runbooks: "Runbook search",
};
export const actionNames: Record<Action, string> = {
  no_action: "No changes proposed",
  restore_inventory_route: "Restore inventory route",
  restore_inventory_service: "Restore inventory service",
  restore_timeout_budget: "Restore timeout budget",
  restore_catalog_path: "Restore catalog path",
  rollback_checkout_release: "Roll back checkout release",
};
export const tabs = ["diagnosis", "rehearsal", "evidence"] as const;
