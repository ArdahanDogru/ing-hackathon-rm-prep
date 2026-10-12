"""Diverse recommendations: asset classes, risk fit, the recommended top 3
(docs/decision.md section 10, D19)."""

import copy
import dataclasses

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import option_features, raw_weights
from rmprep.decision.universe import build_universe
from rmprep.grouping import recommended, top_heads
from tests.decision.conftest import (
    D19_TEXTS,
    T0,
    d9_rows,
    load_persona,
    make_evidence,
    market_row,
)

BASE = dict(size=2e8, investors=500, buyable=1, sell_valor=1)
FUNDS = {
    # three cash-like funds with the best returns (the finding of section 10)
    "MMF": dict(kind="money_market", name="A PORTFÖY PARA PİYASASI (TL) FONU", risk=1,
                returns={"1y": 50.0, "3y": 200.0}, **BASE),
    "KVD": dict(kind="debt", name="B PORTFÖY KISA VADELİ BORÇLANMA ARAÇLARI FONU", risk=1,
                returns={"1y": 49.0, "3y": 195.0}, **BASE),
    "KAT": dict(kind="participation", name="C PORTFÖY PARA PİYASASI KATILIM FONU", risk=1,
                returns={"1y": 48.0, "3y": 190.0}, **BASE),
    # other classes, lower returns
    "UVD": dict(kind="debt", name="D PORTFÖY UZUN VADELİ BORÇLANMA ARAÇLARI FONU", risk=3,
                returns={"1y": 38.0, "3y": 150.0}, **BASE),
    "MIX": dict(kind="mixed", name="E PORTFÖY KARMA FON", risk=4,
                returns={"1y": 36.0, "3y": 140.0}, **BASE),
    "EQF": dict(kind="equity", name="F PORTFÖY HİSSE SENEDİ FONU", risk=5,
                returns={"1y": 34.0, "3y": 160.0}, **BASE),
    "GLD": dict(kind="precious_metals", name="G PORTFÖY ALTIN FONU", risk=4,
                returns={"1y": 20.0, "3y": 120.0}, **BASE),
    "FXD": dict(kind="debt", name="H PORTFÖY EUROBOND (DOLAR) BORÇLANMA ARAÇLARI FONU",
                risk=3, returns={"1y": 30.0, "3y": 110.0}, **BASE),
    "VAR": dict(kind="variable", name="I PORTFÖY DEĞİŞKEN FON", risk=4,
                returns={"1y": 33.0, "3y": 130.0}, **BASE),
}


def _ev(funds=FUNDS):
    return make_evidence(funds, time_deposit=35.0, extra=d9_rows() + [market_row()])


def _decide(cfg, pid, persona=None, funds=FUNDS):
    return decide(_ev(funds), persona or load_persona(pid), cfg, created_at=T0)


def _classes(r, ids):
    by_id = {o.option.option_id: o.option for o in r.options}
    return [by_id[i].asset_class for i in ids]


# --- config ---------------------------------------------------------------------------------

def test_d19_config_is_valid_and_optional(d19_config, config):
    assert d19_config.raw["risk_fit"]["per_step"] == 0.25
    for key in ("asset_classes", "risk_fit", "recommend"):
        assert key not in config.raw


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["asset_classes"]["by_kind"].pop("equity"), "asset_classes.by_kind"),
    (lambda r: r["asset_classes"]["by_kind"].update(gold="hisse"), "asset_classes.by_kind"),
    (lambda r: r["asset_classes"]["by_name"].update({"": "hisse"}), "asset_classes.by_name"),
    (lambda r: r["risk_fit"]["bands"].pop("Dengeli"), "risk_fit.bands"),
    (lambda r: r["risk_fit"]["bands"].update(Dengeli=[5, 3]), "risk_fit.bands"),
    (lambda r: r["risk_fit"]["bands"].update(Dengeli=[0, 5]), "risk_fit.bands"),
    (lambda r: r["risk_fit"].update(per_step=-0.1), "risk_fit.per_step"),
    (lambda r: r["weights"].update(low_risk={"base": 1.0}), "weights"),
    (lambda r: r["priorities"].update({"düzenli gelir": "boost:low_risk"}), "priorities"),
    (lambda r: r["texts"]["reasons"].pop("risk_fit"), "risk_fit"),
    (lambda r: r["recommend"].update(max_per_class=0), "recommend.max_per_class"),
    (lambda r: r["recommend"].update(cash_like="nakit"), "recommend.cash_like"),
    (lambda r: r["recommend"].update(profiles=["Cesur"]), "recommend.profiles"),
    (lambda r: r["texts"]["assumptions"].pop("class_rule"), "class_rule"),
])
def test_bad_d19_config_is_an_error(d19_raw, edit, match):
    edit(d19_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d19_raw)


