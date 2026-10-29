"""E13: the second A/B judge (Gemini over REST, a fake transport: no network) and the
replay of stored A/B questions."""

import json
from datetime import datetime

import httpx
import pytest
import yaml

from rmprep.contracts import TR_TZ
from rmprep.eval.ab_replay import CacheOnly, render, replay_ab, write_replay
from rmprep.eval.config import ConfigError, load_config, parse_config
from rmprep.eval.judge import (
    AbChoice, CachedAbJudge, GeminiAbJudge, _ab_sets, ab_schema, ab_system_text, ab_user_text,
    second_ab_judge_from_env,
)
from tests.eval.conftest import PROJECT

RAW = yaml.safe_load((PROJECT / "config" / "eval.yaml").read_text(encoding="utf-8"))
CFG = load_config(PROJECT / "config" / "eval.yaml").second_ab_judge


def reply(choice="B", reason="B fits the horizon.", finish="STOP", status=200, usage=None, **extra):
    body = {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True},
                                                  {"text": json.dumps({"choice": choice, "reason": reason})}]},
                            "finishReason": finish}],
            "usageMetadata": usage or {"promptTokenCount": 2000, "candidatesTokenCount": 60,
                                       "thoughtsTokenCount": 140},
            "modelVersion": "gemini-3.8-flash", **extra}
    return httpx.Response(status, json=body)


def judge(handler, **kw):
    seen = []

    def wrap(request):
        seen.append(request)
        return handler(request)

    j = GeminiAbJudge(CFG, api_key="k-test", http=httpx.Client(transport=httpx.MockTransport(wrap)),
                      sleep=kw.pop("sleep", lambda s: None), **kw)
    return j, seen


# --- config -------------------------------------------------------------------------

def test_the_project_config_has_a_gemini_second_judge():
    assert CFG.provider == "gemini" and CFG.model and CFG.api_key_env == "GEMINI_API_KEY"
    assert CFG.min_interval_s > 0


def test_the_second_judge_is_optional():
    raw = dict(RAW)
    raw.pop("second_ab_judge")
    assert parse_config(raw).second_ab_judge is None


@pytest.mark.parametrize("change,msg", [
    ({"provider": "openai"}, "provider"),
    ({"extra": 1}, "unknown keys"),
    ({"thinking_level": ""}, "thinking_level"),
    ({"min_interval_s": -1}, "min_interval_s"),
])
def test_a_bad_second_judge_is_refused(change, msg):
    raw = dict(RAW)
    raw["second_ab_judge"] = {**RAW["second_ab_judge"], **change}
    with pytest.raises(ConfigError, match=msg):
        parse_config(raw)


def test_no_key_no_second_judge():
    assert second_ab_judge_from_env(CFG, {}) is None
    assert second_ab_judge_from_env(None, {"GEMINI_API_KEY": "x"}) is None
    assert isinstance(second_ab_judge_from_env(CFG, {"GEMINI_API_KEY": "x"}), GeminiAbJudge)


# --- the call -----------------------------------------------------------------------

def test_the_request_has_the_same_prompt_schema_and_the_key_in_a_header():
    j, seen = judge(lambda r: reply())
    c = j.choose("<client>...</client>")
    assert c.error is None and c.choice == "B" and c.reason == "B fits the horizon."
    req = seen[0]
    assert req.url.path.endswith(f"/models/{CFG.model}:generateContent")
    assert req.headers["x-goog-api-key"] == "k-test" and "key=" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == ab_system_text()
    assert body["contents"][0]["parts"][0]["text"] == "<client>...</client>"
    gen = body["generationConfig"]
    assert gen["responseJsonSchema"] == ab_schema() and gen["responseMimeType"] == "application/json"
    assert gen["thinkingConfig"] == {"thinkingLevel": CFG.thinking_level}


def test_the_cost_counts_thought_tokens_as_output():
    j, _ = judge(lambda r: reply())
    c = j.choose("u")
    want = (2000 * CFG.price_input_per_mtok + 200 * CFG.price_output_per_mtok) / 1e6
    assert c.cost_usd == pytest.approx(want)


