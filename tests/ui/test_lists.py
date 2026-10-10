import dataclasses
import json
import math

import pytest
import yaml

from rmprep.contracts import DecisionResult, DecisionState, RmStatus, ScoredOption
from rmprep.grouping import DEFAULT_RULE, groups
from rmprep.ui import views
from rmprep.ui.fake import FakeBackend
from rmprep.ui.i18n import LABELS, LANGS, t
from tests.ui.conftest import CONTRACT_FIX, app_test, run

READY_FIXTURES = ["decision_p02_ready.json", "decision_p03_ready.json"]
CONFIG = CONTRACT_FIX.parents[2] / "config" / "decision.yaml"


def _fixture(name: str) -> DecisionResult:
    return DecisionResult.from_dict(json.loads((CONTRACT_FIX / name).read_text(encoding="utf-8")))


def _fund(base: ScoredOption, i: int, kind: str, score: float) -> ScoredOption:
    opt = dataclasses.replace(base.option, option_id=f"fund:K{i:02d}", entity=f"K{i:02d}",
                              label=f"FON {i:02d} {kind}", fund_kind=kind, fx=False)
    return ScoredOption(opt, score, {"return": score}, base.constraints, 0.9, 1.0,
                        base.evidence_ids, {"return": f"getiri {i}"})


def _grouped(spec) -> DecisionResult:
    """P02 with the deposit baseline, then one fund per (kind, score) in display order."""
    r = _fixture("decision_p02_ready.json")
    funds = [_fund(r.options[1], i, k, s) for i, (k, s) in enumerate(spec)]
    return dataclasses.replace(r, options=(r.options[0], *funds),
                               warnings=tuple(w for w in r.warnings if not w.option_ids))


def _ids(options):
    return [o.option.option_id for o in options]


# --- pure helpers -------------------------------------------------------------

def test_baseline_is_the_first_deposit():
    r = _fixture("decision_p02_ready.json")
    assert views.baseline(r) is r.options[0]
    assert views.ranked(r) == r.options[1:]
    no_dep = dataclasses.replace(r, options=r.options[1:])
    assert views.baseline(no_dep) is None
    assert views.ranked(no_dep) == r.options[1:]


def test_groups_of_the_p02_fixture():
    r = _fixture("decision_p02_ready.json")
    gs = groups(r.options)
    assert [g.key for g in gs] == ["debt", "money_market", "variable"]
    debt = gs[0]
    assert debt.head.option.option_id == "fund:BBF"
    assert _ids(debt.alternatives) == ["fund:AKE"] and len(debt.alternatives) == 1


def test_pool_is_the_first_20_non_deposit_options():
    spec = [("debt", 1.0 - i / 100) for i in range(DEFAULT_RULE.pool)] + [("equity", 5.0)]
    gs = groups(_grouped(spec).options)
    assert [g.key for g in gs] == ["debt"]
    assert 1 + len(gs[0].alternatives) == DEFAULT_RULE.pool


def test_at_most_5_groups_ordered_by_their_best_score():
    kinds = ["money_market", "debt", "participation", "precious_metals", "equity", "variable", "mixed"]
    spec = [(k, 0.1 * (i + 1)) for i, k in enumerate(kinds)]
    gs = groups(_grouped(spec).options)
    assert len(gs) == DEFAULT_RULE.max_groups
    assert [g.key for g in gs] == ["mixed", "variable", "equity", "precious_metals",
                                        "participation"]


def test_equal_best_scores_are_ordered_by_option_id():
    gs = groups(_grouped([("equity", 0.5), ("debt", 0.5)]).options)
    assert [g.head.option.option_id for g in gs] == ["fund:K00", "fund:K01"]


def test_head_is_the_best_of_its_kind_and_alternatives_follow_by_score():
    r = _grouped([("debt", 0.3), ("debt", 0.5), ("debt", 0.1), ("debt", 0.4)])
    g = groups(r.options)[0]
    assert g.head.option.option_id == "fund:K01"
    assert _ids(g.alternatives) == ["fund:K03", "fund:K00", "fund:K02"]


def test_shown_options_are_baseline_heads_and_visible_alternatives():
    r = _grouped([("debt", 0.9 - i / 10) for i in range(6)] + [("equity", 0.2)])
    shown = views.shown_options(r)
    assert _ids(shown) == ["deposit:ing_turuncu", "fund:K00", "fund:K01", "fund:K02", "fund:K03",
                           "fund:K06"]
    opened = views.shown_options(r, frozenset({"debt"}))
    assert _ids(opened) == ["deposit:ing_turuncu", *[f"fund:K{i:02d}" for i in range(7)]]


def test_positions_count_the_ranked_options_from_1():
    r = _fixture("decision_p02_ready.json")
    pos = views.positions(r)
    assert pos["fund:BBF"] == 1 and pos["fund:ABU"] == 4 and "deposit:ing_turuncu" not in pos


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


def test_every_fund_kind_has_a_kind_label_in_tr_and_en():
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    kinds = {k for k in raw["fund_kinds"].values() if k} | {"deposit"}
    for k in kinds:
        assert set(LABELS[f"kind.{k}"]) == set(LANGS)
    assert views.kind_name("money_market") == "Para Piyasası"
    assert views.kind_name("money_market", "EN") == "Money market"
    assert views.kind_name("new_kind") == "new_kind"


