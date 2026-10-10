"""U9: the "Görüşme metni" pane (docs/narrator.md, contract v1.2) with the FakeBackend."""

import dataclasses
import html

from rmprep.contracts import NarrativeStatus, RmStatus
from rmprep.narrator import template
from rmprep.ui import card
from rmprep.ui.fake import FakeBackend
from rmprep.ui.i18n import t
from tests.ui.conftest import CONTRACT_FIX, SNAPSHOT, app_test, run


class CountingBackend(FakeBackend):
    """Counts draft_narrative calls; checks=() can be overridden to force a banner."""

    def __init__(self, *a, checks=None, **kw):
        super().__init__(*a, **kw)
        self.draft_calls: list[tuple[str, str]] = []
        self._checks = checks

    def draft_narrative(self, run_id, lang="TR"):
        self.draft_calls.append((run_id, lang))
        d = super().draft_narrative(run_id, lang)
        if self._checks is not None and d.status == NarrativeStatus.DRAFT:
            d = dataclasses.replace(d, checks=self._checks)
        return d


def _approved_page(backend=None):
    backend = backend or CountingBackend(CONTRACT_FIX)
    at = run(app_test(backend))
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    oid = r.options[1].option.option_id
    at.checkbox(key=f"sel:{r.run_id}:{oid}").check()
    at.button(key="approve").click()
    return run(at), r.run_id, backend


def _text_key(run_id, lang="TR"):
    return f"nar_text:{run_id}:{lang}"


# --- page ---------------------------------------------------------------------

def test_no_meeting_text_before_approval():
    backend = CountingBackend(CONTRACT_FIX)
    at = run(app_test(backend))
    at.selectbox(key="persona").set_value("P02")
    run(at)
    assert not any(t("nar_title") in s.value for s in at.subheader)
    assert backend.draft_calls == []


def test_approval_opens_the_pane_with_the_draft_as_editable_markdown():
    at, run_id, backend = _approved_page()
    assert any(t("nar_title") in s.value for s in at.subheader)
    assert backend.draft_calls == [(run_id, "TR")]
    d = backend.draft_narrative(run_id, "TR")
    assert at.text_area(key=_text_key(run_id)).value == template.to_markdown(d)
    text = " ".join(m.value for m in at.markdown)
    for sec in d.sections:
        assert template.HEADINGS[sec.key]["TR"] in text
        for s in sec.sentences:
            assert s.text in text
    meta = " ".join(c.value for c in at.caption)
    assert "template" in meta and d.prompt_version in meta and "0.0000" in meta


def test_one_draft_per_language_made_when_first_opened():
    at, run_id, backend = _approved_page()
    run(at)
    assert backend.draft_calls == [(run_id, "TR")]
    at.radio(key="lang").set_value("EN")
    run(at)
    assert backend.draft_calls == [(run_id, "TR"), (run_id, "EN")]
    assert any(t("nar_title", "EN") in s.value for s in at.subheader)
    at.radio(key="lang").set_value("TR")
    run(at)
    assert backend.draft_calls == [(run_id, "TR"), (run_id, "EN")]


def test_sentence_citations_link_to_the_evidence_filter():
    at, run_id, backend = _approved_page()
    d = backend.draft_narrative(run_id, "TR")
    sec_i, sec = next((i, s) for i, s in enumerate(d.sections)
                      if any(x.evidence_ids for x in s.sentences))
    j, sentence = next((j, x) for j, x in enumerate(sec.sentences) if x.evidence_ids)
    at.button(key=f"ev:nar:TR:{sec_i}:{j}").click()
    run(at)
    assert at.session_state["ev_filter"] == (run_id, tuple(dict.fromkeys(sentence.evidence_ids)))
    assert at.session_state["tabs:TR"] == t("tab_evidence")


def test_sentence_option_citations_name_the_options():
    at, run_id, backend = _approved_page()
    r = at.session_state["result"]
    labels = {o.option.option_id: o.option.label for o in r.options}
    d = backend.draft_narrative(run_id, "TR")
    cited = {i for s in d.sections for x in s.sentences for i in x.option_ids}
    captions = " ".join(c.value for c in at.caption)
    for oid in cited:
        assert labels[oid] in captions


