import pytest

from rmprep.ui import views
from rmprep.ui.i18n import t
from tests.ui.conftest import SNAPSHOT, app_test, run

EVIDENCE_TAB = t("tab_evidence")


def _p(pid):
    at = run(app_test())
    at.selectbox(key="persona").set_value(pid)
    return run(at)


def _evidence_ids_shown(at):
    return list(at.tabs[3].dataframe[0].value[t("col_id")])


def _pane_text(at):
    pane = at.columns[1]
    return " ".join(e.value for kind in ("markdown", "caption", "warning", "info")
                    for e in getattr(pane, kind))


# --- pure helpers -------------------------------------------------------------

def test_evidence_rows_filter_to_the_given_ids(fake):
    ev = fake.evidence(SNAPSHOT)
    ids = [ev.datapoints[3].id, ev.datapoints[7].id, "Enotthere"]
    rows = views.evidence_rows(ev, ids)
    assert [r[t("col_id")] for r in rows] == sorted(ids[:2])
    assert len(views.evidence_rows(ev)) == len(ev.datapoints)


def test_evidence_row_has_fund_name_value_unit_and_flag_badges(fake):
    ev = fake.evidence(SNAPSHOT)
    dp = next(d for d in ev.datapoints if d.entity in ev.entities and d.flags)
    row = views.evidence_rows(ev, [dp.id])[0]
    assert ev.entities[dp.entity].name in row[t("col_entity")]
    assert dp.unit in row[t("col_value")]
    for f in dp.flags:
        assert f"badge[{f.value}]" in row[t("col_flags")]
    assert row[t("col_url")] == dp.source_url


def test_citations_name_each_used_source_once(fake):
    r = fake.decide(next(p for p in fake.list_personas() if p.persona_id == "P02"), SNAPSHOT)
    ev = fake.evidence(SNAPSHOT)
    cites = views.citations(r, ev)
    assert cites == [t("cite_evds"), t("cite_manual_ing", as_of="2026-10-09"), t("cite_tefas")]
    cut = fake.evidence(SNAPSHOT, frozenset({"tefas_web"}))
    assert t("cite_tefas") not in views.citations(r, cut)


# --- page ---------------------------------------------------------------------

def test_an_evidence_button_opens_the_tab_filtered_to_its_ids():
    at = _p("P02")
    r = at.session_state["result"]
    o = r.options[1]
    at.button(key=f"ev:opt:{o.option.option_id}").click()
    run(at)
    assert at.session_state[f"tabs:TR"] == EVIDENCE_TAB
    ids = set(o.evidence_ids) | {i for c in o.constraints for i in c.evidence_ids}
    assert set(_evidence_ids_shown(at)) == ids
    at.button(key="ev_all").click()
    run(at)
    assert set(_evidence_ids_shown(at)) == set(r.evidence_ids())


def test_whole_evidence_set_switch(fake):
    at = _p("P02")
    at.toggle(key="ev_whole").set_value(True)
    run(at)
    assert len(_evidence_ids_shown(at)) == len(fake.evidence(SNAPSHOT).datapoints)


def test_evidence_tab_drops_rows_of_excluded_sources():
    at = _p("P02")
    at.toggle(key="ev_whole").set_value(True)
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    ev = at.session_state["backend"].evidence(SNAPSHOT)
    assert len(_evidence_ids_shown(at)) == sum(d.source != "tefas" for d in ev.datapoints)


def test_evidence_tab_works_when_input_is_needed():
    at = run(app_test())
    r = at.session_state["result"]
    assert set(_evidence_ids_shown(at)) == set(r.evidence_ids())


@pytest.mark.parametrize("pid", ["P01", "P02", "P03"])
def test_every_warning_note_and_assumption_is_in_the_pane(pid):
    at = _p(pid)
    r = at.session_state["result"]
    text = _pane_text(at)
    for w in r.warnings:
        assert w.message in text
    for n in r.data_quality:
        assert n.message in text
    for a in r.assumptions:
        assert a in text


def test_warning_names_its_options_and_has_an_evidence_button():
    at = _p("P02")
    r = at.session_state["result"]
    text = _pane_text(at)
    labels = {o.option.option_id: o.option.label for o in r.options}
    for i, w in enumerate(r.warnings):
        for oid in w.option_ids:
            assert labels[oid] in text
        assert any(b.key == f"ev:warn:{i}" for b in at.button) == bool(w.evidence_ids)


def test_the_warning_marker_of_a_row_opens_its_warning_in_the_pane():
    at = _p("P02")
    r = at.session_state["result"]
    fx = next(o for o in r.options if o.option.fx).option.option_id
    i = next(i for i, w in enumerate(r.warnings) if fx in w.option_ids)
    at.button(key=f"warn:{fx}:{i}").click()
    run(at)
    assert at.session_state["warn_open"] == (r.run_id, i)
    pane_exp = at.columns[1].expander
    assert [e.proto.expanded for e in pane_exp[:len(r.warnings)]] == [j == i for j in range(len(r.warnings))]


def test_citations_are_in_the_footer():
    at = _p("P02")
    captions = [c.value for c in at.caption]
    assert t("cite_evds") in captions and t("cite_tefas") in captions
