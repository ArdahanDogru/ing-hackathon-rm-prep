"""E11: the agent part of the eval (agent_eval.py, the agent scenarios, run_suite with
agent=True). A fake model (PackClient) and a fake research; no network."""

import json
import threading
from datetime import datetime

import pytest

from rmprep.contracts import TR_TZ, DecisionState
from rmprep.eval.agent_eval import RecordingResearch, agent_metrics, eval_agent, top3
from rmprep.eval.config import load_config
from rmprep.eval.scenario import (
    AgentNews, Scenario, ScenarioError, agent_scenario_files, load_scenario_file,
    load_scenarios, packaged_scenario_files, parse_scenario,
)
from rmprep.eval.suite import run_suite
from tests.eval.conftest import (
    CONTRACT_FIX, AgentFakeResearch, PackClient, agent_root,
)
from tests.eval.test_runner import runner

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=TR_TZ)
NEWS = AgentNews("@engine1", "{name} hakkında SPK soruşturması başlatıldı.", "2026-10-13",
                 "https://www.dunya.com/finans/haberler")
SPLIT = {"nakit_benzeri": 80, "borclanma": 5, "hisse": 10, "altin_doviz": 5, "dengeli": 0}


def agent_eval(root, client=None, research=None, **kw):
    root = agent_root(root)
    config = load_config(root / "config" / "eval.yaml")
    return eval_agent(root, config, {}, client=client or PackClient(),
                      research=AgentFakeResearch() if research is None else research,
                      created=NOW, **kw)


def run_with_agent(root, scenarios, client=None, research=None, **kw):
    runs = runner(root, narrator=None).run(scenarios)
    ae = agent_eval(root, client, research, **kw)
    ae.run(runs)
    return runs, ae


# --- scenarios -----------------------------------------------------------------

def test_agent_scenarios_are_not_in_the_default_files():
    defaults = load_scenarios(packaged_scenario_files())
    assert not any(s.group == "agent" for s in defaults)
    agent = load_scenarios(agent_scenario_files())
    assert [s.id for s in agent] == ["agent-negative-news", "agent-rm-split", "agent-crash"]
    news, split, crash = agent
    assert news.agent_news[0].option == "@engine1" and not news.narrate
    assert split.persona == "P03" and split.holdings == {k: float(v) for k, v in SPLIT.items()}
    assert split.holdings_origin == "rm"
    assert crash.persona == "P03" and crash.agent_watch == ("stock:KTLEV",)


@pytest.mark.parametrize("raw, msg", [
    ({"holdings": {"nakit_benzeri": 80}}, "holdings"),
    ({"holdings": dict(SPLIT, dengeli=10)}, "add to 100"),
    ({"holdings": SPLIT, "holdings_origin": "persona_text"}, "origin"),
    ({"holdings_origin": "rm"}, "needs holdings"),
    ({"agent_news": [{"option": "@engine4", "text": "x", "date": "2026-10-13"}]}, "@engine1-3"),
    ({"agent_news": [{"option": "@engine1", "text": "x", "date": "13.10.2026"}]}, "YYYY-MM-DD"),
    ({"agent_news": [{"option": "@engine1", "text": "x", "date": "2026-10-13",
                      "url": "http://a"}]}, "https"),
    ({"agent_news": [{"option": "fund:A", "text": "x"}]}, "date"),
])
def test_bad_agent_fields_are_refused(raw, msg):
    with pytest.raises(ValueError, match=msg):
        parse_scenario({"id": "x", "group": "agent", "persona": "P01", **raw})


def test_the_rm_split_makes_a_new_run_with_the_rm_rows(root):
    s = Scenario(id="split", group="agent", persona="P03", holdings=SPLIT, narrate=False)
    [sr] = runner(root, narrator=None).run([s, ])
    [run] = sr.runs
    assert run.result.state == DecisionState.READY
    rows = {b.asset_class: b for b in run.result.allocation}
    assert rows["nakit_benzeri"].current == 80 and rows["hisse"].current == 10
    assert {b.current_source for b in rows.values()} == {"rm"}
    [plain] = runner(root, narrator=None).run([Scenario(id="p", group="base", persona="P03")])
    assert plain.runs[0].result.run_id != run.result.run_id


