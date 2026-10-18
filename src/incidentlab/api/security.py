"""Local browser boundary and bounded API request handling.

Host validation prevents browser DNS rebinding; it is not authentication for an
internet-facing deployment. The CLI and Docker defaults bind to loopback.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from collections.abc import Iterable

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_API_BODY_BYTES = 65_536
BODY_READ_TIMEOUT_SECONDS = 10
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DOC_PATHS = frozenset({"/docs", "/redoc", "/docs/oauth2-redirect"})


def _authority(value: str, scheme: str) -> tuple[str, int] | None:
    if not value or any(ord(character) <= 32 or ord(character) >= 127 for character in value):
        return None
    if any(character in value for character in "/\\?#@%,"):
        return None
    # A Host authority has no credentials, path, query, fragment or zone ID.
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit("//" + value)
        host = parsed.hostname
        port = parsed.port
        if not host or parsed.path or parsed.query or parsed.fragment:
            return None
        if port is not None and not 1 <= port <= 65535:
            return None
        if value.endswith(":"):
            return None
        try:
            host = ipaddress.ip_address(host).compressed
        except ValueError:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.?", host):
                return None
        return host, port if port is not None else 443 if scheme == "https" else 80
    except ValueError:
        return None


def _origin(value: str) -> tuple[str, str, int] | None:
    match = re.fullmatch(r"(https?)://([^/?#]+)", value)
    if not match:
        return None
    scheme, authority = match.groups()
    parsed = _authority(authority, scheme)
    return (scheme, *parsed) if parsed else None


def response_security_headers(path: str, status_code: int) -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "same-origin",
        "X-Frame-Options": "DENY",
        "Cross-Origin-Resource-Policy": "same-origin",
    }
    if path not in _DOC_PATHS:
        headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
    if path == "/api" or path.startswith("/api/") or status_code >= 400:
        headers.update({"Cache-Control": "no-store", "Pragma": "no-cache", "Expires": "0"})
    return headers


def safe_provider_status(error: Exception) -> int | None:
    """Keep a validated numeric status, never interpolate exception text."""
    metadata = getattr(error, "metadata", None)
    if isinstance(metadata, dict):
        status = metadata.get("status_code")
        if type(status) is int and 400 <= status <= 599:
            return status
    # The older investigator emits this fixed prefix. Preserve its useful code
    # while discarding any body, path, credentials or suffix in the exception.
    match = re.match(
        r"^Mistral (?:API|Conversations) returned HTTP ([45][0-9]{2})(?:;|$)", str(error)
    )
    return int(match.group(1)) if match else None


class LocalRequestSecurity:
    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str] | None = None):
        self.app = app
        self.allowed_hosts = frozenset(
            DEFAULT_ALLOWED_HOSTS if allowed_hosts is None else allowed_hosts
        )
        if not self.allowed_hosts or any(
            not isinstance(host, str) or "*" in host or not host for host in self.allowed_hosts
        ):
            raise ValueError(
                "Configure explicit allowed hostnames; wildcard hosts are not supported"
            )
        self.allowed_hosts = frozenset(host.lower().rstrip(".") for host in self.allowed_hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for key, value in response_security_headers(path, message["status"]).items():
                    headers[key] = value
            await send(message)

        async def reject(status: int, detail: str) -> None:
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secured_send)

        values: dict[bytes, list[str]] = {}
        for key, value in scope.get("headers", []):
            values.setdefault(key.lower(), []).append(value.decode("latin-1"))
        hosts = values.get(b"host", [])
        scheme = scope.get("scheme", "http")
        authority = _authority(hosts[0], scheme) if len(hosts) == 1 else None
        if authority is None or authority[0].rstrip(".") not in self.allowed_hosts:
            await reject(400, "Invalid Host header for this local application.")
            return
        origins = values.get(b"origin", [])
        if origins and (len(origins) != 1 or _origin(origins[0]) != (scheme, *authority)):
            await reject(403, "Use the IncidentLab interface on this origin.")
            return
        unsafe = scope["method"] not in _SAFE_METHODS
        fetch_sites = values.get(b"sec-fetch-site", [])
        if (
            unsafe
            and fetch_sites
            and (len(fetch_sites) != 1 or fetch_sites[0] not in {"same-origin", "none"})
        ):
            await reject(403, "Use the IncidentLab interface on this origin.")
            return
        is_api = path == "/api" or path.startswith("/api/")
        if unsafe and is_api:
            lengths = values.get(b"content-length", [])
            if lengths and (len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,12}", lengths[0])):
                await reject(400, "Invalid request body length.")
                return
            if lengths and int(lengths[0]) > MAX_API_BODY_BYTES:
                await reject(413, "API request body exceeds the 64 KiB limit.")
                return
            body = bytearray()
            try:
                async with asyncio.timeout(BODY_READ_TIMEOUT_SECONDS):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        if len(body) + len(chunk) > MAX_API_BODY_BYTES:
                            await reject(413, "API request body exceeds the 64 KiB limit.")
                            return
                        body.extend(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                await reject(408, "The API request body did not complete in time.")
                return
            if lengths and len(body) != int(lengths[0]):
                await reject(400, "Request body length does not match Content-Length.")
                return
            sent_body = False

            async def bounded_receive() -> Message:
                nonlocal sent_body
                if not sent_body:
                    sent_body = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, bounded_receive, secured_send)
        else:
            await self.app(scope, receive, secured_send)