# --- asset classes ------------------------------------------------------------------------------

def test_asset_classes(d19_config):
    u = build_universe(_ev(), d19_config)
    cls = {c.option.option_id: c.option.asset_class for c in u.candidates}
    assert cls["deposit:ing_turuncu"] == "nakit_benzeri"
    assert cls["time_deposit:ing_e_vadeli"] == "nakit_benzeri"
    assert cls["fund:MMF"] == "nakit_benzeri"
    assert cls["fund:KVD"] == "nakit_benzeri"           # debt kind, but "KISA VADELİ"
    assert cls["fund:KAT"] == "nakit_benzeri"           # participation, but "PARA PİYASASI"
    assert cls["fund:UVD"] == "borclanma"
    assert cls["fund:MIX"] == "dengeli" and cls["fund:VAR"] == "dengeli"
    assert cls["fund:EQF"] == "hisse" and cls["fund:GLD"] == "altin_doviz"
    assert cls["fund:FXD"] == "altin_doviz"             # an FX fund


def test_name_match_is_whole_words(d19_config):
    funds = {"X": dict(kind="debt", name="X PORTFÖY KISA VADELİLER FONU", risk=2,
                       returns={"1y": 30.0}, **BASE)}
    u = build_universe(_ev(funds), d19_config)
    assert u.by_id["fund:X"].option.asset_class == "borclanma"


def test_name_match_uses_turkish_upper_case(d19_config):
    funds = {"X": dict(kind="debt", name="x portföy kısa vadeli borçlanma fonu", risk=2,
                       returns={"1y": 30.0}, **BASE)}
    u = build_universe(_ev(funds), d19_config)
    assert u.by_id["fund:X"].option.asset_class == "nakit_benzeri"


def test_without_config_no_asset_class(d12_config):
    u = build_universe(_ev(), d12_config)
    assert {c.option.asset_class for c in u.candidates} == {""}


# --- risk fit -----------------------------------------------------------------------------------

def _features(cfg, pid, funds=FUNDS):
    lv = read_persona(load_persona(pid), cfg).levels
    feats, _ = option_features(build_universe(_ev(funds), cfg), lv, cfg)
    return {f.option.option_id: f for f in feats}


@pytest.mark.parametrize("code,value", [
    ("MMF", 0.5), ("UVD", 1.0), ("MIX", 1.0), ("EQF", 1.0),   # Dengeli band [3, 5]
])
def test_risk_fit_for_dengeli(d19_config, code, value):
    f = _features(d19_config, "P04")[f"fund:{code}"]
    assert f.values["risk_fit"] == value
    assert "low_risk" not in f.values


def test_risk_fit_of_the_deposit_and_muhafazakar(d19_config):
    assert _features(d19_config, "P04")["deposit:ing_turuncu"].values["risk_fit"] == 0.5
    assert _features(d19_config, "P01")["fund:MMF"].values["risk_fit"] == 1.0   # band [1, 2]


def test_risk_fit_weight_and_boosts(d19_config):
    lv = read_persona(load_persona("P01"), d19_config).levels    # sınırlı dalgalanma
    raw = raw_weights(lv, d19_config)
    assert "low_risk" not in raw
    assert raw["risk_fit"] == 1.0 + 1.0                          # base + one boost


def test_inside_the_band_beats_an_equal_fund_below_it(d19_config):
    same = dict(kind="equity", returns={"1y": 30.0, "3y": 100.0}, **BASE)
    funds = {"IN4": dict(same, risk=4), "LO3": dict(same, risk=3)}
    r = _decide(d19_config, "P03", funds=funds)               # Agresif: band [4, 7]
    score = {o.option.option_id: o.score for o in r.options}
    assert score["fund:IN4"] > score["fund:LO3"]
    lo3 = next(o for o in r.options if o.option.option_id == "fund:LO3")
    assert lo3.reasons["risk_fit"] == "Risk değeri 3/7; müşterinin risk aralığı 4-7."


# --- recommended ----------------------------------------------------------------------------------

@pytest.mark.parametrize("pid", ["P02", "P04"])
def test_dengeli_gets_one_cash_like_option_and_other_classes(d19_config, pid):
    r = _decide(d19_config, pid)
    assert len(r.recommended) == 3
    classes = _classes(r, r.recommended)
    assert classes.count("nakit_benzeri") <= 1
    assert len(set(classes)) >= 2
    best = {}                          # the best option of each class (score order)
    for o in sorted(r.options, key=lambda o: (-o.score, o.option.option_id)):
        if o.option.kind != "deposit":
            best.setdefault(o.option.asset_class, o.option.option_id)
    assert set(r.recommended) <= set(best.values())
    scores = {o.option.option_id: o.score for o in r.options}
    assert [scores[i] for i in r.recommended] == sorted(
        (scores[i] for i in r.recommended), reverse=True)    # score order


