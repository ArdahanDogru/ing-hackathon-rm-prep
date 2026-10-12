"""PUT /api/runs/{id}/narrative/{lang}/blocks/{block_id} (docs/web-ui.md
"Section-by-section editing"), on the FakeBackend."""


def _text(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    first = view["result"]["options"][1]["option"]["option_id"]
    client.post(f"/api/runs/{rid}/approval", json={"status": "approved", "selected": [first]})
    return rid, client.get(f"/api/runs/{rid}/narrative").json()


def test_edit_and_restore_a_block(client, persona):
    rid, d = _text(client, persona)
    r = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Yeni amaç cümlesi."})
    assert r.status_code == 200
    r = r.json()
    assert r["rm_edits"] == {"ozet": "Yeni amaç cümlesi."} and "Yeni amaç cümlesi." in r["markdown"]
    assert r["draft_markdown"] == d["draft_markdown"]
    back = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": None}).json()
    assert back["rm_edits"] == {} and back["markdown"] == d["markdown"]


def test_unknown_block_422(client, persona):
    rid, _ = _text(client, persona)
    r = client.put(f"/api/runs/{rid}/narrative/TR/blocks/nope", json={"text": "x"})
    assert r.status_code == 422 and "ozet" in r.json()["detail"]


def test_empty_edit_422(client, persona):
    rid, _ = _text(client, persona)
    assert client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "  "}).status_code == 422


def test_fixing_the_block_clears_the_blocker(client, persona):
    rid, _ = _text(client, persona)
    r = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet",
                   json={"text": "Bu fon kesin getiri sağlar."}).json()
    assert any(f.startswith("phrase:") for f in r["edit_checks"]["ozet"])
    blocked = client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": r["markdown"]})
    assert blocked.status_code == 422 and "blocking" in blocked.json()["detail"]
    ok = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Bu fon düşük risklidir."}).json()
    assert "ozet" not in ok["edit_checks"]
    assert client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": ok["markdown"]}).status_code == 200


def test_no_edit_after_approval(client, persona):
    rid, d = _text(client, persona)
    client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": d["markdown"]})
    assert client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "x"}).status_code == 422


def test_edit_needs_a_known_run(client):
    assert client.put("/api/runs/R0000000000/narrative/TR/blocks/ozet", json={"text": "x"}).status_code == 404
