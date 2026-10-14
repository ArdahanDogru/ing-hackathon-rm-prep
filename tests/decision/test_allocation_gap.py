"""The allocation gap and the criterion allocation_gap (docs/decision.md section 17,
D27; spec docs/superpowers/specs/2026-10-14-portfolio-projection-design.md section 5)."""

import dataclasses

import pytest

from rmprep.contracts import ALLOCATION_CLASSES, HoldingsInput
from rmprep.decision.config import parse_config
from rmprep.decision.confidence import stability
from rmprep.decision.engine import config_hash, decide, run_id
from rmprep.decision.holdings import (
    class_gap,
    estimate,
    gap_value,
    gap_weight_factor,
    with_gap,
)
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import option_features, penalty_maxima, raw_weights
from rmprep.decision.universe import build_universe
from tests.decision.conftest import T0, load_persona
from tests.decision.test_allocation import _ev as _al_ev
from tests.decision.test_diverse import BASE, FUNDS
from tests.decision.test_holdings import D27_TEXTS, add_d27, strip_d27

TO_CONFIRM = D27_TEXTS["holdings"]["to_confirm"]
# + a debt fund of risk 2, so that P01 (ceiling 2) has a borclanma option
GAP_FUNDS = {**FUNDS, "DBT": dict(kind="debt", name="J PORTFÖY BORÇLANMA ARAÇLARI FONU", risk=2,
                                  returns={"1y": 40.0, "3y": 160.0}, **BASE)}


def _ev():
    return _al_ev(GAP_FUNDS)


@pytest.fixture
def d27_raw(d19_raw) -> dict:
    return add_d27(d19_raw)


@pytest.fixture
def cfg(d27_raw):
    return parse_config(d27_raw)


@pytest.fixture
def old(d27_raw):
    """The same config without the D27 keys."""
    return parse_config(strip_d27(d27_raw))


def _p(pid, **changes):
    return dataclasses.replace(load_persona(pid), **changes)


def _h(n, b, h, a, d, origin="rm"):
    return HoldingsInput(dict(zip(ALLOCATION_CLASSES, (n, b, h, a, d))), origin)


def _summary(r):
    return ([(o.option.option_id, o.score, o.score_parts, o.reasons, o.stability)
             for o in r.options], r.recommended, [x.option.option_id for x in r.rejected],
            r.warnings)


def _rank(r, cls):
    """Place (1-based, display order) of the best option of a class."""
    ranked = [o for o in r.options if o.option.kind != "deposit"]
    return next(i for i, o in enumerate(ranked, 1) if o.option.asset_class == cls)


# --- gap and value --------------------------------------------------------------------------

@pytest.mark.parametrize("point, band, gap", [(10, (70, 85), 60), (90, (70, 85), -5),
                                              (75, (70, 85), 0), (70, (70, 85), 0),
                                              (85, (70, 85), 0), (50, None, None)])
def test_class_gap(point, band, gap):
    assert class_gap(point, band) == gap


def test_gap_value_scale_and_overweight(cfg):     # scale 30, overweight 0.5
    assert gap_value(60, True, cfg) == 1.0
    assert gap_value(15, True, cfg) == 0.5
    assert gap_value(-30, True, cfg) == -0.5
    assert gap_value(-90, True, cfg) == -0.5
    assert gap_value(60, False, cfg) == 0.0
    assert gap_value(None, True, cfg) == 0.0


def test_signals_raise_the_weight(cfg):
    # P04: "çeşitlendirme" and "tek ürün veya tek varlık sınıfında yoğunlaşmama"
    p = _p("P04", durum="Varlığı mevduat ağırlıklı")
    est = estimate(p, cfg, None)
    assert gap_weight_factor(p, est, cfg) == pytest.approx(0.75 * 2.0)
    # P01: one signal in rm_notu ("mevduat yoğunluğunu azalt...")
    p1 = load_persona("P01")
    assert gap_weight_factor(p1, estimate(p1, cfg, None), cfg) == pytest.approx(0.75 * 1.5)
    # RM input: source factor 1.0
    assert gap_weight_factor(p1, estimate(p1, cfg, _h(20, 60, 10, 10, 0)), cfg) == \
        pytest.approx(1.0 * 1.5)


def test_signals_are_capped(d27_raw):
    d27_raw["allocation_gap"]["max_signals"] = 1
    cfg = parse_config(d27_raw)
    p = _p("P04", durum="Varlığı mevduat ağırlıklı")
    assert gap_weight_factor(p, estimate(p, cfg, None), cfg) == pytest.approx(0.75 * 1.5)


