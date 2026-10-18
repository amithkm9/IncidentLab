import type { Observation, RehearsalReport } from "../domain";

/** Validate the JSON fields consumed by the UI before a response can replace state.
 * Extra fields remain allowed for forward-compatible saved artifacts.
 * These checks validate shape and primitive types, not the truth of server measurements.
 */
type Check = (value: unknown) => boolean;
const string: Check = (value) => typeof value === "string";
const number: Check = (value) =>
  typeof value === "number" && Number.isFinite(value);
const boolean: Check = (value) => typeof value === "boolean";
const object: Check = (value) =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const array =
  (check: Check): Check =>
  (value) =>
    Array.isArray(value) && value.every(check);
const nullable =
  (check: Check): Check =>
  (value) =>
    value === null || check(value);
const oneOf =
  (...values: string[]): Check =>
  (value) =>
    typeof value === "string" && values.includes(value);
function shape(
  required: Record<string, Check>,
  optional: Record<string, Check> = {},
): Check {
  return (value) => {
    if (!object(value)) return false;
    const fields = value as Record<string, unknown>;
    return (
      Object.entries(required).every(
        ([key, check]) => Object.hasOwn(fields, key) && check(fields[key]),
      ) &&
      Object.entries(optional).every(
        ([key, check]) => !Object.hasOwn(fields, key) || check(fields[key]),
      )
    );
  };
}
const artifactId: Check = (value) =>
  typeof value === "string" && /^[a-f0-9]{32}$/.test(value);
const strings = array(string);
const numbers = array(number);
const action = oneOf(
  "no_action",
  "restore_inventory_route",
  "restore_inventory_service",
  "restore_timeout_budget",
  "restore_catalog_path",
  "rollback_checkout_release",
);
const actions = array(action);
const mode = oneOf("baseline", "mistral", "retrieval", "prompt");
const strategy = oneOf("exhaustive", "adaptive", "mistral");
const contract = shape(
  { id: string, version: (value) => string(value) || number(value) },
  {
    currency: string,
    sha256: string,
    expected_totals_cents: (value) =>
      object(value) &&
      Object.values(value as Record<string, unknown>).every(number),
  },
);
const semanticCheck = shape({
  sku: string,
  expected_total_cents: number,
  observed_total_cents: nullable(number),
  observed_sku: nullable(string),
  http_status: number,
  evaluated: boolean,
  passed: boolean,
  violations: strings,
});
const semanticFields = {
  all_http_healthy: boolean,
  semantic_passed: boolean,
  semantic_checks: array(semanticCheck),
  contract,
};
const verificationFields = {
  requests: number,
  statuses: numbers,
  all_healthy: boolean,
  median_latency_ms: number,
};
const verificationShape = shape(verificationFields, semanticFields);
const verification: Check = (value) =>
  verificationShape(value) && observationsAgree(value as Observation);
const recordedVerificationShape = shape(
  { statuses: numbers, all_healthy: boolean },
  { requests: number, median_latency_ms: number, ...semanticFields },
);
const recordedVerification: Check = (value) =>
  recordedVerificationShape(value) && observationsAgree(value as Observation);

