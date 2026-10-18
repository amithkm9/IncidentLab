import type {
  Contract,
  Observation,
  ProviderFailure,
  SemanticCheck,
} from "./domain";

export function semanticState(verification?: Observation | null) {
  const checks = Array.isArray(verification?.semantic_checks)
    ? verification.semantic_checks
    : [];
  const known = typeof verification?.semantic_passed === "boolean";
  const evaluated = checks.filter((check) => check.evaluated);
  const failed = evaluated.filter((check) => !check.passed);
  return {
    known,
    checks,
    evaluated,
    failed,
    passed: known && verification.semantic_passed === true,
  };
}

export function httpHealthy(verification?: Observation | null) {
  return typeof verification?.all_http_healthy === "boolean"
    ? verification.all_http_healthy
    : !!verification?.statuses?.length &&
        verification.statuses.every((code) => code === 200);
}

export function recoveryVerified(verification?: Observation | null) {
  return (
    !!verification?.all_healthy &&
    httpHealthy(verification) &&
    semanticState(verification).passed
  );
}

export function totalLabel(
  cents: number | null | undefined,
  contract?: Contract,
) {
  if (typeof cents !== "number" || !Number.isFinite(cents))
    return "Not returned";
  if (contract?.currency) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: contract.currency,
      }).format(cents / 100);
    } catch {
      /* Use explicit decimal amounts for older or invalid currency metadata. */
    }
  }
  return `${(cents / 100).toFixed(2)}${contract?.currency ? ` ${contract.currency}` : ""}`;
}

export function mismatchLabel(check: SemanticCheck, contract?: Contract) {
  if (!check.evaluated)
    return `${check.sku}: business checks unavailable after HTTP ${check.http_status}.`;
  const price = `${check.sku}: expected ${totalLabel(check.expected_total_cents, contract)}, observed ${totalLabel(check.observed_total_cents, contract)}`;
  return check.observed_sku !== check.sku
    ? `${price}; expected SKU ${check.sku}, observed ${check.observed_sku ?? "not returned"}.`
    : `${price}.`;
}

export function verificationSummary(verification?: Observation | null) {
  const semantic = semanticState(verification);
  const requests =
    verification?.requests ?? verification?.statuses?.length ?? 0;
  if (!semantic.known)
    return `HTTP responses: ${(verification?.statuses || []).join(", ") || "not recorded"}. Business correctness was not recorded in this report.`;
  if (recoveryVerified(verification))
    return `${requests} of ${requests} fresh requests passed HTTP, price, and SKU checks.`;
  if (httpHealthy(verification))
    return `All ${requests} requests returned HTTP 200, but ${semantic.failed.length || "one or more"} response${semantic.failed.length === 1 ? "" : "s"} violated the business contract.`;
  return `HTTP responses: ${(verification?.statuses || []).join(", ") || "not recorded"}. ${semantic.evaluated.length} responses were evaluated for business correctness${semantic.failed.length ? `; ${semantic.failed.length} failed` : ""}.`;
}

export function providerFailureLabel(failure?: ProviderFailure) {
  if (!failure) return null;
  const categories: Record<string, string> = {
    authentication: "Provider authentication failed",
    rate_limited: "Provider rate limit",
    provider_unavailable: "Provider unavailable",
    request_rejected: "Provider rejected the request",
    transport_timeout: "Provider request timed out",
    transport_error: "Provider connection failed",
    invalid_response: "Provider returned an invalid response",
    unknown_provider_error: "Provider request failed",
  };
  const label = categories[failure.category];
  if (typeof label !== "string") return null;
  const status = failure.status_code;
  const retry = failure.retry_after_seconds;
  const validStatus =
    typeof status === "number" &&
    Number.isInteger(status) &&
    status >= 100 &&
    status <= 599;
  const validRetry =
    typeof retry === "number" &&
    Number.isFinite(retry) &&
    retry >= 0 &&
    retry <= 3600;
  return `${label}${validStatus ? ` (HTTP ${status})` : ""}.${validRetry ? ` Retry after ${Math.ceil(retry)} seconds.` : ""}`;
}