def test_banner_is_shown_for_a_checked_template_draft():
    at, run_id, backend = _approved_page(CountingBackend(CONTRACT_FIX, checks=("too long",)))
    d = backend.draft_narrative(run_id, "TR")
    assert template.banner(d)
    assert any(template.banner(d) in w.value for w in at.warning)


def test_no_banner_without_checks():
    at, run_id, backend = _approved_page()
    assert not any(template.BANNER["TR"] in w.value for w in at.warning)


def test_approve_text_stores_it_and_puts_it_on_the_card():
    at, run_id, backend = _approved_page()
    edited = "# Görüşme metni\n\nRM'in düzenlediği metin."
    at.text_area(key=_text_key(run_id)).input(edited)
    at.button(key="nar_approve").click()
    run(at)
    stored = backend.draft_narrative(run_id, "TR")
    assert stored.status == NarrativeStatus.APPROVED and stored.rm_text == edited
    assert "RM'in düzenlediği metin." in backend.cards[run_id]
    assert any("RM'in düzenlediği metin." in m.value for m in at.markdown
               if t("card_title") in m.value)
    assert any(t("nar_approved") in s.value for s in at.success)
    assert at.text_area(key=_text_key(run_id)).value == edited


def test_empty_text_is_not_approved():
    at, run_id, backend = _approved_page()
    at.text_area(key=_text_key(run_id)).input("   ")
    at.button(key="nar_approve").click()
    run(at)
    assert backend.draft_narrative(run_id, "TR").status == NarrativeStatus.DRAFT
    assert any(t("nar_empty") in e.value for e in at.error)


def test_card_holds_the_approved_text_of_the_page_language_only():
    at, run_id, backend = _approved_page()
    at.text_area(key=_text_key(run_id)).input("Türkçe onaylı metin")
    at.button(key="nar_approve").click()
    run(at)
    at.radio(key="lang").set_value("EN")
    run(at)
    card_md = next(m.value for m in at.markdown if t("card_title", "EN") in m.value)
    assert "Türkçe onaylı metin" not in card_md


def test_a_rejected_run_has_no_meeting_text():
    backend = CountingBackend(CONTRACT_FIX)
    at = run(app_test(backend))
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    at.text_area(key=f"note:{r.run_id}").input("uygun değil")
    at.button(key="reject").click()
    run(at)
    assert at.session_state["result"].rm_status == RmStatus.REJECTED
    assert backend.draft_calls == []


# --- card -----------------------------------------------------------------------

def _approved_result(fake):
    p = next(p for p in fake.list_personas() if p.persona_id == "P02")
    r = fake.decide(p, SNAPSHOT)
    return fake.approve(r.run_id, RmStatus.APPROVED, "", (r.options[1].option.option_id,))


def test_card_renders_include_an_approved_narrative_of_their_language(fake):
    r = _approved_result(fake)
    ev = fake.evidence(SNAPSHOT)
    a = fake.approve_narrative(r.run_id, "TR", "## Öneri\n\nMetin <b>kalın</b> & net.")
    md = card.render_markdown(r, ev, "TR", narrative=a)
    assert t("nar_title") in md and "Metin <b>kalın</b> & net." in md
    doc = card.render_html(r, ev, "TR", narrative=a)
    assert html.escape("Metin <b>kalın</b> & net.") in doc and "<b>kalın</b>" not in doc
    # a narrative of another language is not put on the card
    assert card.render_markdown(r, ev, "EN", narrative=a) == card.render_markdown(r, ev, "EN")


def test_card_ignores_a_draft_narrative(fake):
    r = _approved_result(fake)
    ev = fake.evidence(SNAPSHOT)
    d = fake.draft_narrative(r.run_id, "TR")
    assert card.render_markdown(r, ev, "TR", narrative=d) == card.render_markdown(r, ev, "TR")
