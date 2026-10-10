"""Contract v1.1: the ranked option kind "time_deposit" (ING e-Vadeli Mevduat),
with a hand-made template (tests/contracts/fixtures/ stay as they are)."""

import dataclasses
import json

from rmprep.contracts import DecisionResult, ProductOption, RmStatus, ScoredOption
from rmprep.ui import card, views
from rmprep.ui.fake import FakeBackend
from rmprep.ui.i18n import LABELS, LANGS, t
from tests.ui.conftest import CONTRACT_FIX, SNAPSHOT, app_test, run

TD_ID = "time_deposit:ing_e_vadeli"
TD_LABEL = "ING e-Vadeli Mevduat"
TD_ENTITY = "ING e-Vadeli Mevduat, 32 gün"


def _with_time_deposit() -> DecisionResult:
    """P02 with a time deposit ranked between its debt and money-market funds."""
    r = DecisionResult.from_dict(json.loads(
        (CONTRACT_FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))
    dep = r.options[0]
    parts = {"return": 0.2, "liquidity": 0.1, "income": 0.1, "principal": 0.015}
    td = ScoredOption(ProductOption(TD_ID, "time_deposit", TD_LABEL, TD_ENTITY),
                      sum(parts.values()), parts, (), 0.9, 1.0, dep.evidence_ids,
                      {k: f"(örnek) {k}" for k in parts})
    return dataclasses.replace(r, options=(dep, r.options[1], td, *r.options[2:]))


def _td(r):
    return next(o for o in r.options if o.option.option_id == TD_ID)


# --- pure helpers -------------------------------------------------------------

def test_time_deposit_has_its_own_kind_key_and_label():
    td = _td(_with_time_deposit())
    assert views.kind_key(td) == "time_deposit"
    assert views.kind_label(td) == "Vadeli mevduat"
    assert views.kind_label(td, "EN") == "Time deposit"
    assert set(LABELS["kind.time_deposit"]) == set(LANGS)


def test_time_deposit_is_ranked_not_the_baseline():
    r = _with_time_deposit()
    assert views.baseline(r).option.kind == "deposit"
    assert views.positions(r)[TD_ID] == 2


def test_time_deposit_is_its_own_group():
    groups = views.kind_groups(_with_time_deposit())
    assert [g.kind for g in groups] == ["debt", "time_deposit", "money_market", "variable"]
    td_group = groups[1]
    assert td_group.head.option.option_id == TD_ID and td_group.count == 1


def test_group_key_is_fund_kind_or_kind():
    r = _with_time_deposit()
    for g in views.kind_groups(r):
        for o in (g.head, *g.alternatives):
            assert g.kind == (o.option.fund_kind or o.option.kind)


def test_all_scored_rows_have_no_fund_only_fields():
    r = _with_time_deposit()
    assert "time_deposit" in views.kind_keys(r.options)
    rows = views.table_rows(r, ["time_deposit"])
    assert len(rows) == 1
    row = rows[0]
    assert row[t("col_kind")] == "Vadeli mevduat" and row["FX"] == ""
    assert TD_ENTITY not in json.dumps(row, ensure_ascii=False)


# --- page and card ----------------------------------------------------------------

def _app():
    at = run(app_test(FakeBackend(CONTRACT_FIX, results=[_with_time_deposit()])))
    at.selectbox(key="persona").set_value("P02")
    return run(at)


def test_shortlist_shows_the_time_deposit_as_a_group():
    at = _app()
    headers = [m.value for m in at.tabs[0].markdown if m.value.startswith("####")]
    assert f"#### {t('group_header', label='Vadeli mevduat', n=1)}" in headers
    row = next(e.label for e in at.tabs[0].expander if TD_LABEL in e.label)
    assert row.startswith("2. ") and "Vadeli mevduat" in row
    assert "FX" not in row and TD_ENTITY not in row and TD_ID not in row


def test_english_group_header():
    at = _app()
    at.radio(key="lang").set_value("EN")
    run(at)
    headers = [m.value for m in at.tabs[0].markdown if m.value.startswith("####")]
    assert f"#### {t('group_header', 'EN', label='Time deposit', n=1)}" in headers


def test_all_scored_filter_by_time_deposit():
    at = _app()
    at.multiselect(key="kind_filter").set_value(["time_deposit"])
    run(at)
    df = at.tabs[1].dataframe[0].value
    assert list(df[t("col_label")]) == [TD_LABEL]


def test_time_deposit_can_be_approved_and_is_on_the_card():
    at = _app()
    r = at.session_state["result"]
    at.checkbox(key=f"sel:{r.run_id}:{TD_ID}").check()
    at.button(key="approve").click()
    run(at)
    a = at.session_state["result"]
    assert a.rm_status == RmStatus.APPROVED and a.rm_selected == (TD_ID,)
    md = card.render_markdown(a, at.session_state["backend"].evidence(SNAPSHOT))
    line = next(x for x in md.splitlines() if TD_LABEL in x)
    assert "Vadeli mevduat" in line and "FX" not in line and TD_ENTITY not in md
