"""W44: every profile conflict needs the RM's confirmation (with a reason) before an
approval; the confirmations go into the record, the log and the card."""

import json
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from rmprep.api.action_log import ActionLog
from rmprep.api.app import create_app
from rmprep.api.profile_ai import ProfileCheck
from rmprep.api.profile_checks import load_texts
from rmprep.contracts import TR_TZ
from rmprep.decision import load_config

PROTO = Path(__file__).resolve().parents[2]
TEXTS = load_texts(PROTO / "config" / "profile_checks.yaml")
DC = load_config(PROTO / "config" / "decision.yaml")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=TR_TZ)


class FakeAI:
    """The ProfileAI interface the adapter uses: one AI conflict, or a state."""

    def __init__(self, state="done", findings=()):
        self.state, self.findings = state, list(findings)

    def start(self, persona, answers=None):
        return "k"

    def status(self, persona, answers=None, rule_fields=None):
        return {"state": self.state, "findings": self.findings if self.state == "done" else [],
                "reason": ""}


AI_CONFLICT = {"id": "ai:abc", "kind": "conflict", "fields": ["durum", "likidite_ihtiyaci"],
               "quotes": [{"field": "durum", "text": "x"}, {"field": "likidite_ihtiyaci", "text": "Orta"}],
               "explanation": {"TR": "Nakit ihtiyacı ile likidite çelişiyor.", "EN": "Cash vs liquidity."}}


def setup(backend, client, ai, tmp_path, edit=None):
    log = ActionLog(tmp_path / "log", now=lambda: NOW)
    c = TestClient(create_app(backend, profile_check=ProfileCheck(ai, DC, TEXTS), action_log=log))
    p = next(x for x in client.get("/api/personas").json() if x["persona_id"] == "P02")
    view = c.post("/api/runs", json={"persona": {**p, **(edit or {})}}).json()
    return c, view, tmp_path / "log" / "2026-10-17.jsonl"


def approve(c, view, resolutions=()):
    first = view["result"]["options"][0]["option"]["option_id"]
    return c.post(f"/api/runs/{view['result']['run_id']}/approval",
                  json={"status": "approved", "note": "", "selected": [first],
                        "resolutions": [{"finding_id": i, "note": n} for i, n in resolutions]})


def test_an_open_ai_conflict_blocks_the_approval(backend, client, tmp_path):
    c, view, _ = setup(backend, client, FakeAI(findings=[AI_CONFLICT]), tmp_path)
    r = approve(c, view)
    assert r.status_code == 422 and "Çözülmemiş çelişki var" in r.json()["detail"]
    assert "Nakit ihtiyacı ile likidite çelişiyor." in r.json()["detail"]
    assert approve(c, view, [("ai:abc", "  ")]).status_code == 422        # an empty reason is no reason


def test_a_confirmed_conflict_is_recorded_logged_and_in_the_view(backend, client, tmp_path):
    c, view, log = setup(backend, client, FakeAI(findings=[AI_CONFLICT]), tmp_path)
    r = approve(c, view, [("ai:abc", "Peşinat ayrı hesapta tutuluyor.")])
    assert r.status_code == 200
    res = r.json()["resolutions"]
    assert res["ai_check"] == "done"
    assert res["resolutions"] == [{"id": "ai:abc", "source": "ai", "text": "Nakit ihtiyacı ile likidite çelişiyor.",
                                   "note": "Peşinat ayrı hesapta tutuluyor."}]
    row = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()][-1]
    assert row["action"] == "decision_approved" and row["details"]["resolutions"] == res["resolutions"]


def test_a_rule_conflict_needs_it_too(backend, client, tmp_path):
    c, view, _ = setup(backend, client, FakeAI(), tmp_path, edit={"doviz_maruz_kalma_tercihi": "Açık"})
    assert approve(c, view).status_code == 422                           # fx_open_vs_limit (rule)
    assert approve(c, view, [("fx_open_vs_limit", "Döviz payı en fazla %10 olacak.")]).status_code == 200


def test_a_running_ai_check_does_not_block_and_is_noted(backend, client, tmp_path):
    c, view, _ = setup(backend, client, FakeAI(state="running"), tmp_path)
    r = approve(c, view)
    assert r.status_code == 200 and r.json()["resolutions"]["ai_check"] == "running"


def test_a_rejection_needs_no_confirmation(backend, client, tmp_path):
    c, view, _ = setup(backend, client, FakeAI(findings=[AI_CONFLICT]), tmp_path)
    r = c.post(f"/api/runs/{view['result']['run_id']}/approval",
               json={"status": "rejected", "note": "uygun değil", "selected": []})
    assert r.status_code == 200 and r.json()["resolutions"] is None

