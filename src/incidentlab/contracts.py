"""A versioned checkout contract independent of the application and catalog.

These prices are the lab's product requirements, not inferred scenario labels
or a copy of whatever the currently deployed pricing code happens to return.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, DecimalException
from typing import Any


@dataclass(frozen=True)
class CheckoutContract:
    id: str = "checkout-response"
    version: str = "1.0.0"
    currency: str = "USD"
    prices: tuple[tuple[str, int], ...] = (("notebook", 1200), ("lamp", 4500), ("mug", 850))

    def __post_init__(self) -> None:
        if (not isinstance(self.prices, tuple) or not self.prices
                or any(not isinstance(item, tuple) or len(item) != 2 for item in self.prices)):
            raise ValueError("Contract prices must be an immutable nonempty tuple of SKU/cent pairs")
        if (len({sku for sku, _ in self.prices}) != len(self.prices)
                or any(not isinstance(sku, str) or not sku or type(cents) is not int or cents < 0
                       for sku, cents in self.prices)):
            raise ValueError("Contract SKUs must be unique and prices nonnegative integer cents")

    @property
    def expected_totals_cents(self) -> dict[str, int]:
        return dict(self.prices)

    def definition(self) -> dict:
        return {"id": self.id, "version": self.version, "currency": self.currency,
            "expected_totals_cents": self.expected_totals_cents,
            "required_fields": ["request_id", "sku", "total"], "additional_fields": False,
            "total_unit": "major_currency_units", "maximum_total": 1_000_000_000,
            "monetary_precision": "exact_integer_cents", "duplicate_json_keys": False}

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.definition(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def metadata(self) -> dict:
        return {**self.definition(), "sha256": self.sha256}


CHECKOUT_CONTRACT = CheckoutContract()


def _reject_constant(value: str) -> None:
    raise ValueError(f"Nonstandard JSON numeric constant: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def validate_checkout_response(body: bytes | str, status: int, sku: str,
                               contract: CheckoutContract = CHECKOUT_CONTRACT) -> dict:
    """Validate actual response bytes without permissive float/schema coercion."""
    expected = contract.expected_totals_cents.get(sku)
    check: dict[str, Any] = {"sku": sku, "expected_total_cents": expected,
        "observed_total_cents": None, "observed_sku": None, "request_id": None,
        "http_status": status, "evaluated": status == 200, "passed": False, "violations": []}
    violations = check["violations"]
    if status != 200:
        violations.append("http_status_not_ok")
        return check
    if expected is None:
        violations.append("unknown_requested_sku")
    try:
        if not isinstance(body, (bytes, str)) or len(body) > 16_384:
            raise ValueError("Response must be bounded JSON text")
        payload = json.loads(body, parse_float=Decimal, parse_int=Decimal,
                             parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, TypeError, RecursionError, DecimalException):
        violations.append("invalid_json")
        return check
    if not isinstance(payload, dict):
        violations.append("invalid_response_object")
        return check
    required = {"sku", "total", "request_id"}
    violations.extend("missing_" + name for name in sorted(required - payload.keys()))
    if payload.keys() - required:
        violations.append("unexpected_fields")
    observed_sku = payload.get("sku")
    if isinstance(observed_sku, str):
        check["observed_sku"] = observed_sku
        if observed_sku != sku:
            violations.append("sku_mismatch")
    elif "sku" in payload:
        violations.append("invalid_sku")
    request_id = payload.get("request_id")
    if isinstance(request_id, str) and 1 <= len(request_id) <= 64:
        check["request_id"] = request_id
    elif "request_id" in payload:
        violations.append("invalid_request_id")
    if "total" in payload:
        total = payload["total"]
        if not isinstance(total, Decimal):
            violations.append("invalid_total_type")
        elif not total.is_finite() or total < 0 or total > Decimal(1_000_000_000):
            violations.append("invalid_total_range")
        else:
            # Inspect exact digits before arithmetic: decimal-context rounding
            # must not turn a tiny fractional-cent error into a passing price.
            digits, exponent = total.as_tuple().digits, total.as_tuple().exponent
            if exponent < -2 and any(digits[max(0, len(digits) + exponent + 2):]):
                violations.append("fractional_cent_total")
            else:
                observed = int(total * 100)
                check["observed_total_cents"] = observed
                if expected is not None and observed != expected:
                    violations.append("price_mismatch")
    check["passed"] = not violations
    return check
