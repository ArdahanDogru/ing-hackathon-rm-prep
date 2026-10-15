"""Contract v1.11 (2026-10-15): the agent decision
(spec docs/superpowers/specs/2026-10-15-agent-decision-design.md, section 7)."""
from datetime import datetime

import pytest

from rmprep.contracts import (AGENT_STATES, NODE_STATES, TR_TZ, AgentDecision, AgentNode,
                              AgentPick, AgentReason)

T = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)


def _pick(oid="fund:A", cites=("E0123abcd",)):
    return AgentPick(oid, (AgentReason("Getiri yüksek.", cites),), uses_estimate=False, uses_web=False)


def _decision(**over):
    d = dict(run_id="R0000000001", state="done", picks=(_pick("fund:A"), _pick("fund:B"), _pick("fund:C")),
             dropped=(), summary="Özet.", engine_top3=("fund:A", "fund:B", "fund:D"),
             nodes=(AgentNode("adaylar", "Adaylar", "done", T, T,
                              children=(AgentNode("x", "X", "done", T, T, notes=("not",)),)),),
             model="claude-sonnet-5-5", prompt_version="a1", cost_usd=0.04, created_at=T)
    return AgentDecision(**(d | over))


def test_states():
    assert AGENT_STATES == ("running", "done", "fallback", "off")
    assert NODE_STATES == ("waiting", "running", "done", "failed")


def test_round_trip():
    d = _decision(dropped=(AgentPick("fund:D", (AgentReason("Düşük getiri.", ("puan:getiri",)),)),))
    assert AgentDecision.from_dict(d.to_dict()) == d


def test_reason_needs_a_citation_and_text():
    with pytest.raises(ValueError, match="cite"):
        AgentReason("Metin.", ())
    with pytest.raises(ValueError, match="text"):
        AgentReason(" ", ("E0123abcd",))


def test_cite_forms():
    AgentReason("x", ("E0123abcd", "F89abcdef", "puan:getiri", "portfoy:borclanma", "puan:allocation_gap"))
    for bad in ("bogus", "E123", "F0123ABCD", "portfoy:"):
        with pytest.raises(ValueError, match="cite"):
            AgentReason("x", (bad,))


def test_done_needs_three_different_picks():
    with pytest.raises(ValueError, match="3 picks"):
        _decision(picks=(_pick("fund:A"), _pick("fund:B")))
    with pytest.raises(ValueError, match="twice"):
        _decision(picks=(_pick("fund:A"), _pick("fund:A"), _pick("fund:C")))


def test_fallback_needs_a_reason_and_no_picks():
    d = _decision(state="fallback", picks=(), fallback_reason="timeout")
    assert d.fallback_reason == "timeout"
    with pytest.raises(ValueError, match="fallback_reason"):
        _decision(state="fallback", picks=())
    with pytest.raises(ValueError, match="fallback_reason"):
        _decision(state="fallback", fallback_reason="x")          # picks with a fallback


def test_running_and_off_may_have_no_picks_and_node_state_is_checked():
    _decision(state="running", picks=())
    _decision(state="off", picks=(), fallback_reason="no API key")
    with pytest.raises(ValueError, match="state"):
        AgentNode("x", "X", "busy", T, None)
    with pytest.raises(ValueError, match="state"):
        _decision(state="thinking", picks=())


def test_created_at_must_be_aware():
    with pytest.raises(ValueError, match="aware"):
        _decision(created_at=datetime(2026, 10, 15, 10, 0))
