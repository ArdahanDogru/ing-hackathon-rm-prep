"""Contract v1.12 (2026-10-15): the agent decision records N and the hash of the RM's
research marks (spec docs/superpowers/specs/2026-10-15-rm-run-agent-design.md)."""
from datetime import datetime

from rmprep.contracts import TR_TZ, AgentDecision, AgentPick, AgentReason

T = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)


def _d(**over):
    picks = tuple(AgentPick(i, (AgentReason("x", ("puan:return",)),)) for i in ("fund:A", "fund:B", "fund:C"))
    return AgentDecision(**({"run_id": "R0000000001", "state": "done", "picks": picks, "dropped": (),
                             "summary": "", "engine_top3": ("fund:A", "fund:B", "fund:D"), "nodes": (),
                             "model": "claude-sonnet-5-5", "prompt_version": "a3", "cost_usd": 0.0,
                             "created_at": T} | over))


def test_new_fields_round_trip():
    d = _d(n_candidates=12, marks_hash="3f2a9c01")
    assert (d.n_candidates, d.marks_hash) == (12, "3f2a9c01")
    assert AgentDecision.from_dict(d.to_dict()) == d


def test_v111_json_still_loads():
    raw = _d().to_dict()
    raw.pop("n_candidates")
    raw.pop("marks_hash")
    d = AgentDecision.from_dict(raw)
    assert (d.n_candidates, d.marks_hash) == (0, "")
