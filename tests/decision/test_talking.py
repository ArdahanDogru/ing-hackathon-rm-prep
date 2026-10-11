"""Talking points "Müşteriyle konuşulacaklar" (contract v1.3; docs/decision.md
section 9, D18)."""

import copy
import dataclasses

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.display import display_facts, tr_percent
from rmprep.decision.engine import decide
from rmprep.grouping import top_heads
from tests.decision.conftest import (
    T0,
    d9_rows,
    load_persona,
    make_evidence,
    market_row,
)

TALKING = {
    "order": ["deposit_real", "best_alternative", "access", "risk_fit"],
    "deposit_keywords": ["mevduat"],
    "texts": {
        "deposit_real": {"label": "Mevduatta reel getiri",
                         "text": "Piyasa ortalamasındaki mevduat faizi stopaj ve enflasyon "
                                 "sonrası yıllık {figure} reel getiri veriyor."},
        "best_alternative": {"label": "Alternatif",
                             "text": "{label} son bir yılda enflasyon sonrası {figure} "
                                     "getirdi; geçmiş getiri geleceği göstermez."},
        "access": {"label": "Paraya erişim",
                   "text": "İlk üç öneride para en geç {figure} hesaba geçer."},
        "risk_fit": {"label": "Risk", "figure": "en fazla {max} / 7",
                     "text": "İlk üç önerinin SPK risk değeri en fazla {max} / 7; müşterinin "
                             "sınırı {ceiling} / 7."},
    },
}
ACCESS = {"same_day": "Aynı gün", "days": "{days} iş günü", "term": "Vade sonunda ({days} gün)"}
BASE = dict(size=2e8, investors=500, buyable=1)
FUNDS = {
    "MMF": dict(kind="money_market", risk=1, returns={"1y": 50.0, "3y": 200.0}, sell_valor=0,
                **BASE),
    "DBF": dict(kind="debt", risk=2, returns={"1y": 40.0, "3y": 150.0}, sell_valor=1, **BASE),
    "PAR": dict(kind="participation", risk=2, returns={"1y": 35.0, "3y": 120.0}, sell_valor=2,
                **BASE),
    "EQF": dict(kind="equity", risk=5, returns={"1y": 60.0, "3y": 250.0}, sell_valor=2, **BASE),
}
MINUS = "−"


def _cfg(raw):
    raw["talking_points"] = copy.deepcopy(TALKING)
    raw["display"]["access"] = dict(ACCESS)
    return parse_config(raw)


@pytest.fixture
def tp_raw(d12_raw):
    return d12_raw


@pytest.fixture
def tp_config(tp_raw):
    return _cfg(tp_raw)


def _ev(rows=None):
    return make_evidence(FUNDS, time_deposit=35.0,
                         extra=(d9_rows() if rows is None else rows) + [market_row()])


def _decide(cfg, pid, ev=None, persona=None):
    return decide(ev or _ev(), persona or load_persona(pid), cfg, created_at=T0)


def _codes(r):
    return [tp.code for tp in r.talking_points]


# --- P01: deposit first ----------------------------------------------------------------------

def test_p01_gets_deposit_real_first(tp_config):
    r = _decide(tp_config, "P01")                         # durum "... TL mevduat ağırlıklı"
    assert _codes(r) == ["deposit_real", "best_alternative", "access"]   # at most 3, in order
    tp = r.talking_points[0]
    assert tp.label == "Mevduatta reel getiri"
    assert "ING" not in tp.text and "ING" not in tp.figure


def test_deposit_real_is_the_market_rate_after_stopaj_and_cpi(tp_config):
    r = _decide(tp_config, "P01")
    tp = r.talking_points[0]
    real = ((1 + 0.4382 * (1 - 0.175)) / 1.2973 - 1) * 100
    assert tp.figure == tr_percent(real)
    assert tp.text == ("Piyasa ortalamasındaki mevduat faizi stopaj ve enflasyon sonrası "
                       f"yıllık {tr_percent(real)} reel getiri veriyor.")
    ev = _ev()
    rows = {d.id: d for d in ev.datapoints}
    quantities = {(rows[i].quantity, rows[i].source) for i in tp.evidence_ids}
    assert ("deposit_rate", "evds") in quantities                 # the EVDS market row
    assert ("deposit_rate", "manual") not in quantities           # never an ING row
    assert {"cpi_annual", "withholding_tax_rate"} <= {q for q, _ in quantities}
    assert tp.option_ids == ()


