"""Exchange-traded funds and shares (docs/decision.md section 16, D26)."""

import copy
import dataclasses
from datetime import date

import pytest

from rmprep.contracts import EntityInfo
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.confidence import confidence
from rmprep.decision.display import access_text, display_facts
from rmprep.decision.engine import decide
from rmprep.decision.exchange import spk_risk, stock_risk
from rmprep.decision.persona import read_persona
from rmprep.decision.recommend import choose
from rmprep.decision.scoring import option_features
from rmprep.decision.universe import build_universe, stopaj_entity
from tests.decision.conftest import T0, d9_rows, dp, load_persona, make_evidence
from tests.decision.test_allocation import ALLOCATION
from tests.decision.test_holdings_class import add_d23, hold

ETF_STOPAJ = "Borsa yatırım fonu (BYF), tüm türler"
STOCK_STOPAJ = "Borsa İstanbul payları, alım satım kazancı (gerçek kişi)"
SINGLE_STOCK = "Tek bir şirketin payı: şirkete özgü risk; çeşitlendirmeyi RM değerlendirsin."
EXCLUDED = ("Borsa ürünlerinden varant ve sertifikalar, borsada işlem gören gayrimenkul ve "
            "girişim sermayesi fonları, tahvil ve eurobondlar kapsam dışıdır.")
EXCHANGE = {"TR": "2 iş günü (borsa takası)", "EN": "2 business days (exchange settlement)"}
D26_SECTIONS = {
    "etf": {"source": "tefas_byf",
            "by_name": {"ALTIN": "altin_doviz", "GÜMÜŞ": "altin_doviz", "TLREF": "nakit_benzeri"},
            "default_class": "hisse"},
    "stock": {"source": "bist_bulletin", "risk_floor": 6, "min_turnover_try": 10_000_000,
              "max_in_top3": 1,
              "spk_bands": [[2, 1], [5, 2], [10, 3], [15, 4], [20, 5], [30, 6]],
              "asset_class": "hisse"},
}
D26_KINDS = {"etf": {"liquidity": 0.8, "income": 0.2, "simplicity": 0.6},
             "stock": {"liquidity": 0.8, "income": 0.2, "simplicity": 0.4}}
D26_TEXTS = {
    "warnings": {"single_stock": SINGLE_STOCK},
    "data_quality": {"excluded_exchange_groups": EXCLUDED},
    "constraint": {
        "stock_risk": "Risk değeri {risk}/7: 1 yıllık oynaklıktan (%{volatility:.1f}) SPK "
                      "yöntemiyle tahmin; tek şirket payı için en az {floor}. Sınır {ceiling}/7.",
        "stock_risk_missing": "Oynaklık verisi yok: risk değeri 7 kabul edildi (tahmin). "
                              "Sınır {ceiling}/7.",
    },
}


def add_d26(raw: dict) -> dict:
    """Add the D26 config (section 16) and texts to a raw config, in place."""
    raw.update(copy.deepcopy(D26_SECTIONS))
    raw["kinds"].update(copy.deepcopy(D26_KINDS))
    raw["real_return"]["stopaj"].update(etf=ETF_STOPAJ, stock=STOCK_STOPAJ)
    raw["display"].setdefault("access", {"same_day": "Aynı gün", "days": "{days} iş günü",
                                         "term": "Vade sonunda ({days} gün)"})
    raw["display"]["access"]["exchange"] = dict(EXCHANGE)
    for section, texts in D26_TEXTS.items():
        raw["texts"][section].update(texts)
    return raw


@pytest.fixture
def d26_raw(d19_raw) -> dict:
    return add_d26(add_d23(d19_raw))


@pytest.fixture
def d26_config(d26_raw):
    return parse_config(d26_raw)


def etf(code, *, name=None, risk=6, returns=None, size=5e8, buyable=0):
    """Rows and entity of an ETF (source tefas_byf); buyable 0 = TEFAS status
    "Platformda İşlem Görmüyor"."""
    rows = [dp(f"fund_return_{p}", code, v, source="tefas_byf")
            for p, v in (returns or {"1y": 40.0, "3y": 150.0}).items()]
    if risk is not None:
        rows.append(dp("fund_risk_level", code, risk, source="tefas_byf"))
    if size is not None:
        rows.append(dp("fund_total_value", code, size, source="tefas_byf"))
    if buyable is not None:
        rows.append(dp("fund_buyable", code, buyable))
    info = EntityInfo(name or f"{code} HİSSE SENEDİ YOĞUN BORSA YATIRIM FONU", "Hisse Senedi Yoğun",
                      "tefas_byf")
    return rows, {code: info}


