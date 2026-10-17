"""W43 layer 3: the AI check of the client profile (a fake SDK; no network, no cost)."""

import json
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rmprep.api.app import create_app
from rmprep.api.profile_ai import (FALLBACK_BETA, ProfileAI, ProfileCheck, load_ai_config,
                                   reading_summary, validate)
from rmprep.api.profile_checks import load_texts
from rmprep.contracts import TR_TZ, Persona
from rmprep.decision import load_config

PROTO = Path(__file__).resolve().parents[2]
PERSONAS = PROTO / "tests" / "contracts" / "fixtures" / "personas"
CFG = load_ai_config(PROTO / "config" / "profile_checks.yaml")
DC = load_config(PROTO / "config" / "decision.yaml")
NOW = datetime(2026, 10, 17, 12, 0, tzinfo=TR_TZ)


def persona(pid="p01", **change) -> Persona:
    d = json.loads((PERSONAS / f"{pid}.json").read_text(encoding="utf-8"))
    return Persona.from_dict({**d, **change})


CASH = persona("p03", durum="Gelecek yıl ev alacak, peşinat için nakde ihtiyacı var.")


def answer(*findings, stop="end_turn"):
    text = json.dumps({"findings": list(findings)}, ensure_ascii=False)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                           model="claude-opus-5-5",
                           usage=SimpleNamespace(input_tokens=2000, output_tokens=500))


def finding(kind="conflict", quotes=(("durum", "peşinat için nakde ihtiyacı var"), ("likidite_ihtiyaci", "Düşük"))):
    return {"kind": kind, "quotes": [{"field": f, "text": t} for f, t in quotes],
            "explanation_tr": "Nakit ihtiyacı ile likidite düzeyi çelişiyor.",
            "explanation_en": "The cash need conflicts with the liquidity level."}


class FakeSdk:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


def ai(tmp_path, sdk, **cfg) -> ProfileAI:
    return ProfileAI(replace(CFG, **cfg), DC, tmp_path, api_key="k", sdk=sdk, now=lambda: NOW)


def wait_done(a: ProfileAI, p: Persona, timeout=5.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        s = a.status(p)
        if s["state"] != "running":
            return s
        time.sleep(0.02)
    raise AssertionError("still running")


# --- the quote check --------------------------------------------------------------

def test_a_verbatim_quote_passes_in_any_case_and_spacing():
    kept, dropped = validate({"findings": [finding(quotes=(("durum", "PEŞİNAT  için nakde"),
                                                           ("likidite_ihtiyaci", "düşük")))]}, CASH)
    assert dropped == 0 and kept[0]["fields"] == ["durum", "likidite_ihtiyaci"]


@pytest.mark.parametrize("bad", [
    finding(quotes=(("durum", "yazlık alacak"), ("likidite_ihtiyaci", "Düşük"))),   # not in the field
    finding(quotes=(("durum", "peşinat"),)),                                         # a conflict needs 2
    finding(quotes=(("nope", "x"), ("durum", "peşinat"))),                           # unknown field
    finding(kind="maybe"),
    {**finding(), "explanation_tr": " "},
])
def test_a_finding_that_fails_the_check_is_dropped(bad):
    kept, dropped = validate({"findings": [bad]}, CASH)
    assert kept == [] and dropped == 1


def test_a_repeat_of_a_rule_finding_is_dropped():
    kept, dropped = validate({"findings": [finding()]}, CASH, [{"durum", "likidite_ihtiyaci", "oncelikler"}])
    assert kept == [] and dropped == 1


def test_the_reading_names_what_the_engine_did_not_match():
    p = persona("p01", oncelikler=["düzenli gelir", "torunlara miras"])
    r = reading_summary(p, DC)
    assert r["priorities_not_matched"] == ["torunlara miras"] and r["risk_profile"] == "Muhafazakâr"


# --- the service ------------------------------------------------------------------

def test_a_check_is_made_once_and_cached(tmp_path):
    sdk = FakeSdk(answer(finding()))
    a = ai(tmp_path, sdk)
    s = wait_done(a, CASH)
    assert s["state"] == "done" and len(s["findings"]) == 1 and s["cost_usd"] == pytest.approx(0.018)
    kw = sdk.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["output_config"]["format"]["type"] == "json_schema" and kw["output_config"]["effort"] == "medium"
    b = ai(tmp_path, FakeSdk())                      # a new process: the cache answers, no call
    assert b.status(CASH)["state"] == "done"
    assert a.spent_today() == pytest.approx(0.018)


def test_a_refusal_is_failed_and_not_cached(tmp_path):
    a = ai(tmp_path, FakeSdk(answer(stop="refusal")))
    s = wait_done(a, CASH)
    assert s["state"] == "failed" and "declined" in s["reason"]
    assert not list(tmp_path.glob("*.json"))


def test_the_daily_limit_stops_the_call(tmp_path):
    (tmp_path / "costs.jsonl").write_text(json.dumps({"day": "2026-10-17", "cost_usd": 2.0}) + "\n",
                                          encoding="utf-8")
    sdk = FakeSdk()
    s = wait_done(ai(tmp_path, sdk), CASH)
    assert s["state"] == "failed" and "daily limit" in s["reason"] and sdk.calls == []


def test_off_without_a_key(tmp_path):
    a = ProfileAI(CFG, DC, tmp_path, api_key=None)
    assert a.status(CASH) == {"state": "off", "findings": [], "reason": "no ANTHROPIC_API_KEY"}


# --- the route --------------------------------------------------------------------

def test_the_route_answers_running_then_done(backend, persona, tmp_path):
    sdk = FakeSdk(answer())
    texts = load_texts(PROTO / "config" / "profile_checks.yaml")
    c = TestClient(create_app(backend, profile_check=ProfileCheck(ai(tmp_path, sdk), DC, texts)))
    rid = c.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    end = time.time() + 5
    while True:
        r = c.get(f"/api/runs/{rid}/profile-check")
        if r.status_code == 200 or time.time() > end:
            break
        assert r.status_code == 202 and r.json()["state"] == "running"
        time.sleep(0.02)
    assert r.status_code == 200 and r.json()["state"] == "done" and r.json()["findings"] == []
    assert len(sdk.calls) == 1                        # started when the run opened, once


def test_the_route_without_the_check_is_off(backend, persona):
    c = TestClient(create_app(backend))
    rid = c.post("/api/runs", json={"persona": persona}).json()["result"]["run_id"]
    assert c.get(f"/api/runs/{rid}/profile-check").json()["state"] == "off"
