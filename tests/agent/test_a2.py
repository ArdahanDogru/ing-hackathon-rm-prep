"""A2 (spec 2026-10-15-rm-run-agent-design section 4; plan Task 3): the agent on the
RM's request with N candidates and the RM's marks on the research findings.

✗ ("wrong") findings never reach the agent; ✓ ("ok") findings carry "RM doğruladı"
and give the label "(web, RM doğruladı)"; prompt a3; the user message has two blocks
(block 1 stable with cache_control, block 2 the research with the marks); the
decision cache key adds N and the hash of the marks of the candidates' findings."""

import json
import threading

import pytest

from rmprep.agent.checks import check_decision
from rmprep.agent.pack import build_pack, candidates, finding_id, marks_hash
from rmprep.agent.service import PROMPTS
from tests.agent.conftest import (
    FakeResearch,
    ScriptedClient,
    call,
    cand_ids,
    karar,
    pack_of,
    reason,
    turn,
    valid_picks,
)


def _research(result, n=10):
    opts = [s.option for s in candidates(result, n)]
    return {r.option_id: r for r in FakeResearch().research_many(opts, "TR")}


def _fid(research, oid, i=0, news=False):
    r = research[oid]
    return finding_id(oid, (r.news if news else r.findings)[i])


def _run(svc, result, ev, n=None):
    svc.start(result, ev, n=n)
    svc.wait()
    return svc.status(result.run_id)


# --- pack ------------------------------------------------------------------------

def test_wrong_findings_are_removed_and_ok_findings_marked(ready_p01, ev, dcfg):
    research = _research(ready_p01)
    ok, wrong = _fid(research, "fund:EIL"), _fid(research, "fund:BBF", news=True)
    pack = build_pack(ready_p01, ev, dcfg, research, "TR", marks={ok: "ok", wrong: "wrong"})
    eil, bbf = pack["arastirma"]["fund:EIL"], pack["arastirma"]["fund:BBF"]
    assert eil["bulgular"][0]["id"] == ok and eil["bulgular"][0]["dogrulama"] == "RM doğruladı"
    assert eil["haberler"][0]["dogrulama"] == "doğrulanmamış"
    assert bbf["haberler"] == [] and len(bbf["bulgular"]) == 1
    assert wrong not in json.dumps(pack)


def test_marks_hash_counts_only_the_candidates_findings(ready_p01):
    research = _research(ready_p01)
    ok = _fid(research, "fund:EIL")
    assert marks_hash(research, {}) == ""
    assert marks_hash(research, {"F00000000": "ok"}) == ""         # not a candidate's finding
    one = marks_hash(research, {ok: "ok"})
    assert one and one == marks_hash(research, {ok: "ok", "F00000000": "wrong"})
    assert one != marks_hash(research, {ok: "wrong"})
    two = marks_hash(research, {ok: "ok", _fid(research, "fund:BBF"): "wrong"})
    assert two not in ("", one)


# --- checks ----------------------------------------------------------------------

def test_a_confirmed_finding_gets_the_confirmed_label(ready_p01, ev, dcfg, phrases):
    research = _research(ready_p01)
    picks = valid_picks(ready_p01)
    ok, plain = _fid(research, picks[0]), _fid(research, picks[0], news=True)
    pack = build_pack(ready_p01, ev, dcfg, research, "TR", marks={ok: "ok"})
    raw = karar(ready_p01, picks)
    raw["secimler"][0]["gerekceler"][0] = reason("Fon tanıtım bilgisi doğrulandı.", ok)
    raw["secimler"][1]["gerekceler"].append(
        reason("Habere göre fon büyüklüğü %12 arttı.", _fid(research, picks[1], news=True)))
    picks_out, _, _, problems = check_decision(raw, pack, dcfg, phrases, "TR")
    assert problems == []
    assert picks_out[0].reasons[0].labels == ("(web, RM doğruladı)",) and picks_out[0].uses_web
    assert picks_out[1].reasons[-1].labels == ("(web, doğrulanmamış)",)
    raw["secimler"][0]["gerekceler"][0] = reason("İki bulgu.", ok, plain)
    picks_out = check_decision(raw, pack, dcfg, phrases, "TR")[0]
    assert set(picks_out[0].reasons[0].labels) == {"(web, RM doğruladı)", "(web, doğrulanmamış)"}


def test_a_wrong_finding_cannot_be_cited(ready_p01, ev, dcfg, phrases):
    research = _research(ready_p01)
    picks = valid_picks(ready_p01)
    wrong = _fid(research, picks[0])
    pack = build_pack(ready_p01, ev, dcfg, research, "TR", marks={wrong: "wrong"})
    raw = karar(ready_p01, picks)
    raw["secimler"][0]["gerekceler"].append(reason("Web bulgusu.", wrong))
    assert any(wrong in p and "unknown" in p
               for p in check_decision(raw, pack, dcfg, phrases, "TR")[3])


# --- prompt a3 -------------------------------------------------------------------

def test_prompt_a3_has_the_marks_rule():
    tr, en = PROMPTS["a3"]["TR"], PROMPTS["a3"]["EN"]
    assert "henüz incelenmedi, yanlış değil" in tr and "RM tarafından doğrulandığı" in tr
    assert "not reviewed yet" in en and "%47,5" in tr and "47.5%" in en
    assert "henüz incelenmedi" not in PROMPTS["a2"]["TR"]


# --- service: N ------------------------------------------------------------------

@pytest.mark.parametrize("n", [2, 21, 0, "abc", 5.5, True])
def test_n_out_of_range_is_a_value_error(svc_factory, ready_p01, ev, n):
    client = ScriptedClient()
    svc = svc_factory(client)
    with pytest.raises(ValueError, match="n"):
        svc.start(ready_p01, ev, n=n)
    assert svc.status(ready_p01.run_id) is None and client.sent == []


