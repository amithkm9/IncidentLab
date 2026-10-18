import { describe, expect, it } from "vitest";
import type {
  RecoveryProof,
  RehearsalRecord,
  Status,
  Verification,
} from "./domain";
import {
  matchesSnapshot,
  proofBlocksPromotion,
  proofConclusion,
} from "./recovery";

const status: Status = {
  episode_id: "episode-1",
  revision: 2,
  window: 1,
  scenario_id: "test",
  seed: 42,
  requests: 1,
  errors: 1,
  error_rate: 1,
  median_latency_ms: 4,
  telemetry_available: true,
  recent_statuses: [502],
  services: [],
};
const verified: Verification = {
  requests: 1,
  statuses: [200],
  all_healthy: true,
  all_http_healthy: true,
  semantic_passed: true,
  median_latency_ms: 2,
};
const proof: RecoveryProof = {
  id: "proof-1",
  schema_version: 1,
  created_at: "2026-01-01",
  rehearsal_id: "rehearsal-1",
  plan_id: "plan-1",
  episode_id: "episode-1",
  revision: 2,
  source_fingerprint: "source-hash",
  source_unchanged: true,
  contract: { id: "checkout-v1", version: 1 },
  actions: ["restore_inventory_route"],
  probe_count: 9,
  trials: [],
  necessity: [],
  summary: {
    full_plan_passed: true,
    control_failed: true,
    all_actions_necessary: true,
    conclusion: "supported",
    promotion_eligible: true,
    planned_trials: 2,
    completed_trials: 2,
  },
  budget: {
    max_trials: 4,
    max_requests: 36,
    planned_trials: 2,
    started_trials: 2,
    completed_trials: 2,
    probe_count_per_trial: 9,
    planned_requests: 18,
    completed_trial_requests: 18,
    provider_calls: 0,
    accounting_note: "Completed trials only.",
  },
  limitations: [],
  digest: {
    algorithm: "sha256",
    value: "hash",
    scope: "content",
    signed: false,
  },
  error: null,
  elapsed_ms: 100,
};
const record: RehearsalRecord = {
  id: "rehearsal-1",
  created_at: "2026-01-01",
  scenario_id: "test",
  episode_id: "episode-1",
  revision: 2,
  observation: status,
  report: {
    elapsed_ms: 1,
    probe_count: 3,
    max_actions: 1,
    control: {
      id: "control",
      actions: [],
      verification: verified,
      elapsed_ms: 1,
    },
    experiments: [],
    recommended_plan_id: "plan-1",
    summary: {
      tested_plans: 1,
      successful_plans: 1,
      minimal_action_count: 1,
      control_healthy: false,
    },
    limitations: [],
    source_fingerprint: "source-hash",
  },
  proof,
};

describe("snapshot and proof guards", () => {
  it("requires the same episode and revision", () => {
    expect(matchesSnapshot(record, status)).toBe(true);
    expect(matchesSnapshot(record, { ...status, revision: 3 })).toBe(false);
    expect(
      matchesSnapshot(record, { ...status, episode_id: "another-episode" }),
    ).toBe(false);
    expect(matchesSnapshot(null, status)).toBe(false);
  });
  it("allows the optional proof to be absent, but never bypasses a failed attempt", () => {
    expect(proofBlocksPromotion({ ...record, proof: null })).toBe(false);
    expect(
      proofBlocksPromotion({
        ...record,
        proof_failure: {
          code: "proof_failed",
          message: "Failed",
          created_at: "now",
        },
      }),
    ).toBe(true);
    expect(proofBlocksPromotion(record)).toBe(false);
  });
  it.each([
    { source_unchanged: false },
    { rehearsal_id: "old" },
    { plan_id: "other" },
    { episode_id: "old" },
    { revision: 1 },
    { source_fingerprint: "changed" },
  ])("rejects a proof with invalid binding: %j", (change) => {
    expect(
      proofBlocksPromotion({ ...record, proof: { ...proof, ...change } }),
    ).toBe(true);
  });
  it("blocks incomplete comparisons and explains the missing conclusion", () => {
    const incomplete = {
      ...proof,
      summary: {
        ...proof.summary,
        full_plan_passed: null,
        all_actions_necessary: null,
        conclusion: "inconclusive",
        promotion_eligible: false,
      },
    };
    expect(proofBlocksPromotion({ ...record, proof: incomplete })).toBe(true);
    expect(proofConclusion(incomplete).title).toBe("The proof is incomplete.");
  });
  it("does not claim that a redundant action is necessary or globally minimal", () => {
    const redundant = {
      ...proof,
      summary: {
        ...proof.summary,
        all_actions_necessary: false,
        conclusion: "redundant_action",
      },
    };
    expect(proofConclusion(redundant).description).toContain(
      "smaller variant also passed",
    );
    expect(proofBlocksPromotion({ ...record, proof: redundant })).toBe(false);
  });
});
