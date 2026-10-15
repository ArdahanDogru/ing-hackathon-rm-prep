import html
import re
import string
from pathlib import Path

import pytest

from rmprep.contracts import RmStatus
from rmprep.ui import card, views
from rmprep.ui.i18n import LABELS, LANGS, t
from tests.ui.conftest import SNAPSHOT, app_test, run

UI_SRC = Path(__file__).resolve().parents[2] / "src" / "rmprep" / "ui"


def _approved(fake, note="genel not", option_note="BBF için not"):
    p = next(p for p in fake.list_personas() if p.persona_id == "P02")
    r = fake.decide(p, SNAPSHOT)
    fx = next(o for o in r.options if o.option.fx).option.option_id
    sel = (r.options[1].option.option_id, fx)
    fake.approve(r.run_id, RmStatus.APPROVED, note, sel)
    return fake.annotate(r.run_id, note, {sel[0]: option_note})


# --- card -----------------------------------------------------------------------

def test_markdown_card_holds_selected_options_notes_and_citations(fake):
    r = _approved(fake)
    ev = fake.evidence(SNAPSHOT)
    md = card.render_markdown(r, ev)
    selected = [o for o in r.options if o.option.option_id in r.rm_selected]
    others = [o for o in r.options if o.option.option_id not in r.rm_selected]
    for o in selected:
        # 2026-10-15 (the user): scores x100 ("85"), parts signed ("+24"), confidence as %
        assert o.option.label in md and f"skor {card.points(o.score)}" in md
        assert f"%{round(o.confidence * 100)}" in md
        for part in views.main_parts(o):
            assert o.reasons[part["key"]] in md
            assert f"({card.points(part['value'], signed=True)})" in md
    for o in others:
        assert o.option.label not in md
    fx_warning = next(w for w in r.warnings if w.code == "fx_exposure")
    assert fx_warning.message in md
    for n in r.data_quality:
        assert n.message in md
    for a in r.assumptions:
        assert a in md
    for c in views.citations(r, ev):
        assert c in md
    assert "genel not" in md and "BBF için not" in md
    assert r.persona.profil in md and r.run_id in md


def test_main_parts_are_the_largest_by_size(fake):
    r = _approved(fake)
    fx = next(o for o in r.options if o.option.fx)
    keys = [p["key"] for p in views.main_parts(fx)]
    assert len(keys) == views.MAIN_PARTS and keys[0] == "return"
    assert "penalty:fx_exposure" in keys


def test_html_card_has_the_same_content_escaped(fake):
    r = _approved(fake, note="<b>dikkat</b> & not")
    ev = fake.evidence(SNAPSHOT)
    doc = card.render_html(r, ev)
    assert doc.startswith("<!DOCTYPE html>") and "</html>" in doc
    assert "<b>dikkat</b>" not in doc and html.escape("<b>dikkat</b> & not") in doc
    for o in r.options:
        if o.option.option_id in r.rm_selected:
            assert html.escape(o.option.label) in doc
    for c in views.citations(r, ev):
        assert html.escape(c) in doc


def test_card_needs_an_approved_result(fake):
    p = fake.list_personas()[1]
    r = fake.decide(p, SNAPSHOT)
    with pytest.raises(ValueError):
        card.render_markdown(r, fake.evidence(SNAPSHOT))


def test_english_card_uses_english_labels(fake):
    r = _approved(fake)
    md = card.render_markdown(r, fake.evidence(SNAPSHOT), lang="EN")
    assert t("card_title", "EN") in md and t("card_title", "TR") not in md


# --- page -----------------------------------------------------------------------

def _approve_on_page():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    oid = r.options[1].option.option_id
    at.checkbox(key=f"sel:{r.run_id}:{oid}").check()
    at.button(key="approve").click()
    return run(at), r.run_id, oid


def test_approval_shows_saves_and_offers_the_card():
    at, run_id, oid = _approve_on_page()
    backend = at.session_state["backend"]
    assert run_id in backend.cards
    assert any(t("card_title") in m.value for m in at.markdown)
    assert len(at.get("download_button")) == 2


def test_notes_after_approval_are_saved_in_the_result_and_the_card():
    at, run_id, oid = _approve_on_page()
    at.text_area(key=f"card_note:{run_id}").input("müşteri altın soracak")
    at.text_area(key=f"card_onote:{run_id}:{oid}").input("vade 1 yıl")
    at.button(key="save_notes").click()
    run(at)
    backend = at.session_state["backend"]
    r = at.session_state["result"]
    assert r.rm_note == "müşteri altın soracak" and r.rm_option_notes == {oid: "vade 1 yıl"}
    assert backend.saved[run_id] == r
    assert "müşteri altın soracak" in backend.cards[run_id] and "vade 1 yıl" in backend.cards[run_id]


def test_empty_option_notes_are_not_stored():
    at, run_id, oid = _approve_on_page()
    at.text_area(key=f"card_note:{run_id}").input("x")
    at.button(key="save_notes").click()
    run(at)
    assert at.session_state["result"].rm_option_notes == {}


def test_rejected_run_has_no_card():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    at.text_area(key=f"note:{r.run_id}").input("uygun değil")
    at.button(key="reject").click()
    run(at)
    assert not at.get("download_button") and r.run_id not in at.session_state["backend"].cards


def test_english_toggle_changes_labels_and_adds_the_footer():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    at.radio(key="lang").set_value("EN")
    run(at)
    assert [tab.label for tab in at.tabs] == [t(k, "EN") for k in
                                              ("tab_short", "tab_all", "tab_rejected", "tab_evidence")]
    assert any(t("en_footer", "EN") in c.value for c in at.caption)
    at.radio(key="lang").set_value("TR")
    run(at)
    assert not any(t("en_footer", "EN") in c.value for c in at.caption)


# --- labels ---------------------------------------------------------------------

def _fields(text):
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


def test_every_label_exists_in_tr_and_en_with_the_same_fields():
    assert LANGS == ("TR", "EN")
    for key, texts in LABELS.items():
        assert set(texts) == set(LANGS), key
        assert all(texts[lang].strip() for lang in LANGS), key
        assert _fields(texts["TR"]) == _fields(texts["EN"]), key


def test_every_label_key_used_in_the_code_exists():
    used = set()
    for path in UI_SRC.glob("*.py"):
        used |= set(re.findall(r"""\bt\(\s*["']([a-z_]+)["']\s*[,)]""",
                               path.read_text(encoding="utf-8")))
    assert used and used <= set(LABELS), sorted(used - set(LABELS))
    # keys made from a prefix: t("f_" + field), t("rm_" + status)
    import dataclasses

    from rmprep.contracts import Persona
    assert {"f_" + f.name for f in dataclasses.fields(Persona)} <= set(LABELS)
    assert {"rm_approved", "rm_rejected"} <= set(LABELS)
    assert {"need_selection", "need_note"} <= set(LABELS)     # t(err) in the RM bar


@pytest.mark.parametrize("x, signed, out", [(0.854, False, "85"), (0.855, False, "86"), (0.2449, True, "+24"),
                                            (-0.105, True, "−11"), (0.0, True, "0"), (-0.004, True, "0")])
def test_points(x, signed, out):
    assert card.points(x, signed=signed) == out
