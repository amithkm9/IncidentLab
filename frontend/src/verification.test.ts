import { describe, expect, it } from "vitest";
import type { SemanticCheck, Verification } from "./domain";
import {
  httpHealthy,
  mismatchLabel,
  providerFailureLabel,
  recoveryVerified,
  semanticState,
  verificationSummary,
} from "./verification";

const priceMismatch: SemanticCheck = {
  sku: "sku-1",
  expected_total_cents: 1500,
  observed_total_cents: 1800,
  observed_sku: "sku-1",
  http_status: 200,
  evaluated: true,
  passed: false,
  violations: ["price_mismatch"],
};
const falseRecovery: Verification = {
  requests: 1,
  statuses: [200],
  all_healthy: false,
  all_http_healthy: true,
  semantic_passed: false,
  semantic_checks: [priceMismatch],
  median_latency_ms: 4,
};

describe("recovery evidence", () => {
  it("distinguishes successful HTTP from an incorrect checkout total", () => {
    expect(httpHealthy(falseRecovery)).toBe(true);
    expect(recoveryVerified(falseRecovery)).toBe(false);
    expect(semanticState(falseRecovery).failed).toEqual([priceMismatch]);
    expect(verificationSummary(falseRecovery)).toContain(
      "violated the business contract",
    );
    expect(mismatchLabel(priceMismatch)).toContain(
      "expected 15.00, observed 18.00",
    );
  });
  it("never upgrades a legacy HTTP-only result to full recovery", () => {
    const legacy = {
      requests: 3,
      statuses: [200, 200, 200],
      all_healthy: true,
    };
    expect(httpHealthy(legacy)).toBe(true);
    expect(recoveryVerified(legacy)).toBe(false);
    expect(verificationSummary(legacy)).toContain(
      "Business correctness was not recorded",
    );
  });
  it("requires both HTTP and semantic success", () => {
    expect(
      recoveryVerified({
        ...falseRecovery,
        all_healthy: true,
        semantic_passed: true,
      }),
    ).toBe(true);
    expect(
      recoveryVerified({
        ...falseRecovery,
        all_healthy: true,
        semantic_passed: true,
        all_http_healthy: false,
      }),
    ).toBe(false);
    expect(recoveryVerified(null)).toBe(false);
  });
  it("does not count transport failures as evaluated business results", () => {
    const blocked = {
      ...falseRecovery,
      statuses: [502],
      all_http_healthy: false,
      semantic_checks: [
        { ...priceMismatch, evaluated: false, http_status: 502 },
      ],
    };
    expect(semanticState(blocked).failed).toHaveLength(0);
    expect(verificationSummary(blocked)).toContain(
      "0 responses were evaluated",
    );
    expect(mismatchLabel(blocked.semantic_checks[0])).toContain(
      "unavailable after HTTP 502",
    );
  });
  it("makes a wrong product ID visible even when the amount matches", () => {
    expect(
      mismatchLabel({
        ...priceMismatch,
        observed_total_cents: 1500,
        observed_sku: "sku-2",
      }),
    ).toContain("expected SKU sku-1, observed sku-2");
  });
});

describe("safe provider diagnostics", () => {
  it("explains a known rate limit without scheduling another call", () => {
    expect(
      providerFailureLabel({
        category: "rate_limited",
        status_code: 429,
        retry_after_seconds: 3.2,
      }),
    ).toBe("Provider rate limit (HTTP 429). Retry after 4 seconds.");
  });
  it("does not reflect unrecognized categories or out-of-bounds metadata", () => {
    expect(
      providerFailureLabel({ category: "provider-secret-body" }),
    ).toBeNull();
    expect(
      providerFailureLabel({
        category: "rate_limited",
        status_code: 999,
        retry_after_seconds: 3601,
      }),
    ).toBe("Provider rate limit.");
    expect(providerFailureLabel()).toBeNull();
  });
});
