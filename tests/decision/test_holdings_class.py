"""Asset class from the holdings (docs/decision.md section 13, D23)."""

import copy
from datetime import date

import pytest

from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.engine import decide
from rmprep.decision.universe import build_universe, fold
from tests.decision.conftest import (
    T0,
    d9_rows,
    dp,
    load_persona,
    make_evidence,
)

# the label table of scripts/analysis/varlik_impact.py (2026-10-14)
LABELS = {
    "nakit_benzeri": ["Ters-Repo", "Repo", "Mevduat (TL)", "Katılma Hesabı (TL)",
                      "Takasbank Para Piyasası", "Borsa İstanbul Para Piyasası",
                      "BİST Taahhütlü İşlem Pazarı Alım", "BİST Taahhütlü İşlem Pazarı Satım"],
    "borclanma": ["Devlet Tahvili", "Hazine Bonosu", "Özel Sektör Tahvili", "Finansman Bonosu",
                  "Özel Sektör Kira Sertifikaları", "Kamu Kira Sertifikaları (TL)",
                  "Varlığa Dayalı Menkul Kıymetler"],
    "hisse": ["Hisse Senedi", "Yabancı Hisse Senedi", "Yabancı Borsa Yatırım Fonları"],
    "altin_doviz": ["Kıymetli Madenler", "Kıymetli Madenler Cinsinden BYF",
                    "Mevduat (Döviz)", "Mevduat (Altın)", "Kamu Dış Borçlanma Araçları",
                    "Yabancı Kamu Borçlanma Araçları"],
    "fon": ["Yatırım Fonları Katılma Payları", "Borsa Yatırım Fonları Katılma Payları"],
    "ignore": ["Diğer", "Vadeli İşlemler Nakit Teminatları"],
}
CLASS_LABELS = {"nakit_benzeri": "nakit benzeri", "borclanma": "borçlanma araçları",
                "hisse": "hisse senedi", "altin_doviz": "altın ve döviz"}
BY_HOLDINGS = {"kinds": ["variable", "mixed", "fund_of_funds", "participation"],
               "fx_debt_kinds": ["debt"], "min_share": 50, "labels": LABELS,
               "class_labels": CLASS_LABELS}
REASON = "Varlık sınıfı: portföyün %{share:.0f}'i {label} (TEFAS portföy dağılımı)."
UNKNOWN = "Bilinmeyen portföy varlık türü \"{text}\": {count} fonda dikkate alınmadı."
FULL = dict(returns={"1y": 40.0, "3y": 150.0}, size=2e8, investors=500)


def add_d23(raw: dict) -> dict:
    """Add the D23 config (section 13) and texts to a raw config with asset_classes."""
    raw["asset_classes"]["by_holdings"] = copy.deepcopy(BY_HOLDINGS)
    raw["asset_classes"]["by_name"]["ALTIN"] = "altin_doviz"
    raw["texts"]["reasons"]["holdings_class"] = REASON
    raw["texts"]["data_quality"]["unknown_holding_type"] = UNKNOWN
    return raw


@pytest.fixture
def d23_raw(d19_raw) -> dict:
    return add_d23(d19_raw)


@pytest.fixture
def d23_config(d23_raw):
    return parse_config(d23_raw)


def hold(code, shares, as_of=date(2026, 10, 9)):
    """Holdings rows of one fund (ingest I8): entity "<code>/<kiymetTip>", value = %."""
    return [dp("fund_holding_share", f"{code}/{tip}", v, source="tefas_detail", as_of=as_of)
            for tip, v in shares.items()]


def _ev(funds, holdings=()):
    return make_evidence(funds, extra=[*d9_rows(), *holdings])


def _classes(ev, cfg):
    return {c.option.entity: c.option.asset_class for c in build_universe(ev, cfg).candidates
            if c.option.kind == "fund"}


# --- the class ------------------------------------------------------------------------

def test_variable_fund_with_80_percent_equities_is_hisse(d23_config):
    ev = _ev({"VR": dict(kind="variable", risk=5, **FULL)},
             hold("VR", {"Hisse Senedi": 80.0, "Ters-Repo": 20.0}))
    assert _classes(ev, d23_config)["VR"] == "hisse"


def test_no_class_reaches_the_min_share_gives_dengeli(d23_config):
    ev = _ev({"VR": dict(kind="variable", risk=4, **FULL)},
             hold("VR", {"Hisse Senedi": 45.0, "Devlet Tahvili": 40.0, "Ters-Repo": 15.0}))
    assert _classes(ev, d23_config)["VR"] == "dengeli"