def stock(code, *, vol=25.0, returns=None, turnover=5e8, bist100=1, name=None):
    rows = [dp(f"stock_return_{p}", code, v, source="bist_bulletin")
            for p, v in (returns or {"1m": 3.0, "3m": 10.0, "6m": 20.0, "1y": 50.0}).items()]
    for q, v in (("stock_volatility_1y", vol), ("stock_turnover_3m", turnover),
                 ("stock_bist100", bist100), ("stock_close", 100.0)):
        if v is not None:
            rows.append(dp(q, code, v, source="bist_bulletin"))
    info = EntityInfo(name or f"{code} A.Ş.", "BIST pay · YILDIZ PAZAR", "bist_bulletin")
    return rows, {code: info}


FULL = dict(returns={"1y": 40.0, "3y": 150.0}, size=2e8, investors=500)
FUNDS = {"MM": dict(kind="money_market", risk=1, **FULL), "DB": dict(kind="debt", risk=3, **FULL)}


def _ev(*products, funds=FUNDS):
    rows, ents = [], {}
    for r, e in products:
        rows += r
        ents.update(e)
    ev = make_evidence(funds, extra=[*d9_rows(), *rows,
                                     dp("withholding_tax_rate", ETF_STOPAJ, 17.5),
                                     dp("withholding_tax_rate", STOCK_STOPAJ, 0.0)])
    return dataclasses.replace(ev, entities={**ev.entities, **ents})


def _by_id(r):
    return {o.option.option_id: o for o in r.options}


def _rejected(r):
    return {x.option.option_id: [c.rule_id for c in x.failed] for x in r.rejected}


# --- ETFs ---------------------------------------------------------------------------------

def test_etf_not_on_tefas_stays_in(d26_config):
    ev = _ev(etf("BOE", buyable=0))
    r = decide(ev, load_persona("P03"), d26_config, created_at=T0)
    o = _by_id(r)["etf:BOE"]
    assert o.option.kind == "etf" and o.option.fund_kind == ""
    assert "not_buyable" not in [c.rule_id for c in o.constraints]


def test_a_fund_with_buyable_0_is_still_rejected(d26_config):
    ev = _ev(funds={**FUNDS, "NB": dict(kind="debt", risk=3, buyable=0, **FULL)})
    r = decide(ev, load_persona("P03"), d26_config, created_at=T0)
    assert _rejected(r)["fund:NB"] == ["not_buyable"]


def test_etf_liquidity_quality_and_size_penalty(d26_config):
    ev = _ev(etf("BIG", size=9e8), etf("SML", size=2.5e7))
    lv = read_persona(load_persona("P03"), d26_config).levels
    feats, _ = option_features(build_universe(ev, d26_config), lv, d26_config)
    f = {x.option.option_id: x for x in feats}
    assert f["etf:BIG"].values["liquidity"] == 0.8            # kind table (T+2)
    assert f["etf:BIG"].values["quality"] == 1.0               # size percentile among ETFs
    assert f["etf:SML"].values["quality"] == 0.0
    assert f["etf:BIG"].factors["fund_size"] == 0.0            # no investor count needed
    assert f["etf:SML"].factors["fund_size"] == pytest.approx(0.75)    # 1 - 25 / 100 million
    assert not f["etf:BIG"].liquidity_proxy


def test_etf_without_size_row_gets_the_full_size_penalty(d26_config):
    ev = _ev(etf("NOS", size=None))
    lv = read_persona(load_persona("P03"), d26_config).levels
    feats, _ = option_features(build_universe(ev, d26_config), lv, d26_config)
    f = next(x for x in feats if x.option.option_id == "etf:NOS")
    assert f.factors["fund_size"] == 1.0 and f.values["quality"] == 0.0


