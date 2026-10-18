"""The shipped page must load compiled assets, never raw TypeScript sources."""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from incidentlab.api.frontend import mount_frontend


def test_built_frontend_loads_all_referenced_assets(client):
    page = client.get("/")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-cache"
    references = re.findall(r'(?:src|href)="(/static/[^\"]+)"', page.text)
    assert any(path.endswith(".js") for path in references)
    assert any(path.endswith(".css") for path in references)
    assert 'type="module"' in page.text
    for path in references:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/app.js").status_code == 404
    assert client.get("/src/main.ts").status_code == 404


def test_missing_frontend_build_explains_setup_without_breaking_api(tmp_path):
    app = FastAPI()
    mount_frontend(app, tmp_path / "missing-build")

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/")
        assert response.status_code == 503
        assert "make bootstrap" in response.json()["detail"]
        assert client.get("/static/missing.js").status_code == 404