def test_fund_share_majority_keeps_the_old_rule(d23_config):
    # participation: by_kind borclanma; fund shares (no look-through) -> old rule
    ev = _ev({"KT": dict(kind="participation", risk=3, **FULL)},
             hold("KT", {"Yatırım Fonları Katılma Payları": 70.0, "Hisse Senedi": 30.0}))
    assert _classes(ev, d23_config)["KT"] == "borclanma"


def test_money_market_fund_keeps_its_umbrella_class(d23_config):
    ev = _ev({"PP": dict(kind="money_market", risk=1, **FULL)},
             hold("PP", {"Devlet Tahvili": 90.0, "Ters-Repo": 10.0}))
    assert _classes(ev, d23_config)["PP"] == "nakit_benzeri"


def test_equity_fund_with_a_cash_day_stays_hisse(d23_config):
    ev = _ev({"HS": dict(kind="equity", risk=6, **FULL)}, hold("HS", {"Ters-Repo": 100.0}))
    assert _classes(ev, d23_config)["HS"] == "hisse"


def test_debt_fund_with_fx_debt_is_altin_doviz(d23_config):
    ev = _ev({"FX": dict(kind="debt", risk=3, **FULL), "TL": dict(kind="debt", risk=3, **FULL)},
             [*hold("FX", {"Kamu Dış Borçlanma Araçları": 90.0, "Ters-Repo": 10.0}),
              *hold("TL", {"Devlet Tahvili": 90.0, "Ters-Repo": 10.0})])
    classes = _classes(ev, d23_config)
    assert classes["FX"] == "altin_doviz"
    assert classes["TL"] == "borclanma"


def test_debt_fund_with_an_equity_majority_keeps_the_old_rule(d23_config):
    ev = _ev({"DB": dict(kind="debt", risk=3, **FULL)}, hold("DB", {"Hisse Senedi": 90.0}))
    assert _classes(ev, d23_config)["DB"] == "borclanma"


def test_name_rule_wins_over_the_holdings(d23_config):
    ev = _ev({"AL": dict(kind="variable", risk=5, name="X ALTIN DEĞİŞKEN FONU", **FULL)},
             hold("AL", {"Hisse Senedi": 80.0, "Ters-Repo": 20.0}))
    assert _classes(ev, d23_config)["AL"] == "altin_doviz"


def test_holdings_win_over_by_risk(d23_raw):
    d23_raw["asset_classes"]["by_risk"] = {"participation": [{"min_risk": 5, "class": "hisse"}]}
    cfg = parse_config(d23_raw)
    ev = _ev({"KT": dict(kind="participation", risk=6, **FULL)},
             hold("KT", {"Özel Sektör Kira Sertifikaları": 70.0, "Hisse Senedi": 30.0}))
    assert _classes(ev, cfg)["KT"] == "borclanma"


def test_ignore_and_negative_shares_do_not_count(d23_config):
    # hisse 40 of a counted total 40 + 30 = 70 -> 57 %; Diğer and Repo -30 do not count
    ev = _ev({"VR": dict(kind="variable", risk=5, **FULL)},
             hold("VR", {"Hisse Senedi": 40.0, "Devlet Tahvili": 30.0, "Diğer": 60.0,
                         "Repo": -30.0}))
    assert _classes(ev, d23_config)["VR"] == "hisse"


def test_only_ignored_rows_keep_the_old_rule(d23_config):
    ev = _ev({"KT": dict(kind="participation", risk=3, **FULL)},
             hold("KT", {"Diğer": 100.0}))
    assert _classes(ev, d23_config)["KT"] == "borclanma"


def test_only_the_latest_day_counts(d23_config):
    old = hold("VR", {"Hisse Senedi": 90.0}, as_of=date(2026, 10, 8))
    new = hold("VR", {"Devlet Tahvili": 80.0, "Ters-Repo": 20.0})
    ev = _ev({"VR": dict(kind="variable", risk=4, **FULL)}, [*old, *new])
    assert _classes(ev, d23_config)["VR"] == "borclanma"


# --- matching -----------------------------------------------------------------------------

def test_fold_keeps_only_ascii_letters_and_digits():
    assert fold("Kıymetli Madenler (BYF)") == "kymetlimadenlerbyf"
    assert fold("K�ymetli Madenler (BYF)") == "kymetlimadenlerbyf"
    assert fold("HİSSE SENEDİ") == fold("Hisse Senedi")