@pytest.mark.parametrize("name,cls,fx", [
    ("QNB ALTIN BORSA YATIRIM FONU", "altin_doviz", False),
    ("İŞ GÜMÜŞ BORSA YATIRIM FONU", "altin_doviz", False),
    ("ZİRAAT TLREF BORSA YATIRIM FONU", "nakit_benzeri", False),
    ("X DOLAR BORSA YATIRIM FONU", "altin_doviz", True),
    ("X BIST 30 ENDEKS BORSA YATIRIM FONU", "hisse", False),
])
def test_etf_class_by_name(d26_config, name, cls, fx):
    u = build_universe(_ev(etf("EF", name=name)), d26_config)
    o = u.by_id["etf:EF"].option
    assert (o.asset_class, o.fx) == (cls, fx)


def test_etf_class_by_holdings_before_the_name(d26_config):
    rows, ents = etf("EF", name="X TLREF BORSA YATIRIM FONU")
    ev = _ev((rows + hold("EF", {"Hisse Senedi": 90.0, "Ters-Repo": 10.0}), ents))
    u = build_universe(ev, d26_config)
    assert u.by_id["etf:EF"].option.asset_class == "hisse"
    assert u.holdings_class["etf:EF"].share == pytest.approx(90.0)


def test_etf_stopaj_row(d26_config):
    u = build_universe(_ev(etf("EF")), d26_config)
    assert stopaj_entity(u.by_id["etf:EF"].option, d26_config) == ETF_STOPAJ
    assert u.stopaj[ETF_STOPAJ].value == 17.5


# --- share risk -----------------------------------------------------------------------------

BANDS = D26_SECTIONS["stock"]["spk_bands"]


@pytest.mark.parametrize("vol,risk", [
    (0.0, 1), (1.99, 1), (2.0, 2), (4.99, 2), (5.0, 3), (9.99, 3), (10.0, 4), (14.99, 4),
    (15.0, 5), (19.99, 5), (20.0, 6), (29.99, 6), (30.0, 7), (250.0, 7),
])
def test_spk_volatility_bands(vol, risk):
    assert spk_risk(vol, BANDS) == risk


def test_risk_floor(d26_config):
    row = dp("stock_volatility_1y", "S", 3.0, source="bist_bulletin")
    assert stock_risk(row, d26_config) == 6
    row = dp("stock_volatility_1y", "S", 45.0, source="bist_bulletin")
    assert stock_risk(row, d26_config) == 7
    assert stock_risk(None, d26_config) == 7


def test_share_risk_is_an_estimate_and_the_reason_says_so(d26_config):
    ev = _ev(stock("THYAO", vol=25.0))
    r = decide(ev, load_persona("P03"), d26_config, created_at=T0)
    o = _by_id(r)["stock:THYAO"]
    assert o.option.asset_class == "hisse" and not o.option.fx
    [c] = [c for c in o.constraints if c.rule_id == "risk_ceiling"]
    assert "oynaklık" in c.reason and "%25.0" in c.reason and "en az 6" in c.reason
    vol_id = next(d.id for d in ev.datapoints if d.quantity == "stock_volatility_1y")
    assert c.evidence_ids == (vol_id,)
    # SPK band 6 from 1-year volatility: confidence x 0.7 (risk estimate) x 0.8 (1y for 3y)
    assert o.confidence == pytest.approx(0.7 * 0.8)
    assert "penalty:risk_unknown" not in o.score_parts


def test_share_without_volatility_row_is_risk_7(d26_config):
    r = decide(_ev(stock("NEW", vol=None)), load_persona("P03"), d26_config, created_at=T0)
    o = _by_id(r)["stock:NEW"]
    [c] = [c for c in o.constraints if c.rule_id == "risk_ceiling"]
    assert "Oynaklık verisi yok" in c.reason and c.evidence_ids == ()
    assert display_facts(r, _ev(stock("NEW", vol=None)), d26_config)["stock:NEW"].risk is None


@pytest.mark.parametrize("pid", ["P01", "P02", "P04", "P05"])
def test_share_above_the_ceiling_is_rejected(d26_config, pid):
    ev = _ev(stock("THYAO", vol=8.0))           # band 3, floor 6
    r = decide(ev, load_persona(pid), d26_config, created_at=T0)
    assert "risk_ceiling" in _rejected(r)["stock:THYAO"]
    [c] = [c for x in r.rejected if x.option.option_id == "stock:THYAO" for c in x.failed
           if c.rule_id == "risk_ceiling"]
    assert c.evidence_ids == tuple(d.id for d in ev.datapoints
                                   if d.quantity == "stock_volatility_1y")


