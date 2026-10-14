import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.research.config import load_config
from rmprep.research.service import ResearchService
from rmprep.ui.fake import FakeBackend
from tests.research.conftest import NOW, RECOMMENDED, FakeProvider, ready_result

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"


def make(tmp_path, *providers, workers=1):
    service = ResearchService(load_config(), providers, tmp_path, now=lambda: NOW,
                              max_workers=workers, off_reason="no key in .env: EXA_API_KEY")
    client = TestClient(create_app(FakeBackend(FIX, results=[ready_result()]), research=service))
    return client, service


def new_run(client) -> str:
    persona = next(p for p in client.get("/api/personas").json() if p["persona_id"] == "P02")
    return client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]


def test_a_new_run_starts_the_research(tmp_path):
    p = FakeProvider()
    client, service = make(tmp_path, p)
    run_id = new_run(client)
    service.wait()
    assert [c[1] for c in p.calls] == list(RECOMMENDED)
    body = client.get(f"/api/runs/{run_id}/research?lang=TR").json()
    assert body["state"] == "ready"
    assert [x["option_id"] for x in body["products"]] == list(RECOMMENDED)


def test_running_is_202(tmp_path):
    gate = threading.Event()
    client, service = make(tmp_path, FakeProvider(gate=gate), workers=3)
    run_id = new_run(client)
    r = client.get(f"/api/runs/{run_id}/research")
    assert r.status_code == 202 and r.json() == {"state": "running"}
    gate.set()
    service.wait()


def test_off_without_a_provider(tmp_path):
    client, _ = make(tmp_path)
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research").json() == {
        "state": "off", "reason": "no key in .env: EXA_API_KEY"}


def test_unknown_run_and_bad_lang(tmp_path):
    client, _ = make(tmp_path, FakeProvider())
    assert client.get("/api/runs/Rnope/research").status_code == 404
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research?lang=DE").status_code == 422
    assert client.post(f"/api/runs/{run_id}/research/questions",
                       json={"question": "PPN nedir?", "lang": "DE"}).status_code == 422


def test_question_answer_and_refusal(tmp_path):
    client, _ = make(tmp_path, FakeProvider())
    run_id = new_run(client)
    r = client.post(f"/api/runs/{run_id}/research/questions",
                    json={"question": "Nurol Portföy son haberler", "lang": "TR"})
    assert r.status_code == 200 and r.json()["summary"] == "Yanıt."
    bad = client.post(f"/api/runs/{run_id}/research/questions",
                      json={"question": "Müşterim için hangisi?", "lang": "TR"})
    assert bad.status_code == 422 and "müşteri bilgisi" in bad.json()["detail"]


def test_without_research_the_route_is_absent(tmp_path):
    client = TestClient(create_app(FakeBackend(FIX)))
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research").status_code == 404
