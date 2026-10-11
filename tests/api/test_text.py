"""Meeting text, card, evidence and glossary endpoints (docs/web-ui.md section 6)."""

import threading

from fastapi.testclient import TestClient

from rmprep.api.app import create_app


def _approved(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    first = view["result"]["options"][0]["option"]["option_id"]
    r = client.post(f"/api/runs/{rid}/approval",
                    json={"status": "approved", "note": "", "selected": [first]})
    assert r.status_code == 200
    return view, rid


def test_narrative_and_approval(client, persona):
    _, rid = _approved(client, persona)
    d = client.get(f"/api/runs/{rid}/narrative", params={"lang": "TR"}).json()
    assert d["lang"] == "TR" and d["status"] == "draft" and d["markdown"].strip()
    a = client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": d["markdown"]}).json()
    assert a["status"] == "approved" and a["rm_text"] == d["markdown"]
    again = client.get(f"/api/runs/{rid}/narrative", params={"lang": "TR"}).json()
    assert again["status"] == "approved" and again["markdown"] == d["markdown"]


def test_narrative_needs_approval_and_known_run(client, persona):
    rid = client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    assert client.get(f"/api/runs/{rid}/narrative").status_code == 422
    assert client.get("/api/runs/R0000000000/narrative").status_code == 404


def test_empty_approved_text_422(client, persona):
    _, rid = _approved(client, persona)
    client.get(f"/api/runs/{rid}/narrative")
    assert client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": " "}).status_code == 422


def test_narrative_timeout_504(backend, persona):
    gate = threading.Event()
    slow = backend.draft_narrative

    def wait_then_draft(run_id, lang="TR"):
        gate.wait(5)
        return slow(run_id, lang)

    backend.draft_narrative = wait_then_draft
    client = TestClient(create_app(backend, narrative_timeout_s=0.1))
    _, rid = _approved(client, persona)
    try:
        r = client.get(f"/api/runs/{rid}/narrative")
        assert r.status_code == 504 and r.json()["detail"]
    finally:
        gate.set()


def test_card_markdown_is_saved(client, backend, persona):
    _, rid = _approved(client, persona)
    r = client.get(f"/api/runs/{rid}/card.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert backend.cards[rid] == r.text


def test_card_holds_the_approved_text(client, persona):
    _, rid = _approved(client, persona)
    client.get(f"/api/runs/{rid}/narrative")
    client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": "ONAYLI METİN 123"})
    assert "ONAYLI METİN 123" in client.get(f"/api/runs/{rid}/card.md").text


def test_card_needs_approval(client, persona):
    rid = client.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    assert client.get(f"/api/runs/{rid}/card.md").status_code == 422


def test_notes_save_the_card(client, backend, persona):
    view, rid = _approved(client, persona)
    client.put(f"/api/runs/{rid}/notes", json={"note": "NOT-XYZ", "option_notes": {}})
    assert "NOT-XYZ" in backend.cards[rid]


def test_evidence_item_and_404(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    opt = next(o for o in view["result"]["options"] if o["option"]["kind"] == "fund")
    eid = opt["evidence_ids"][0]
    snap = view["result"]["snapshot_id"]
    item = client.get(f"/api/evidence/{snap}/{eid}").json()
    assert item["id"] == eid and item["source"] and "entity_name" in item
    assert client.get(f"/api/evidence/{snap}/nope").status_code == 404
    assert client.get(f"/api/evidence/nosnap/{eid}").status_code == 404


def test_glossary_terms_of_the_run(client, persona, tmp_path):
    _, rid = _approved(client, persona)
    client.get(f"/api/runs/{rid}/narrative")
    client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": "Valör ve stopaj önemlidir."})
    terms = client.get("/api/glossary", params={"lang": "TR", "run_id": rid}).json()
    assert [t["term"] for t in terms] == ["valor", "stopaj"]
    assert all({"term", "form", "explanation"} <= set(t) for t in terms)
    assert client.get("/api/glossary", params={"lang": "TR"}).json() == []
