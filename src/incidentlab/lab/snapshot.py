"""Immutable description of actual lab state, without scenario labels."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from incidentlab.domain.contracts import CHECKOUT_CONTRACT, CheckoutContract


@dataclass(frozen=True)
class LabSnapshot:
    """Actual mutable state, without the scenario's identity or expected answer."""

    config: dict[str, Any]
    catalog_bytes: bytes
    configured_catalog_bytes: bytes | None
    catalog_is_default: bool
    catalog_target: str
    inventory_target: str
    inventory_ready: bool
    inventory_delay: float
    telemetry_available: bool
    seed: int
    contract: CheckoutContract = CHECKOUT_CONTRACT

    def fingerprint(self) -> str:
        config = {
            **self.config,
            "inventory_url": self.inventory_target,
            "catalog_path": self.catalog_target,
        }
        state = {
            "config": config,
            "catalog": hashlib.sha256(self.catalog_bytes).hexdigest(),
            "configured_catalog": (
                hashlib.sha256(self.configured_catalog_bytes).hexdigest()
                if self.configured_catalog_bytes is not None
                else None
            ),
            "inventory_ready": self.inventory_ready,
            "inventory_delay": self.inventory_delay,
            "telemetry_available": self.telemetry_available,
            "seed": self.seed,
            "contract": self.contract.metadata(),
        }
        return hashlib.sha256(
            json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
