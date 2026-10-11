"""API core (docs/web-ui.md sections 6 and 8): personas, snapshots, runs,
answers, approval, notes, errors."""


def test_personas_and_snapshots(client):
    assert {p["persona_id"] for p in client.get("/api/personas").json()} >= {"P01", "P02"}
    snaps = client.get("/api/snapshots").json()
    assert snaps and all(isinstance(s, str) for s in snaps)
    sources = client.get(f"/api/snapshots/{snaps[0]}/sources").json()
    assert isinstance(sources, dict) and sources


def test_run_and_get_again(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    run_id = view["result"]["run_id"]
    assert view["test_run"] is False and view["persona_changes"] == []
    assert client.get(f"/api/runs/{run_id}").json()["result"]["run_id"] == run_id


def test_unknown_run_404(client):
    r = client.get("/api/runs/R0000000000")
    assert r.status_code == 404 and "run" in r.json()["detail"]
    r = client.post("/api/runs/R0000000000/approval", json={"status": "approved", "selected": ["x"]})
    assert r.status_code == 404


def test_bad_persona_422(client, persona):
    bad = dict(persona)
    bad.pop("profil")
    assert client.post("/api/runs", json={"persona": bad}).status_code == 422


def test_test_run_cannot_be_approved(client, persona):
    edited = dict(persona, yas=persona["yas"] + 1)
    view = client.post("/api/runs", json={"persona": edited}).json()
    assert view["test_run"] is True
    assert view["persona_changes"] == [
        {"field": "yas", "original": persona["yas"], "edited": persona["yas"] + 1}]
    first = view["result"]["options"][0]["option"]["option_id"]
    r = client.post(f"/api/runs/{view['result']['run_id']}/approval",
                    json={"status": "approved", "note": "", "selected": [first]})
    assert r.status_code == 422 and r.json()["detail"]


def test_approve_then_notes(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    first = view["result"]["options"][0]["option"]["option_id"]
    a = client.post(f"/api/runs/{rid}/approval",
                    json={"status": "approved", "note": "n", "selected": [first]})
    assert a.status_code == 200 and a.json()["result"]["rm_status"] == "approved"
    n = client.put(f"/api/runs/{rid}/notes", json={"note": "genel", "option_notes": {first: "not"}})
    assert n.status_code == 200
    assert n.json()["result"]["rm_note"] == "genel"
    assert n.json()["result"]["rm_option_notes"] == {first: "not"}


def test_reject_needs_note(client, persona):
    rid = client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    r = client.post(f"/api/runs/{rid}/approval", json={"status": "rejected", "note": "", "selected": []})
    assert r.status_code == 422


def test_bad_status_422(client, persona):
    rid = client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    assert client.post(f"/api/runs/{rid}/approval", json={"status": "pending"}).status_code == 422


def test_answer_makes_new_run(client):
    p01 = next(p for p in client.get("/api/personas").json() if p["persona_id"] == "P01")
    view = client.post("/api/runs", json={"persona": p01}).json()
    assert view["result"]["state"] == "needs_rm_input"
    q = next(q for q in view["result"]["questions"] if q["answer"] is None)
    new = client.post(f"/api/runs/{view['result']['run_id']}/answers",
                      json={"question_id": q["question_id"], "answer": q["choices"][0]}).json()
    assert new["result"]["run_id"] != view["result"]["run_id"]
    assert client.get(f"/api/runs/{new['result']['run_id']}").status_code == 200
