import dataclasses
import json
import math

import pytest

from rmprep.contracts import DecisionResult, DecisionState
from rmprep.ui import views
from rmprep.ui.fake import FakeBackend
from tests.ui.conftest import CONTRACT_FIX, app_test, run

READY_FIXTURES = ["decision_p02_ready.json", "decision_p03_ready.json"]
N_RANKED = 25


def _fixture(name: str) -> DecisionResult:
    return DecisionResult.from_dict(json.loads((CONTRACT_FIX / name).read_text(encoding="utf-8")))


def _big() -> DecisionResult:
    """P02 with N_RANKED options after the deposit baseline (clones of its funds)."""
    r = _fixture("decision_p02_ready.json")
    funds = list(r.options[1:])
    i = 0
    while len(funds) < N_RANKED:
        src = r.options[1 + i % (len(r.options) - 1)]
        opt = dataclasses.replace(src.option, option_id=f"fund:X{i:02d}", entity=f"X{i:02d}",
                                  label=f"{src.option.label} #{i}")
        funds.append(dataclasses.replace(src, option=opt))
        i += 1
    return dataclasses.replace(r, options=(r.options[0], *funds))


def _app_with_big():
    at = run(app_test(FakeBackend(CONTRACT_FIX, results=[_big()])))
    at.selectbox(key="persona").set_value("P02")
    return run(at)


def _ranked_rows(at):
    base = views_label("baseline")
    return [e for e in at.tabs[0].expander if not e.label.startswith(base)]


def views_label(key):
    from rmprep.ui.i18n import t
    return t(key)


# --- pure helpers -------------------------------------------------------------

def test_baseline_is_the_first_deposit():
    r = _fixture("decision_p02_ready.json")
    assert views.baseline(r) is r.options[0]
    assert views.ranked(r) == r.options[1:]
    no_dep = dataclasses.replace(r, options=r.options[1:])
    assert views.baseline(no_dep) is None
    assert views.ranked(no_dep) == r.options[1:]


def test_page_steps_are_3_then_10_then_plus_10():
    steps = [views.FIRST_PAGE]
    for _ in range(3):
        steps.append(views.next_count(steps[-1]))
    assert steps == [3, 10, 20, 30]


@pytest.mark.parametrize("name", READY_FIXTURES)
def test_bars_add_up_to_the_score(name):
    for o in _fixture(name).options:
        bars = views.part_rows(o)
        assert [b["key"] for b in bars] == list(o.score_parts)
        assert math.isclose(sum(b["value"] for b in bars), o.score, abs_tol=1e-9)
        for b in bars:
            assert b["reason"] == o.reasons[b["key"]]
            if b["key"].startswith("penalty:"):
                assert b["value"] < 0


def test_part_labels_name_the_penalty_rule():
    assert views.part_label("return") == "Getiri"
    assert "fx_exposure" in views.part_label("penalty:fx_exposure")
    assert views.part_label("unknown_part") == "unknown_part"


def test_warned_maps_option_ids_to_their_warnings():
    r = _fixture("decision_p02_ready.json")
    w = views.warned(r)
    fx = next(o for o in r.options if o.option.fx).option.option_id
    assert [x.code for x in w[fx]] == ["fx_exposure"]
    assert r.options[0].option.option_id not in w


def test_kind_filter_keys():
    r = _fixture("decision_p02_ready.json")
    assert views.kind_keys(r.options) == ["debt", "deposit", "money_market", "variable"]


# --- page ---------------------------------------------------------------------

def test_shortlist_pins_the_baseline_and_grows_3_10_20_25():
    at = _app_with_big()
    tab = at.tabs[0]
    assert tab.expander[0].label.startswith(views_label("baseline"))
    counts = [len(_ranked_rows(at))]
    while any(b.key == "more" for b in at.button):
        at.button(key="more").click()
        run(at)
        counts.append(len(_ranked_rows(at)))
    assert counts == [3, 10, 20, 25]
    labels = [e.label for e in _ranked_rows(at)]
    assert labels[0].startswith("1.") and labels[-1].startswith(f"{N_RANKED}.")


def test_shown_count_resets_on_a_new_run():
    at = _app_with_big()
    at.button(key="more").click()
    run(at)
    assert len(_ranked_rows(at)) == 10
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    assert len(_ranked_rows(at)) == 3


def test_row_shows_kind_fx_score_confidence_stability_and_warning_marker():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    labels = [e.label for e in at.tabs[0].expander]
    fx = next(i for i, o in enumerate(r.options) if o.option.fx)
    assert "FX" in labels[fx] and "⚠" in labels[fx]
    assert "⚠" not in labels[1]
    o = r.options[1]
    assert f"{o.score:.2f}" in labels[1] and f"{o.confidence:.2f}" in labels[1]
    assert f"{o.stability:.2f}" in labels[1]


def test_expanded_row_lists_reasons_constraints_and_evidence():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    o = r.options[1]
    row = at.tabs[0].expander[1]
    text = " ".join(m.value for m in row.markdown) + " ".join(c.value for c in row.caption)
    for reason in o.reasons.values():
        assert reason in text
    for c in o.constraints:
        assert c.reason in text
    for eid in o.evidence_ids:
        assert eid in text


def test_all_scored_tab_has_every_option_and_filters_by_kind():
    at = _app_with_big()
    r = at.session_state["result"]
    assert len(at.tabs[1].dataframe[0].value) == N_RANKED + 1
    at.multiselect(key="kind_filter").set_value(["debt"])
    run(at)
    n_debt = sum(o.option.fund_kind == "debt" for o in r.options)
    assert len(at.tabs[1].dataframe[0].value) == n_debt > 0


def test_rejected_tab_shows_each_failed_rule_and_reason():
    at = run(app_test())
    at.selectbox(key="persona").set_value("P02")
    run(at)
    r = at.session_state["result"]
    tab = at.tabs[2]
    assert len(tab.expander) == len(r.rejected) == 1
    text = " ".join(m.value for m in tab.markdown)
    for c in r.rejected[0].failed:
        assert c.rule_id in text and c.reason in text


def test_needs_input_tabs_ask_for_answers_first():
    at = run(app_test())
    r = at.session_state["result"]
    assert r.state == DecisionState.NEEDS_RM_INPUT
    for tab in at.tabs[:3]:
        assert not tab.expander and not tab.dataframe
        assert any("yanıtlayın" in i.value for i in tab.info)
