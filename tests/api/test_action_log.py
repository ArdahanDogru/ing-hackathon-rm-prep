"""L1 (spec 2026-10-15-rm-action-log-design): every decision and edit of the RM is one
JSON line in data/logs/rm-actions/<day>.jsonl (FakeBackend, a fake research service)."""
import json
import os
import stat
import threading
from datetime import date, datetime

from fastapi.testclient import TestClient

from rmprep.api.action_log import ActionLog
from rmprep.api.app import create_app
from rmprep.contracts import TR_TZ

T = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)
SHARES = {"nakit_benzeri": 80, "borclanma": 10, "hisse": 5, "altin_doviz": 5, "dengeli": 0}


def _setup(backend, tmp_path, **kw):
    log = ActionLog(tmp_path / "rm-actions", now=lambda: T)
    return TestClient(create_app(backend, action_log=log, **kw)), log


def _records(log):
    p = log.path_for(T.date())
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def _ready(c):
    for p in c.get("/api/personas").json():
        v = c.post("/api/runs", json={"persona": p}).json()
        if v["result"]["state"] == "ready":
            return v
    raise AssertionError("no ready run")


def _approved(c):
    v = _ready(c)
    rid = v["result"]["run_id"]
    first = v["result"]["options"][0]["option"]["option_id"]
    c.post(f"/api/runs/{rid}/approval", json={"status": "approved", "note": "tamam", "selected": [first]})
    return rid


def test_run_opened_and_the_record_shape(backend, tmp_path, persona):
    c, log = _setup(backend, tmp_path)
    v = c.post("/api/runs", json={"persona": persona}).json()
    [r] = _records(log)
    assert list(r) == ["ts", "action", "run_id", "persona_id", "snapshot_id", "details"]
    assert r["action"] == "run_opened" and r["run_id"] == v["result"]["run_id"]
    assert r["ts"] == T.isoformat() and r["persona_id"] == persona["persona_id"]
    assert r["details"] == {"test_run": False, "persona_changes": [], "excluded_sources": [],
                            "state": v["result"]["state"]}


