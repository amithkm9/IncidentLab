import { describe, expect, it } from "vitest";
import { proof, record, status, verified } from "../testing/fixtures";
import { validResponse } from "./validation";

describe("response contracts", () => {
  it("accepts current records, nullable failed proof results, and extra metadata", () => {
    expect(validResponse("/api/rehearse", record)).toBe(true);
    expect(
      validResponse("/api/status", { ...status, future_metadata: true }),
    ).toBe(true);
    const incomplete = {
      ...proof,
      summary: {
        ...proof.summary,
        full_plan_passed: null,
        all_actions_necessary: null,
        promotion_eligible: false,
      },
    };
    expect(
      validResponse("/api/rehearsals/saved/proof", {
        proof: incomplete,
        authority: { is_current: true, reason: "current_snapshot" },
      }),
    ).toBe(true);
  });
  it("keeps older HTTP-only verification readable without inventing business checks", () => {
    const legacy = {
      requests: 1,
      statuses: [200],
      all_healthy: true,
      median_latency_ms: 2,
    };
    expect(validResponse("/api/probe", { status, verification: legacy })).toBe(
      true,
    );
  });
  it.each(["false", 1, null])(
    "rejects an ambiguous health flag %j",
    (all_healthy) => {
      expect(
        validResponse("/api/probe", {
          status,
          verification: { ...verified, all_healthy },
        }),
      ).toBe(false);
      expect(
        validResponse("/api/rehearse", {
          ...record,
          report: {
            ...record.report,
            control: {
              ...record.report.control,
              verification: { ...verified, all_healthy },
            },
          },
        }),
      ).toBe(false);
    },
  );
  it("rejects string proof authority and malformed nested arrays before rendering", () => {
    expect(
      validResponse("/api/rehearsals/saved/proof", {
        proof,
        authority: { is_current: "false", reason: "stale" },
      }),
    ).toBe(false);
    expect(
      validResponse("/api/rehearse", {
        ...record,
        report: { ...record.report, experiments: {} },
      }),
    ).toBe(false);
    expect(
      validResponse("/api/probe", {
        status,
        verification: { ...verified, semantic_checks: [{ passed: true }] },
      }),
    ).toBe(false);
  });
  it("rejects missing required fields, invalid options, and non-finite numbers", () => {
    expect(validResponse("/api/config", { mistral_configured: "true" })).toBe(
      false,
    );
    expect(
      validResponse("/api/status", { ...status, requests: Infinity }),
    ).toBe(false);
    expect(
      validResponse("/api/rehearse", {
        ...record,
        report: { ...record.report, strategy: "unrecognized" },
      }),
    ).toBe(false);
  });
});

describe("saved artifact consistency", () => {
  it.each(["", ".", "..", "saved/path", "x".repeat(32), "a".repeat(31)])(
    "rejects an invalid stored ID before rendering: %j",
    (id) => {
      expect(validResponse("/api/rehearse", { ...record, id })).toBe(false);
    },
  );
  it("rejects an invalid linked rehearsal ID or proof ID", () => {
    expect(
      validResponse("/api/rehearse", {
        ...record,
        proof: { ...proof, id: ".." },
      }),
    ).toBe(false);
    expect(
      validResponse("/api/rehearsals/saved/proof", {
        proof: { ...proof, rehearsal_id: ".." },
        authority: { is_current: false, reason: "invalid" },
      }),
    ).toBe(false);
  });
  it("rejects a passing summary when the measured control failed", () => {
    expect(
      validResponse("/api/rehearse", {
        ...record,
        report: {
          ...record.report,
          summary: { ...record.report.summary, control_healthy: true },
        },
      }),
    ).toBe(false);
  });
  it("rejects a failed candidate selected as the recommended plan", () => {
    const failed = {
      ...verified,
      statuses: [502],
      all_healthy: false,
      all_http_healthy: false,
      semantic_passed: false,
    };
    expect(
      validResponse("/api/rehearse", {
        ...record,
        report: {
          ...record.report,
          experiments: [
            { ...record.report.experiments[0], verification: failed },
          ],
          summary: { ...record.report.summary, successful_plans: 0 },
        },
      }),
    ).toBe(false);
  });
  it("rejects positive health flags contradicted by recorded responses", () => {
    expect(
      validResponse("/api/probe", {
        status,
        verification: { ...verified, statuses: [502] },
      }),
    ).toBe(false);
    expect(
      validResponse("/api/probe", {
        status,
        verification: { ...verified, semantic_passed: false },
      }),
    ).toBe(false);
    expect(
      validResponse("/api/probe", {
        status,
        verification: { ...verified, requests: 3 },
      }),
    ).toBe(false);
  });
  it.each([false, true])(
    "preserves v0.1 archive fields with HTTP-only recovery %j",
    (all_healthy) => {
      const legacy = {
        id: "c".repeat(32),
        episode_id: "legacy-episode",
        revision: 0,
        created_at: "2026-10-17T12:00:00Z",
        observation: { requests: 4, errors: 4, scenario_id: "wrong_route" },
        result: {
          mode: "baseline",
          elapsed_ms: 1,
          traces: [],
          finding: {
            cause: "configuration_error",
            title: "Inventory route failed",
            explanation: "The request returned HTTP 404.",
            evidence_ids: [],
            action: "restore_inventory_route",
            verification: "Issue fresh requests.",
            limitations: "Controlled local lab.",
          },
        },
        remediation: {
          verification: { all_healthy, statuses: [all_healthy ? 200 : 502] },
        },
      };
      expect(validResponse(`/api/investigations/${legacy.id}`, legacy)).toBe(
        true,
      );
      expect(
        validResponse(`/api/investigations/${legacy.id}`, {
          ...legacy,
          rehearsal_id: "..",
        }),
      ).toBe(false);
    },
  );
});