def test_best_alternative_is_the_first_recommendation(tp_config):
    r = _decide(tp_config, "P01")
    head = top_heads(r.options, 3)[0]
    facts = display_facts(r, _ev(), tp_config)[head.option.option_id]
    tp = r.talking_points[1]
    assert tp.option_ids == (head.option.option_id,)
    assert tp.figure == tr_percent(facts.real_1y.value)
    assert tp.text.startswith(head.option.label)
    assert "geçmiş getiri" in tp.text
    assert facts.real_1y.evidence_id in tp.evidence_ids


def test_access_is_the_slowest_of_the_top_3(tp_config):
    r = _decide(tp_config, "P01")
    top = top_heads(r.options, 3)
    facts = display_facts(r, _ev(), tp_config)
    tp = next(t for t in r.talking_points if t.code == "access")
    days = [facts[o.option.option_id].lock_days
            if facts[o.option.option_id].lock_days is not None
            else facts[o.option.option_id].sell_valor_days.value for o in top]
    slowest = max(days)
    expected = ("Vade sonunda (32 gün)" if any(facts[o.option.option_id].lock_days == slowest
                                                for o in top)
                else "Aynı gün" if slowest == 0 else f"{slowest:.0f} iş günü")
    assert tp.figure == expected
    assert tp.option_ids == tuple(o.option.option_id for o in top)


# --- P03: no deposit point, no access point -------------------------------------------------------

def test_no_deposit_point_without_keyword(tp_config):
    r = _decide(tp_config, "P03")                         # durum without "mevduat"
    assert "deposit_real" not in _codes(r)


def test_p03_gets_risk_fit_with_the_ceiling(tp_config):
    r = _decide(tp_config, "P03")                         # likidite Düşük, no liquidity priority
    assert _codes(r) == ["best_alternative", "risk_fit"]
    tp = r.talking_points[1]
    top = top_heads(r.options, 3)
    facts = display_facts(r, _ev(), tp_config)
    highest = max(facts[o.option.option_id].risk.value if facts[o.option.option_id].risk
                  else 1 for o in top)
    assert tp.figure == f"en fazla {highest:.0f} / 7"
    assert tp.text.endswith("müşterinin sınırı 7 / 7.")


def test_access_for_a_liquidity_priority(tp_raw):
    p = dataclasses.replace(load_persona("P03"), oncelikler=("yüksek likidite",))
    r = _decide(_cfg(tp_raw), "P03", persona=p)
    assert "access" in _codes(r)


# --- format, evidence, edge cases ------------------------------------------------------------------

@pytest.mark.parametrize("pid", ["P01", "P02", "P03", "P04", "P05"])
def test_figures_turkish_format(tp_config, pid):
    for tp in _decide(tp_config, pid).talking_points:
        if tp.code in ("deposit_real", "best_alternative"):
            assert tp.figure[0] in "+" + MINUS and "," in tp.figure and "." not in tp.figure
            assert "-" not in tp.figure


@pytest.mark.parametrize("pid", ["P01", "P02", "P03", "P04", "P05"])
def test_points_cite_evidence_and_options(tp_config, pid):
    r = _decide(tp_config, pid)
    ids = {o.option.option_id for o in r.options}
    assert r.talking_points and len(r.talking_points) <= 3
    for tp in r.talking_points:
        assert tp.evidence_ids and set(tp.option_ids) <= ids
        assert "{" not in tp.text and "{" not in tp.figure


def test_needs_input_has_no_points(tp_config):
    p = dataclasses.replace(load_persona("P01"), acik_kisitlar=("bilinmeyen bir kısıt",))
    assert _decide(tp_config, "P01", persona=p).talking_points == ()


def test_without_cpi_no_return_points(tp_config):
    r = _decide(tp_config, "P01", ev=_ev(rows=d9_rows(cpi=None)))
    assert _codes(r) == ["access", "risk_fit"]


def test_without_config_no_points(d12_config):
    assert _decide(d12_config, "P01").talking_points == ()


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["talking_points"]["order"].append("weather"), "talking_points.order"),
    (lambda r: r["talking_points"]["texts"].pop("access"), "talking_points.texts"),
    (lambda r: r["talking_points"]["texts"]["risk_fit"].pop("figure"), "risk_fit"),
    (lambda r: r["talking_points"]["texts"]["access"].update(label=""), "talking_points.texts"),
    (lambda r: r["talking_points"].update(deposit_keywords="mevduat"), "deposit_keywords"),
    (lambda r: r["display"].pop("access"), "display.access"),
])
def test_bad_talking_config_is_an_error(tp_raw, edit, match):
    tp_raw["talking_points"] = copy.deepcopy(TALKING)
    tp_raw["display"]["access"] = dict(ACCESS)
    edit(tp_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(tp_raw)
