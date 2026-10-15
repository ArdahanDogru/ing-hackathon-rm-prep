"""A1b: prompt version a2 — numbers in the Turkish form for TR ("%47,5"), the
English form for EN ("47.5%"), as the meeting text; the checks accept both forms
against the cited data (rounded to one decimal)."""

import dataclasses

import pytest
import yaml

from rmprep.agent.checks import check_decision
from rmprep.agent.config import PROMPT_VERSIONS, ConfigError, parse_agent_config
from rmprep.agent.pack import build_pack
from rmprep.agent.service import PROMPTS
from tests.agent.conftest import FIXTURES, ScriptedClient, call, karar, reason, turn, valid_picks


def _raw() -> dict:
    return yaml.safe_load((FIXTURES / "agent.yaml").read_text(encoding="utf-8"))


def test_config_accepts_the_known_versions_only():
    assert set(PROMPT_VERSIONS) == set(PROMPTS)
    for v in ("a1", "a2"):
        assert parse_agent_config(_raw() | {"prompt_version": v}).prompt_version == v
    with pytest.raises(ConfigError, match="prompt_version"):
        parse_agent_config(_raw() | {"prompt_version": "a3"})


def test_a2_states_the_number_form():
    tr, en = PROMPTS["a2"]["TR"], PROMPTS["a2"]["EN"]
    assert "%47,5" in tr and "virgül" in tr
    assert "47.5%" in en
    assert "%47,5" not in PROMPTS["a1"]["TR"]       # a1 stays as it was (cached decisions)


@pytest.fixture
def pack01(ready_p01, ev, dcfg):
    return build_pack(ready_p01, ev, dcfg, {}, "TR")


def _one_year(pack, oid):
    c = next(c for c in pack["adaylar"] if c["option_id"] == oid)
    return c["getiri"]["1y"]["deger"], c["getiri"]["1y"]["kanit"]


def _with_text(result, picks, text, eid):
    raw = karar(result, picks)
    raw["secimler"][0]["gerekceler"][0] = reason(text, eid)
    return raw


def test_checks_accept_the_turkish_form(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    v, eid = _one_year(pack01, picks[0])
    tr = f"%{v:.1f}".replace(".", ",")
    raw = _with_text(ready_p01, picks, f"Yıllık getirisi {tr}.", eid)
    assert check_decision(raw, pack01, dcfg, phrases, "TR")[3] == []
    wrong = f"%{v + 0.3:.1f}".replace(".", ",")
    raw = _with_text(ready_p01, picks, f"Yıllık getirisi {wrong}.", eid)
    assert any("number" in p for p in check_decision(raw, pack01, dcfg, phrases, "TR")[3])


def test_checks_accept_the_english_form(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    v, eid = _one_year(pack01, picks[0])
    raw = _with_text(ready_p01, picks, f"The 1-year return is {v:.1f}%.", eid)
    raw["secimler"][0]["gerekceler"][1] = reason("The debt share is below the band.",
                                                 "portfoy:borclanma")
    assert check_decision(raw, pack01, dcfg, phrases, "EN")[3] == []


def test_service_sends_the_a2_prompt(svc_factory, cfg, ready_p01, ev):
    assert cfg.prompt_version == "a2"
    picks = valid_picks(ready_p01)
    client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, picks))))
    svc = svc_factory(client)
    svc.start(ready_p01, ev)
    svc.wait()
    assert svc.status(ready_p01.run_id).prompt_version == "a2"
    assert "%47,5" in client.sent[0][0]


def test_a1_config_still_runs(svc_factory, cfg, dcfg, phrases, ready_p01, ev, tmp_path):
    from rmprep.agent.service import AgentService
    from tests.agent.conftest import CREATED, FakeClock, FakeResearch

    picks = valid_picks(ready_p01)
    client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, picks))))
    svc = AgentService(dataclasses.replace(cfg, prompt_version="a1"), client, FakeResearch(),
                       dcfg, phrases, tmp_path / "a1", now=lambda: CREATED, clock=FakeClock())
    svc.start(ready_p01, ev)
    svc.wait()
    assert svc.status(ready_p01.run_id).prompt_version == "a1"
    assert "%47,5" not in client.sent[0][0]
