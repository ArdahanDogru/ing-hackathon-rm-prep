import inspect

import pytest

from rmprep.contracts import Backend, DecisionState, RmStatus
from tests.ui.conftest import PERSONA_IDS, SNAPSHOT


def _persona(fake, pid):
    return next(p for p in fake.list_personas() if p.persona_id == pid)


def test_fake_has_every_backend_method_with_the_same_signature(fake):
    names = [n for n, _ in inspect.getmembers(Backend, inspect.isfunction) if not n.startswith("_")]
    assert len(names) == 11          # v1.4 adds brief
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


def test_given_results_replace_the_fixture_of_their_persona(fake):
    import dataclasses

    from rmprep.ui.fake import FakeBackend
    from tests.ui.conftest import CONTRACT_FIX

    p02 = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    named = {oid for w in p02.warnings for oid in w.option_ids}
    keep = tuple(o for i, o in enumerate(p02.options) if i == 0 or o.option.option_id in named)
    assert len(keep) < len(p02.options)
    short = dataclasses.replace(p02, options=keep)
    other = FakeBackend(CONTRACT_FIX, results=[short])
    assert other.decide(_persona(other, "P02"), SNAPSHOT).options == keep
    assert other.decide(_persona(other, "P03"), SNAPSHOT).persona_id == "P03"


# --- narrator (contract v1.2) -------------------------------------------------

def _approved_run(fake):
    r = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    fx = next(o for o in r.options if o.option.fx).option.option_id
    return fake.approve(r.run_id, RmStatus.APPROVED, "ok", (r.options[1].option.option_id, fx))


def test_draft_narrative_is_a_template_draft_of_the_approved_run(fake):
    from rmprep.contracts import NARRATIVE_SECTIONS, NarrativeStatus

    r = _approved_run(fake)
    d = fake.draft_narrative(r.run_id)
    assert (d.run_id, d.lang, d.source, d.model, d.prompt_version) == (r.run_id, "TR", "template", "",
                                                                       "fake")
    assert d.status == NarrativeStatus.DRAFT and d.checks == () and d.rm_text == ""
    assert [s.key for s in d.sections] == list(NARRATIVE_SECTIONS)
    assert all(s.sentences and all(x.text.strip() for x in s.sentences) for s in d.sections)
    oneriler = next(s for s in d.sections if s.key == "oneriler")
    assert {i for x in oneriler.sentences for i in x.option_ids} == set(r.rm_selected)
    scored = {o.option.option_id for o in r.options}
    assert {i for s in d.sections for x in s.sentences for i in x.option_ids} <= scored
    ev = {dp.id for dp in fake.evidence(SNAPSHOT).datapoints}
    assert {i for s in d.sections for x in s.sentences for i in x.evidence_ids} <= ev


def test_draft_narrative_is_cached_per_run_and_language(fake):
    r = _approved_run(fake)
    tr = fake.draft_narrative(r.run_id)
    assert fake.draft_narrative(r.run_id, "TR") is tr
    en = fake.draft_narrative(r.run_id, "EN")
    assert en.lang == "EN" and en is not tr and en.sections != tr.sections


def test_draft_narrative_needs_an_approved_run(fake):
    r = fake.decide(_persona(fake, "P02"), SNAPSHOT)
    with pytest.raises(ValueError):
        fake.draft_narrative(r.run_id)
    rej = fake.approve(r.run_id, RmStatus.REJECTED, "hayır")
    with pytest.raises(ValueError):
        fake.draft_narrative(rej.run_id)
    with pytest.raises(KeyError):
        fake.draft_narrative("Rnope")


def test_draft_narrative_rejects_an_unknown_language(fake):
    r = _approved_run(fake)
    with pytest.raises(ValueError):
        fake.draft_narrative(r.run_id, "DE")


def test_approve_narrative_stores_the_rm_text(fake):
    from rmprep.contracts import NarrativeStatus

    r = _approved_run(fake)
    draft = fake.draft_narrative(r.run_id)
    text = "# Metin\nRM yazdı"
    a = fake.approve_narrative(r.run_id, "TR", text)
    assert a.status == NarrativeStatus.APPROVED and a.rm_text == text
    assert a.sections == draft.sections
    assert fake.draft_narrative(r.run_id, "TR") == a
    assert fake.draft_narrative(r.run_id, "EN").status == NarrativeStatus.DRAFT


def test_approve_narrative_needs_text_and_an_approved_run(fake):
    r = _approved_run(fake)
    with pytest.raises(ValueError):
        fake.approve_narrative(r.run_id, "TR", "  ")
    pending = fake.decide(_persona(fake, "P03"), SNAPSHOT)
    with pytest.raises(ValueError):
        fake.approve_narrative(pending.run_id, "TR", "metin")
