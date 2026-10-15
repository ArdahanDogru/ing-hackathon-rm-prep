"""E11: the run check `agent_decision` (spec section 6 on the stored decision). A real
decision of the fake model, then one broken rule per test."""

import dataclasses
from datetime import datetime

import pytest

from rmprep.contracts import TR_TZ, AgentDecision, AgentPick, AgentReason
from rmprep.decision.config import load_config as load_decision_config
from rmprep.eval.agent_eval import AgentRecord
from rmprep.eval.checks import FAIL, NA, PASS, Context, check_agent_decision
from rmprep.eval.report import RULE_LABELS
from rmprep.eval.scenario import Scenario
from tests.eval.conftest import PackClient
from tests.eval.test_agent_eval import run_with_agent

WEB = "(web, doğrulanmamış)"


@pytest.fixture
def done(root):
    """A ready P01 run with a done decision: the engine's #1 swapped, the first pick
    with a web reason."""
    s = Scenario(id="base-p01", group="base", persona="P01", narrate=False)
    runs, _ = run_with_agent(root, [s], PackClient("swap", web=True), repeat=False)
    run = runs[0].runs[0]
    assert run.agent.decision.state == "done"
    return s, run


def check(s, run):
    raw = load_decision_config().raw
    return check_agent_decision(Context(s, run, raw, {}))


def with_decision(run, **kw):
    a = run.agent
    return dataclasses.replace(run, agent=dataclasses.replace(
        a, decision=dataclasses.replace(a.decision, **kw)))


def with_pick(run, i, pick):
    picks = list(run.agent.decision.picks)
    picks[i] = pick
    return with_decision(run, picks=tuple(picks))


def puan(run, oid):
    c = next(c for c in run.agent.pack["adaylar"] if c["option_id"] == oid)
    return c["puan_parcalari"][0]["id"]


def plain_pick(run, oid, text="Puanı adaylar arasında güçlü.", cites=None, labels=()):
    return AgentPick(oid, (AgentReason(text, tuple(cites or (puan(run, oid),)), labels),))


def test_a_valid_decision_passes(done):
    s, run = done
    assert run.agent.decision.picks[0].uses_web
    r = check(s, run)
    assert r.status == PASS, r.details
    assert "agent_decision" in RULE_LABELS


def test_na_without_a_decision(done):
    s, run = done
    assert check(s, dataclasses.replace(run, agent=None)).status == NA
    no = dataclasses.replace(run, agent=AgentRecord(error="budget: eval limit reached"))
    r = check(s, no)
    assert r.status == NA and "budget" in r.details[0]


def test_na_when_the_agent_is_off(done):
    s, run = done
    off = with_decision(run, state="off", picks=(), dropped=(), summary="",
                        fallback_reason="ajan kapalı: no ANTHROPIC_API_KEY")
    r = check(s, off)
    assert r.status == NA and "off" in r.details[0]


def test_a_fallback_passes_with_its_reason(done):
    s, run = done
    fb = with_decision(run, state="fallback", picks=(), dropped=(), summary="",
                       fallback_reason="Motor önerisi kullanıldı: süre sınırı aşıldı (90 sn)")
    r = check(s, fb)
    assert r.status == PASS and r.details == ("fallback: Motor önerisi kullanıldı: süre sınırı "
                                              "aşıldı (90 sn)",)


def test_no_decision_at_the_deadline_fails(done):
    s, run = done
    r = check(s, with_decision(run, state="running", picks=(), dropped=(), summary=""))
    assert r.status == FAIL and "deadline" in r.details[0]


def test_a_pick_outside_the_candidates_fails(done):
    s, run = done
    cands = {c["option_id"] for c in run.agent.pack["adaylar"]}
    outside = next((o.option.option_id for o in run.result.options
                    if o.option.kind != "deposit" and o.option.option_id not in cands),
                   "fund:ZZZ")
    bad = with_pick(run, 1, AgentPick(outside, (AgentReason("Puanı güçlü.", ("puan:return",)),)))
    r = check(s, bad)
    assert r.status == FAIL and any("not a candidate" in d for d in r.details)


def test_too_many_shares_fail(done):
    s, run = done
    pack = run.agent.pack
    pack["kurallar"]["en_fazla_hisse"] = 0
    first = run.agent.decision.picks[0].option_id
    next(c for c in pack["adaylar"] if c["option_id"] == first)["tur"] = "stock"
    r = check(s, run)
    assert r.status == FAIL and any("shares" in d for d in r.details)


def test_the_class_rule_is_checked_when_the_candidates_allow_it(done):
    s, run = done
    pack = run.agent.pack
    pack["kurallar"].update(sinif_kurali=True, sinif_basina_en_fazla=1, nakit_benzeri_en_fazla=1)
    cash = [c["option_id"] for c in pack["adaylar"] if c["varlik_sinifi"] == "nakit_benzeri"][:3]
    picks = tuple(plain_pick(run, oid) for oid in cash)
    engine = run.result.recommended
    dropped = tuple(plain_pick(run, oid) for oid in engine if oid not in cash)
    r = check(s, with_decision(run, picks=picks, dropped=dropped))
    assert r.status == FAIL and any("nakit_benzeri" in d for d in r.details)


def test_an_unknown_citation_fails(done):
    s, run = done
    oid = run.agent.decision.picks[1].option_id
    r = check(s, with_pick(run, 1, plain_pick(run, oid, cites=("E00000000",))))
    assert r.status == FAIL and any("unknown evidence id" in d for d in r.details)