def test_get_requests_are_not_logged(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    rid = _ready(c)["result"]["run_id"]
    n = len(_records(log))
    c.get(f"/api/runs/{rid}")
    c.get("/api/personas")
    assert len(_records(log)) == n


def test_answer_and_holdings_carry_the_new_run(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    v = _ready(c)
    rid = v["result"]["run_id"]
    new = c.post(f"/api/runs/{rid}/holdings", json={"shares": SHARES, "origin": "rm"}).json()
    back = c.post(f"/api/runs/{new['result']['run_id']}/holdings", json={"shares": None}).json()
    recs = _records(log)
    h = recs[-2]
    assert h["action"] == "holdings_set" and h["run_id"] == rid and h["new_run_id"] == new["result"]["run_id"]
    assert h["details"] == {"shares": {k: float(x) for k, x in SHARES.items()}, "origin": "rm"}
    assert recs[-1]["action"] == "holdings_reset" and recs[-1]["new_run_id"] == back["result"]["run_id"]
    # a refused split (422) changes nothing and is not logged
    n = len(recs)
    assert c.post(f"/api/runs/{rid}/holdings", json={"shares": {"hisse": 1}, "origin": "rm"}).status_code == 422
    assert len(_records(log)) == n


def test_question_answered(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    for p in c.get("/api/personas").json():
        v = c.post("/api/runs", json={"persona": p}).json()
        q = next((q for q in v["result"]["questions"] if q["answer"] is None and q["choices"]), None)
        if q:
            rid = v["result"]["run_id"]
            new = c.post(f"/api/runs/{rid}/answers", json={"question_id": q["question_id"],
                                                           "answer": q["choices"][0]}).json()
            r = _records(log)[-1]
            assert r["action"] == "question_answered" and r["new_run_id"] == new["result"]["run_id"]
            assert r["details"] == {"question_id": q["question_id"], "answer": q["choices"][0]}
            return
    raise AssertionError("no open question in the fixtures")


def test_decision_approved_and_rejected(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    v = _ready(c)
    rid = v["result"]["run_id"]
    first = v["result"]["options"][0]["option"]["option_id"]
    c.post(f"/api/runs/{rid}/approval", json={"status": "approved", "note": "tamam", "selected": [first]})
    r = _records(log)[-1]
    assert r["action"] == "decision_approved"
    assert r["details"] == {"engine_top3": v["result"]["recommended"], "agent_top3": [],
                            "agent_state": "none", "selected": [first], "note": "tamam"}
    c.post(f"/api/runs/{rid}/approval", json={"status": "rejected", "note": "uygun değil", "selected": []})
    assert _records(log)[-1]["action"] == "decision_rejected"


def test_notes_saved(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    rid = _approved(c)
    c.put(f"/api/runs/{rid}/notes", json={"note": "Genel not.", "option_notes": {}})
    r = _records(log)[-1]
    assert r["action"] == "notes_saved" and r["details"] == {"note": "Genel not.", "option_notes": {}}


def test_block_edit_delete_restore(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    rid = _approved(c)
    d = c.get(f"/api/runs/{rid}/narrative").json()
    original = " ".join(s["text"] for s in next(x for x in d["sections"] if x["key"] == "ozet")["sentences"])
    c.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Yeni özet."})
    c.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": " "})
    c.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": None})
    e, dl, rs = _records(log)[-3:]
    assert (e["action"], e["lang"], e["details"]["block_id"]) == ("text_block_edited", "TR", "ozet")
    assert e["details"]["before"] == original and e["details"]["after"] == "Yeni özet."
    assert e["details"]["findings"] == []
    assert dl["action"] == "text_block_deleted" and dl["details"]["before"] == "Yeni özet." and dl["details"]["after"] == ""
    assert rs["action"] == "text_block_restored" and rs["details"]["before"] == "" and rs["details"]["after"] == original


def test_restore_of_an_unedited_block(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    rid = _approved(c)
    c.get(f"/api/runs/{rid}/narrative")
    c.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": None})
    r = _records(log)[-1]
    assert r["action"] == "text_block_restored" and r["details"]["before"] == r["details"]["after"] != ""


def test_card_download_and_refused_card_are_logged(backend, tmp_path):
    c, log = _setup(backend, tmp_path)
    rid = _approved(c)
    c.get(f"/api/runs/{rid}/narrative")
    assert c.get(f"/api/runs/{rid}/card.md").status_code == 200
    r = _records(log)[-1]
    assert r["action"] == "card_downloaded" and r["details"] == {"format": "md", "has_text": True, "refused": False}
    c.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Bu fon garanti getiri sağlar."})
    assert c.get(f"/api/runs/{rid}/card.md").status_code == 422
    r = _records(log)[-1]
    assert r["action"] == "card_downloaded" and r["details"]["refused"] is True


class FakeResearch:
    enabled = True

    def start(self, result, lang="TR"):
        pass

    def status(self, result, lang):
        return {"state": "ready", "products": [], "questions": []}

    def ask(self, result, question, lang):
        from rmprep.research.service import QuestionRefused
        if "müşteri" in question:
            raise QuestionRefused("Soru müşteri bilgisi içeriyor.")

        class A:
            findings = (1, 2)

            def to_dict(self):
                return {"question": question, "findings": [{}, {}]}
        return A()


def test_research_questions_are_logged_also_when_refused(backend, tmp_path):
    c, log = _setup(backend, tmp_path, research=FakeResearch())
    rid = _ready(c)["result"]["run_id"]
    assert c.post(f"/api/runs/{rid}/research/questions", json={"question": "Fonun son haberi?", "lang": "TR"}).status_code == 200
    ok = _records(log)[-1]
    assert ok["action"] == "research_question" and ok["details"] == {"question": "Fonun son haberi?",
                                                                    "refused": False, "findings": 2}
    assert c.post(f"/api/runs/{rid}/research/questions",
                  json={"question": "müşterinin yaşı?", "lang": "TR"}).status_code == 422
    no = _records(log)[-1]
    assert no["details"]["refused"] is True and no["details"]["findings"] == 0


def test_write_failure_does_not_break_the_action(backend, tmp_path, persona, capsys):
    folder = tmp_path / "rm-actions"
    folder.write_text("not a folder")          # the log cannot create its folder
    log = ActionLog(folder, now=lambda: T)
    c = TestClient(create_app(backend, action_log=log))
    assert c.post("/api/runs", json={"persona": persona}).status_code == 200
    assert "action log" in capsys.readouterr().err


def test_parallel_appends_stay_whole(tmp_path):
    log = ActionLog(tmp_path / "rm-actions", now=lambda: T)
    def many(k):
        for i in range(50):
            log.append("notes_saved", run_id=f"R{k:010d}", details={"note": "x" * 500, "i": i})
    threads = [threading.Thread(target=many, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = log.path_for(T.date()).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 200 and all(json.loads(x)["action"] == "notes_saved" for x in lines)


def test_one_file_per_day(tmp_path):
    days = iter([datetime(2026, 10, 15, 23, 59, tzinfo=TR_TZ), datetime(2026, 10, 16, 0, 1, tzinfo=TR_TZ)])
    log = ActionLog(tmp_path / "rm-actions", now=lambda: next(days))
    log.append("notes_saved", run_id="R0000000001")
    log.append("notes_saved", run_id="R0000000001")
    assert log.path_for(date(2026, 10, 15)).exists() and log.path_for(date(2026, 10, 16)).exists()
