import type {
  BoundRecord,
  RecoveryProof,
  RehearsalRecord,
  Status,
} from "./domain";

/** Revision-bound artifacts must never authorize changes to another lab snapshot. */
export function matchesSnapshot(
  record: BoundRecord | null | undefined,
  status: Status | null,
): boolean {
  return (
    !!record &&
    !!status &&
    record.episode_id === status.episode_id &&
    record.revision === status.revision
  );
}

/** A cached snapshot cannot authorize another mutation after refresh failure. */
export function mutationsLocked(context: {
  workspaceFresh: boolean;
  busy: boolean;
  archive: boolean;
  status: Status | null;
}): boolean {
  return (
    !context.workspaceFresh ||
    context.busy ||
    context.archive ||
    !context.status ||
    context.status.busy === true
  );
}

/** A failed or stale optional proof cannot be bypassed by promoting its rehearsal. */
export function proofBlocksPromotion(record: RehearsalRecord | null): boolean {
  if (!record) return true;
  if (record.proof_failure) return true;
  const proof = record.proof;
  if (!proof) return false;
  return (
    proof.summary.promotion_eligible !== true ||
    proof.source_unchanged !== true ||
    proof.rehearsal_id !== record.id ||
    proof.plan_id !== record.report.recommended_plan_id ||
    proof.episode_id !== record.episode_id ||
    proof.revision !== record.revision ||
    proof.source_fingerprint !== record.report.source_fingerprint
  );
}

export function proofConclusion(proof: RecoveryProof): {
  title: string;
  description: string;
} {
  switch (proof.summary.conclusion) {
    case "supported":
      return {
        title: "Every action made a measured difference.",
        description:
          "The full plan passed. Removing each action caused the sampled checkout checks to fail. This supports necessity within this plan and snapshot.",
      };
    case "redundant_action":
      return {
        title: "The plan works, but an action may be unnecessary.",
        description:
          "At least one smaller variant also passed. This proof does not establish that every action is needed; inspect the omission results before applying the plan.",
      };
    case "full_plan_failed":
      return {
        title: "The full plan did not hold up.",
        description:
          "Fresh measurements did not verify the recommended plan. Promotion is blocked; run a new rehearsal against the current state.",
      };
    case "control_healthy":
      return {
        title: "The unchanged control already passes.",
        description:
          "The proof did not establish a need for intervention. Promotion is blocked; inspect the control and current lab observations.",
      };
    default:
      return {
        title: "The proof is incomplete.",
        description:
          "The required comparisons did not all complete. No necessity conclusion is established, and promotion is blocked until a valid proof or new rehearsal completes.",
      };
  }
}