# --- page ---------------------------------------------------------------------

BIG = [("debt", 0.9 - i / 100) for i in range(8)] + [("money_market", 0.95), ("money_market", 0.5),
                                                     ("equity", 0.3)]


def _app(result=None):
    backend = FakeBackend(CONTRACT_FIX, results=[result]) if result else None
    at = run(app_test(backend))
    at.selectbox(key="persona").set_value("P02")
    return run(at)


def _rows(at):
    return [e.label for e in at.tabs[0].expander]


def test_shortlist_pins_the_baseline_then_shows_one_block_per_kind():
    at = _app(_grouped(BIG))
    rows = _rows(at)
    assert rows[0].startswith(t("baseline"))
    headers = [m.value for m in at.tabs[0].markdown if m.value.startswith("####")]
    assert headers == [f"#### {t('group_header', label='Para Piyasası', n=2)}",
                       f"#### {t('group_header', label='Borçlanma Araçları', n=8)}",
                       f"#### {t('group_header', label='Hisse Senedi', n=1)}"]
    # baseline + mm (head + 1) + debt (head + 3) + equity (head)
    assert len(rows) == 1 + 2 + 4 + 1
    assert rows[1].startswith("9. FON 08") and rows[2].startswith("↳ 10. FON 09")
    assert [b.key for b in at.button if b.key.startswith("more")] == ["more:debt"]


def test_more_shows_all_alternatives_of_one_kind_and_resets_on_a_new_run():
    at = _app(_grouped(BIG))
    at.button(key="more:debt").click()
    run(at)
    assert len(_rows(at)) == 1 + 2 + 8 + 1
    assert not any(b.key.startswith("more") for b in at.button)
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    assert len(_rows(at)) == 1 + 2 + 4 + 1


def test_options_outside_the_pool_are_only_in_all_scored():
    spec = [("debt", 1.0 - i / 100) for i in range(DEFAULT_RULE.pool)] + [("equity", 5.0)]
    at = _app(_grouped(spec))
    assert not any("FON 20" in label for label in _rows(at))
    assert len(at.tabs[1].dataframe[0].value) == len(spec) + 1


def test_row_shows_kind_fx_score_confidence_stability_and_warning_marker():
    at = _app()
    r = at.session_state["result"]
    rows = _rows(at)
    fx = next(o for o in r.options if o.option.fx)
    fx_row = next(x for x in rows if fx.option.label in x)
    assert "FX" in fx_row and "⚠" in fx_row and fx_row.startswith("↳ ")
    o = r.options[1]
    row = next(x for x in rows if o.option.label in x)
    assert "⚠" not in row and "Borçlanma Araçları" in row
    assert f"{o.score:.2f}" in row and f"{o.confidence:.2f}" in row and f"{o.stability:.2f}" in row


def test_expanded_row_lists_reasons_constraints_and_evidence():
    at = _app()
    r = at.session_state["result"]
    o = r.options[1]
    row = next(e for e in at.tabs[0].expander if o.option.label in e.label)
    text = " ".join(m.value for m in row.markdown) + " ".join(c.value for c in row.caption)
    for reason in o.reasons.values():
        assert reason in text
    for c in o.constraints:
        assert c.reason in text
    for eid in o.evidence_ids:
        assert eid in text


def test_heads_and_alternatives_can_be_selected_and_approved():
    at = _app(_grouped(BIG))
    r = at.session_state["result"]
    keys = [c.key for c in at.checkbox if c.key.startswith("sel:")]
    assert keys == [f"sel:{r.run_id}:{oid}" for oid in _ids(views.shown_options(r))]
    head, alt = "fund:K08", "fund:K01"
    at.checkbox(key=f"sel:{r.run_id}:{head}").check()
    at.checkbox(key=f"sel:{r.run_id}:{alt}").check()
    at.button(key="approve").click()
    run(at)
    a = at.session_state["result"]
    assert a.rm_status == RmStatus.APPROVED and set(a.rm_selected) == {head, alt}


def test_all_scored_tab_has_every_option_and_filters_by_kind():
    at = _app(_grouped(BIG))
    r = at.session_state["result"]
    assert len(at.tabs[1].dataframe[0].value) == len(BIG) + 1
    at.multiselect(key="kind_filter").set_value(["debt"])
    run(at)
    n_debt = sum(o.option.fund_kind == "debt" for o in r.options)
    assert len(at.tabs[1].dataframe[0].value) == n_debt > 0


def test_rejected_tab_shows_each_failed_rule_and_reason():
    at = _app()
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


def test_the_ui_has_no_local_grouping_rule():
    for name in ("kind_groups", "kind_key", "KindGroup", "POOL_SIZE", "MAX_GROUPS", "ALTERNATIVES",
                 "visible_alternatives"):
        assert not hasattr(views, name), name


def test_shortlist_blocks_follow_the_shared_rule():
    r = _grouped(BIG)
    at = _app(r)
    headers = [m.value for m in at.tabs[0].markdown if m.value.startswith("####")]
    gs = groups(r.options)
    assert headers == [f"#### {t('group_header', label=views.kind_name(g.key), n=1 + len(g.alternatives))}"
                       for g in gs]