const status = shape(
  {
    episode_id: string,
    window: number,
    scenario_id: string,
    seed: number,
    requests: number,
    errors: number,
    error_rate: number,
    median_latency_ms: number,
    telemetry_available: boolean,
    recent_statuses: numbers,
    services: strings,
  },
  {
    revision: number,
    busy: boolean,
    http_errors: number,
    semantic_failures: number,
    semantic_checked_requests: number,
    business_error_rate: number,
    recent_semantic_checks: array(semanticCheck),
    contract,
  },
);
const evidence = shape({
  id: string,
  source: string,
  summary: string,
  data: object,
});
const trace = shape(
  {
    tool: string,
    arguments: object,
    evidence: array(evidence),
    elapsed_ms: number,
  },
  { error: nullable(string) },
);
const finding = shape({
  cause: string,
  title: string,
  explanation: string,
  evidence_ids: strings,
  action,
  verification: string,
  limitations: string,
});
const investigation = shape(
  {
    mode,
    finding,
    traces: array(trace),
    elapsed_ms: number,
  },
  {
    model: nullable(string),
    estimated_cost_usd: nullable(number),
    input_tokens: number,
    output_tokens: number,
    cost_note: string,
  },
);
const recovery = shape(
  { verification: recordedVerification },
  { actions, action, created_at: string, method: string, scope: string },
);
const recordFields = {
  id: artifactId,
  episode_id: string,
  revision: number,
  created_at: string,
  scenario_id: string,
};
const investigationRecord = shape(
  {
    id: artifactId,
    episode_id: string,
    revision: number,
    created_at: string,
    observation: shape(
      { requests: number, errors: number },
      { scenario_id: string },
    ),
    result: investigation,
  },
  {
    question: string,
    scenario_id: string,
    remediation: nullable(recovery),
    episode_recovery: nullable(recovery),
    rehearsal_id: artifactId,
  },
);
const trial = shape(
  { id: string, actions, verification, elapsed_ms: number },
  { evidence: array(evidence) },
);
const summary = shape(
  {
    tested_plans: number,
    successful_plans: number,
    minimal_action_count: nullable(number),
    control_healthy: boolean,
  },
  { telemetry_available: boolean, abstention_reason: nullable(string) },
);
const providerFailure = shape(
  { category: string },
  { status_code: nullable(number), retry_after_seconds: nullable(number) },
);
const reportError = shape(
  { code: string, message: string },
  { provider_failure: providerFailure },
);
const reportShape = shape(
  {
    elapsed_ms: number,
    probe_count: number,
    max_actions: number,
    control: trial,
    experiments: array(trial),
    recommended_plan_id: nullable(string),
    summary,
    limitations: strings,
  },
  {
    strategy,
    source_fingerprint: string,
    decision_trace: array(
      shape(
        {
          step: number,
          actions,
          hypothesis: string,
          evidence_ids: strings,
          outcome: string,
          statuses: numbers,
        },
        { ...verificationFields, ...semanticFields },
      ),
    ),
    budget: shape(
      { used_experiments: number, stop_reason: string },
      { max_experiments: nullable(number), max_elapsed_seconds: number },
    ),
    provider_usage: shape(
      {},
      {
        model: nullable(string),
        input_tokens: number,
        output_tokens: number,
        api_calls: number,
        estimated_cost_usd: nullable(number),
        cost_note: string,
      },
    ),
    error: nullable(reportError),
  },
);
const report: Check = (value) =>
  reportShape(value) && reportAgrees(value as RehearsalReport);

const proofTrial = shape({
  id: string,
  kind: oneOf("control", "full_plan", "ablation"),
  actions,
  removed_action: nullable(action),
  verification: nullable(verification),
  elapsed_ms: number,
  error: nullable(
    (value) =>
      string(value) || shape({}, { code: string, message: string })(value),
  ),
});
const proof = shape(
  {
    id: artifactId,
    schema_version: number,
    created_at: string,
    rehearsal_id: artifactId,
    plan_id: string,
    episode_id: string,
    revision: number,
    source_fingerprint: string,
    contract,
    actions,
    probe_count: number,
    trials: array(proofTrial),
    necessity: array(
      shape({
        action,
        trial_id: string,
        necessary: nullable(boolean),
        conclusion: string,
      }),
    ),
    summary: shape({
      full_plan_passed: nullable(boolean),
      control_failed: nullable(boolean),
      all_actions_necessary: nullable(boolean),
      conclusion: string,
      promotion_eligible: boolean,
      planned_trials: number,
      completed_trials: number,
    }),
    budget: shape({
      max_trials: number,
      max_requests: number,
      planned_trials: number,
      started_trials: number,
      completed_trials: number,
      probe_count_per_trial: number,
      planned_requests: number,
      completed_trial_requests: number,
      provider_calls: number,
      accounting_note: string,
    }),
    limitations: strings,
    error: nullable(
      shape({ code: string, message: string }, { trial_id: string }),
    ),
    elapsed_ms: number,
    digest: shape({
      algorithm: string,
      value: string,
      scope: string,
      signed: boolean,
    }),
  },
  { source_unchanged: boolean },
);
const rehearsalRecord = shape(
  { ...recordFields, observation: status, report },
  {
    promotion: nullable(recovery),
    proof: nullable(proof),
    proof_failure: nullable(
      shape({ code: string, message: string, created_at: string }),
    ),
  },
);
const investigationSummary = shape(
  { ...recordFields, mode, title: string, cause: string, remediated: boolean },
  { verified: boolean, investigation_verified: boolean },
);
const rehearsalSummary = shape(
  {
    ...recordFields,
    summary,
    promoted: boolean,
    recommended_plan_id: nullable(string),
  },
  { strategy },
);
const proofResponse = shape({
  proof,
  authority: shape({ is_current: boolean, reason: string }),
});
const responses: Record<string, Check> = {
  "/api/config": shape({
    mistral_configured: boolean,
    model: string,
    scope: string,
    version: string,
  }),
  "/api/scenarios": array(
    shape({
      id: string,
      name: string,
      description: string,
      fault_count: number,
    }),
  ),
  "/api/status": status,
  "/api/inject": status,
  "/api/workspace": shape({
    status,
    latest_investigation: nullable(investigationRecord),
    latest_rehearsal: nullable(rehearsalRecord),
    events: array(
      shape(
        {
          id: string,
          created_at: string,
          type: string,
          title: string,
          detail: string,
          episode_id: string,
        },
        { data: object },
      ),
    ),
    history: array(investigationSummary),
    summary: shape({
      investigations: number,
      rehearsals: number,
      verified_recoveries: number,
    }),
  }),
  "/api/history": shape({
    investigations: array(investigationSummary),
    rehearsals: array(rehearsalSummary),
  }),
  "/api/investigate": investigationRecord,
  "/api/probe": shape({ status, verification }),
  "/api/remediate": shape({ status, verification }, { action }),
  "/api/rehearse": rehearsalRecord,
  "/api/promote": shape({ status, verification }, { actions }),
};

