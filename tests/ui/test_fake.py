import inspect

import pytest

from rmprep.contracts import Backend, DecisionState, RmStatus
from tests.ui.conftest import PERSONA_IDS, SNAPSHOT


def _persona(fake, pid):
    return next(p for p in fake.list_personas() if p.persona_id == pid)


def test_fake_has_every_backend_method_with_the_same_signature(fake):
    names = [n for n, _ in inspect.getmembers(Backend, inspect.isfunction) if not n.startswith("_")]
    assert len(names) == 8
    for name in names:
        expected = list(inspect.signature(getattr(Backend, name)).parameters)[1:]
        assert list(inspect.signature(getattr(fake, name)).parameters) == expected, name


def test_lists_personas_and_snapshots(fake):
    assert [p.persona_id for p in fake.list_personas()] == PERSONA_IDS
    assert fake.list_snapshots() == [SNAPSHOT]


def test_evidence_drops_the_rows_of_excluded_sources(fake):
    full = fake.evidence(SNAPSHOT)
    assert {"tefas", "tefas_web"} <= {dp.source for dp in full.datapoints}
    cut = fake.evidence(SNAPSHOT, frozenset({"tefas"}))
    assert cut.excluded_sources == frozenset({"tefas"})
    assert "tefas" not in {dp.source for dp in cut.datapoints}
    assert len(cut.datapoints) == sum(dp.source != "tefas" for dp in full.datapoints)
    assert cut.source_status == full.source_status


def test_unknown_snapshot_raises(fake):
    with pytest.raises(KeyError):
        fake.evidence("nope")


@pytest.mark.parametrize("pid,state", [("P01", DecisionState.NEEDS_RM_INPUT),
                                       ("P02", DecisionState.READY),
                                       ("P03", DecisionState.READY),
                                       ("P04", DecisionState.READY),
                                       ("P05", DecisionState.READY)])
def test_decide_puts_in_the_persona_and_the_inputs(fake, pid, state):
    persona = _persona(fake, pid)
    r = fake.decide(persona, SNAPSHOT)
    assert r.persona == persona
    assert r.state == state
    assert r.snapshot_id == SNAPSHOT
    assert r.rm_status == RmStatus.PENDING


def test_run_id_follows_the_inputs(fake):
    p = _persona(fake, "P02")
    a = fake.decide(p, SNAPSHOT)
    assert fake.decide(p, SNAPSHOT).run_id == a.run_id
    b = fake.decide(p, SNAPSHOT, frozenset({"tefas"}))
    assert b.run_id != a.run_id
    assert b.excluded_sources == frozenset({"tefas"})
    assert a.run_id.startswith("R") and len(a.run_id) == 11


def test_answer_question_makes_a_new_run(fake):
    r = fake.decide(_persona(fake, "P01"), SNAPSHOT)
    q = r.questions[0]
    r2 = fake.answer_question(r.run_id, q.question_id, q.choices[0])
    assert r2.run_id != r.run_id
    assert r2.state == DecisionState.READY
    assert r2.questions[0].answer == q.choices[0]
    r3 = fake.answer_question(r2.run_id, q.question_id, q.choices[1])
    assert r3.questions[0].answer == q.choices[1]
    assert r3.run_id not in (r.run_id, r2.run_id)


def test_answers_are_kept_in_a_later_answer(fake):
    p = _persona(fake, "P02")
    r = fake.decide(p, SNAPSHOT)
    q = r.questions[0]
    r2 = fake.answer_question(r.run_id, q.question_id, q.choices[0])
    # same inputs and same answers -> same run id
    assert fake.answer_question(r.run_id, q.question_id, q.choices[0]).run_id == r2.run_id
    assert r2.state == DecisionState.READY and r2.options == r.options


def test_answer_to_an_unknown_question_raises(fake):
    r = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    with pytest.raises(KeyError):
        fake.answer_question(r.run_id, "q:nope", "x")


def test_approve_annotate_and_save_card(fake):
    r = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    sel = (r.options[1].option.option_id,)
    a = fake.approve(r.run_id, RmStatus.APPROVED, "ok", sel)
    assert (a.rm_status, a.rm_note, a.rm_selected, a.run_id) == (RmStatus.APPROVED, "ok", sel, r.run_id)
    n = fake.annotate(r.run_id, "genel", {sel[0]: "not"})
    assert n.rm_note == "genel" and n.rm_option_notes == {sel[0]: "not"}
    where = fake.save_card(r.run_id, "# kart")
    assert fake.cards[r.run_id] == "# kart" and r.run_id in where
    assert fake.saved[r.run_id] == n


def test_approve_needs_a_selection_and_reject_needs_a_note(fake):
    r = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    with pytest.raises(ValueError):
        fake.approve(r.run_id, RmStatus.APPROVED, "ok")
    with pytest.raises(ValueError):
        fake.approve(r.run_id, RmStatus.REJECTED, "")
    rej = fake.approve(r.run_id, RmStatus.REJECTED, "uygun değil")
    assert rej.rm_status == RmStatus.REJECTED and rej.rm_selected == ()
    assert fake.saved[r.run_id] == rej


def test_needs_input_result_cannot_be_approved(fake):
    r = fake.decide(_persona(fake, "P01"), SNAPSHOT)
    with pytest.raises(ValueError):
        fake.approve(r.run_id, RmStatus.APPROVED, "", ())


def test_annotate_and_save_card_need_an_approved_run(fake):
    r = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    with pytest.raises(ValueError):
        fake.annotate(r.run_id, "x", {})
    with pytest.raises(ValueError):
        fake.save_card(r.run_id, "# x")


def test_unknown_run_raises(fake):
    with pytest.raises(KeyError):
        fake.answer_question("Rnope", "q:x", "y")