# --- share criteria -------------------------------------------------------------------------

def _stock_features(cfg, *products, pid="P03"):
    lv = read_persona(load_persona(pid), cfg).levels
    feats, _ = option_features(build_universe(_ev(*products), cfg), lv, cfg)
    return {f.option.option_id: f for f in feats}


def test_share_return_liquidity_income_simplicity(d26_config):
    f = _stock_features(d26_config, stock("THYAO"))["stock:THYAO"]
    assert f.period == "1y" and f.shorter_period            # P03: 3y horizon, no 3y data
    assert f.annual_return == pytest.approx(0.50)
    assert (f.values["liquidity"], f.values["income"], f.values["simplicity"]) == (0.8, 0.2, 0.4)
    assert f.values["principal"] == pytest.approx(max(0.0, 0.8 - 0.15 * 5))   # risk 6
    assert f.stopaj_entity == STOCK_STOPAJ and f.net_return == pytest.approx(0.50)


def test_turnover_quality_and_bist100(d26_config):
    f = _stock_features(d26_config, stock("A", turnover=9e8, bist100=1),
                        stock("B", turnover=5e8, bist100=0),
                        stock("C", turnover=1e7, bist100=1),
                        stock("D", turnover=1e6, bist100=0))
    q = {k.split(":")[1]: v.values["quality"] for k, v in f.items() if k.startswith("stock:")}
    assert q["A"] == 1.0
    assert q["B"] == pytest.approx(2 / 3)
    assert q["C"] == 0.5                         # 1/3, but BIST 100 -> at least 0.5
    assert q["D"] == 0.0


def test_low_turnover_gets_the_small_fund_penalty(d26_config):
    f = _stock_features(d26_config, stock("A", turnover=5e8), stock("B", turnover=2.5e6),
                        stock("C", turnover=None))
    assert f["stock:A"].factors["fund_size"] == 0.0
    assert f["stock:B"].factors["fund_size"] == pytest.approx(0.75)
    assert f["stock:C"].factors["fund_size"] == 1.0 and f["stock:C"].values["quality"] == 0.5


# --- short list and top 3 -------------------------------------------------------------------

STOCKS = [stock(c, returns={"1y": 300.0 - i}) for i, c in enumerate(("S1", "S2", "S3", "S4"))]


def test_shares_count_as_their_own_kind_in_the_caps(d26_config):
    r = decide(_ev(*STOCKS), load_persona("P03"), d26_config, created_at=T0)
    ranked = [o for o in r.options if o.option.kind != "deposit"]
    first_cap = d26_config.raw["display"]["first_cap"]
    assert sum(o.option.kind == "stock" for o in ranked[:3]) <= first_cap


def test_at_most_one_share_in_the_top_3_and_the_warning(d26_config):
    ev = _ev(*STOCKS, etf("EF", returns={"1y": 50.0}))
    r = decide(ev, load_persona("P03"), d26_config, created_at=T0)
    stocks = [i for i in r.recommended if i.startswith("stock:")]
    assert len(stocks) == 1 and len(r.recommended) == 3
    [w] = [w for w in r.warnings if w.code == "single_stock"]
    assert w.option_ids == tuple(stocks) and w.message == SINGLE_STOCK and w.audience == "rm"


def test_no_warning_without_a_share_in_the_top_3(d26_config):
    r = decide(_ev(etf("EF")), load_persona("P03"), d26_config, created_at=T0)
    assert not [w for w in r.warnings if w.code == "single_stock"]


def test_share_cap_without_the_class_rule(d26_raw):
    d26_raw["stock"]["max_in_top3"] = 0
    cfg = parse_config(d26_raw)
    lv = dataclasses.replace(read_persona(load_persona("P03"), cfg).levels,
                             risk_profile="Temkinli", diversity=False)
    r = decide(_ev(*STOCKS), load_persona("P03"), cfg, created_at=T0)
    rec, _ = choose(r.options, lv, cfg)
    assert rec and not [i for i in rec if i.startswith("stock:")]


