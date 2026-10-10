"""U10: one line per hard rule above the short list, "Elenenler" filtered by rule,
rule labels on rejected rows, and the q:override:fx_limit question (D12/D13)."""

import dataclasses
import json

import pytest

from rmprep.contracts import (
    ClarificationQuestion,
    ConstraintResult,
    DecisionResult,
    DecisionState,
    RejectedOption,
)
from rmprep.ui import views
from rmprep.ui.fake import FakeBackend
from rmprep.ui.i18n import t
from tests.ui.conftest import CONTRACT_FIX, app_test, run

Q_FX = "q:override:fx_limit"
LIFT = "gerekçeyle kaldır"
FX_ID = "fund:AKE"
REASONS = {
    "not_buyable": "TEFAS'ta alıma kapalı.",
    "risk_ceiling": "Risk değeri 6, müşterinin risk tavanı 5 üzerinde.",
    "fx_limit": "Döviz fonu; açık kısıt: döviz maruziyetini gerekçesiz artırmama.",
    "liquidity_need": "Satış valörü 5 gün; açık kısıt 3 gün.",
}


def _p02() -> DecisionResult:
    return DecisionResult.from_dict(json.loads(
        (CONTRACT_FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))


def _rejected(base, i, *rules):
    opt = dataclasses.replace(base.option, option_id=f"fund:R{i:02d}", entity=f"R{i:02d}",
                              label=f"ELENEN {i:02d}")
    return RejectedOption(opt, tuple(ConstraintResult(rule, False, REASONS[rule]) for rule in rules))


def _with_rules() -> DecisionResult:
    """P02: 3 not buyable (one of them also above the ceiling), 2 more above the
    ceiling, the FX fund rejected by fx_limit, 1 by liquidity_need; the
    non-blocking override question is open."""
    r = _p02()
    base = r.rejected[0]
    fx = next(o for o in r.options if o.option.option_id == FX_ID)
    rejected = (
        _rejected(base, 0, "not_buyable"),
        _rejected(base, 1, "not_buyable", "risk_ceiling"),
        _rejected(base, 2, "not_buyable"),
        _rejected(base, 3, "risk_ceiling"),
        _rejected(base, 4, "risk_ceiling"),
        RejectedOption(fx.option, (ConstraintResult("fx_limit", False, REASONS["fx_limit"]),)),
        _rejected(base, 5, "liquidity_need"),
    )
    q = ClarificationQuestion(Q_FX, "Döviz fonları müşterinin açık kısıtı nedeniyle elendi. "
                              "Kısıt gerekçeyle kaldırılsın mı?",
                              "Kısıt \"gerekçesiz\" diyor; RM gerekçe yazarak kaldırabilir.",
                              "acik_kisitlar[0]", ("uygula", LIFT), blocking=False)
    return dataclasses.replace(r, options=tuple(o for o in r.options if o.option.option_id != FX_ID),
                               rejected=rejected, questions=(q,))


class OverrideBackend(FakeBackend):
    """Like the engine (D13): with LIFT, the FX fund comes back as a scored option."""

    def answer_question(self, run_id, question_id, answer):
        new = super().answer_question(run_id, question_id, answer)
        if question_id != Q_FX or answer != LIFT:
            return new
        fx = next(o for o in _p02().options if o.option.option_id == FX_ID)
        lifted = dataclasses.replace(
            new, options=(*new.options, fx),
            rejected=tuple(x for x in new.rejected if x.option.option_id != FX_ID),
            assumptions=(*new.assumptions, "RM döviz fonları kısıtını gerekçeyle kaldırdı."))
        self._runs[lifted.run_id] = (lifted, self._runs[new.run_id][1])
        return lifted


def _app(backend=None):
    at = run(app_test(backend or FakeBackend(CONTRACT_FIX, results=[_with_rules()])))
    at.selectbox(key="persona").set_value("P02")
    return run(at)


def _rule_buttons(at):
    return {b.key[len("rule:"):]: b.label for b in at.button if b.key.startswith("rule:")}


# --- pure helpers -------------------------------------------------------------

def test_rule_counts_count_each_option_once_per_failed_rule():
    r = _with_rules()
    assert views.rule_counts(r) == [("not_buyable", 3), ("risk_ceiling", 3), ("fx_limit", 1),
                                    ("liquidity_need", 1)]


def test_a_rule_failed_twice_by_one_option_counts_once():
    r = _p02()
    base = r.rejected[0]
    twice = RejectedOption(base.option, (base.failed[0], base.failed[0]))
    assert views.rule_counts(dataclasses.replace(r, rejected=(twice,))) == [("risk_ceiling", 1)]


def test_unknown_rules_come_last_by_name():
    r = _p02()
    base = r.rejected[0]
    odd = RejectedOption(base.option, (ConstraintResult("zzz", False, "x"),
                                       ConstraintResult("aaa", False, "y")))
    assert [k for k, _ in views.rule_counts(dataclasses.replace(r, rejected=(odd,)))] == ["aaa", "zzz"]


@pytest.mark.parametrize("rule, tr, en", [
    ("not_buyable", "189 fon alıma kapalı", "189 funds not buyable"),
    ("risk_ceiling", "189 fon risk tavanının üstünde", "189 funds above the risk ceiling"),
    ("fx_limit", "189 döviz fonu açık kısıt nedeniyle elendi",
     "189 FX funds excluded by an explicit constraint"),
    ("liquidity_need", "189 fon likidite kısıtı nedeniyle elendi",
     "189 funds excluded by the liquidity constraint"),
])
def test_rule_lines_in_tr_and_en(rule, tr, en):
    assert views.rule_line(rule, 189).startswith(tr)
    assert views.rule_line(rule, 189, "EN").startswith(en)


@pytest.mark.parametrize("rule, tr, en", [
    ("not_buyable", "Alıma kapalı", "Not buyable"),
    ("risk_ceiling", "Risk tavanı", "Risk ceiling"),
    ("fx_limit", "Döviz kısıtı", "FX constraint"),
    ("liquidity_need", "Likidite kısıtı", "Liquidity constraint"),
])
def test_rule_labels_in_tr_and_en(rule, tr, en):
    assert views.rule_label(rule) == tr and views.rule_label(rule, "EN") == en


def test_unknown_rule_has_a_generic_line_and_its_id_as_label():
    assert "new_rule" in views.rule_line("new_rule", 2) and "2" in views.rule_line("new_rule", 2)
    assert views.rule_label("new_rule") == "new_rule"


def test_rejected_with_rule_filters():
    r = _with_rules()
    assert len(views.rejected_with_rule(r, None)) == len(r.rejected)
    ids = [x.option.option_id for x in views.rejected_with_rule(r, "risk_ceiling")]
    assert ids == ["fund:R01", "fund:R03", "fund:R04"]


# --- page ---------------------------------------------------------------------

def test_one_line_per_rule_above_the_tabs():
    at = _app()
    lines = _rule_buttons(at)
    assert lines == {rule: views.rule_line(rule, n) for rule, n in views.rule_counts(_with_rules())}


def test_no_rule_lines_without_rejected_options():
    at = _app(FakeBackend(CONTRACT_FIX, results=[dataclasses.replace(_p02(), rejected=())]))
    assert _rule_buttons(at) == {}


def test_english_rule_lines():
    at = _app()
    at.radio(key="lang").set_value("EN")
    run(at)
    assert _rule_buttons(at)["not_buyable"] == views.rule_line("not_buyable", 3, "EN")


def test_clicking_a_line_opens_rejected_filtered_to_the_rule():
    at = _app()
    at.button(key="rule:risk_ceiling").click()
    run(at)
    assert at.session_state["tabs:TR"] == t("tab_rejected")
    labels = [e.label for e in at.tabs[2].expander]
    assert [x.split(" · ")[0] for x in labels] == ["ELENEN 01", "ELENEN 03", "ELENEN 04"]
    assert any(t("rej_filter", rule=t("rule.risk_ceiling"), n=3) in i.value for i in at.tabs[2].info)
    at.button(key="rej_all").click()
    run(at)
    assert len(at.tabs[2].expander) == len(_with_rules().rejected)


def test_rejected_rows_show_rule_labels_and_reasons():
    at = _app()
    tab = at.tabs[2]
    both = next(e for e in tab.expander if e.label.startswith("ELENEN 01"))
    assert "Alıma kapalı" in both.label and "Risk tavanı" in both.label
    text = " ".join(m.value for m in both.markdown)
    assert REASONS["not_buyable"] in text and REASONS["risk_ceiling"] in text
    assert "Alıma kapalı" in text and "Risk tavanı" in text


def test_filter_resets_on_a_new_run():
    at = _app()
    at.button(key="rule:fx_limit").click()
    run(at)
    assert len(at.tabs[2].expander) == 1
    at.checkbox(key="src:tefas").uncheck()
    run(at)
    assert len(at.tabs[2].expander) == len(_with_rules().rejected)


# --- q:override:fx_limit ----------------------------------------------------------

def test_override_question_is_shown_with_its_choices():
    at = _app()
    r = at.session_state["result"]
    assert r.state == DecisionState.READY
    assert at.radio(key=f"qv:{Q_FX}").options == ["uygula", LIFT]
    assert FX_ID not in {o.option.option_id for o in r.options}


def test_lifting_the_fx_constraint_brings_the_fx_funds_back():
    at = _app(OverrideBackend(CONTRACT_FIX, results=[_with_rules()]))
    first = at.session_state["result"]
    at.radio(key=f"qv:{Q_FX}").set_value(LIFT)
    at.button(key=f"qa:{Q_FX}").click()
    run(at)
    r = at.session_state["result"]
    assert r.run_id != first.run_id and r.questions[0].answer == LIFT
    assert FX_ID in {o.option.option_id for o in r.options}
    assert "fx_limit" not in _rule_buttons(at)
    fx_label = next(o.option.label for o in r.options if o.option.option_id == FX_ID)
    assert any(fx_label in e.label for e in at.tabs[0].expander)
    assert at.session_state["history"][-1]["change"].startswith("yanıt: q:override:")


def test_keeping_the_fx_constraint_keeps_the_fx_funds_out():
    at = _app(OverrideBackend(CONTRACT_FIX, results=[_with_rules()]))
    at.radio(key=f"qv:{Q_FX}").set_value("uygula")
    at.button(key=f"qa:{Q_FX}").click()
    run(at)
    r = at.session_state["result"]
    assert FX_ID not in {o.option.option_id for o in r.options}
    assert _rule_buttons(at)["fx_limit"] == views.rule_line("fx_limit", 1)
