"""Browser-boundary, resource-bound and stored-export regressions, without model calls."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from incidentlab.api import create_app, security
from incidentlab.application import IncidentService, markdown
from incidentlab.storage import RecordStore


@pytest.fixture
def boundary_client():
    # No lifespan is entered: these HTTP-boundary tests cannot start a lab or
    # call a model. The stub records whether a rejected request reached a write.
    app = create_app()
    calls = []

    def inject(scenario, seed):
        calls.append((scenario, seed))
        return {"scenario": scenario, "seed": seed}

    app.state.service = SimpleNamespace(inject=inject, status=lambda: {"busy": False})
    client = TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False)
    yield client, calls
    client.close()


@pytest.mark.parametrize(
    "method,path", [("GET", "/api/config"), ("GET", "/healthz"), ("POST", "/api/inject")]
)
def test_rebinding_host_cannot_read_or_mutate_local_api(boundary_client, method, path):
    client, calls = boundary_client
    response = client.request(
        method,
        path,
        json={"scenario_id": "healthy"},
        headers={"Host": "attacker.example", "Origin": "http://attacker.example"},
    )
    assert response.status_code == 400
    assert calls == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1",
        "http://127.0.0.1:8001",
        "http://127.0.0.1/path",
        "http://127.0.0.1/",
        "http://127.0.0.1?query",
        "http://127.0.0.1#fragment",
        "http://[",
        "null",
        "",
        "http://user@127.0.0.1",
        "http://127.0.0.1:invalid",
        "http://127.0.0.1:99999",
        "http://127.0.0.1 http://evil.example",
    ],
)
def test_origin_requires_exact_valid_scheme_host_and_port(boundary_client, origin):
    client, calls = boundary_client
    response = client.post(
        "/api/inject", json={"scenario_id": "healthy"}, headers={"Origin": origin}
    )
    assert response.status_code == 403
    assert calls == []
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "host,origin",
    [
        ("127.0.0.1", "http://127.0.0.1:80"),
        ("localhost:8000", "http://localhost:8000"),
        ("[::1]:8000", "http://[::1]:8000"),
    ],
)
def test_valid_local_origins_and_default_port_are_accepted(boundary_client, host, origin):
    client, calls = boundary_client
    response = client.post(
        "/api/inject",
        json={"scenario_id": "healthy", "seed": 107},
        headers={"Host": host, "Origin": origin, "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200
    assert calls == [("healthy", 107)]


@pytest.mark.parametrize("site", ["cross-site", "same-site", "unrecognized"])
def test_missing_origin_does_not_bypass_browser_fetch_metadata(boundary_client, site):
    client, calls = boundary_client
    assert (
        client.post(
            "/api/inject", json={"scenario_id": "healthy"}, headers={"Sec-Fetch-Site": site}
        ).status_code
        == 403
    )
    assert calls == []


def test_local_cli_without_browser_headers_remains_supported(boundary_client):
    client, calls = boundary_client
    assert client.post("/api/inject", json={"scenario_id": "healthy"}).status_code == 200
    assert calls == [("healthy", 42)]


@pytest.mark.parametrize(
    "headers,status",
    [
        ([("Host", "127.0.0.1"), ("Host", "attacker.example")], 400),
        ([("Origin", "http://127.0.0.1"), ("Origin", "http://evil.example")], 403),
        ([("Host", "127.0.0.1@evil.example")], 400),
        ([("Host", "127.0.0.1:invalid")], 400),
    ],
)
def test_ambiguous_or_malformed_host_and_origin_headers_fail_closed(
    boundary_client, headers, status
):
    client, calls = boundary_client
    assert (
        client.post("/api/inject", json={"scenario_id": "healthy"}, headers=headers).status_code
        == status
    )
    assert calls == []


def test_explicit_custom_host_is_possible_without_default_wildcards():
    app = create_app(allowed_hosts=["console.internal"])
    with_client = TestClient(app, base_url="http://console.internal")
    try:
        assert with_client.get("/healthz").status_code == 200
        assert with_client.get("/healthz", headers={"Host": "attacker.example"}).status_code == 400
    finally:
        with_client.close()
    with pytest.raises(ValueError, match="wildcard"):
        security.LocalRequestSecurity(app, allowed_hosts=["*"])


@pytest.mark.parametrize(
    "headers,body,status",
    [
        ({"Content-Length": "65537"}, b"{}", 413),
        ({"Content-Length": "2"}, b"x" * 65537, 413),
        ({"Content-Length": "-1"}, b"{}", 400),
        ({"Content-Length": "invalid"}, b"{}", 400),
        ({"Content-Length": "1"}, b"{}", 400),
    ],
)
def test_declared_and_actual_body_limits_precede_application_work(
    boundary_client, headers, body, status
):
    client, calls = boundary_client
    response = client.post("/api/inject", content=body, headers=headers)
    assert response.status_code == status
    assert calls == []


def test_streaming_body_stops_reading_at_bound_without_invoking_application():
    messages, reads, called = [], [], []

    async def receive():
        reads.append(True)
        return {
            "type": "http.request",
            "body": b"x" * security.MAX_API_BODY_BYTES if len(reads) == 1 else b"x",
            "more_body": True,
        }

    async def app(scope, receive, send):
        called.append(True)
        await JSONResponse({})(scope, receive, send)

    async def send(message):
        messages.append(message)

    asyncio.run(
        security.LocalRequestSecurity(app)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/inject",
                "scheme": "http",
                "headers": [(b"host", b"127.0.0.1")],
            },
            receive,
            send,
        )
    )
    assert messages[0]["status"] == 413
    assert len(reads) == 2 and called == []


def test_slow_incomplete_body_has_a_bounded_read_deadline(monkeypatch):
    messages = []
    monkeypatch.setattr(security, "BODY_READ_TIMEOUT_SECONDS", 0.001)

    async def receive():
        await asyncio.sleep(0.05)
        return {"type": "http.request", "body": b"", "more_body": True}

    async def app(*args):
        raise AssertionError("An incomplete request must not invoke an operation")

    async def send(message):
        messages.append(message)

    asyncio.run(
        security.LocalRequestSecurity(app)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/inject",
                "scheme": "http",
                "headers": [(b"host", b"127.0.0.1")],
            },
            receive,
            send,
        )
    )
    assert messages[0]["status"] == 408


def test_api_success_validation_errors_and_exports_are_not_cacheable(boundary_client, tmp_path):
    client, _ = boundary_client
    store = RecordStore(tmp_path)
    item = {
        "id": "a" * 32,
        "episode_id": "episode",
        "created_at": "today",
        "evidence": "private observations",
    }
    store.save_many([("investigation", item)])
    client.app.state.service.read = lambda identifier: store.read("investigation", identifier)
    for path in (
        "/api/config",
        "/api/status",
        "/api/investigations/" + item["id"],
        "/api/investigations/not-an-id",
    ):
        response = client.get(path)
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert client.post("/api/inject", json={}).headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("SECRET-TOKEN /private/secret.json", None),
        ("Mistral API returned HTTP 429; SECRET-TOKEN SECRET-RAW-BODY", "429"),
    ],
)
def test_runtime_errors_do_not_echo_body_credentials_or_paths(boundary_client, message, expected):
    client, _ = boundary_client

    def fail(request):
        raise RuntimeError(message)

    client.app.state.service.investigate = fail
    response = client.post("/api/investigate", json={"mode": "baseline"})
    assert response.status_code == 502
    assert "SECRET" not in response.text and "/private" not in response.text
    if expected:
        assert expected in response.text
    assert response.headers["cache-control"] == "no-store"


def test_unexpected_exception_has_generic_uncacheable_response(boundary_client):
    client, _ = boundary_client

    def fail():
        raise OSError("SECRET-PATH")

    client.app.state.service.status = fail
    response = client.get("/api/status")
    assert response.status_code == 500 and "SECRET" not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_invalid_export_identifiers_never_query_paths(boundary_client, tmp_path):
    client, _ = boundary_client
    store = RecordStore(tmp_path)
    client.app.state.service.read = lambda identifier: store.read("investigation", identifier)
    for identifier in ("..%2Fhistory.sqlite", "%2e%2e%2f.env", "a%0d%0aX-Evil%3Ayes", "x" * 32):
        response = client.get("/api/investigations/" + identifier)
        assert response.status_code == 404
        assert "content-disposition" not in response.headers


def test_legacy_import_ignores_nonobjects_symlinks_and_oversized_files(tmp_path, monkeypatch):
    exports = tmp_path / "investigations"
    exports.mkdir()
    (exports / "array.json").write_text("[]")
    (exports / "null.json").write_text("null")
    (exports / "large.json").write_text(" " * 2048)
    outside = tmp_path / "private.json"
    record = {"id": "a" * 32, "episode_id": "episode", "created_at": "today"}
    outside.write_text(json.dumps(record))
    (exports / "linked.json").symlink_to(outside)
    from incidentlab import storage

    monkeypatch.setattr(storage, "MAX_LEGACY_RECORD_BYTES", 1024)
    assert RecordStore(tmp_path).summary()["investigations"] == 0


def test_postmortem_escapes_stored_metadata_and_normalizes_control_characters():
    malicious = "`[open](https://evil.example)`\r\n<script>alert(1)</script>"
    record = {
        "id": "a" * 32,
        "episode_id": malicious,
        "created_at": "today",
        "observation": {"requests": 1, "errors": 1},
        "result": {
            "mode": "baseline",
            "traces": [],
            "finding": {
                "title": malicious,
                "explanation": malicious,
                "action": malicious,
                "evidence_ids": [],
                "limitations": malicious,
            },
        },
    }
    instance = IncidentService.__new__(IncidentService)
    instance.store = SimpleNamespace(
        read=lambda *args: record, latest_recovery=lambda *args: None, events=lambda *args: []
    )
    document = instance.postmortem(record["id"])
    assert "[open](https://evil.example)" not in document
    assert "<script>" not in document and "\r" not in document
    assert "\\[open\\]\\(https://evil.example\\)" in document
    assert "\x00" not in markdown("first\x00second")
