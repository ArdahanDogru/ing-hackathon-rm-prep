"""Display facts for the web UI (docs/decision.md section 9, D17)."""

import dataclasses

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.display import access_text, display_facts, tr_percent
from rmprep.decision.engine import decide
from rmprep.decision.scoring import _net
from rmprep.decision.universe import latest, stopaj_entity
from tests.decision.conftest import CPI, T0, d9_rows, load_persona, make_evidence

FUNDS = {
    "MMF": dict(kind="money_market", risk=1, returns={"3m": 10.0, "1y": 50.0, "3y": 200.0},
                size=2e8, investors=500, buyable=1, sell_valor=0),
    "DBF": dict(kind="debt", risk=2, returns={"6m": 12.0, "1y": 20.0, "3y": 80.0},
                size=2e8, investors=500, buyable=1, sell_valor=2),
    "NEG": dict(kind="mixed", risk=2, returns={"1y": -10.0, "3y": 10.0}, size=2e8,
                investors=500),
    "EQ6": dict(kind="equity", risk=6, returns={"1y": 40.0}, size=2e8, investors=500),
}
WHY = {"liquidity": "Paraya erişim: {access}", "low_risk": "SPK risk değeri {risk} / 7",
       "income": "Son bir yıl getirisi {ret1y}"}
ACCESS = {"same_day": "Aynı gün", "days": "{days} iş günü", "term": "Vade sonunda ({days} gün)"}


def _run(cfg, pid="P01", rows=None, persona=None, excluded=frozenset()):
    ev = make_evidence(FUNDS, time_deposit=35.0, extra=d9_rows() if rows is None else rows)
    ev = dataclasses.replace(ev, excluded_sources=excluded)
    return decide(ev, persona or load_persona(pid), cfg, {}, created_at=T0), ev


@pytest.fixture
def why_config(d12_raw):
    d12_raw["display"]["why"] = dict(WHY)
    d12_raw["display"]["access"] = dict(ACCESS)
    return parse_config(d12_raw)


def _facts(cfg, **kw):
    r, ev = _run(cfg, **kw)
    return display_facts(r, ev, cfg), r, ev


# --- every option -----------------------------------------------------------------------------

def test_every_scored_and_rejected_option_has_facts(d9_config):
    facts, r, _ = _facts(d9_config)
    assert r.rejected                                    # EQ6 is above the P01 ceiling
    ids = {o.option.option_id for o in r.options} | {x.option.option_id for x in r.rejected}
    assert set(facts) == ids
    assert all(f.option_id == oid for oid, f in facts.items())


def test_fund_returns_cite_their_rows(d9_config):
    facts, _, ev = _facts(d9_config)
    f = facts["fund:MMF"]
    assert set(f.returns) == {"3m", "1y"}               # no 6m row, so no 6m key
    row = next(d for d in ev.datapoints if d.id == f.returns["1y"].evidence_id)
    assert row.quantity == "fund_return_1y" and row.value == f.returns["1y"].value == 50.0
    assert set(facts["fund:DBF"].returns) == {"6m", "1y"}


def test_risk_cites_its_row(d9_config):
    facts, _, ev = _facts(d9_config)
    f = facts["fund:DBF"].risk
    row = next(d for d in ev.datapoints if d.id == f.evidence_id)
    assert row.quantity == "fund_risk_level" and f.value == 2.0
    assert facts["fund:EQ6"].risk.value == 6.0           # rejected options too


def test_real_1y_is_net_of_stopaj_then_cpi(d9_config):
    """Percent values; no fees (a fact of the fund, not of the client's horizon)."""
    facts, r, ev = _facts(d9_config)
    o = next(x for x in r.options if x.option.option_id == "fund:MMF").option
    stopaj = latest(ev, "withholding_tax_rate", stopaj_entity(o, d9_config)).value / 100
    cpi = latest(ev, "cpi_annual", CPI).value / 100
    expected = ((1 + _net(o, 0.50, stopaj, d9_config)) / (1 + cpi) - 1) * 100
    real = facts["fund:MMF"].real_1y
    assert real.value == pytest.approx(expected)
    assert real.evidence_id == facts["fund:MMF"].returns["1y"].evidence_id


def test_real_1y_ignores_fees_and_the_horizon(d12_config):
    funds_fee = {**FUNDS, "MMF": {**FUNDS["MMF"], "entry_fee": 1.0, "exit_fee": 2.0}}
    ev = make_evidence(funds_fee, time_deposit=35.0, extra=d9_rows())
    p04 = decide(ev, load_persona("P04"), d12_config, {}, created_at=T0)   # 3y horizon
    real = display_facts(p04, ev, d12_config)["fund:MMF"].real_1y.value
    assert real == pytest.approx(((1 + 0.5 * 0.825) / 1.2973 - 1) * 100)


def test_negative_return_has_no_stopaj(d9_config):
    facts, _, _ = _facts(d9_config)
    assert facts["fund:NEG"].real_1y.value == pytest.approx((0.9 / 1.2973 - 1) * 100)