export function validResponse(path: string, payload: unknown): boolean {
  const check =
    (Object.hasOwn(responses, path) ? responses[path] : undefined) ??
    (/^\/api\/investigations\/[^/]+$/.test(path)
      ? investigationRecord
      : /^\/api\/rehearsals\/[^/]+\/proof$/.test(path)
        ? proofResponse
        : /^\/api\/rehearsals\/[^/]+$/.test(path)
          ? rehearsalRecord
          : undefined);
  return !!check && check(payload);
}

/** Only reject contradictions inside the artifact; this does not authenticate measurements. */
function observationsAgree(value: Observation): boolean {
  const statuses = value.statuses || [];
  if (
    !statuses.length ||
    !statuses.every(
      (status) => Number.isInteger(status) && status >= 100 && status <= 599,
    )
  )
    return false;
  if (value.requests !== undefined && value.requests !== statuses.length)
    return false;
  const httpPassed = statuses.every((status) => status === 200);
  if (
    value.all_http_healthy !== undefined &&
    value.all_http_healthy !== httpPassed
  )
    return false;
  if (
    value.all_healthy === true &&
    (!httpPassed || value.semantic_passed === false)
  )
    return false;
  if (value.semantic_passed === true && !httpPassed) return false;
  const checks = value.semantic_checks;
  if (checks) {
    if (checks.length !== statuses.length) return false;
    if (
      checks.some(
        (check, index) =>
          check.http_status !== statuses[index] ||
          check.evaluated !== (statuses[index] === 200) ||
          (check.passed &&
            (!check.evaluated ||
              check.observed_sku !== check.sku ||
              check.observed_total_cents !== check.expected_total_cents ||
              check.violations.length > 0)),
      )
    )
      return false;
    if (
      value.semantic_passed === true &&
      !checks.every((check) => check.passed)
    )
      return false;
  }
  return true;
}
function reportAgrees(value: RehearsalReport): boolean {
  if (value.summary.control_healthy !== value.control.verification.all_healthy)
    return false;
  if (value.summary.tested_plans !== value.experiments.length) return false;
  if (
    value.summary.successful_plans !==
    value.experiments.filter((trial) => trial.verification.all_healthy).length
  )
    return false;
  if (value.recommended_plan_id !== null) {
    const recommended = value.experiments.filter(
      (trial) => trial.id === value.recommended_plan_id,
    );
    if (
      recommended.length !== 1 ||
      !recommended[0].verification.all_healthy ||
      value.control.verification.all_healthy
    )
      return false;
  }
  return true;
}
