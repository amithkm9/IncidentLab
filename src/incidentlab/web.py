"""Serve the compiled TypeScript app from a source checkout or Python wheel."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def frontend_directory() -> Path:
    package_directory = Path(__file__).resolve().parent
    packaged = package_directory / "web"
    if (packaged / "index.html").is_file():
        return packaged
    return package_directory.parents[1] / "frontend" / "dist"


def mount_frontend(app: FastAPI, directory: Path | None = None) -> None:
    """Keep API development available before the optional local UI build exists."""
    directory = directory or frontend_directory()

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_file = directory / "index.html"
        if not index_file.is_file():
            raise HTTPException(
                status_code=503,
                detail="The frontend is not built. Run make bootstrap, then restart IncidentLab.",
            )
        return FileResponse(index_file, headers={"Cache-Control": "no-cache"})

    if (directory / "static").is_dir():
        app.mount("/static", StaticFiles(directory=directory / "static"), name="static")