# --- the agent per run --------------------------------------------------------------

def test_the_agent_decides_for_base_and_agent_scenarios_only(root):
    scenarios = [Scenario(id="base-p01", group="base", persona="P01", repeat=2, narrate=False),
                 Scenario(id="edit", group="persona_edit", persona="P02", narrate=False),
                 Scenario(id="agent-x", group="agent", persona="P03", narrate=False)]
    client = PackClient("swap")
    runs, _ = run_with_agent(root, scenarios, client)
    base, edit, agent = runs
    assert base.runs[0].agent is not None and base.runs[1].agent is None
    assert edit.runs[0].agent is None
    a = base.runs[0].agent
    r = base.runs[0].result
    assert a.decision.state == "done" and a.error is None and not a.cached
    assert a.decision.engine_top3 == r.recommended
    assert top3(a.decision)[0] != r.recommended[0] and top3(a.decision)[1:] == r.recommended[1:]
    assert a.cost_usd == pytest.approx((1000 * 2 + 200 * 10) / 1e6)
    assert a.seconds >= 0 and a.pack["motor_ilk3"] == list(r.recommended)
    # P03 has no other candidate of its #1's class: the fake keeps the engine's top 3
    assert top3(agent.runs[0].agent.decision) == agent.runs[0].result.recommended
    # main decision + repeat for each of the two scenarios
    assert client.calls == 4


def test_the_same_run_of_two_scenarios_has_its_own_cache(root):
    """agent-negative-news is the same engine run as base-p01: its decision must not
    come from the base scenario's cache."""
    scenarios = [Scenario(id="base-p01", group="base", persona="P01", narrate=False),
                 Scenario(id="news", group="agent", persona="P01", narrate=False,
                          agent_news=(NEWS,))]
    client = PackClient()
    runs, ae = run_with_agent(root, scenarios, client, repeat=False)
    a, b = (sr.runs[0] for sr in runs)
    assert a.result.run_id == b.result.run_id
    assert client.calls == 2 and not b.agent.cached
    assert (ae.cache_root / "base-p01" / f"{a.result.run_id}.json").exists()
    assert (ae.cache_root / "news" / f"{a.result.run_id}.json").exists()


def test_injected_news_reaches_the_pack_of_the_engines_first(root):
    s = Scenario(id="news", group="agent", persona="P01", narrate=False, agent_news=(NEWS,))
    client = PackClient()
    runs, _ = run_with_agent(root, [s], client, repeat=False)
    run = runs[0].runs[0]
    first = run.result.recommended[0]
    label = next(o.option.label for o in run.result.options if o.option.option_id == first)
    sent = client.packs[0]["arastirma"][first]["haberler"]
    assert sent[0]["metin"] == f"{label} hakkında SPK soruşturması başlatıldı."
    assert sent[0]["tarih"] == "2026-10-13" and sent[0]["kaynak"] == "www.dunya.com"
    assert sent[0]["id"].startswith("F")
    # the eval's own pack is the one the agent saw
    assert run.agent.pack["arastirma"] == client.packs[0]["arastirma"]
    assert run.agent.news == [first]


def test_news_without_research_still_reaches_the_agent(root):
    s = Scenario(id="news", group="agent", persona="P01", narrate=False, agent_news=(NEWS,))
    client = PackClient()
    runs = runner(root, narrator=None).run([s])
    eval_agent(agent_root(root), load_config(root / "config" / "eval.yaml"), {}, client=client,
               research=None, created=NOW, repeat=False).run(runs)
    first = runs[0].runs[0].result.recommended[0]
    block = client.packs[0]["arastirma"][first]
    assert block["durum"] == "var" and len(block["haberler"]) == 1
    assert runs[0].runs[0].agent.decision.state == "done"


def test_recording_research_injects_into_a_failed_product():
    from rmprep.research.types import Finding, ProductResearch, Source

    class Failing:
        def research_many(self, options, lang):
            return [ProductResearch(o.option_id, o.label, "", "", (), lang, "", NOW,
                                    error="connection: timeout") for o in options]

    class Opt:
        option_id, label = "fund:AAA", "A Fonu"

    f = Finding("A Fonu haberi.", "haber", (Source("https://x.com/a"),), "medium", "2026-10-13")
    rec = RecordingResearch(Failing(), {"fund:AAA": (f,)}, now=lambda: NOW)
    [r] = rec.research_many([Opt()], "TR")
    assert r.error == "" and r.news[0].text == "A Fonu haberi." and r.news[0].id
    assert rec.products["fund:AAA"] is r