@pytest.mark.parametrize("response,error", [
    (httpx.Response(429, json={"error": {"message": "quota"}}), "rate_limit: quota"),
    (httpx.Response(400, json={"error": {"message": "bad schema"}}), "api 400: bad schema"),
    (reply(finish="MAX_TOKENS"), "cut off"),
    (reply(finish="SAFETY"), "stopped (SAFETY)"),
    (reply(choice="C"), "unknown choice"),
    (httpx.Response(200, json={"promptFeedback": {"blockReason": "OTHER"}}), "blocked (OTHER)"),
])
def test_errors_come_back_in_the_choice(response, error):
    j, _ = judge(lambda r: response)
    c = j.choose("u")
    assert c.choice == "" and error in c.error


def test_a_busy_server_is_tried_again_then_reported():
    answers = iter([httpx.Response(503, json={"error": {"message": "high demand"}}), reply()])
    waits = []
    j, seen = judge(lambda r: next(answers), sleep=waits.append)
    assert j.choose("u").choice == "B" and len(seen) == 2 and 20.0 in waits
    j2, seen2 = judge(lambda r: httpx.Response(503, json={"error": {"message": "high demand"}}))
    assert j2.choose("u").error == "api 503: high demand" and len(seen2) == 3


def test_a_timeout_is_tried_again():
    calls = []

    def slow_then_ok(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return reply()

    j, _ = judge(slow_then_ok)
    assert j.choose("u").choice == "B" and len(calls) == 2


def test_a_connection_error_does_not_raise():
    def fail(request):
        raise httpx.ConnectError("down")

    j, _ = judge(fail)
    assert j.choose("u").error == "connection: ConnectError"


def test_calls_keep_the_free_tier_interval():
    t = [100.0]
    waits = []
    j, _ = judge(lambda r: reply(), sleep=waits.append, clock=lambda: t[0])
    j.choose("a")
    t[0] += 2
    j.choose("b")
    assert waits == [pytest.approx(CFG.min_interval_s - 2)]


def test_errors_are_not_cached(tmp_path):
    answers = iter([httpx.Response(429, json={"error": {"message": "q"}}), reply()])
    j, seen = judge(lambda r: next(answers))
    cj = CachedAbJudge(j, tmp_path)
    assert cj.choose("u").error and cj.choose("u").choice == "B"
    assert cj.choose("u").choice == "B" and len(seen) == 2       # the third is cached


# --- the replay ---------------------------------------------------------------------

def persona(rid: str) -> dict:
    """A different fixture persona per run id (R...1 = P01 ... R...5 = P05): different
    runs ask different questions, as in a real report."""
    n = int(rid[-1])
    path = PROJECT / "tests" / "contracts" / "fixtures" / "personas" / f"p0{n}.json"
    return json.loads(path.read_text(encoding="utf-8"))
PACK = {"portfoy": [], "adaylar": [
    {"option_id": f"fund:{c}", "ad": f"Fon {c}", "tur": "Para piyasası", "varlik_sinifi": "nakit_benzeri",
     "risk": {"deger": 1}, "getiri": {"1y": {"deger": 45.0}}, "reel_getiri_1y": {"deger": 7.0},
     "erisim": "aynı gün", "uyarilar": []} for c in ("AAA", "BBB", "CCC", "DDD")], "arastirma": {}}


class Fixed:
    def __init__(self, choice, model):
        self.choice, self.model, self.calls = choice, model, 0

    def choose(self, user):
        self.calls += 1
        return AbChoice(self.choice, f"{self.model} says {self.choice}", self.model, cost_usd=0.002)


def store(root, report, sid, rid, agent, engine, *, pack=True, state="done"):
    rep = root / "data" / "eval" / report
    rep.mkdir(parents=True, exist_ok=True)
    path = rep / "report.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"scenarios": []}
    data["scenarios"].append({"id": sid, "runs": [{"run_id": rid, "persona": persona(rid), "agent": {
        "state": state, "top3": list(agent), "engine_top3": list(engine)}}]})
    path.write_text(json.dumps(data), encoding="utf-8")
    if pack:
        d = root / "data" / "eval" / "agent" / sid
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{rid}.pack.json").write_text(json.dumps(PACK), encoding="utf-8")


AGENT = ("fund:AAA", "fund:BBB", "fund:DDD")
ENGINE = ("fund:AAA", "fund:BBB", "fund:CCC")


def first_answers(root, rows, choice="A"):
    """The first judge's cached answers for these run ids."""
    from rmprep.eval.ab_replay import _Stored
    from rmprep.contracts import Persona

    cj = CachedAbJudge(Fixed(choice, "haiku"), root / "data" / "eval" / "judge-ab")
    for rid in rows:
        _, a, b = _ab_sets(rid, AGENT, ENGINE)
        cj.choose(ab_user_text(_Stored(Persona.from_dict(persona(rid)), rid), PACK, a, b))


def test_the_replay_asks_only_questions_the_first_judge_saw(tmp_path):
    store(tmp_path, "r1", "base-p01", "R0000000001", AGENT, ENGINE)
    store(tmp_path, "r1", "base-p02", "R0000000002", AGENT, AGENT)               # same top 3
    store(tmp_path, "r1", "base-p03", "R0000000003", AGENT, ENGINE, pack=False)
    store(tmp_path, "r1", "base-p04", "R0000000004", AGENT, ENGINE)              # not asked before
    store(tmp_path, "r1", "base-p05", "R0000000005", AGENT, ENGINE, state="fallback")
    store(tmp_path, "r2", "base-p01", "R0000000001", AGENT, ENGINE)              # the same question again
    first_answers(tmp_path, ["R0000000001"])
    cache = tmp_path / "data" / "eval" / "judge-ab"
    second = Fixed("B", "gemini")
    r = replay_ab(tmp_path, ["r1", "r2"], CachedAbJudge(CacheOnly("haiku"), cache),
                  CachedAbJudge(second, cache))
    skipped = {(x.report, x.scenario_id): x.skipped for x in r.rows}
    assert skipped == {("r1", "base-p01"): "", ("r1", "base-p03"): "no stored pack",
                       ("r1", "base-p04"): skipped[("r1", "base-p04")],
                       ("r2", "base-p01"): "same question as an earlier row"}
    assert skipped[("r1", "base-p04")].startswith("input differs")
    assert second.calls == 1 and len(r.asked()) == 1
    row = r.asked()[0]
    assert row.first.choice.choice == "A" and row.second.choice.choice == "B"
    assert row.first.winner != row.second.winner and r.agreement() == (0, 1)


def test_the_report_shows_both_judges_and_the_agreement(tmp_path):
    store(tmp_path, "r1", "base-p01", "R0000000001", AGENT, ENGINE)
    store(tmp_path, "r1", "base-p03", "R0000000003", AGENT, ENGINE)
    first_answers(tmp_path, ["R0000000001", "R0000000003"], choice="esit")
    cache = tmp_path / "data" / "eval" / "judge-ab"
    r = replay_ab(tmp_path, ["r1"], CachedAbJudge(CacheOnly("haiku"), cache),
                  CachedAbJudge(Fixed("esit", "gemini"), cache))
    assert r.tally("first") == r.tally("second") == {"agent": 0, "engine": 0, "equal": 2, "error": 0}
    assert r.agreement() == (2, 2) and r.cost_usd() == pytest.approx(0.004)
    out = write_replay(tmp_path, r, ["r1"], now=datetime(2026, 10, 29, 12, 0, tzinfo=TR_TZ))
    md = (out / "report.md").read_text(encoding="utf-8")
    assert "Agreement: the two judges pick the same winner in 2 of 2 questions." in md
    assert "| gemini | 0 | 0 | 2 | 0 |" in md
    data = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert data["agreement"] == [2, 2] and len(data["rows"]) == 2
    assert render(r, ["r1"], datetime(2026, 10, 29, tzinfo=TR_TZ)).startswith("# A/B judge replay")
