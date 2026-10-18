from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from incidentlab import __version__
from incidentlab.api.frontend import mount_frontend
from incidentlab.api.security import (
    LocalRequestSecurity,
    response_security_headers,
    safe_provider_status,
)
from incidentlab.application import ConflictError, IncidentService
from incidentlab.domain.models import (
    InjectRequest,
    InvestigateRequest,
    ProbeRequest,
    PromoteRequest,
    RehearseRequest,
    RemediateRequest,
)
from incidentlab.lab.scenarios import SCENARIO_BY_ID, SCENARIOS


def create_app(directory: Path | None = None, *, allowed_hosts: list[str] | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = IncidentService(
            directory or Path(os.environ.get("INCIDENTLAB_DATA_DIR", "runtime"))
        )
        app.state.service = service
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="IncidentLab", version=__version__, lifespan=lifespan)
    app.add_middleware(LocalRequestSecurity, allowed_hosts=allowed_hosts)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "The operation could not complete. Check the local server logs."},
            headers=response_security_headers(request.url.path, 500),
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {
            "mistral_configured": bool(os.environ.get("MISTRAL_API_KEY", "").strip()),
            "model": os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
            "scope": "Disposable local lab",
            "version": __version__,
        }

    @app.get("/api/scenarios")
    def scenarios():
        # Labels are visible to the operator, never passed to the investigator.
        return [
            {"id": s.id, "name": s.name, "description": s.description, "fault_count": s.fault_count}
            for s in SCENARIOS
        ]

    @app.get("/api/status")
    def status(request: Request):
        return request.app.state.service.status()

    @app.get("/api/workspace")
    def workspace(request: Request):
        return request.app.state.service.workspace()

    @app.get("/api/history")
    def history(request: Request, limit: int = Query(default=50, ge=1, le=100)):
        return request.app.state.service.history(limit)

    @app.post("/api/inject")
    def inject(body: InjectRequest, request: Request):
        if body.scenario_id not in SCENARIO_BY_ID:
            raise HTTPException(422, "Unknown scenario")
        return request.app.state.service.inject(body.scenario_id, body.seed)

    @app.post("/api/probe")
    def probe(body: ProbeRequest, request: Request):
        return request.app.state.service.probe(body.count)

    @app.post("/api/investigate")
    def investigate(body: InvestigateRequest, request: Request):
        if body.mode != "baseline" and not os.environ.get("MISTRAL_API_KEY", "").strip():
            raise HTTPException(
                503,
                "MISTRAL_API_KEY is not configured. Choose the offline baseline or configure the server environment.",
            )
        try:
            return request.app.state.service.investigate(body)
        except ValueError as exc:
            raise HTTPException(
                502,
                "The investigator returned an invalid or unsupported finding. No action was applied.",
            ) from exc
        except RuntimeError as exc:
            status = safe_provider_status(exc)
            provider = f" (provider HTTP {status})" if status is not None else ""
            raise HTTPException(
                502, f"The investigator could not complete{provider}. No action was applied."
            ) from None

    @app.post("/api/remediate")
    def remediate(body: RemediateRequest, request: Request):
        return request.app.state.service.remediate(body.investigation_id, body.action)

    @app.post("/api/rehearse")
    def rehearse(body: RehearseRequest, request: Request):
        if body.strategy == "mistral" and not os.environ.get("MISTRAL_API_KEY", "").strip():
            raise HTTPException(
                503,
                "MISTRAL_API_KEY is not configured. Choose the offline adaptive policy or configure the server environment.",
            )
        try:
            return request.app.state.service.rehearse(
                body.max_actions,
                body.probe_count,
                strategy=body.strategy,
                max_experiments=body.max_experiments,
            )
        except ValueError as exc:
            raise HTTPException(
                502,
                "The planner returned an invalid or unsupported experiment. No new plan was authorized.",
            ) from exc
        except RuntimeError:
            raise HTTPException(
                502, "The rehearsal did not complete. No new plan was authorized."
            ) from None

    @app.post("/api/promote")
    def promote(body: PromoteRequest, request: Request):
        return request.app.state.service.promote(body.rehearsal_id, body.plan_id)

    @app.post("/api/rehearsals/{rehearsal_id}/proof")
    def prove_recovery(rehearsal_id: str, request: Request):
        try:
            return request.app.state.service.prove(rehearsal_id)
        except RuntimeError:
            raise HTTPException(
                502,
                "The recovery proof did not complete. No promotion is authorized by this attempt.",
            ) from None

    @app.get("/api/rehearsals/{rehearsal_id}/proof")
    def proof_artifact(rehearsal_id: str, request: Request):
        try:
            result = request.app.state.service.read_proof(rehearsal_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Recovery proof not found") from exc
        return JSONResponse(
            result,
            headers={
                "Content-Disposition": f'attachment; filename="incidentlab-proof-{rehearsal_id}.json"'
            },
        )

    @app.get("/api/rehearsals/{rehearsal_id}")
    def rehearsal_artifact(rehearsal_id: str, request: Request):
        try:
            record = request.app.state.service.read_rehearsal(rehearsal_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Rehearsal not found") from exc
        return JSONResponse(
            record,
            headers={
                "Content-Disposition": f'attachment; filename="incidentlab-rehearsal-{rehearsal_id}.json"'
            },
        )

    @app.get("/api/postmortems/{investigation_id}")
    def postmortem(investigation_id: str, request: Request):
        try:
            content = request.app.state.service.postmortem(investigation_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Investigation not found") from exc
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="incidentlab-{investigation_id}.md"'
            },
        )

    @app.get("/api/investigations/{investigation_id}")
    def artifact(investigation_id: str, request: Request):
        try:
            record = request.app.state.service.read(investigation_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Investigation not found") from exc
        return JSONResponse(
            record,
            headers={
                "Content-Disposition": f'attachment; filename="incidentlab-{investigation_id}.json"'
            },
        )

    mount_frontend(app)
    return app
