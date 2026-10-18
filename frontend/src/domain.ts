/** HTTP boundary types. Optional semantic fields preserve older saved artifacts. */
export type Action =
  | "no_action"
  | "restore_inventory_route"
  | "restore_inventory_service"
  | "restore_timeout_budget"
  | "restore_catalog_path"
  | "rollback_checkout_release";
export type Mode = "baseline" | "mistral" | "retrieval" | "prompt";
export type Strategy = "exhaustive" | "adaptive" | "mistral";
export type Tab = "diagnosis" | "rehearsal" | "evidence";
export type View = "workbench" | "history";
export interface Config {
  mistral_configured: boolean;
  model: string;
  scope: string;
  version: string;
}
export interface Scenario {
  id: string;
  name: string;
  description: string;
  fault_count: number;
}
export interface Contract {
  id: string;
  version: string | number;
  currency?: string;
  sha256?: string;
  expected_totals_cents?: Record<string, number>;
}
export interface SemanticCheck {
  sku: string;
  expected_total_cents: number;
  observed_total_cents: number | null;
  observed_sku: string | null;
  http_status: number;
  evaluated: boolean;
  passed: boolean;
  violations: string[];
}
export interface Verification {
  requests: number;
  statuses: number[];
  all_healthy: boolean;
  median_latency_ms: number;
  all_http_healthy?: boolean;
  semantic_passed?: boolean;
  semantic_checks?: SemanticCheck[];
  contract?: Contract;
}
export type Observation = Partial<Verification>;
export interface Status {
  episode_id: string;
  window: number;
  revision?: number;
  scenario_id: string;
  seed: number;
  requests: number;
  errors: number;
  error_rate: number;
  median_latency_ms: number;
  telemetry_available: boolean;
  recent_statuses: number[];
  services: string[];
  busy?: boolean;
  http_errors?: number;
  semantic_failures?: number;
  semantic_checked_requests?: number;
  business_error_rate?: number;
  recent_semantic_checks?: SemanticCheck[];
  contract?: Contract;
}
export interface Evidence {
  id: string;
  source: string;
  summary: string;
  data: Record<string, unknown>;
}
export interface ToolTrace {
  tool: string;
  arguments: Record<string, unknown>;
  evidence: Evidence[];
  elapsed_ms: number;
  error?: string | null;
}
export interface Finding {
  cause: string;
  title: string;
  explanation: string;
  evidence_ids: string[];
  action: Action;
  verification: string;
  limitations: string;
}
export interface Investigation {
  mode: Mode;
  finding: Finding;
  traces: ToolTrace[];
  elapsed_ms: number;
  model?: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd?: number | null;
  cost_note: string;
}
export interface Recovery {
  verification: Verification;
  actions?: Action[];
  action?: Action;
  created_at?: string;
  method?: string;
  scope?: string;
}
export interface BoundRecord {
  id: string;
  episode_id: string;
  revision: number;
}
export interface InvestigationRecord extends BoundRecord {
  created_at: string;
  scenario_id: string;
  question: string;
  observation: Status;
  result: Investigation;
  remediation?: Recovery | null;
  episode_recovery?: Recovery | null;
  rehearsal_id?: string;
}
export interface Trial {
  id: string;
  actions: Action[];
  verification: Verification;
  elapsed_ms: number;
  evidence?: Evidence[];
}
export interface Decision extends Observation {
  step: number;
  actions: Action[];
  hypothesis: string;
  evidence_ids: string[];
  outcome: string;
  statuses: number[];
}
export interface ProviderFailure {
  category: string;
  status_code?: number | null;
  retry_after_seconds?: number | null;
}
export interface ProviderUsage {
  model?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  api_calls?: number;
  estimated_cost_usd?: number | null;
  cost_note?: string;
}
export interface RehearsalSummary {
  tested_plans: number;
  successful_plans: number;
  minimal_action_count: number | null;
  control_healthy: boolean;
  telemetry_available?: boolean;
  abstention_reason?: string | null;
}
export interface RehearsalReport {
  strategy?: Strategy;
  elapsed_ms: number;
  probe_count: number;
  max_actions: number;
  control: Trial;
  experiments: Trial[];
  recommended_plan_id: string | null;
  summary: RehearsalSummary;
  limitations: string[];
  source_fingerprint?: string;
  decision_trace?: Decision[];
  budget?: {
    max_experiments?: number;
    used_experiments: number;
    stop_reason: string;
    max_elapsed_seconds?: number;
  };
  provider_usage?: ProviderUsage;
  error?: {
    code: string;
    message: string;
    provider_failure?: ProviderFailure;
  } | null;
}
export interface ProofTrial {
  id: string;
  kind: "control" | "full_plan" | "ablation";
  actions: Action[];
  removed_action: Action | null;
  verification: Verification | null;
  elapsed_ms: number;
  error: { code?: string; message?: string } | string | null;
}
export interface RecoveryProof {
  id: string;
  schema_version: number;
  created_at: string;
  rehearsal_id: string;
  plan_id: string;
  episode_id: string;
  revision: number;
  source_fingerprint: string;
  contract: Contract;
  actions: Action[];
  probe_count: number;
  trials: ProofTrial[];
  necessity: {
    action: Action;
    trial_id: string;
    necessary: boolean | null;
    conclusion: string;
  }[];
  summary: {
    full_plan_passed: boolean | null;
    control_failed: boolean | null;
    all_actions_necessary: boolean | null;
    conclusion: string;
    promotion_eligible: boolean;
    planned_trials: number;
    completed_trials: number;
  };
  budget: {
    max_trials: number;
    max_requests: number;
    planned_trials: number;
    started_trials: number;
    completed_trials: number;
    probe_count_per_trial: number;
    planned_requests: number;
    completed_trial_requests: number;
    provider_calls: number;
    accounting_note: string;
  };
  limitations: string[];
  error: { code: string; message: string; trial_id?: string } | null;
  source_unchanged?: boolean;
  elapsed_ms: number;
  digest: { algorithm: string; value: string; scope: string; signed: boolean };
}
export interface RehearsalRecord extends BoundRecord {
  created_at: string;
  scenario_id: string;
  observation: Status;
  report: RehearsalReport;
  promotion?: Recovery | null;
  proof?: RecoveryProof | null;
  proof_failure?: { code: string; message: string; created_at: string } | null;
}
export interface LabEvent {
  id: string;
  created_at: string;
  type: string;
  title: string;
  detail: string;
  episode_id: string;
  data?: Record<string, unknown>;
}
export interface WorkspaceSummary {
  investigations: number;
  rehearsals: number;
  verified_recoveries: number;
}
export interface InvestigationSummary extends BoundRecord {
  created_at: string;
  scenario_id: string;
  mode: Mode;
  title: string;
  cause: string;
  remediated: boolean;
  verified?: boolean;
  investigation_verified?: boolean;
}
export interface RehearsalHistory extends BoundRecord {
  created_at: string;
  scenario_id: string;
  summary: RehearsalSummary;
  strategy?: Strategy;
  promoted: boolean;
  recommended_plan_id: string | null;
}
export interface History {
  investigations: InvestigationSummary[];
  rehearsals: RehearsalHistory[];
}
export interface Workspace {
  status: Status;
  latest_investigation: InvestigationRecord | null;
  latest_rehearsal: RehearsalRecord | null;
  events: LabEvent[];
  history: InvestigationSummary[];
  summary: WorkspaceSummary;
}
export interface ProofResponse {
  proof: RecoveryProof;
  authority: { is_current: boolean; reason: string };
}
