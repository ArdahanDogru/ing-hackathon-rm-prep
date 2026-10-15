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


def make(tmp_path, *providers, workers=1, action_log=None):
    service = ResearchService(load_config(), providers, tmp_path, now=lambda: NOW,
                              max_workers=workers, off_reason="no key in .env: EXA_API_KEY")
    client = TestClient(create_app(FakeBackend(FIX, results=[ready_result()]), research=service,
                                   action_log=action_log))
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
    assert r.status_code == 200 and r.json()["summary"] == "" and r.json()["version"] == 2
    bad = client.post(f"/api/runs/{run_id}/research/questions",
                      json={"question": "Müşterim için hangisi?", "lang": "TR"})
    assert bad.status_code == 422 and "müşteri bilgisi" in bad.json()["detail"]


def test_without_research_the_route_is_absent(tmp_path):
    client = TestClient(create_app(FakeBackend(FIX)))
    run_id = new_run(client)
    assert client.get(f"/api/runs/{run_id}/research").status_code == 404


# --- R4: RM marks ------------------------------------------------------------


class RecordingLog:
    """Stands in for ActionLog: keeps every append call."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def append(self, action, **kw):
        self.calls.append((action, kw))


def first_finding(client, run_id):
    body = client.get(f"/api/runs/{run_id}/research?lang=TR").json()
    p = body["products"][0]
    return p["option_id"], p["findings"][0]


def test_set_mark_shows_in_the_next_research_get_and_null_removes_it(tmp_path):
    client, service = make(tmp_path, FakeProvider())
    run_id = new_run(client)
    service.wait()
    option_id, finding = first_finding(client, run_id)
    assert finding["mark"] is None
    r = client.post("/api/research/marks", json={
        "finding_id": finding["id"], "option_id": option_id, "mark": "ok", "run_id": run_id})
    assert r.status_code == 200 and r.json() == {"finding_id": finding["id"], "mark": "ok"}
    assert first_finding(client, run_id)[1]["mark"] == "ok"
    r = client.post("/api/research/marks", json={
        "finding_id": finding["id"], "option_id": option_id, "mark": None, "run_id": run_id})
    assert r.status_code == 200 and r.json() == {"finding_id": finding["id"], "mark": None}
    assert first_finding(client, run_id)[1]["mark"] is None


def test_a_refused_mark_is_422_and_not_logged(tmp_path):
    log = RecordingLog()
    client, service = make(tmp_path, FakeProvider(), action_log=log)
    run_id = new_run(client)
    service.wait()
    option_id, finding = first_finding(client, run_id)
    for body in ({"finding_id": finding["id"], "mark": "maybe"}, {"finding_id": "x123", "mark": "ok"}):
        r = client.post("/api/research/marks", json={**body, "option_id": option_id, "run_id": run_id})
        assert r.status_code == 422
    assert "maybe" in client.post("/api/research/marks", json={
        "finding_id": finding["id"], "option_id": option_id, "mark": "maybe",
        "run_id": run_id}).json()["detail"]
    assert [c for c in log.calls if c[0] == "research_marked"] == []
    assert service.marks() == {}


def test_a_mark_is_logged_with_the_run_also_for_a_removal_and_an_unknown_run(tmp_path):
    log = RecordingLog()
    client, service = make(tmp_path, FakeProvider(), action_log=log)
    run_id = new_run(client)
    service.wait()
    option_id, finding = first_finding(client, run_id)
    base = {"finding_id": finding["id"], "option_id": option_id}
    assert client.post("/api/research/marks", json={**base, "mark": "wrong", "run_id": run_id}).status_code == 200
    assert client.post("/api/research/marks", json={**base, "mark": None, "run_id": run_id}).status_code == 200
    assert client.post("/api/research/marks", json={**base, "mark": "ok", "run_id": "Rnope"}).status_code == 200
    marked = [c for c in log.calls if c[0] == "research_marked"]
    assert [kw["details"]["mark"] for _, kw in marked] == ["wrong", None, "ok"]
    assert all(kw["details"] == {**base, "mark": kw["details"]["mark"]} for _, kw in marked)
    assert [kw["run_id"] for _, kw in marked] == [run_id, run_id, "Rnope"]
    assert marked[0][1]["run"].run_id == run_id and marked[1][1]["run"].run_id == run_id
    assert marked[2][1]["run"] is None


def test_the_marks_route_is_absent_without_research(tmp_path):
    client = TestClient(create_app(FakeBackend(FIX)))
    assert client.post("/api/research/marks", json={
        "finding_id": "Fabcdef01", "option_id": "fund:BBF", "mark": "ok", "run_id": "R1"}).status_code in (404, 405)