def test_no_cpi_no_real(d9_config):
    facts, _, _ = _facts(d9_config, rows=d9_rows(cpi=None))
    assert all(f.real_1y is None for f in facts.values())


def test_without_real_return_config_no_real(config):
    facts, _, _ = _facts(config)
    assert all(f.real_1y is None for f in facts.values())


def test_excluded_source_gives_no_fact(d9_config):
    facts, _, _ = _facts(d9_config, excluded=frozenset({"tefas_web"}))
    assert all(not f.returns and f.risk is None
               for oid, f in facts.items() if oid.startswith("fund:"))


# --- deposits ---------------------------------------------------------------------------------

def test_time_deposit_lock_days(d9_config):
    facts, r, _ = _facts(d9_config)
    f = facts["time_deposit:ing_e_vadeli"]
    assert f.lock_days == 32 and f.sell_valor_days is None and f.risk is None
    assert f.returns["1y"].value == 35.0                 # the published annual rate
    td = next(o.option for o in r.options if o.option.kind == "time_deposit")
    n = _net(td, 0.35, 0.15, d9_config)                  # renewed every 32 days
    assert f.real_1y.value == pytest.approx(((1 + n) / 1.2973 - 1) * 100)


def test_deposit_facts(d9_config):
    facts, _, _ = _facts(d9_config)
    f = facts["deposit:ing_turuncu"]
    assert f.lock_days is None and f.returns["1y"].value == 23.0
    assert f.real_1y.value == pytest.approx(((1 + 0.23 * 0.825) / 1.2973 - 1) * 100)


# --- sell valör and access ------------------------------------------------------------------------

def test_sell_valor_cites_its_row(d12_config):
    facts, _, ev = _facts(d12_config)
    f = facts["fund:DBF"].sell_valor_days
    row = next(d for d in ev.datapoints if d.id == f.evidence_id)
    assert row.quantity == "fund_sell_valor_days" and f.value == 2.0
    assert facts["fund:NEG"].sell_valor_days is None      # no row


def test_no_sell_valor_without_fund_detail(d9_config):
    facts, _, _ = _facts(d9_config)
    assert all(f.sell_valor_days is None for f in facts.values())


def test_access_text(why_config):
    facts, _, _ = _facts(why_config)
    assert access_text(facts["fund:MMF"], why_config) == "Aynı gün"
    assert access_text(facts["fund:DBF"], why_config) == "2 iş günü"
    assert access_text(facts["time_deposit:ing_e_vadeli"], why_config) == "Vade sonunda (32 gün)"
    assert access_text(facts["fund:NEG"], why_config) is None


# --- why ------------------------------------------------------------------------------------------

def test_why_uses_persona_wording(why_config):
    facts, r, _ = _facts(why_config)
    persona = r.persona.oncelikler
    for f in facts.values():
        assert all(p in persona for p, _ in f.why)            # exactly as written in the persona
        assert all("puan" not in t and "score" not in t for _, t in f.why)


def test_why_lines_for_a_fund(why_config):
    facts, _, _ = _facts(why_config)
    # P01 priorities: düzenli gelir (income), likiditeyi koruma (liquidity),
    # sınırlı dalgalanma (low_risk); persona order
    assert facts["fund:MMF"].why == (
        ("düzenli gelir", "Son bir yıl getirisi +%50,0"),
        ("likiditeyi koruma", "Paraya erişim: Aynı gün"),
        ("sınırlı dalgalanma", "SPK risk değeri 1 / 7"),
    )


def test_why_skips_a_line_without_its_value(why_config):
    facts, _, _ = _facts(why_config)
    # NEG has no sell valör: no access line
    assert [p for p, _ in facts["fund:NEG"].why] == ["düzenli gelir", "sınırlı dalgalanma"]


def test_why_matches_turkish_case(why_config):
    p = dataclasses.replace(load_persona("P01"),
                            oncelikler=("SINIRLI DALGALANMA", "Likiditeyi Koruma"))
    facts, _, _ = _facts(why_config, persona=p)
    assert [w for w, _ in facts["fund:MMF"].why] == ["SINIRLI DALGALANMA", "Likiditeyi Koruma"]


def test_why_without_config_is_empty(d12_config):
    facts, _, _ = _facts(d12_config)
    assert all(f.why == () for f in facts.values())


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["display"].update(why={"risk": "x"}), "display.why"),
    (lambda r: r["display"].update(why={"low_risk": ""}), "display.why"),
    (lambda r: r["display"].pop("access"), "display.access"),
    (lambda r: r["display"]["access"].pop("term"), "display.access"),
])
def test_bad_display_config_is_an_error(d12_raw, edit, match):
    d12_raw["display"]["why"] = dict(WHY)
    d12_raw["display"]["access"] = dict(ACCESS)
    edit(d12_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d12_raw)


# --- number format ------------------------------------------------------------------------------

@pytest.mark.parametrize("x,text", [
    (8.7, "+%8,7"), (-8.29, "−%8,3"), (0.0, "+%0,0"), (123.456, "+%123,5"),
])
def test_tr_percent(x, text):
    assert tr_percent(x) == text