def test_share_cap_with_the_class_rule(d26_raw):
    d26_raw["stock"]["max_in_top3"] = 0
    cfg = parse_config(d26_raw)
    r = decide(_ev(*STOCKS), load_persona("P03"), cfg, created_at=T0)
    assert r.recommended and not [i for i in r.recommended if i.startswith("stock:")]


def test_warning_cannot_be_for_the_client(d26_raw):
    d26_raw["warnings"]["audience"] = {"single_stock": "client"}
    with pytest.raises(ConfigError, match="warnings.audience.single_stock"):
        parse_config(d26_raw)


# --- notes, display -------------------------------------------------------------------------

def test_excluded_groups_note(d26_config):
    r = decide(_ev(stock("THYAO")), load_persona("P03"), d26_config, created_at=T0)
    assert EXCLUDED in [n.message for n in r.data_quality]


def test_no_excluded_groups_note_without_exchange_products(d26_config):
    r = decide(_ev(), load_persona("P03"), d26_config, created_at=T0)
    assert EXCLUDED not in [n.message for n in r.data_quality]


def test_access_label_for_exchange_products(d26_config):
    ev = _ev(stock("THYAO"), etf("EF"))
    r = decide(ev, load_persona("P03"), d26_config, created_at=T0)
    facts = display_facts(r, ev, d26_config)
    for oid in ("stock:THYAO", "etf:EF"):
        assert facts[oid].kind == oid.split(":")[0]
        assert access_text(facts[oid], d26_config) == EXCHANGE["TR"]
        assert access_text(facts[oid], d26_config, lang="EN") == EXCHANGE["EN"]
    assert access_text(facts["fund:MM"], d26_config, lang="EN") is None    # no valör row


def test_share_display_facts(d26_config):
    ev = _ev(stock("THYAO", vol=25.0))
    r = decide(ev, load_persona("P03"), d26_config, created_at=T0)
    f = display_facts(r, ev, d26_config)["stock:THYAO"]
    ids = {d.quantity: d.id for d in ev.datapoints if d.entity == "THYAO"}
    assert f.returns["1y"].value == 50.0 and f.returns["1y"].evidence_id == ids["stock_return_1y"]
    assert set(f.returns) == {"3m", "6m", "1y"}
    assert (f.risk.value, f.risk.evidence_id) == (6, ids["stock_volatility_1y"])
    assert f.real_1y is not None                              # stopaj 0, then TÜFE


# --- without the new sources or config ------------------------------------------------------

def _summary(r):
    return ([(o.option.option_id, o.option.asset_class, o.score, o.evidence_ids, o.reasons)
             for o in r.options], r.recommended, r.data_quality, r.warnings)


def strip_d26(raw: dict) -> dict:
    """A copy of the config without the D26 keys (they will be in config/decision.yaml)."""
    raw = copy.deepcopy(raw)
    for key in ("etf", "stock"):
        raw.pop(key, None)
        raw["kinds"].pop(key, None)
        raw["real_return"]["stopaj"].pop(key, None)
    raw["display"]["access"].pop("exchange", None)
    for section, texts in D26_TEXTS.items():
        for key in texts:
            raw["texts"][section].pop(key, None)
    return raw


@pytest.mark.parametrize("pid", ["P01", "P03", "P04"])
def test_without_the_new_sources_the_results_are_unchanged(d26_raw, d26_config, pid):
    old = parse_config(strip_d26(d26_raw))
    ev = make_evidence(FUNDS, extra=d9_rows())
    a = decide(ev, load_persona(pid), old, created_at=T0)
    b = decide(ev, load_persona(pid), d26_config, created_at=T0)
    assert _summary(a) == _summary(b)


def test_without_config_shares_are_ignored(d26_raw):
    cfg = parse_config(strip_d26(d26_raw))
    a = decide(make_evidence(FUNDS, extra=d9_rows()), load_persona("P03"), cfg, created_at=T0)
    b = decide(_ev(stock("THYAO")), load_persona("P03"), cfg, created_at=T0)
    assert [o.option.option_id for o in b.options] == [o.option.option_id for o in a.options]


# --- config checks --------------------------------------------------------------------------

