from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from incidentlab.api import create_app
from incidentlab.lab import Lab


@pytest.fixture
def lab(tmp_path: Path):
    lab = Lab(tmp_path / "lab")
    yield lab
    lab.close()


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with TestClient(create_app(tmp_path / "api"), base_url="http://127.0.0.1") as client:
        yield client