def test_muhafazakar_keeps_the_score_order(d19_config):
    r = _decide(d19_config, "P01")
    assert r.recommended == tuple(o.option.option_id for o in top_heads(r.options, 3))
    assert D19_TEXTS["assumptions"]["class_rule"] not in r.assumptions


def test_temkinli_without_diversity_keeps_the_score_order(d19_config):
    r = _decide(d19_config, "P05")
    assert r.recommended == tuple(o.option.option_id for o in top_heads(r.options, 3))


def test_diversity_priority_applies_the_rule(d19_config):
    p = dataclasses.replace(load_persona("P05"), oncelikler=("çeşitlendirme",))
    r = _decide(d19_config, "P05", persona=p)
    assert _classes(r, r.recommended).count("nakit_benzeri") <= 1


def test_rule_relaxes_with_too_few_classes(d19_config):
    cash = {k: FUNDS[k] for k in ("MMF", "KVD", "KAT")}
    r = _decide(d19_config, "P04", funds=cash)
    ranked = [o for o in r.options if o.option.kind != "deposit"]
    assert len(r.recommended) == min(3, len(ranked))      # relaxed: cash-like options fill


def test_reason_and_assumption_name_the_class_rule(d19_config):
    r = _decide(d19_config, "P04")
    plain = {o.option.option_id for o in top_heads(r.options, 3)}
    moved = [i for i in r.recommended if i not in plain]
    assert moved                                           # the rule changed the choice
    text = D19_TEXTS["reasons"]["class_rule"]
    for o in r.options:
        mentions = any(text in t for t in o.reasons.values())
        assert mentions == (o.option.option_id in moved)
    assert D19_TEXTS["assumptions"]["class_rule"] in r.assumptions


def test_recommended_is_valid(d19_config):
    for pid in ("P01", "P02", "P03", "P04", "P05"):
        r = _decide(d19_config, pid)
        ids = {o.option.option_id for o in r.options}
        assert set(r.recommended) <= ids and len(r.recommended) <= 3
        assert tuple(o.option.option_id for o in recommended(r)) == r.recommended


def test_without_config_recommended_is_the_first_three_heads(d12_config):
    r = _decide(d12_config, "P04")
    assert r.recommended == tuple(o.option.option_id for o in top_heads(r.options, 3))


# --- talking points use recommended ----------------------------------------------------------------

def test_talking_points_use_recommended(d19_raw):
    from tests.decision.test_talking import ACCESS, TALKING
    d19_raw["talking_points"] = copy.deepcopy(TALKING)
    d19_raw["display"]["access"] = dict(ACCESS)
    cfg = parse_config(d19_raw)
    r = _decide(cfg, "P04")
    by_code = {tp.code: tp for tp in r.talking_points}
    assert by_code["best_alternative"].option_ids == (r.recommended[0],)
    for code in ("access", "risk_fit"):
        if code in by_code:
            assert by_code[code].option_ids == r.recommended


# --- D19b: a real-return floor for the class rule ---------------------------------------------------

FLOOR_FUNDS = {
    # P03 (Agresif, 3y horizon): the 3y returns rank; the floor looks at the real 1y return
    "EQA": dict(kind="equity", name="A HİSSE SENEDİ FONU", risk=6,
                returns={"1y": 60.0, "3y": 350.0}, **BASE),
    "MXB": dict(kind="mixed", name="B KARMA FON", risk=5,
                returns={"1y": 50.0, "3y": 320.0}, **BASE),
    # long-term debt: a strong 3y return, but 1y 10 % -> negative after stopaj and CPI
    "UVC": dict(kind="debt", name="C UZUN VADELİ BORÇLANMA ARAÇLARI FONU", risk=5,
                returns={"1y": 10.0, "3y": 310.0}, **BASE),
    "EQD": dict(kind="equity", name="D HİSSE SENEDİ FONU", risk=6,
                returns={"1y": 45.0, "3y": 200.0}, **BASE),
}


def test_without_a_floor_the_negative_class_pick_stays(d19_config):
    r = _decide(d19_config, "P03", funds=FLOOR_FUNDS)
    assert "fund:UVC" in r.recommended                    # the case of P03 (KUT)


def test_floor_replaces_a_negative_real_class_pick(d19_raw):
    d19_raw["recommend"]["min_real_return"] = 0.0
    r = _decide(parse_config(d19_raw), "P03", funds=FLOOR_FUNDS)
    assert "fund:UVC" not in r.recommended
    # the next class with a real return >= 0: the time deposit (cash-like)
    assert r.recommended == ("fund:EQA", "fund:MXB", "time_deposit:ing_e_vadeli")


