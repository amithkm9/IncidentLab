"""Operator/evaluator scenario labels; never supplied to model tools."""

from dataclasses import dataclass

from incidentlab.domain.models import Action, Cause


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    cause: Cause
    action: Action
    expected_actions: tuple[Action, ...] = ()

    @property
    def fault_count(self) -> int:
        return len(self.expected_actions)


SCENARIOS = (
    Scenario(
        "wrong_route",
        "Configuration drift",
        "A deployment points checkout to a missing inventory route.",
        Cause.configuration,
        Action.route,
        (Action.route,),
    ),
    Scenario(
        "inventory_down",
        "Dependency unavailable",
        "Inventory starts returning real HTTP 503 responses.",
        Cause.dependency,
        Action.dependency,
        (Action.dependency,),
    ),
    Scenario(
        "tight_timeout",
        "Timeout mismatch",
        "The client deadline is shorter than the dependency response time.",
        Cause.timeout,
        Action.timeout,
        (Action.timeout,),
    ),
    Scenario(
        "missing_database",
        "Catalog connection failure",
        "Checkout attempts to open a nonexistent database in read/write mode.",
        Cause.database,
        Action.database,
        (Action.database,),
    ),
    Scenario(
        "bad_release",
        "Application regression",
        "A pricing regression raises an exception during checkout.",
        Cause.regression,
        Action.rollback,
        (Action.rollback,),
    ),
    Scenario(
        "healthy",
        "Healthy control",
        "Requests succeed. The investigator should avoid inventing an incident.",
        Cause.healthy,
        Action.none,
    ),
    Scenario(
        "telemetry_gap",
        "Missing evidence",
        "Checkout fails, but diagnostic telemetry is unavailable to the investigator.",
        Cause.unknown,
        Action.none,
    ),
    Scenario(
        "route_and_release",
        "Route drift masks a pricing regression",
        "An invalid inventory route hides a second failure in checkout pricing.",
        Cause.configuration,
        Action.route,
        (Action.route, Action.rollback),
    ),
    Scenario(
        "database_and_inventory",
        "Catalog failure masks an inventory outage",
        "The catalog path fails before checkout can reach an unavailable inventory service.",
        Cause.database,
        Action.database,
        (Action.database, Action.dependency),
    ),
    Scenario(
        "timeout_and_release",
        "A timeout masks a pricing regression",
        "An inventory deadline expires before checkout reaches a broken pricing release.",
        Cause.timeout,
        Action.timeout,
        (Action.timeout, Action.rollback),
    ),
    Scenario(
        "silent_price_drift",
        "Successful HTTP, incorrect checkout price",
        "A deployed pricing regression returns HTTP 200 while charging the wrong total.",
        Cause.regression,
        Action.rollback,
        (Action.rollback,),
    ),
    Scenario(
        "route_and_price_drift",
        "Route repair reveals silent price drift",
        "A missing inventory route masks incorrect checkout totals that still return HTTP 200.",
        Cause.configuration,
        Action.route,
        (Action.route, Action.rollback),
    ),
)
SCENARIO_BY_ID = {s.id: s for s in SCENARIOS}
