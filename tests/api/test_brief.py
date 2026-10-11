"""GET /api/runs/{id}/brief (docs/web-ui.md "LLM brief")."""

from fastapi.testclient import TestClient

from rmprep.api.app import create_app


def test_brief_of_a_ready_run(client, persona):
    rid = client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    r = client.get(f"/api/runs/{rid}/brief", params={"lang": "TR"})
    assert r.status_code == 200
    b = r.json()
    assert b["text"].strip() and b["source"] == "template" and b["run_id"] == rid
    en = client.get(f"/api/runs/{rid}/brief", params={"lang": "EN"}).json()
    assert en["lang"] == "EN"


def test_brief_running_202(backend, persona):
    backend.brief = lambda run_id, lang="TR": None
    c = TestClient(create_app(backend))
    rid = c.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    r = c.get(f"/api/runs/{rid}/brief")
    assert r.status_code == 202 and r.json() == {"status": "running"}


def test_no_brief_for_needs_input(client):
    p01 = next(p for p in client.get("/api/personas").json() if p["persona_id"] == "P01")
    view = client.post("/api/runs", json={"persona": p01}).json()
    assert view["result"]["state"] == "needs_rm_input"          # the fixture of P01
    assert client.get(f"/api/runs/{view['result']['run_id']}/brief").status_code == 422
    assert client.get("/api/runs/R0000000000/brief").status_code == 404


def test_bad_lang_422(client, persona):
    rid = client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    assert client.get(f"/api/runs/{rid}/brief", params={"lang": "DE"}).status_code == 422