def test_a_finding_of_another_option_fails(done):
    s, run = done
    first = run.agent.decision.picks[0]
    fid = next(c for r in first.reasons for c in r.cites if c.startswith("F"))
    oid = run.agent.decision.picks[1].option_id
    bad = plain_pick(run, oid, "Web bulgusu ürünü destekliyor.", (fid,), (WEB,))
    r = check(s, with_pick(run, 1, dataclasses.replace(bad, uses_web=True)))
    assert r.status == FAIL and any("does not belong" in d for d in r.details)


def test_a_missing_web_label_fails(done):
    s, run = done
    first = run.agent.decision.picks[0]
    reasons = tuple(dataclasses.replace(r, labels=()) for r in first.reasons)
    r = check(s, with_pick(run, 0, dataclasses.replace(first, reasons=reasons)))
    assert r.status == FAIL and any("label" in d for d in r.details)
    r = check(s, with_pick(run, 0, dataclasses.replace(first, uses_web=False)))
    assert r.status == FAIL and any("uses_web" in d for d in r.details)


def test_a_number_not_in_the_cited_data_fails(done):
    s, run = done
    oid = run.agent.decision.picks[2].option_id
    r = check(s, with_pick(run, 2, plain_pick(run, oid, "Getirisi %97,3 oldu.")))
    assert r.status == FAIL and any("97,3" in d for d in r.details)


def test_a_forbidden_phrase_fails(done):
    s, run = done
    oid = run.agent.decision.picks[2].option_id
    r = check(s, with_pick(run, 2, plain_pick(run, oid, "Getirisi garanti bir üründür.")))
    assert r.status == FAIL and any("forbidden phrase" in d for d in r.details)


def test_a_dropped_engine_option_without_a_reason_fails(done):
    s, run = done
    r = check(s, with_decision(run, dropped=()))
    assert r.status == FAIL and any("without a reason" in d for d in r.details)


def test_the_engine_top3_must_be_the_runs(done):
    s, run = done
    top = run.result.recommended
    r = check(s, with_decision(run, engine_top3=(top[1], top[0], top[2])))
    assert r.status == FAIL and any("engine_top3" in d for d in r.details)


def test_no_pack_fails(done):
    s, run = done
    r = check(s, dataclasses.replace(run, agent=dataclasses.replace(run.agent, pack=None)))
    assert r.status == FAIL and any("pack" in d for d in r.details)


# --- E12: agent_marks -------------------------------------------------------------------

from rmprep.eval.checks import check_agent_marks  # noqa: E402
from rmprep.eval.scenario import AgentMark  # noqa: E402

CONFIRMED = "(web, RM doğruladı)"
MARKS = (AgentMark("engine2", "findings", 0, "wrong"), AgentMark("engine1", "findings", 0, "ok"))


@pytest.fixture
def marked(root):
    """P01 with ✗ on the first highlight of the engine's #2 and ✓ on the first of #1;
    the fake keeps the engine's top 3 and cites the ✓ finding."""
    s = Scenario(id="agent-marks", group="agent", persona="P01", narrate=False,
                 agent_marks=MARKS)
    runs, _ = run_with_agent(root, [s], PackClient("keep", web=True), repeat=False)
    return s, runs[0].runs[0]


def marks_check(s, run):
    return check_agent_marks(Context(s, run, load_decision_config().raw, {}))


def test_marks_pass(marked):
    s, run = marked
    r = marks_check(s, run)
    assert r.status == PASS, r.details
    assert "agent_marks" in RULE_LABELS
    assert check(s, run).status == PASS          # agent_decision knows the confirmed label


def test_marks_na_without_marks(done):
    s, run = done
    assert marks_check(s, run).status == NA


def test_marks_na_without_a_decision(marked):
    s, run = marked
    assert marks_check(s, dataclasses.replace(run, agent=None)).status == NA


def test_a_wrong_finding_in_the_pack_fails(marked):
    s, run = marked
    wrong = run.agent.marks[0]
    two = run.agent.pack["arastirma"][wrong["option_id"]]
    two["bulgular"].append({"id": wrong["finding_id"], "metin": wrong["text"], "konu": "urun",
                            "tarih": "", "kaynak": "x", "dogrulama": "doğrulanmamış"})
    r = marks_check(s, run)
    assert r.status == FAIL and any("still in the pack" in d for d in r.details)


def test_an_ok_finding_without_the_confirmation_fails(marked):
    s, run = marked
    ok = run.agent.marks[1]
    run.agent.pack["arastirma"][ok["option_id"]]["bulgular"][0]["dogrulama"] = "doğrulanmamış"
    r = marks_check(s, run)
    assert r.status == FAIL and any("RM doğruladı" in d for d in r.details)


def test_a_reason_on_the_ok_finding_without_the_label_fails(marked):
    s, run = marked
    first = run.agent.decision.picks[0]
    reasons = tuple(dataclasses.replace(r, labels=()) for r in first.reasons)
    bad = with_pick(run, 0, dataclasses.replace(first, reasons=reasons))
    r = marks_check(s, bad)
    assert r.status == FAIL and any(CONFIRMED in d for d in r.details)


def test_no_marks_hash_fails(marked):
    s, run = marked
    r = marks_check(s, with_decision(run, marks_hash=""))
    assert r.status == FAIL and any("marks_hash" in d for d in r.details)


def test_an_unresolved_mark_fails(root):
    s = Scenario(id="agent-marks", group="agent", persona="P01", narrate=False,
                 agent_marks=(AgentMark("engine1", "findings", 7, "ok"),))
    runs, _ = run_with_agent(root, [s], PackClient("keep"), repeat=False)
    r = marks_check(s, runs[0].runs[0])
    assert r.status == FAIL and any("no findings item 7" in d for d in r.details)
