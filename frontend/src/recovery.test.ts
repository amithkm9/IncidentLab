import { describe, expect, it } from "vitest";
import {
  matchesSnapshot,
  mutationsLocked,
  proofBlocksPromotion,
  proofConclusion,
} from "./recovery";

import { status, proof, record } from "./testing/fixtures";

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

describe("workspace refresh guard", () => {
  it("locks an otherwise current snapshot until its refresh succeeds", () => {
    const context = {
      status,
      busy: false,
      archive: false,
      workspaceFresh: false,
    };
    expect(mutationsLocked(context)).toBe(true);
    expect(mutationsLocked({ ...context, workspaceFresh: true })).toBe(false);
  });
  it("keeps busy and archived workspaces read-only even when fresh", () => {
    const context = {
      status,
      busy: false,
      archive: false,
      workspaceFresh: true,
    };
    expect(mutationsLocked({ ...context, busy: true })).toBe(true);
    expect(mutationsLocked({ ...context, archive: true })).toBe(true);
    expect(
      mutationsLocked({ ...context, status: { ...status, busy: true } }),
    ).toBe(true);
    expect(mutationsLocked({ ...context, status: null })).toBe(true);
  });
});
