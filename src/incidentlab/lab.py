"""A disposable application with real HTTP traffic and SQLite failures.

The investigator only sees observations. SCENARIOS and their labels belong to
the experiment runner, never to the tool interface or model context.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import sqlite3
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .contracts import CHECKOUT_CONTRACT, CheckoutContract, validate_checkout_response
from .models import Action, Cause, Evidence


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
    Scenario("wrong_route", "Configuration drift", "A deployment points checkout to a missing inventory route.", Cause.configuration, Action.route, (Action.route,)),
    Scenario("inventory_down", "Dependency unavailable", "Inventory starts returning real HTTP 503 responses.", Cause.dependency, Action.dependency, (Action.dependency,)),
    Scenario("tight_timeout", "Timeout mismatch", "The client deadline is shorter than the dependency response time.", Cause.timeout, Action.timeout, (Action.timeout,)),
    Scenario("missing_database", "Catalog connection failure", "Checkout attempts to open a nonexistent database in read/write mode.", Cause.database, Action.database, (Action.database,)),
    Scenario("bad_release", "Application regression", "A pricing regression raises an exception during checkout.", Cause.regression, Action.rollback, (Action.rollback,)),
    Scenario("healthy", "Healthy control", "Requests succeed. The investigator should avoid inventing an incident.", Cause.healthy, Action.none),
    Scenario("telemetry_gap", "Missing evidence", "Checkout fails, but diagnostic telemetry is unavailable to the investigator.", Cause.unknown, Action.none),
    Scenario("route_and_release", "Route drift masks a pricing regression", "An invalid inventory route hides a second failure in checkout pricing.", Cause.configuration, Action.route, (Action.route, Action.rollback)),
    Scenario("database_and_inventory", "Catalog failure masks an inventory outage", "The catalog path fails before checkout can reach an unavailable inventory service.", Cause.database, Action.database, (Action.database, Action.dependency)),
    Scenario("timeout_and_release", "A timeout masks a pricing regression", "An inventory deadline expires before checkout reaches a broken pricing release.", Cause.timeout, Action.timeout, (Action.timeout, Action.rollback)),
    Scenario("silent_price_drift", "Successful HTTP, incorrect checkout price", "A deployed pricing regression returns HTTP 200 while charging the wrong total.", Cause.regression, Action.rollback, (Action.rollback,)),
    Scenario("route_and_price_drift", "Route repair reveals silent price drift", "A missing inventory route masks incorrect checkout totals that still return HTTP 200.", Cause.configuration, Action.route, (Action.route, Action.rollback)),
)
SCENARIO_BY_ID = {s.id: s for s in SCENARIOS}


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
        config = {**self.config, "inventory_url": self.inventory_target, "catalog_path": self.catalog_target}
        state = {"config": config, "catalog": hashlib.sha256(self.catalog_bytes).hexdigest(),
            "configured_catalog": (hashlib.sha256(self.configured_catalog_bytes).hexdigest()
                if self.configured_catalog_bytes is not None else None),
            "inventory_ready": self.inventory_ready, "inventory_delay": self.inventory_delay,
            "telemetry_available": self.telemetry_available, "seed": self.seed,
            "contract": self.contract.metadata()}
        return hashlib.sha256(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Lab:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "catalog.sqlite"
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, price REAL)")
            db.executemany("INSERT OR REPLACE INTO products VALUES (?, ?)", [("notebook", 12.0), ("lamp", 45.0), ("mug", 8.5)])
        self.lock = threading.RLock()
        self.logs: list[Evidence] = []
        self.latencies: list[float] = []
        self.responses: list[int] = []
        self.semantic_checks: list[dict] = []
        self.contract = CHECKOUT_CONTRACT
        self.changes: list[Evidence] = []
        self.episode_id = uuid.uuid4().hex[:10]
        self.window = 1
        self.seed = 42
        self.scenario_id = "healthy"
        self.telemetry_available = True
        self.inventory_ready = True
        self.inventory_delay = 0.0
        self.config: dict[str, Any] = {}
        self.servers: list[ThreadingHTTPServer] = []
        self.threads: list[threading.Thread] = []
        try:
            self.inventory_url = self._serve(self._inventory_handler())
            self.checkout_url = self._serve(self._checkout_handler())
        except Exception:
            self.close()
            raise
        self.config = self._default_config()

    def _serve(self, handler: type[BaseHTTPRequestHandler]) -> str:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.servers.append(server)
        self.threads.append(thread)
        return f"http://127.0.0.1:{server.server_port}"

    def close(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=1)
        self.servers.clear()
        self.threads.clear()

    @staticmethod
    def _database_snapshot(path: Path) -> bytes:
        # SQLite's backup API captures committed state, including a WAL, rather
        # than copying a possibly incomplete database file while it is in use.
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(":memory:") as destination:
                source.backup(destination)
                return destination.serialize()

    @staticmethod
    def _restore_database(data: bytes, path: Path) -> None:
        with sqlite3.connect(":memory:") as source:
            source.deserialize(data)
            with sqlite3.connect(path) as destination:
                source.backup(destination)

    def snapshot(self) -> LabSnapshot:
        """Capture current state, including partial repairs, without traffic."""
        with self.lock:
            config = copy.deepcopy(self.config)
            configured_path = Path(config["catalog_path"]).resolve()
            is_default = configured_path == self.database
            catalog_target = (str(configured_path.relative_to(self.directory))
                if configured_path.is_relative_to(self.directory) else str(configured_path))
            target = urllib.parse.urlsplit(config["inventory_url"])
            origin = urllib.parse.urlsplit(self.inventory_url)
            if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
                raise ValueError("Only this lab's inventory endpoint can be cloned")
            return LabSnapshot(
                config=config,
                catalog_bytes=self._database_snapshot(self.database),
                configured_catalog_bytes=(self._database_snapshot(configured_path)
                    if not is_default and configured_path.is_file() else None),
                catalog_is_default=is_default,
                catalog_target=catalog_target,
                inventory_target=urllib.parse.urlunsplit(("", "", target.path, target.query, target.fragment)),
                inventory_ready=self.inventory_ready,
                inventory_delay=self.inventory_delay,
                telemetry_available=self.telemetry_available,
                seed=self.seed,
                contract=self.contract,
            )

    @classmethod
    def from_snapshot(cls, snapshot: LabSnapshot, directory: Path) -> Lab:
        """Create independent endpoints and databases from one frozen state."""
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("A clone requires an empty directory")
        clone = cls(directory)
        try:
            with clone.lock:
                clone._restore_database(snapshot.catalog_bytes, clone.database)
                clone.config = copy.deepcopy(snapshot.config)
                clone.config["inventory_url"] = clone.inventory_url + snapshot.inventory_target
                if snapshot.catalog_is_default:
                    catalog_path = clone.database
                else:
                    catalog_path = clone.directory / "configured-catalog.sqlite"
                    if snapshot.configured_catalog_bytes is not None:
                        clone._restore_database(snapshot.configured_catalog_bytes, catalog_path)
                clone.config["catalog_path"] = str(catalog_path)
                clone.inventory_ready = snapshot.inventory_ready
                clone.inventory_delay = snapshot.inventory_delay
                clone.telemetry_available = snapshot.telemetry_available
                clone.seed = snapshot.seed
                clone.contract = snapshot.contract
                clone.scenario_id = "snapshot"
            return clone
        except Exception:
            clone.close()
            raise

    def clone(self, directory: Path) -> Lab:
        return self.from_snapshot(self.snapshot(), directory)

    def fingerprint(self) -> str:
        return self.snapshot().fingerprint()

    @property
    def observation_id(self) -> str:
        return f"{self.episode_id}-{self.window}"

    def _default_config(self) -> dict[str, Any]:
        return {"inventory_url": self.inventory_url + "/v1/stock", "timeout_ms": 400,
                "catalog_path": str(self.database), "release": "checkout-1.0"}

    @staticmethod
    def _send(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        try:
            handler.send_response(status)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(encoded)))
            handler.end_headers()
            handler.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass  # An intentionally short client deadline can close the socket.

    def _log(self, episode: str, service: str, summary: str, **data: Any) -> None:
        with self.lock:
            if episode != self.observation_id:
                return
            self.logs.append(Evidence(id=f"log-{episode}-{len(self.logs) + 1:03d}",
                source=service, summary=summary, data=data))

    def _inventory_handler(self) -> type[BaseHTTPRequestHandler]:
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                with lab.lock:
                    episode = lab.observation_id
                    ready, delay = lab.inventory_ready, lab.inventory_delay
                path = urllib.parse.urlparse(self.path).path
                if path == "/health":
                    lab._send(self, 200 if ready else 503, {"ready": ready})
                    return
                if path != "/v1/stock":
                    lab._log(episode, "inventory", "Inventory route not found", level="error", path=path, status=404)
                    lab._send(self, 404, {"error": "route_not_found"})
                    return
                if delay:
                    time.sleep(delay)
                if not ready:
                    lab._log(episode, "inventory", "Inventory readiness check failed", level="error", status=503)
                    lab._send(self, 503, {"error": "service_unavailable"})
                    return
                lab._log(episode, "inventory", "Stock lookup completed", level="info", status=200, duration_ms=round(delay * 1000))
                lab._send(self, 200, {"available": 50})

        return Handler

    def _checkout_handler(self) -> type[BaseHTTPRequestHandler]:
        lab = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None:
                pass

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/health":
                    lab._send(self, 200, {"alive": True, "note": "Process liveness, not dependency readiness."})
                    return
                if parsed.path != "/checkout":
                    lab._send(self, 404, {"error": "not_found"})
                    return
                with lab.lock:
                    config, episode, contract = copy.deepcopy(lab.config), lab.observation_id, lab.contract
                request_id = uuid.uuid4().hex[:8]
                started = time.perf_counter()
                status, payload = 200, {}
                sku = urllib.parse.parse_qs(parsed.query).get("sku", ["notebook"])[0]
                try:
                    uri = Path(config["catalog_path"]).as_uri() + "?mode=rw"
                    with sqlite3.connect(uri, uri=True, timeout=0.1) as db:
                        row = db.execute("SELECT price FROM products WHERE sku = ?", (sku,)).fetchone()
                    if row is None:
                        raise ValueError("Unknown product")
                    with urllib.request.urlopen(config["inventory_url"], timeout=config["timeout_ms"] / 1000) as response:
                        json.load(response)
                    discount = None if config["release"] == "checkout-1.1" else 1.0
                    total = round(row[0] * discount, 2)
                    if config["release"] == "checkout-1.2":
                        total = round(total + 1.0, 2)
                    payload = {"total": total, "sku": sku, "request_id": request_id}
                    lab._log(episode, "checkout", "Checkout completed", level="info", request_id=request_id, status=200)
                except urllib.error.HTTPError as exc:
                    status, payload = 502, {"error": "upstream_error", "request_id": request_id}
                    lab._log(episode, "checkout", "Inventory request failed", level="error", request_id=request_id,
                        error_type="upstream_http_error", upstream_status=exc.code, endpoint=config["inventory_url"])
                except (TimeoutError, urllib.error.URLError) as exc:
                    status, payload = 504, {"error": "upstream_timeout", "request_id": request_id}
                    lab._log(episode, "checkout", "Inventory request exceeded client deadline", level="error", request_id=request_id,
                        error_type="upstream_timeout", timeout_ms=config["timeout_ms"], detail=str(exc))
                except sqlite3.Error as exc:
                    status, payload = 500, {"error": "catalog_error", "request_id": request_id}
                    lab._log(episode, "checkout", "Catalog database connection failed", level="error", request_id=request_id,
                        error_type=type(exc).__name__, detail=str(exc), catalog_path=config["catalog_path"])
                except (TypeError, ValueError) as exc:
                    status, payload = 500, {"error": "application_error", "request_id": request_id}
                    lab._log(episode, "checkout", "Checkout pricing failed", level="error", request_id=request_id,
                        error_type=type(exc).__name__, detail=str(exc), release=config["release"])
                elapsed = round((time.perf_counter() - started) * 1000, 2)
                check = validate_checkout_response(json.dumps(payload), status, sku, contract)
                with lab.lock:
                    if episode == lab.observation_id:
                        lab.responses.append(status)
                        lab.latencies.append(elapsed)
                        lab.semantic_checks.append(check)
                        if status == 200 and not check["passed"]:
                            error_type = ("price_mismatch" if "price_mismatch" in check["violations"]
                                else "response_contract_violation")
                            lab._log(episode, "checkout", "Checkout response violates the independent business contract",
                                level="error", error_type=error_type, contract_id=contract.id,
                                contract_version=contract.version, contract_sha256=contract.sha256, **check)
                lab._send(self, status, payload)

        return Handler

    def inject(self, scenario_id: str, seed: int = 42) -> dict:
        if scenario_id not in SCENARIO_BY_ID:
            raise ValueError("Unknown scenario")
        with self.lock:
            self.episode_id = uuid.uuid4().hex[:10]
            self.window = 1
            self.seed, self.scenario_id = seed, scenario_id
            self.logs, self.latencies, self.responses, self.changes = [], [], [], []
            self.semantic_checks = []
            self.config = self._default_config()
            self.inventory_ready, self.inventory_delay = True, 0.0
            self.telemetry_available = scenario_id != "telemetry_gap"
            before = copy.deepcopy(self.config)
            if scenario_id in {"wrong_route", "route_and_release", "route_and_price_drift"}:
                self.config["inventory_url"] = self.inventory_url + "/v2/stock"
            if scenario_id in {"inventory_down", "telemetry_gap", "database_and_inventory"}:
                self.inventory_ready = False
            if scenario_id in {"tight_timeout", "timeout_and_release"}:
                self.config["timeout_ms"] = 35 + (seed % 3) * 5
                self.inventory_delay = 0.12 + (seed % 3) * 0.01
            if scenario_id in {"missing_database", "database_and_inventory"}:
                self.config["catalog_path"] = str(self.directory / f"missing-{seed}.sqlite")
            if scenario_id in {"bad_release", "route_and_release", "timeout_and_release"}:
                self.config["release"] = "checkout-1.1"
            if scenario_id in {"silent_price_drift", "route_and_price_drift"}:
                self.config["release"] = "checkout-1.2"
            changed = {key: {"before": before[key], "after": value} for key, value in self.config.items() if before[key] != value}
            if changed:
                self.changes.append(Evidence(id=f"change-{self.episode_id}-01", source="deployments",
                    summary="Checkout configuration changed", data={"changes": changed}))
        self.probe(4)
        return self.status()

    def probe(self, count: int = 4) -> dict:
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 20:
            raise ValueError("Probe count must be between 1 and 20")
        with self.lock:
            seed, contract = self.seed, self.contract
        skus = list(contract.expected_totals_cents)
        random.Random(seed).shuffle(skus)
        statuses: list[int] = []
        durations: list[float] = []
        checks: list[dict] = []
        for index in range(count):
            sku = skus[index % len(skus)]
            started = time.perf_counter()
            try:
                query = urllib.parse.urlencode({"sku": sku})
                with urllib.request.urlopen(f"{self.checkout_url}/checkout?{query}", timeout=2) as response:
                    body, status = response.read(), response.status
            except urllib.error.HTTPError as exc:
                body, status = exc.read(), exc.code
            statuses.append(status)
            checks.append(validate_checkout_response(body, status, sku, contract))
            durations.append(round((time.perf_counter() - started) * 1000, 2))
        http_healthy = all(status == 200 for status in statuses)
        semantic_passed = all(check["passed"] for check in checks)
        return {"requests": count, "statuses": statuses, "all_healthy": http_healthy and semantic_passed,
                "all_http_healthy": http_healthy, "semantic_passed": semantic_passed,
                "semantic_checks": checks, "contract": contract.metadata(),
                "median_latency_ms": round(statistics.median(durations), 2)}

    def status(self) -> dict:
        with self.lock:
            http_errors = sum(code != 200 for code in self.responses)
            semantic_failures = sum(check["http_status"] == 200 and not check["passed"] for check in self.semantic_checks)
            errors = http_errors + semantic_failures
            return {"episode_id": self.episode_id, "window": self.window, "scenario_id": self.scenario_id, "seed": self.seed,
                "requests": len(self.responses), "errors": errors,
                "http_errors": http_errors, "semantic_failures": semantic_failures,
                "semantic_checked_requests": sum(check["evaluated"] for check in self.semantic_checks),
                "business_error_rate": round(semantic_failures / len(self.responses), 3) if self.responses else 0,
                "error_rate": round(errors / len(self.responses), 3) if self.responses else 0,
                "median_latency_ms": round(statistics.median(self.latencies), 2) if self.latencies else 0,
                "telemetry_available": self.telemetry_available,
                "recent_statuses": self.responses[-8:], "recent_semantic_checks": copy.deepcopy(self.semantic_checks[-8:]),
                "contract": self.contract.metadata(), "services": ["checkout", "inventory", "catalog"]}

    def _unavailable(self) -> list[Evidence]:
        return [Evidence(id=f"telemetry-{self.episode_id}", source="collector",
            summary="Diagnostic telemetry is unavailable", data={"available": False})]

    def query_logs(self, service: str = "all", limit: int = 12) -> list[Evidence]:
        with self.lock:
            if not self.telemetry_available:
                return self._unavailable()
            logs = [entry for entry in self.logs if service == "all" or entry.source == service]
            return copy.deepcopy(logs[-limit:])

    def get_recent_changes(self) -> list[Evidence]:
        with self.lock:
            if not self.telemetry_available:
                return self._unavailable()
            return copy.deepcopy(self.changes) or [Evidence(id=f"change-{self.episode_id}-none",
                source="deployments", summary="No checkout deployment changes recorded", data={})]

    def get_metrics(self) -> list[Evidence]:
        with self.lock:
            if not self.telemetry_available:
                return self._unavailable()
            status = self.status()
            return [Evidence(id=f"metrics-{self.observation_id}-{status['requests']}", source="metrics", summary="Observed checkout request metrics",
                data={key: status[key] for key in ["requests", "errors", "error_rate", "http_errors", "semantic_failures",
                    "semantic_checked_requests", "business_error_rate", "median_latency_ms", "recent_statuses",
                    "recent_semantic_checks", "contract"]})]

    def get_service_health(self) -> list[Evidence]:
        if not self.telemetry_available:
            return self._unavailable()
        observations = []
        for name, url in [("checkout", self.checkout_url), ("inventory", self.inventory_url)]:
            try:
                with urllib.request.urlopen(url + "/health", timeout=1) as response:
                    code, data = response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                code, data = exc.code, json.load(exc)
            observations.append(Evidence(id=f"health-{self.observation_id}-{name}", source="health",
                summary=f"{name} health endpoint returned HTTP {code}", data={"service": name, "status": code, **data}))
        return observations

    def apply(self, action: Action) -> dict:
        result = self.apply_plan([action])
        return {"action": Action(action).value, "scope": result["scope"], "verification": result["verification"]}

    def apply_plan(self, actions: list[Action] | tuple[Action, ...], probe_count: int = 5) -> dict:
        """Apply a bounded allowlisted plan, then verify on one fresh window."""
        plan = tuple(Action(action) for action in actions)
        if not 1 <= len(plan) <= 2 or len(set(plan)) != len(plan) or Action.none in plan:
            raise ValueError("A remediation plan requires one or two unique executable actions")
        if not isinstance(probe_count, int) or isinstance(probe_count, bool) or not 1 <= probe_count <= 20:
            raise ValueError("Probe count must be between 1 and 20")
        with self.lock:
            defaults = self._default_config()
            for action in plan:
                if action == Action.route:
                    self.config["inventory_url"] = defaults["inventory_url"]
                elif action == Action.dependency:
                    self.inventory_ready = True
                elif action == Action.timeout:
                    self.config["timeout_ms"] = defaults["timeout_ms"]
                elif action == Action.database:
                    self.config["catalog_path"] = defaults["catalog_path"]
                elif action == Action.rollback:
                    self.config["release"] = defaults["release"]
            # Recovery must be measured on fresh traffic, not cumulative failures.
            # In-flight requests from the previous window cannot contaminate it.
            self.window += 1
            self.logs, self.latencies, self.responses = [], [], []
            self.semantic_checks = []
        result = self.probe(probe_count)
        return {"actions": [action.value for action in plan], "scope": "disposable local lab", "verification": result}