def test_no_active_class_gives_weight_0(cfg):
    p = load_persona("P05")
    assert gap_weight_factor(p, estimate(p, cfg, None), cfg) == 0.0


# --- the criterion in decide ------------------------------------------------------------------

@pytest.mark.parametrize("pid", ["P02", "P04", "P05"])
def test_no_active_class_no_criterion(cfg, old, pid):
    a = decide(_ev(), load_persona(pid), cfg, created_at=T0)
    b = decide(_ev(), load_persona(pid), old, created_at=T0)
    assert all("allocation_gap" not in o.score_parts for o in a.options)
    assert _summary(a) == _summary(b)           # same options, scores, order and stability
    assert "allocation_gap" not in a.effective_weights


def test_p01_cash_down_debt_up(cfg, old):
    a = decide(_ev(), load_persona("P01"), cfg, created_at=T0)
    b = decide(_ev(), load_persona("P01"), old, created_at=T0)
    by_id = {o.option.option_id: o for o in a.options}
    cash = [o for o in a.options if o.option.asset_class == "nakit_benzeri"]
    assert cash and all(o.score_parts["allocation_gap"] < 0 for o in cash)
    assert _rank(a, "borclanma") <= _rank(b, "borclanma")
    old_score = {o.option.option_id: o.score for o in b.options}
    assert all(by_id[o.option.option_id].score < old_score[o.option.option_id] for o in cash)


def test_rm_input_hisse_gap_lifts_equity(cfg, old):
    p = load_persona("P03")
    a = decide(_ev(), p, cfg, created_at=T0, holdings=_h(80, 5, 10, 5, 0))
    b = decide(_ev(), p, old, created_at=T0)
    assert _rank(a, "hisse") <= _rank(b, "hisse")
    hisse = [o for o in a.options if o.option.asset_class == "hisse"]
    assert hisse and all(o.score_parts["allocation_gap"] > 0 for o in hisse)
    assert a.holdings_input == _h(80, 5, 10, 5, 0)


def test_hard_rules_unchanged(cfg, old):
    for pid, h in (("P01", None), ("P01", _h(0, 0, 100, 0, 0)), ("P03", _h(80, 5, 10, 5, 0))):
        a = decide(_ev(), load_persona(pid), cfg, created_at=T0, holdings=h)
        b = decide(_ev(), load_persona(pid), old, created_at=T0)
        assert [(x.option.option_id, x.failed) for x in a.rejected] == \
            [(x.option.option_id, x.failed) for x in b.rejected]


def test_reason_texts(cfg):
    r = decide(_ev(), load_persona("P01"), cfg, created_at=T0)
    cash = next(o for o in r.options if o.option.asset_class == "nakit_benzeri"
                and o.option.kind == "fund")
    assert cash.reasons["allocation_gap"] == ("Nakit benzeri payı persona metnine göre %75; "
                                              "Muhafazakâr model bandı %10–20.")
    debt = next(o for o in r.options if o.option.asset_class == "borclanma")
    assert debt.reasons["allocation_gap"] == ("Borçlanma araçları payı bilinmiyor (tahmini "
                                              "senaryo); RM onayı bekleniyor.")
    assert set(cash.reasons) == set(cash.score_parts)


def test_reason_for_a_class_without_band(cfg):
    r = decide(_ev(), load_persona("P03"), cfg, created_at=T0, holdings=_h(80, 5, 5, 5, 5))
    mixed = [o for o in r.options if o.option.asset_class == "dengeli"]
    assert mixed and mixed[0].reasons["allocation_gap"].startswith("Dengeli fon için model bandı")
    assert mixed[0].score_parts["allocation_gap"] == 0.0


def test_stability_varies_the_new_weight(cfg):
    p = load_persona("P01")
    r = decide(_ev(), p, cfg, created_at=T0)
    lv = read_persona(p, cfg).levels
    lv = with_gap(lv, p, cfg, estimate(p, cfg, None))
    assert "allocation_gap" in raw_weights(lv, cfg)
    feats, _ = option_features(build_universe(_ev(), cfg), lv, cfg)
    n_runs = 2 * (len(raw_weights(lv, cfg)) + len(penalty_maxima(cfg)))
    s = stability(feats, lv, cfg)
    assert all(abs(v * n_runs - round(v * n_runs)) < 1e-9 for v in s.values())
    assert r.options


# --- run id, weights, to_confirm, allocation rows ----------------------------------------------

