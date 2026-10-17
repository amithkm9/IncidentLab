from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .lab import SCENARIOS, SCENARIO_BY_ID
from .models import InjectRequest, InvestigateRequest, ProbeRequest, PromoteRequest, RehearseRequest, RemediateRequest
from .service import ConflictError, IncidentService


def create_app(directory: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = IncidentService(directory or Path(os.environ.get("INCIDENTLAB_DATA_DIR", "runtime")))
        app.state.service = service
        try:
            yield
        finally:
            service.close()

    app = FastAPI(title="IncidentLab", version="0.2.0", lifespan=lifespan)
    static = Path(__file__).parent / "static"

    @app.middleware("http")
    async def local_browser_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin and urlsplit(origin).netloc != request.headers.get("host")
            ):
                return JSONResponse(status_code=403, content={"detail": "Use the IncidentLab interface on this origin."})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        # FastAPI's interactive documentation loads its own Swagger/ReDoc assets.
        if request.url.path not in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
            response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/api/config")
    def config():
        return {"mistral_configured": bool(os.environ.get("MISTRAL_API_KEY", "").strip()),
                "model": os.environ.get("MISTRAL_MODEL", "mistral-small-latest"),
                "scope": "Disposable local lab", "version": "0.2.0"}

    @app.get("/api/scenarios")
    def scenarios():
        # Labels are visible to the operator, never passed to the investigator.
        return [{"id": s.id, "name": s.name, "description": s.description,
                 "fault_count": s.fault_count} for s in SCENARIOS]

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
            raise HTTPException(503, "MISTRAL_API_KEY is not configured. Choose the offline baseline or configure the server environment.")
        try:
            return request.app.state.service.investigate(body)
        except ValueError as exc:
            raise HTTPException(502, "The investigator returned an invalid or unsupported finding. No action was applied.") from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/remediate")
    def remediate(body: RemediateRequest, request: Request):
        return request.app.state.service.remediate(body.investigation_id, body.action)

    @app.post("/api/rehearse")
    def rehearse(body: RehearseRequest, request: Request):
        if body.strategy == "mistral" and not os.environ.get("MISTRAL_API_KEY", "").strip():
            raise HTTPException(503, "MISTRAL_API_KEY is not configured. Choose the offline adaptive policy or configure the server environment.")
        try:
            return request.app.state.service.rehearse(body.max_actions, body.probe_count,
                strategy=body.strategy, max_experiments=body.max_experiments)
        except ValueError as exc:
            raise HTTPException(502, "The planner returned an invalid or unsupported experiment. No new plan was authorized.") from exc
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.post("/api/promote")
    def promote(body: PromoteRequest, request: Request):
        return request.app.state.service.promote(body.rehearsal_id, body.plan_id)

    @app.get("/api/rehearsals/{rehearsal_id}")
    def rehearsal_artifact(rehearsal_id: str, request: Request):
        try:
            record = request.app.state.service.read_rehearsal(rehearsal_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Rehearsal not found") from exc
        return JSONResponse(record, headers={"Content-Disposition": f'attachment; filename="incidentlab-rehearsal-{rehearsal_id}.json"'})

    @app.get("/api/postmortems/{investigation_id}")
    def postmortem(investigation_id: str, request: Request):
        try:
            content = request.app.state.service.postmortem(investigation_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Investigation not found") from exc
        return PlainTextResponse(content, media_type="text/markdown", headers={
            "Content-Disposition": f'attachment; filename="incidentlab-{investigation_id}.md"'})

    @app.get("/api/investigations/{investigation_id}")
    def artifact(investigation_id: str, request: Request):
        try:
            record = request.app.state.service.read(investigation_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, "Investigation not found") from exc
        return JSONResponse(record, headers={"Content-Disposition": f'attachment; filename="incidentlab-{investigation_id}.json"'})

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