def test_d26_config_is_valid(d26_config):
    assert d26_config.raw["stock"]["risk_floor"] == 6


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["stock"].pop("risk_floor"), "stock"),
    (lambda r: r["stock"].update(extra=1), "stock"),
    (lambda r: r["stock"].update(risk_floor=8), "stock.risk_floor"),
    (lambda r: r["stock"].update(min_turnover_try=-1), "stock.min_turnover_try"),
    (lambda r: r["stock"].update(max_in_top3=-1), "stock.max_in_top3"),
    (lambda r: r["stock"].update(spk_bands=[[5, 2], [2, 1]]), "stock.spk_bands"),
    (lambda r: r["stock"].update(spk_bands=[[2, 1], [5, 1]]), "stock.spk_bands"),
    (lambda r: r["stock"].update(spk_bands=[[2, 1], [5, 8]]), "stock.spk_bands"),
    (lambda r: r["stock"].update(spk_bands="x"), "stock.spk_bands"),
    (lambda r: r["stock"].update(source=""), "stock.source"),
    (lambda r: r["etf"].pop("default_class"), "etf"),
    (lambda r: r["etf"].update(by_name=["ALTIN"]), "etf.by_name"),
    (lambda r: r["kinds"].pop("stock"), "kinds"),
    (lambda r: r["kinds"].pop("etf"), "kinds"),
    (lambda r: r["texts"]["warnings"].pop("single_stock"), "single_stock"),
    (lambda r: r["texts"]["data_quality"].pop("excluded_exchange_groups"),
     "excluded_exchange_groups"),
    (lambda r: r["texts"]["constraint"].pop("stock_risk"), "stock_risk"),
    (lambda r: r["texts"]["constraint"].update(stock_risk="{vol}"), "stock_risk"),
    (lambda r: r["display"]["access"].update(exchange="2 gün"), "display.access.exchange"),
    (lambda r: r["display"]["access"].update(exchange={"TR": "x"}), "display.access.exchange"),
])
def test_bad_d26_config_is_an_error(d26_raw, edit, match):
    edit(d26_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d26_raw)


# --- D26b: excluded markets, no single share as a class example ----------------------------

REMOVED = "{count} pay, {markets} pazarında işlem gördüğü için çıkarıldı (yakın izleme / nitelikli yatırımcı)."


def _market(rows_ents, market):
    rows, ents = rows_ents
    return rows, {k: dataclasses.replace(v, category=f"BIST pay · {market}")
                  for k, v in ents.items()}


@pytest.fixture
def d26b_raw(d26_raw) -> dict:
    d26_raw["stock"]["exclude_markets"] = ["W", "S"]
    d26_raw["texts"]["data_quality"]["removed_stock_market"] = REMOVED
    return d26_raw


@pytest.fixture
def d26b_config(d26b_raw):
    return parse_config(d26b_raw)


def test_shares_of_excluded_markets_are_removed_and_counted(d26b_config):
    ev = _ev(_market(stock("YLDZ"), "Z"), _market(stock("WTCH"), "W"),
             _market(stock("WTC2"), "W"), _market(stock("QUAL"), "S"))
    u = build_universe(ev, d26b_config)
    assert {c.option.entity for c in u.candidates if c.option.kind == "stock"} == {"YLDZ"}
    assert u.removed_stock_market == {"S": ("QUAL",), "W": ("WTC2", "WTCH")}
    r = decide(ev, load_persona("P03"), d26b_config, created_at=T0)
    assert REMOVED.format(count=3, markets="S, W") in [n.message for n in r.data_quality]
    assert "stock:WTCH" not in {x.option.option_id for x in r.rejected}


def test_no_note_when_no_share_is_removed(d26b_config):
    r = decide(_ev(_market(stock("YLDZ"), "Z")), load_persona("P03"), d26b_config,
               created_at=T0)
    assert not [n for n in r.data_quality if "pazarında" in n.message]


def test_without_exclude_markets_no_share_is_removed(d26_config):
    u = build_universe(_ev(_market(stock("WTCH"), "W")), d26_config)
    assert "stock:WTCH" in u.by_id and u.removed_stock_market == {}


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["stock"].update(exclude_markets="W"), "stock.exclude_markets"),
    (lambda r: r["stock"].update(exclude_markets=["W", ""]), "stock.exclude_markets"),
    (lambda r: r["texts"]["data_quality"].pop("removed_stock_market"), "removed_stock_market"),
    (lambda r: r["texts"]["data_quality"].update(removed_stock_market="{codes}"),
     "removed_stock_market"),
])
def test_bad_d26b_config_is_an_error(d26b_raw, edit, match):
    edit(d26b_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d26b_raw)