def test_floor_fills_by_score_when_no_class_is_left(d19_raw):
    d19_raw["recommend"]["min_real_return"] = 0.0
    funds = {k: FLOOR_FUNDS[k] for k in ("EQA", "UVC", "EQD")}
    ev = make_evidence(funds, extra=d9_rows() + [market_row()])     # no time deposit
    r = decide(ev, load_persona("P03"), parse_config(d19_raw), created_at=T0)
    # class picks: EQA (hisse); UVC is below the floor; the class cap is relaxed
    # first (EQD, hisse); the last step fills by score without the floor (UVC)
    assert set(r.recommended) == {"fund:EQA", "fund:UVC", "fund:EQD"}
    scores = {o.option.option_id: o.score for o in r.options}
    assert [scores[i] for i in r.recommended] == sorted(scores[i] for i in r.recommended)[::-1]


def test_floor_does_not_touch_the_plain_score_order(d19_raw):
    # P05 (Temkinli, no diversity): no class rule, so the floor does not apply
    d19_raw["recommend"]["min_real_return"] = 100.0      # every option is below it
    cfg = parse_config(d19_raw)
    r = _decide(cfg, "P05")
    assert r.recommended == tuple(o.option.option_id for o in top_heads(r.options, 3))


def test_floor_that_blocks_all_falls_back_to_score_order(d19_raw):
    d19_raw["recommend"]["min_real_return"] = 100.0
    r = _decide(parse_config(d19_raw), "P04")
    assert len(r.recommended) == 3


def test_floor_is_optional_and_checked(d19_raw, d19_config):
    assert "min_real_return" not in d19_config.raw["recommend"]
    d19_raw["recommend"]["min_real_return"] = "0"
    with pytest.raises(ConfigError, match="recommend.min_real_return"):
        parse_config(d19_raw)


# --- D19c: risk-based class split (by_risk) -------------------------------------------------------

def _by_risk(d19_raw):
    d19_raw["asset_classes"]["by_risk"] = {"participation": [{"min_risk": 5, "class": "hisse"}]}
    return parse_config(d19_raw)


@pytest.mark.parametrize("risk,cls", [(5, "hisse"), (6, "hisse"), (2, "borclanma"),
                                      (None, "borclanma")])
def test_participation_class_by_risk(d19_raw, risk, cls):
    funds = {"KTL": dict(kind="participation", name="X PORTFÖY TEKNOLOJİ KATILIM FONU",
                         risk=risk, returns={"1y": 30.0}, **BASE)}
    u = build_universe(_ev(funds), _by_risk(d19_raw))
    assert u.by_id["fund:KTL"].option.asset_class == cls


def test_by_name_comes_before_by_risk(d19_raw):
    funds = {"KPP": dict(kind="participation", name="X PORTFÖY PARA PİYASASI KATILIM FONU",
                         risk=5, returns={"1y": 30.0}, **BASE)}
    u = build_universe(_ev(funds), _by_risk(d19_raw))
    assert u.by_id["fund:KPP"].option.asset_class == "nakit_benzeri"


def test_an_estimated_risk_does_not_count(d19_raw):
    # no risk row: the scoring estimates the risk from the kind (here 6), the class does not
    funds = {"K6": dict(kind="participation", name="K6 KATILIM FONU", risk=6,
                        returns={"1y": 30.0}, **BASE),
             "KNR": dict(kind="participation", name="KNR KATILIM FONU", returns={"1y": 30.0},
                         **BASE)}
    cfg = _by_risk(d19_raw)
    r = _decide(cfg, "P03", funds=funds)
    by_id = {o.option.option_id: o.option for o in r.options}
    assert by_id["fund:KNR"].asset_class == "borclanma"


def test_without_by_risk_nothing_changes(d19_config):
    funds = {"KTL": dict(kind="participation", name="X KATILIM FONU", risk=5,
                         returns={"1y": 30.0}, **BASE)}
    u = build_universe(_ev(funds), d19_config)
    assert u.by_id["fund:KTL"].option.asset_class == "borclanma"


@pytest.mark.parametrize("value,match", [
    ({"gold": [{"min_risk": 5, "class": "hisse"}]}, "asset_classes.by_risk"),
    ({"participation": [{"min_risk": 8, "class": "hisse"}]}, "asset_classes.by_risk"),
    ({"participation": [{"min_risk": 5}]}, "asset_classes.by_risk"),
    ({"participation": {"min_risk": 5, "class": "hisse"}}, "asset_classes.by_risk"),
])
def test_bad_by_risk_is_an_error(d19_raw, value, match):
    d19_raw["asset_classes"]["by_risk"] = value
    with pytest.raises(ConfigError, match=match):
        parse_config(d19_raw)
