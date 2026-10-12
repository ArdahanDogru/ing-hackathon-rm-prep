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


def test_approved_text_keeps_the_draft_markdown(client, persona):
    _, rid = _approved(client, persona)
    d = client.get(f"/api/runs/{rid}/narrative").json()
    assert d["draft_markdown"] == d["markdown"]
    a = client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": "edited"}).json()
    assert a["markdown"] == "edited" and a["draft_markdown"] == d["markdown"]


def test_a_new_approval_drops_the_old_text_everywhere(client, persona):
    view, rid = _approved(client, persona)
    client.get(f"/api/runs/{rid}/narrative")
    client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": "ESKİ ONAYLI METİN"})
    other = view["result"]["options"][2]["option"]["option_id"]
    client.post(f"/api/runs/{rid}/approval", json={"status": "approved", "note": "", "selected": [other]})
    d = client.get(f"/api/runs/{rid}/narrative").json()
    assert d["status"] == "draft" and "ESKİ ONAYLI METİN" not in d["markdown"]
    assert "ESKİ ONAYLI METİN" not in client.get(f"/api/runs/{rid}/card.md").text


def test_the_card_shows_the_approval_times(client, persona):
    _, rid = _approved(client, persona)
    client.get(f"/api/runs/{rid}/narrative")
    client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": "# Onaylı metin"})
    md = client.get(f"/api/runs/{rid}/card.md").text
    assert "RM onayı" in md and "Metin onayı" in md


def test_markdown_headings_use_short_fund_names(client, persona):
    """N13: the backend passes the screen names; without them a heading is the fund code."""
    _, rid = _approved(client, persona)
    md = client.get(f"/api/runs/{rid}/narrative").json()["markdown"]
    part = md.split("## Öneriler", 1)[1].split("\n## ", 1)[0]
    heads = [line[4:] for line in part.splitlines() if line.startswith("### ")]
    assert heads and all(" " in h and not h.startswith("fund:") for h in heads)
