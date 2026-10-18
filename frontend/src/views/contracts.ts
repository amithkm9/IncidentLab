import type {
  Contract,
  Observation,
  Recovery,
  SemanticCheck,
  Status,
} from "../domain";
import { $, el, text } from "../dom";
import { number } from "../format";
import {
  semanticState,
  totalLabel,
  mismatchLabel,
  recoveryVerified,
  httpHealthy,
  verificationSummary,
} from "../verification";

function contractChecks(checks: SemanticCheck[], contract?: Contract) {
  return checks.map((check) => {
    const item = el(
      "div",
      `contract-check${check.evaluated && !check.passed ? " failed" : ""}`,
    );
    const heading = el("div", "contract-check-heading");
    heading.append(
      el("strong", "", check.sku),
      el(
        "span",
        "",
        !check.evaluated
          ? `Not evaluated · HTTP ${check.http_status}`
          : check.passed
            ? `Contract passed · HTTP ${check.http_status}`
            : `Contract failed · HTTP ${check.http_status}`,
      ),
    );
    const values = el("dl", "contract-values");
    for (const [label, value] of [
      ["Expected total", totalLabel(check.expected_total_cents, contract)],
      ["Observed total", totalLabel(check.observed_total_cents, contract)],
      ["Expected SKU", check.sku],
      ["Observed SKU", check.observed_sku ?? "Not returned"],
    ]) {
      const pair = el("div");
      pair.append(el("dt", "", label), el("dd", "", value));
      values.append(pair);
    }
    item.append(heading, values);
    if (check.evaluated && check.violations?.length)
      item.append(
        el(
          "p",
          "contract-violations",
          check.violations.map((code) => code.replaceAll("_", " ")).join(" · "),
        ),
      );
    return item;
  });
}

export function appendContractDetails(
  target: HTMLElement,
  verification?: Observation | null,
  preview = true,
) {
  const semantic = semanticState(verification);
  const label = !semantic.known
    ? "Business checks not recorded"
    : semantic.failed.length
      ? `${semantic.failed.length} business contract failure${semantic.failed.length === 1 ? "" : "s"}`
      : semantic.passed
        ? "Price & SKU contracts passed"
        : semantic.evaluated.length
          ? "Business checks incomplete"
          : "Business checks not evaluated";
  target.append(
    el(
      "span",
      `contract-outcome${semantic.failed.length ? " failed" : semantic.passed ? " passed" : ""}`,
      label,
    ),
  );
  if (preview && semantic.failed.length)
    target.append(
      el(
        "p",
        "contract-inline-mismatch",
        mismatchLabel(semantic.failed[0], verification?.contract),
      ),
    );
  if (semantic.checks.length) {
    const details = el("details", "contract-details compact");
    details.append(
      el("summary", "", `Inspect ${semantic.checks.length} response checks`),
    );
    const list = el("div", "contract-check-list");
    list.append(...contractChecks(semantic.checks, verification?.contract));
    details.append(list);
    target.append(details);
  }
}

export function renderContractStatus(status: Status) {
  const known = typeof status.semantic_checked_requests === "number";
  const checked = Number(status.semantic_checked_requests || 0);
  const failed = Number(status.semantic_failures || 0);
  const checks = Array.isArray(status.recent_semantic_checks)
    ? status.recent_semantic_checks
    : [];
  const passing =
    known && status.requests > 0 && checked === status.requests && failed === 0;
  $("contract-health").classList.toggle("failed", failed > 0);
  $("contract-health").classList.toggle("passed", passing);
  text(
    "contract-health-title",
    failed
      ? "Successful responses contain incorrect checkout results."
      : passing
        ? "Correct prices. Correct products."
        : known
          ? "Business checks follow successful responses."
          : "Business correctness is not recorded.",
  );
  text(
    "contract-health-badge",
    failed
      ? `${number(failed)} CONTRACT FAILURE${failed === 1 ? "" : "S"}`
      : passing
        ? "CONTRACTS PASSED"
        : known
          ? "AWAITING VALID RESPONSES"
          : "HTTP-ONLY OBSERVATIONS",
  );
  $("contract-health-badge").classList.toggle("amber", failed > 0);
  text(
    "contract-health-summary",
    !known
      ? "This observation window only records transport health. HTTP 200 alone does not establish that checkout totals or product IDs are correct."
      : checked
        ? `${number(checked - failed)} of ${number(checked)} evaluated responses matched the expected price and SKU.${status.requests > checked ? ` ${number(status.requests - checked)} requests could not be evaluated after an HTTP failure.` : ""}`
        : "No successful checkout responses have been evaluated yet. HTTP failures must be resolved before prices and product IDs can be checked.",
  );
  const mismatch = checks.find((check) => check.evaluated && !check.passed);
  $("contract-mismatch-preview").hidden = !mismatch;
  text(
    "contract-mismatch-preview",
    mismatch ? mismatchLabel(mismatch, status.contract) : "",
  );
  $("contract-health-details").hidden = !checks.length;
  $("contract-health-checks").replaceChildren(
    ...contractChecks(checks, status.contract),
  );
  $("contract-version").hidden = !status.contract;
  text(
    "contract-version",
    status.contract
      ? `Contract ${status.contract.id} · version ${status.contract.version} · expected values are independent of the response.`
      : "",
  );
}

export function verificationNotice(
  target: HTMLElement,
  result: Recovery | null | undefined,
  successText: string,
) {
  const verification = result?.verification;
  if (!verification) {
    target.hidden = true;
    return;
  }
  target.hidden = false;
  const semantic = semanticState(verification);
  const recovered = recoveryVerified(verification);
  target.className = `notice${!semantic.known && httpHealthy(verification) ? " neutral" : recovered ? "" : " error"}`;
  target.textContent = `${recovered ? successText : !semantic.known && httpHealthy(verification) ? "Availability was verified; full recovery was not established." : "Recovery not verified."} ${verificationSummary(verification)}`;
  appendContractDetails(target, verification);
}