def test_spelling_variants_match(d23_config):
    ev = _ev({"VR": dict(kind="variable", risk=5, **FULL),
              "AD": dict(kind="variable", risk=5, **FULL)},
             [*hold("VR", {"HİSSE SENEDİ": 80.0, "ters repo": 20.0}),
              *hold("AD", {"K�ymetli Madenler": 70.0, "Hisse Senedi": 30.0})])
    classes = _classes(ev, d23_config)
    assert classes["VR"] == "hisse"
    assert classes["AD"] == "altin_doviz"


def test_unknown_text_is_ignored_and_noted(d23_config):
    ev = _ev({"V1": dict(kind="variable", risk=5, **FULL),
              "V2": dict(kind="variable", risk=5, **FULL)},
             [*hold("V1", {"Yeni Tür": 60.0, "Hisse Senedi": 40.0}),
              *hold("V2", {"Yeni Tür": 10.0, "Hisse Senedi": 90.0})])
    assert set(_classes(ev, d23_config).values()) == {"hisse"}
    r = decide(ev, load_persona("P04"), d23_config, created_at=T0)
    [note] = [n for n in r.data_quality if "Yeni Tür" in n.message]
    assert note.message == UNKNOWN.format(text="Yeni Tür", count=2)
    assert note.evidence_ids == tuple(sorted(d.id for d in ev.datapoints
                                             if d.entity.endswith("/Yeni Tür")))


def test_unknown_text_of_a_fund_kind_without_holdings_rule_is_not_noted(d23_config):
    ev = _ev({"HS": dict(kind="equity", risk=6, **FULL)}, hold("HS", {"Yeni Tür": 100.0}))
    r = decide(ev, load_persona("P04"), d23_config, created_at=T0)
    assert not [n for n in r.data_quality if "Yeni Tür" in n.message]


# --- reason and evidence ------------------------------------------------------------------

def test_reason_with_the_evidence_ids(d23_config):
    rows = hold("VR", {"Hisse Senedi": 60.0, "Yabancı Hisse Senedi": 20.0, "Ters-Repo": 20.0})
    ev = _ev({"VR": dict(kind="variable", risk=5, **FULL)}, rows)
    r = decide(ev, load_persona("P04"), d23_config, created_at=T0)
    [o] = [o for o in r.options if o.option.option_id == "fund:VR"]
    assert o.option.asset_class == "hisse"
    text = REASON.format(share=80, label="hisse senedi")
    assert text in " ".join(o.reasons.values())
    equity = {d.id for d in rows if "Hisse" in d.entity}
    assert equity <= set(o.evidence_ids)
    assert not {d.id for d in rows if "Repo" in d.entity} & set(o.evidence_ids)
    assert set(o.reasons) == set(o.score_parts)                     # reason keys unchanged


def test_dengeli_from_the_holdings_has_no_class_reason(d23_config):
    rows = hold("VR", {"Hisse Senedi": 45.0, "Devlet Tahvili": 40.0, "Ters-Repo": 15.0})
    ev = _ev({"VR": dict(kind="variable", risk=4, **FULL)}, rows)
    r = decide(ev, load_persona("P04"), d23_config, created_at=T0)
    [o] = [o for o in r.options if o.option.option_id == "fund:VR"]
    assert "Varlık sınıfı" not in " ".join(o.reasons.values())
    assert not {d.id for d in rows} & set(o.evidence_ids)


def test_option_of_the_old_rule_has_no_class_reason(d23_config):
    ev = _ev({"PP": dict(kind="money_market", risk=1, **FULL)},
             hold("PP", {"Devlet Tahvili": 90.0, "Ters-Repo": 10.0}))
    r = decide(ev, load_persona("P04"), d23_config, created_at=T0)
    [o] = [o for o in r.options if o.option.option_id == "fund:PP"]
    assert "Varlık sınıfı" not in " ".join(o.reasons.values())


# --- no holdings rows, no config ----------------------------------------------------------

FUNDS = {"VR": dict(kind="variable", risk=5, **FULL), "DB": dict(kind="debt", risk=3, **FULL),
         "PP": dict(kind="money_market", risk=1, **FULL), "HS": dict(kind="equity", risk=6, **FULL)}


def _summary(r):
    return [(o.option.option_id, o.option.asset_class, o.score, o.evidence_ids, o.reasons)
            for o in r.options], r.recommended, r.data_quality