def test_n_sets_the_candidates(svc_factory, ready_p01, ev):
    picks = valid_picks(ready_p01)
    research = FakeResearch()
    client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, picks))))
    d = _run(svc_factory(client, research), ready_p01, ev, n=5)
    assert d.state == "done" and d.n_candidates == 5
    assert len(pack_of(client.sent[0][1])["adaylar"]) == 5
    assert research.many_calls == [cand_ids(ready_p01)[:5]]
    assert "5" in d.nodes[0].notes[0]


def test_default_n_is_the_config_candidates(svc_factory, ready_p01, ev, cfg):
    client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, valid_picks(ready_p01)))))
    d = _run(svc_factory(client), ready_p01, ev)
    assert d.n_candidates == cfg.candidates == 10


# --- service: two blocks, cache key ------------------------------------------------

def test_the_client_gets_two_blocks_with_cache_control_only_on_block1(svc_factory, ready_p01,
                                                                       ev):
    client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, valid_picks(ready_p01)))))
    _run(svc_factory(client), ready_p01, ev)
    system, messages, _ = client.sent[0]
    b1, b2 = messages[0]["content"]
    assert b1["cache_control"] == {"type": "ephemeral"} and "cache_control" not in b2
    stable = json.loads(b1["text"].removeprefix("<veri>\n").removesuffix("\n</veri>"))
    assert list(stable) == ["dil", "musteri", "portfoy", "motor_ilk3", "adaylar", "kurallar"]
    assert b2["text"].startswith("<arastirma>\n") and "karar_ver" in b2["text"]
    assert "henüz incelenmedi" in system


def _marked_run(svc_factory, ready_p01, ev, research, root):
    picks = valid_picks(ready_p01)
    client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, picks))),
                            turn(call("karar_ver", **karar(ready_p01, picks))))
    return client, svc_factory(client, research, root=root)


def test_rerun_with_new_marks_keeps_block1(svc_factory, ready_p01, ev, tmp_path):
    """Review Focus 5: a re-run with new marks and the same N gives a new decision
    (the marks hash differs) and an identical block 1 (read from the prompt cache)."""
    research = FakeResearch()
    ids = _research(ready_p01)
    research.marks_map.update({_fid(ids, "fund:EIL"): "ok", _fid(ids, "fund:BBF"): "wrong"})
    client, svc = _marked_run(svc_factory, ready_p01, ev, research, tmp_path / "a")
    d1 = _run(svc, ready_p01, ev)
    research.marks_map[_fid(ids, "fund:AIS")] = "ok"
    d2 = _run(svc, ready_p01, ev)
    assert len(client.sent) == 2
    assert d1.marks_hash and d2.marks_hash and d1.marks_hash != d2.marks_hash
    assert d1.n_candidates == d2.n_candidates == 10
    b1 = [s[1][0]["content"][0] for s in client.sent]
    b2 = [s[1][0]["content"][1] for s in client.sent]
    assert b1[0] == b1[1]                                   # the cached prefix
    assert b2[0] != b2[1]
    assert svc.status(ready_p01.run_id) == d2               # the latest decision of the run
    # the marked findings in the pack of the second run
    pack = pack_of(client.sent[1][1])
    assert all(f["id"] != _fid(ids, "fund:BBF") for f in pack["arastirma"]["fund:BBF"]["bulgular"])
    ais = pack["arastirma"]["fund:AIS"]["bulgular"][0]
    assert ais["dogrulama"] == "RM doğruladı"


def test_same_n_and_marks_give_the_stored_decision(svc_factory, ready_p01, ev, tmp_path):
    research = FakeResearch()
    ids = _research(ready_p01)
    research.marks_map[_fid(ids, "fund:EIL")] = "ok"
    client, svc = _marked_run(svc_factory, ready_p01, ev, research, tmp_path / "a")
    d1 = _run(svc, ready_p01, ev)
    assert _run(svc, ready_p01, ev) == d1 and len(client.sent) == 1
    # a new service on the same cache (a restart): no new call
    again = ScriptedClient()
    d2 = _run(svc_factory(again, research, root=tmp_path / "a"), ready_p01, ev)
    assert d2 == d1 and again.sent == []
    # another N: a new call; then back to N = 10: the stored decision of N = 10
    d3 = _run(svc, ready_p01, ev, n=6)
    assert d3.n_candidates == 6 and len(client.sent) == 2
    assert _run(svc, ready_p01, ev, n=10) == d1 and len(client.sent) == 2


def test_double_start_is_one_job(svc_factory, ready_p01, ev):
    gate = threading.Event()
    picks = valid_picks(ready_p01)
    calls = []

    class Slow:
        def step(self, system, messages, tools):
            calls.append(1)
            gate.wait(5)
            return turn(call("karar_ver", **karar(ready_p01, picks)))

    svc = svc_factory(Slow())
    svc.start(ready_p01, ev)
    svc.start(ready_p01, ev)
    svc.start(ready_p01, ev, n=7)            # also while it runs: the running job stays
    assert svc.status(ready_p01.run_id).state == "running"
    gate.set()
    svc.wait()
    assert len(calls) == 1 and svc.status(ready_p01.run_id).n_candidates == 10


def test_research_without_marks_or_failing_marks(svc_factory, ready_p01, ev):
    class NoMarks(FakeResearch):
        marks = None

    class BadMarks(FakeResearch):
        def marks(self):
            raise OSError("marks file")

    for research in (NoMarks(), BadMarks()):
        client = ScriptedClient(turn(call("karar_ver", **karar(ready_p01, valid_picks(ready_p01)))))
        d = _run(svc_factory(client, research), ready_p01, ev)
        assert d.state == "done" and d.marks_hash == ""