def _hisse_band(cfg, *products):
    raw = copy.deepcopy(dict(cfg.raw))
    raw["allocation"] = copy.deepcopy(ALLOCATION)
    r = decide(_ev(*products), load_persona("P03"), parse_config(raw), created_at=T0)
    return next(b for b in r.allocation if b.asset_class == "hisse"), r


def test_the_class_example_is_never_a_share(d26_config):
    band, r = _hisse_band(d26_config, stock("TOP", returns={"1y": 500.0}),
                          etf("EF", returns={"1y": 20.0}))
    ranked = [o.option.option_id for o in r.options if o.option.asset_class == "hisse"]
    assert ranked[0] == "stock:TOP"              # the share is the best hisse option ...
    assert band.option_id == "etf:EF"            # ... but the example is the ETF


def test_a_class_with_only_shares_has_no_example(d26_config):
    band, r = _hisse_band(d26_config, stock("TOP"))
    assert any(o.option.option_id == "stock:TOP" for o in r.options)
    assert band.option_id is None and band.note == "none"


# --- a share in a crash (lead, 2026-10-14; the user: a warning, not an exclusion) ------------

CRASH = ("{name}: son 1 ayda %{ret:.0f} değer kaybı (art arda taban fiyat olabilir); "
         "şirket haberlerini kontrol edin.")


def _crash_config(d26_raw, limit=-50):
    d26_raw["stock"]["crash_1m_pct"] = limit
    d26_raw["texts"]["warnings"]["stock_crash"] = CRASH
    return parse_config(d26_raw)


def test_a_share_in_a_crash_gets_a_warning_and_stays(d26_raw):
    cfg = _crash_config(d26_raw)
    crash = stock("CRSH", returns={"1m": -88.0, "3m": -80.0, "6m": 200.0, "1y": 900.0},
                  name="CRASH HOLDING")
    r = decide(_ev(crash, stock("OKAY")), load_persona("P03"), cfg, created_at=T0)
    assert "stock:CRSH" in _by_id(r)                         # not excluded
    [w] = [w for w in r.warnings if w.code == "stock_crash"]
    assert w.option_ids == ("stock:CRSH",) and w.audience == "rm"
    assert w.message == "CRASH HOLDING: son 1 ayda %-88 değer kaybı (art arda taban fiyat olabilir); şirket haberlerini kontrol edin."
    ev = {d.id: d for d in _ev(crash).datapoints}
    [eid] = w.evidence_ids
    assert ev[eid].quantity == "stock_return_1m" and ev[eid].entity == "CRSH"


def test_no_crash_warning_above_the_limit_or_without_the_key(d26_raw, d26_config):
    small = stock("DOWN", returns={"1m": -49.0, "3m": -40.0, "6m": 10.0, "1y": 30.0})
    r = decide(_ev(small), load_persona("P03"), _crash_config(d26_raw), created_at=T0)
    assert not [w for w in r.warnings if w.code == "stock_crash"]
    big = stock("CRSH", returns={"1m": -88.0, "3m": -80.0, "6m": 200.0, "1y": 900.0})
    r = decide(_ev(big), load_persona("P03"), d26_config, created_at=T0)   # no crash_1m_pct
    assert not [w for w in r.warnings if w.code == "stock_crash"]


def test_crash_limit_needs_its_text_and_a_negative_value(d26_raw):
    d26_raw["texts"]["warnings"].pop("stock_crash", None)     # the real config has the text
    d26_raw["stock"]["crash_1m_pct"] = -50
    with pytest.raises(ConfigError, match="stock_crash"):
        parse_config(d26_raw)
    d26_raw["texts"]["warnings"]["stock_crash"] = CRASH
    d26_raw["stock"]["crash_1m_pct"] = 10
    with pytest.raises(ConfigError, match="crash_1m_pct"):
        parse_config(d26_raw)
    d26_raw["stock"]["crash_1m_pct"] = -50
    d26_raw["warnings"]["audience"] = {"stock_crash": "client"}
    with pytest.raises(ConfigError, match="warnings.audience.stock_crash"):
        parse_config(d26_raw)
