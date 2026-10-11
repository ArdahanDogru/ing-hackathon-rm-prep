"""Shared fixtures of the API tests: the FakeBackend on the contract fixtures
(no network, no data/)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.ui.fake import FakeBackend

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


@pytest.fixture
def backend():
    return FakeBackend(FIX)


@pytest.fixture
def client(backend):
    return TestClient(create_app(backend))


@pytest.fixture
def persona(client):
    return next(p for p in client.get("/api/personas").json() if p["persona_id"] == "P02")