def test_run_id_unchanged_without_holdings(cfg):
    p = load_persona("P01")
    h = config_hash(cfg)
    base = run_id(h, p, "S", frozenset(), {})
    assert run_id(h, p, "S", frozenset(), {}, None) == base
    with_input = run_id(h, p, "S", frozenset(), {}, _h(20, 60, 10, 10, 0))
    assert with_input != base
    assert run_id(h, p, "S", frozenset(), {}, _h(20, 60, 10, 10, 0, "rm_confirmed")) != with_input


def test_reset_gives_the_original_run_id(cfg):
    p = load_persona("P01")
    a = decide(_ev(), p, cfg, created_at=T0)
    b = decide(_ev(), p, cfg, created_at=T0, holdings=_h(20, 60, 10, 10, 0))
    c = decide(_ev(), p, cfg, created_at=T0, holdings=None)
    assert a.run_id != b.run_id and a.run_id == c.run_id


def test_effective_weights_sum_to_one_and_name_criteria(cfg):
    r = decide(_ev(), load_persona("P01"), cfg, created_at=T0)
    w = r.effective_weights
    assert sum(w.values()) == pytest.approx(1.0)
    assert set(w) == set(cfg.criteria) | {"allocation_gap"}
    fund = next(o for o in r.options if o.option.kind == "fund")
    crits = [k for k in fund.score_parts if not k.startswith("penalty:")]
    assert set(crits) <= set(w)


def test_effective_weights_without_the_feature(old):
    r = decide(_ev(), load_persona("P01"), old, created_at=T0)
    assert set(r.effective_weights) == set(old.criteria)


def test_to_confirm_first_item_while_estimate(cfg):
    for pid in ("P01", "P05"):
        r = decide(_ev(), load_persona(pid), cfg, created_at=T0)
        assert r.to_confirm[0] == TO_CONFIRM
        assert "Mevcut portföy dağılımını sorun." not in r.to_confirm     # replaces D20's
    r = decide(_ev(), load_persona("P01"), cfg, created_at=T0, holdings=_h(20, 60, 10, 10, 0))
    assert TO_CONFIRM not in r.to_confirm


def test_blocked_result_has_the_item_too(cfg):
    r = decide(_ev(), _p("P01", risk_profili="?"), cfg, created_at=T0)
    assert r.to_confirm[0] == TO_CONFIRM and r.options == ()


def test_allocation_rows_carry_current_and_gap(cfg):
    r = decide(_ev(), load_persona("P01"), cfg, created_at=T0)
    rows = {b.asset_class: b for b in r.allocation}
    n = rows["nakit_benzeri"]
    assert (n.current, n.current_low, n.current_high) == (75.0, 60.0, 90.0)
    assert (n.current_source, n.current_ref, n.gap, n.active) == (
        "persona_text", "mevduat_agirlikli", -55.0, True)
    b = rows["borclanma"]
    assert b.current_source == "profile" and not b.active and b.current_ref == "Emekli"
    assert b.gap == pytest.approx(60 - b.current)
    assert rows["dengeli"].gap is None and rows["dengeli"].current is not None


def test_allocation_rows_with_rm_input(cfg):
    r = decide(_ev(), load_persona("P03"), cfg, created_at=T0, holdings=_h(80, 5, 10, 5, 0))
    rows = {b.asset_class: b for b in r.allocation}
    assert all(b.active and b.current_source == "rm" for b in rows.values())
    assert rows["hisse"].gap == 60.0 and rows["nakit_benzeri"].gap == -75.0


def test_without_config_rows_have_no_current(old):
    r = decide(_ev(), load_persona("P01"), old, created_at=T0)
    assert r.allocation and all(b.current is None and not b.active for b in r.allocation)


def test_deterministic(cfg):
    p = load_persona("P01")
    a = decide(_ev(), p, cfg, created_at=T0, holdings=_h(20, 60, 10, 10, 0))
    b = decide(_ev(), p, cfg, created_at=T0, holdings=_h(20, 60, 10, 10, 0))
    assert a.to_dict() == b.to_dict()


def test_change_signals_are_the_phrases_found(cfg):
    """2026-10-15: the phrases that raise the weight, for the explanation in the web app."""
    from rmprep.decision.holdings import change_signals
    p1 = load_persona("P01")
    assert change_signals(p1, cfg) == ("mevduat yoğunluğunu azalt",)
    assert gap_weight_factor(p1, estimate(p1, cfg, None), cfg) == pytest.approx(0.75 * 1.5)