def test_a_cached_decision_costs_nothing_and_the_cache_gives_the_same(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    client = PackClient("swap", web=True)
    runs, _ = run_with_agent(root, [s], client, repeat=False)
    first = runs[0].runs[0].agent
    assert first.cache_same is True
    again = runner(root, narrator=None).run([s])
    agent_eval(root, client, repeat=False).run(again)
    second = again[0].runs[0].agent
    assert client.calls == 1 and second.cached and second.cost_usd == 0
    assert second.decision.to_dict() == first.decision.to_dict()
    # the pack (with the research the agent saw) comes back from the eval's cache
    assert second.pack == first.pack


def test_repeat_without_the_cache(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    client = PackClient("swap")
    runs, ae = run_with_agent(root, [s], client)
    a = runs[0].runs[0].agent
    assert client.calls == 2 and a.repeat is not None and a.repeat.state == "done"
    assert top3(a.repeat) == top3(a.decision) and a.repeat_cost_usd > 0
    assert ae.repeat_root != ae.cache_root and (ae.repeat_root / "base-p01").exists()
    m = agent_metrics(runs, [])
    assert m["repeat"] == {"runs": 1, "identical": 1, "same_set": 1, "share_identical": 1.0}


def test_a_hanging_agent_is_cut_at_the_deadline(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    gate = threading.Event()
    try:
        runs, _ = run_with_agent(root, [s], PackClient(block=gate), deadline_s=0.2,
                                 repeat=False)
    finally:
        gate.set()
    a = runs[0].runs[0].agent
    assert a.decision.state == "running" and a.error.startswith("deadline")


def test_no_new_decision_over_the_budget(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    client = PackClient()
    runs = runner(root, narrator=None).run([s])
    agent_eval(root, client).run(runs, budget_left=lambda: 0.0, spend=lambda x: None)
    a = runs[0].runs[0].agent
    assert client.calls == 0 and a.decision is None and a.error.startswith("budget")


def test_the_spent_cost_goes_to_the_eval_limit(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    spent = []
    runs = runner(root, narrator=None).run([s])
    agent_eval(root).run(runs, budget_left=lambda: 5.0, spend=spent.append)
    assert sum(spent) == pytest.approx(2 * (1000 * 2 + 200 * 10) / 1e6)


def test_the_watch_list_follows_an_option(root):
    runs = runner(root, narrator=None).run([Scenario(id="w", group="agent", persona="P01",
                                                     narrate=False)])
    first = runs[0].runs[0].result.recommended[0]
    s = Scenario(id="w", group="agent", persona="P01", narrate=False,
                 agent_watch=(first, "stock:NONE"))
    runs, _ = run_with_agent(root, [s], PackClient("swap"), repeat=False)
    w1, w2 = runs[0].runs[0].agent.watch
    assert w1 == {"option_id": first, "candidate": True, "engine_place": 1,
                  "warnings": [], "engine_top3": True, "agent_top3": False}
    assert w2["candidate"] is False and w2["agent_top3"] is False


def test_without_a_key_the_agent_is_off_and_costs_nothing(root):
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    runs = runner(root, narrator=None).run([s])
    ae = eval_agent(agent_root(root), load_config(root / "config" / "eval.yaml"), {},
                    research=AgentFakeResearch(), created=NOW)
    ae.run(runs)
    a = runs[0].runs[0].agent
    assert a.decision.state == "off" and a.cost_usd == 0 and a.repeat is None


# --- the suite ------------------------------------------------------------------------

def write_suite(tmp_path):
    f = tmp_path / "agent.yaml"
    f.write_text("""
scenarios:
  - {id: base-p01, group: base, persona: P01, repeat: 2}
  - id: agent-negative-news
    group: agent
    persona: P01
    narrate: false
    agent_news: [{option: "@engine1", date: "2026-10-13", text: "{name}: SPK soruşturması."}]
  - id: agent-rm-split
    group: agent
    persona: P03
    narrate: false
    holdings: {nakit_benzeri: 80, borclanma: 5, hisse: 10, altin_doviz: 5, dengeli: 0}
  - {id: edit-p02, group: persona_edit, persona: P02, edit: {risk_profili: "Muhafazakâr"}}
""", encoding="utf-8")
    return f


class FirstJudge:
    """An A/B judge that always prefers set A."""

    model = "fake-ab"

    def __init__(self):
        self.users: list[str] = []

    def choose(self, user):
        from rmprep.eval.judge import AbChoice

        self.users.append(user)
        return AbChoice("A", "A is safer.", self.model, cost_usd=0.001)


def test_run_suite_with_the_agent_writes_the_agent_section(root, tmp_path):
    agent_root(root)
    ab = FirstJudge()
    res = run_suite(root, suite="agent", scenario_files=[write_suite(tmp_path)],
                    personas_dir=CONTRACT_FIX / "personas", narrator=None, judge=None,
                    agent=True, agent_client=PackClient("swap"), research=AgentFakeResearch(),
                    ab_judge=ab, now=lambda: NOW)
    by_id = {sr.scenario.id: sr for sr in res.runs}
    assert by_id["edit-p02"].runs[0].agent is None
    checks = {sc.scenario.id: sc for sc in res.checks}
    agent_checks = [c for c in checks["base-p01"].runs[0] if c.check == "agent_decision"]
    assert agent_checks[0].status == "pass"
    assert [c.status for c in checks["edit-p02"].runs[0] if c.check == "agent_decision"] == ["n/a"]
    m = res.metrics["agent"]
    assert m["decisions"] == 3 and m["states"] == {"done": 3}
    # P01 swaps (A/B graded twice); an unchanged top 3 is not sent to the judge
    assert m["ab"]["graded"] >= 2 and len(ab.users) == m["ab"]["graded"]
    assert m["ab"]["graded"] + m["ab"]["same"] == 3
    assert 0 <= m["ab"]["share_agent"] <= 1
    assert res.metrics["cost"]["agent_usd"] == pytest.approx(6 * (1000 * 2 + 200 * 10) / 1e6)
    assert res.metrics["cost"]["ab_judge_usd"] == pytest.approx(0.002)
    assert res.meta["agent"]["model"] == "claude-sonnet-5-5"
    md = (res.report_dir / "report.md").read_text(encoding="utf-8")
    assert "## Agent (E11)" in md and "agent-negative-news" in md
    assert "Repeatability" in md and "A/B judge" in md
    data = json.loads((res.report_dir / "report.json").read_text(encoding="utf-8"))
    run0 = data["scenarios"][0]["runs"][0]
    assert run0["agent"]["state"] == "done" and len(run0["agent"]["top3"]) == 3
    assert data["scenarios"][0]["runs"][1]["agent"] is None
    assert data["scenarios"][0]["ab"]["winner"] in ("agent", "engine", "equal")


def test_run_suite_without_the_agent_is_unchanged(root, tmp_path):
    agent_root(root)
    client = PackClient()
    res = run_suite(root, scenario_files=[write_suite(tmp_path)],
                    personas_dir=CONTRACT_FIX / "personas", narrator=None, judge=None,
                    agent_client=client, research=AgentFakeResearch(), now=lambda: NOW,
                    write=False)
    assert client.calls == 0 and "agent" not in res.metrics and res.meta["agent"] is None
    assert not any(c.check == "agent_decision" for sc in res.checks for c in sc.all())
    assert all(r.agent is None for sr in res.runs for r in sr.runs)


def test_run_suite_with_the_agent_adds_the_agent_files(root, monkeypatch, tmp_path):
    seen = []
    import rmprep.eval.suite as suite

    monkeypatch.setattr(suite, "load_scenarios", lambda files: seen.append(list(files)) or [])
    agent_root(root)
    run_suite(root, only=["nothing"], personas_dir=CONTRACT_FIX / "personas", narrator=None,
              judge=None, agent=True, agent_client=PackClient(), research=AgentFakeResearch(),
              ab_judge=None, now=lambda: NOW, write=False)
    assert seen[0] == packaged_scenario_files() + agent_scenario_files()