def test_no_holdings_rows_give_todays_result(d19_raw, d23_config):
    d19_raw["asset_classes"].pop("by_holdings", None)
    old = parse_config(d19_raw)
    for pid in ("P01", "P04"):
        a = decide(_ev(FUNDS), load_persona(pid), old, created_at=T0)
        b = decide(_ev(FUNDS), load_persona(pid), d23_config, created_at=T0)
        assert _summary(a) == _summary(b)


def test_without_config_holdings_rows_change_nothing(d19_raw):
    d19_raw["asset_classes"].pop("by_holdings", None)
    cfg = parse_config(d19_raw)
    rows = hold("VR", {"Hisse Senedi": 80.0, "Ters-Repo": 20.0})
    a = decide(_ev(FUNDS), load_persona("P04"), cfg, created_at=T0)
    b = decide(_ev(FUNDS, rows), load_persona("P04"), cfg, created_at=T0)
    assert _summary(a) == _summary(b)


def test_holdings_rows_are_not_funds(d19_raw):
    """A holdings entity "<code>/<kiymetTip>" is not a fund code (no 'no entity' count)."""
    d19_raw["asset_classes"].pop("by_holdings", None)
    ev = _ev(FUNDS, hold("VR", {"Hisse Senedi": 80.0, "Ters-Repo": 20.0}))
    u = build_universe(ev, parse_config(d19_raw))
    assert u.removed_no_entity == ()
    assert sorted(c.option.entity for c in u.candidates if c.option.kind == "fund") == \
        sorted(FUNDS)


def test_class_rule_and_risk_estimate_use_the_holdings_class(d23_config):
    # the class is on the ProductOption, which D19-D21 read
    ev = _ev(FUNDS, hold("VR", {"Hisse Senedi": 80.0, "Ters-Repo": 20.0}))
    r = decide(ev, load_persona("P04"), d23_config, created_at=T0)
    by_id = {o.option.option_id: o for o in r.options}
    assert by_id["fund:VR"].option.asset_class == "hisse"
    assert len({by_id[i].option.asset_class for i in r.recommended}) == len(r.recommended)


# --- config checks ------------------------------------------------------------------------

def test_d23_config_is_valid(d23_config):
    assert d23_config.raw["asset_classes"]["by_holdings"]["min_share"] == 50


@pytest.mark.parametrize("edit,match", [
    (lambda r: r["asset_classes"]["by_holdings"].pop("labels"), "by_holdings"),
    (lambda r: r["asset_classes"]["by_holdings"].update(extra=1), "by_holdings"),
    (lambda r: r["asset_classes"]["by_holdings"].update(kinds=["no_such_kind"]),
     "by_holdings.kinds"),
    (lambda r: r["asset_classes"]["by_holdings"].update(fx_debt_kinds="debt"),
     "by_holdings.fx_debt_kinds"),
    (lambda r: r["asset_classes"]["by_holdings"].update(min_share=0), "by_holdings.min_share"),
    (lambda r: r["asset_classes"]["by_holdings"].update(min_share=101),
     "by_holdings.min_share"),
    (lambda r: r["asset_classes"]["by_holdings"]["labels"].update(
        hisse=["Hisse Senedi", "HİSSE SENEDİ"]), "by_holdings.labels"),
    (lambda r: r["asset_classes"]["by_holdings"]["labels"].update(
        borclanma=["Devlet Tahvili", "Hisse Senedi"]), "by_holdings.labels"),
    (lambda r: r["asset_classes"]["by_holdings"]["labels"].update(hisse=[]),
     "by_holdings.labels.hisse"),
    (lambda r: r["asset_classes"]["by_holdings"]["labels"].update(hisse=["(%)"]),
     "by_holdings.labels.hisse"),
    (lambda r: r["asset_classes"]["by_holdings"]["class_labels"].pop("hisse"),
     "by_holdings.class_labels"),
    (lambda r: r["texts"]["reasons"].pop("holdings_class"), "holdings_class"),
    (lambda r: r["texts"]["reasons"].update(holdings_class="%{pct}"), "holdings_class"),
    (lambda r: r["texts"]["data_quality"].pop("unknown_holding_type"), "unknown_holding_type"),
    (lambda r: r["texts"]["data_quality"].update(unknown_holding_type="{fund}"),
     "unknown_holding_type"),
])
def test_bad_d23_config_is_an_error(d23_raw, edit, match):
    edit(d23_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d23_raw)
