"""The estimate of the client's current split (docs/decision.md section 17, D27;
spec docs/superpowers/specs/2026-10-14-portfolio-projection-design.md section 4)."""

import copy
import dataclasses

import pytest

from rmprep.contracts import ALLOCATION_CLASSES, HoldingsInput
from rmprep.decision.config import ConfigError, parse_config
from rmprep.decision.holdings import estimate, holdings_status
from tests.decision.conftest import load_persona
from tests.decision.test_allocation import ALLOCATION

TCMB = "TCMB Finansal İstikrar Raporu 2026-I, Tablo III.1.2 (Mart 2026)"


def _shares(n, b, h, a, d):
    return dict(zip(ALLOCATION_CLASSES, (n, b, h, a, d)))


D27_SECTIONS = {
    "holdings": {
        "national": {"label": "Türkiye hanehalkı ortalaması", "source": TCMB,
                     "url": "https://www.tcmb.gov.tr/finansal-istikrar-raporu",
                     "shares": _shares(39, 10, 10, 30, 11)},
        "profiles": [
            {"match": ["emekli"], "label": "Emekli", "rule": "ulusal ortalamadan, daha fazla "
             "borçlanma aracı", "source": "varsayım", "shares": _shares(32, 22, 10, 26, 10)},
            {"match": ["ihracatçı", "şirket sahibi"], "label": "İhracatçı şirket sahibi",
             "rule": "döviz geliri: daha fazla altın/döviz", "source": "varsayım",
             "shares": _shares(22, 22, 13, 33, 10)},
            {"match": ["teknoloji kurucusu", "kurucu"], "label": "Teknoloji kurucusu",
             "rule": "nakit ağırlıklı", "source": "varsayım", "shares": _shares(45, 12, 20, 15, 8)},
            {"match": ["aile ofisi"], "label": "Aile ofisi", "rule": "UBS GFO 2025, Orta Doğu",
             "source": "varsayım", "shares": _shares(15, 28, 27, 15, 15)},
            {"match": ["hekim", "doktor"], "label": "Hekim", "rule": "ulusal ortalamadan",
             "source": "varsayım", "shares": _shares(28, 12, 13, 25, 22)},
        ],
        "text_rules": [
            {"id": "mevduat_agirlikli", "fields": ["durum"], "match": "mevduat ağırlıklı",
             "class": "nakit_benzeri", "range": [60, 90]},
            {"id": "sirket_satisi_nakit", "fields": ["durum"],
             "match": "şirket satışından gelen nakdi", "class": "nakit_benzeri", "range": [50, 100]},
        ],
        "spread": 5,
    },
    "allocation_gap": {
        "scale": 30, "overweight_factor": 0.5, "per_signal": 0.5, "max_signals": 2,
        "source_factor": {"rm": 1.0, "rm_confirmed": 0.75, "persona_text": 0.75},
        "signals": ["çeşitlendirme", "mevduat yoğunluğunu azalt",
                    "tek ürün veya tek varlık sınıfında yoğunlaşmama", "fırsat maliyetini azaltma"],
    },
}
D27_TEXTS = {
    "reasons": {
        "allocation_gap": "{class_label} payı {source_label} %{current:.0f}; {profile} model "
                          "bandı %{low:.0f}–{high:.0f}.",
        "allocation_gap_inactive": "{class_label} payı bilinmiyor (tahmini senaryo); RM onayı "
                                   "bekleniyor.",
        "allocation_gap_no_band": "{class_label} için model bandı yok; portföy açığı "
                                  "hesaplanmadı.",
    },
    "holdings": {
        "source_labels": {"rm": "RM'e göre", "rm_confirmed": "RM onaylı tahmine göre",
                          "persona_text": "persona metnine göre"},
        "class_labels": {"nakit_benzeri": "Nakit benzeri", "borclanma": "Borçlanma araçları",
                         "hisse": "Hisse senedi", "altin_doviz": "Altın ve döviz",
                         "dengeli": "Dengeli fon"},
        "to_confirm": "Müşterinin mevcut portföy dağılımını alın (şu an tahmini senaryo).",
    },
}


def add_d27(raw: dict) -> dict:
    """Add the D27 config (plan Task 3) and texts to a raw config with D19 and D20."""
    raw.setdefault("allocation", copy.deepcopy(ALLOCATION))
    raw.update(copy.deepcopy(D27_SECTIONS))
    raw["weights"]["allocation_gap"] = {"base": 1.0}
    raw["texts"]["reasons"].update(D27_TEXTS["reasons"])
    raw["texts"]["holdings"] = copy.deepcopy(D27_TEXTS["holdings"])
    return raw


def strip_d27(raw: dict) -> dict:
    """A copy without the D27 keys (they will be in config/decision.yaml)."""
    raw = copy.deepcopy(raw)
    for key in ("holdings", "allocation_gap"):
        raw.pop(key, None)
    raw["weights"].pop("allocation_gap", None)
    raw["texts"].pop("holdings", None)
    for key in D27_TEXTS["reasons"]:
        raw["texts"]["reasons"].pop(key, None)
    return raw


@pytest.fixture
def d27_raw(d19_raw) -> dict:
    return add_d27(d19_raw)


@pytest.fixture
def cfg(d27_raw):
    return parse_config(d27_raw)


def _p(pid, **changes):
    return dataclasses.replace(load_persona(pid), **changes)


def _by_class(est):
    return {e.asset_class: e for e in est}


# --- estimate -------------------------------------------------------------------------------

def test_national_default_when_nothing_matches(cfg):
    est = estimate(_p("P05", profil="Mimar"), cfg, None)
    assert [e.asset_class for e in est] == list(ALLOCATION_CLASSES)
    assert [e.source for e in est] == ["national"] * 5
    assert [e.point for e in est] == [39.0, 10.0, 10.0, 30.0, 11.0]
    assert sum(e.point for e in est) == 100.0
    e = _by_class(est)["hisse"]
    assert (e.low, e.high) == (5.0, 15.0) and e.ref == "Türkiye hanehalkı ortalaması"


def test_profile_row(cfg):
    est = _by_class(estimate(_p("P03", durum="Yatırım yapıyor"), cfg, None))
    assert est["nakit_benzeri"].point == 45.0 and est["hisse"].point == 20.0
    assert est["hisse"].source == "profile" and est["hisse"].ref == "Teknoloji kurucusu"


def test_first_matching_profile_wins(cfg):
    est = _by_class(estimate(_p("P05", profil="Emekli hekim", durum="x"), cfg, None))
    assert est["borclanma"].point == 22.0 and est["borclanma"].ref == "Emekli"


def test_text_rule_and_rest_in_base_proportions(cfg):
    est = _by_class(estimate(load_persona("P01"), cfg, None))     # "Emekli girişimci"
    n = est["nakit_benzeri"]
    assert (n.point, n.low, n.high, n.source, n.ref) == (75.0, 60.0, 90.0, "persona_text",
                                                         "mevduat_agirlikli")
    rest = {k: e for k, e in est.items() if k != "nakit_benzeri"}
    assert round(sum(e.point for e in rest.values()), 1) == 25.0
    assert {e.source for e in rest.values()} == {"profile"}
    # emekli base 22/10/26/10 (sum 68) scaled to 25 points
    assert rest["altin_doviz"].point == pytest.approx(25 * 26 / 68, abs=0.11)
    assert rest["hisse"].low == 0.0 and rest["hisse"].high == pytest.approx(
        rest["hisse"].point + 5)
    assert round(sum(e.point for e in est.values()), 1) == 100.0


def test_text_rule_of_p03(cfg):
    est = _by_class(estimate(load_persona("P03"), cfg, None))
    assert est["nakit_benzeri"].point == 75.0 and est["nakit_benzeri"].source == "persona_text"


def test_text_rule_turkish_case(cfg):
    loud = _p("P01", durum="VARLIĞI TL MEVDUAT AĞIRLIKLI")
    assert estimate(loud, cfg, None)[0].source == "persona_text"


def test_text_rule_in_a_list_field(d27_raw):
    d27_raw["holdings"]["text_rules"].append(
        {"id": "kirli", "fields": ["oncelikler"], "match": "SINIRLI DALGALANMA",
         "class": "borclanma", "range": [10, 20]})
    est = _by_class(estimate(load_persona("P01"), parse_config(d27_raw), None))
    assert est["borclanma"].source == "persona_text" and est["borclanma"].point == 15.0


def test_text_rules_capped(cfg):
    """Two rules on one class: the first wins; the text points never pass 100."""
    raw = copy.deepcopy(dict(cfg.raw))
    raw["holdings"]["text_rules"] += [
        {"id": "again", "fields": ["durum"], "match": "mevduat", "class": "nakit_benzeri",
         "range": [95, 100]},
        {"id": "fx", "fields": ["durum"], "match": "tl", "class": "altin_doviz",
         "range": [60, 100]}]
    est = _by_class(estimate(load_persona("P01"), parse_config(raw), None))
    assert est["nakit_benzeri"].point == 75.0 and est["nakit_benzeri"].ref == "mevduat_agirlikli"
    a = est["altin_doviz"]
    assert a.point == 25.0 and a.source == "persona_text"     # capped: 75 + 80 > 100 -> 25
    assert a.low <= a.point <= a.high
    assert round(sum(e.point for e in est.values()), 1) == 100.0
    assert all(e.point == 0.0 for k, e in est.items() if k not in ("nakit_benzeri",
                                                                    "altin_doviz"))


def test_rm_input_replaces_all(cfg):
    h = HoldingsInput(_shares(20, 60, 10, 10, 0), "rm")
    est = estimate(load_persona("P01"), cfg, h)
    assert {e.source for e in est} == {"rm"}
    assert est[1].point == 60.0 and est[1].low == est[1].high == 60.0
    assert holdings_status(est) == "rm"


def test_rm_confirmed_and_a_total_within_the_tolerance(cfg):
    h = HoldingsInput(_shares(20, 60, 10, 10, 0.4), "rm_confirmed")
    est = estimate(load_persona("P01"), cfg, h)
    assert {e.source for e in est} == {"rm_confirmed"}
    assert round(sum(e.point for e in est), 1) == 100.0       # the rest from the largest class
    assert holdings_status(est) == "rm_confirmed"


@pytest.mark.parametrize("pid, status", [("P01", "persona_text"), ("P03", "persona_text"),
                                         ("P02", "estimate"), ("P04", "estimate"),
                                         ("P05", "estimate")])
def test_holdings_status(cfg, pid, status):
    assert holdings_status(estimate(load_persona(pid), cfg, None)) == status


def test_rounding_keeps_the_text_point(cfg):
    for pid in ("P01", "P02", "P03", "P04", "P05"):
        est = estimate(load_persona(pid), cfg, None)
        assert round(sum(e.point for e in est), 1) == 100.0
        for e in est:
            assert 0 <= e.low <= e.point <= e.high <= 100
            assert e.point == round(e.point, 1)


def test_without_config_no_estimate(d27_raw):
    assert estimate(load_persona("P01"), parse_config(strip_d27(d27_raw)), None) == ()


# --- config checks ----------------------------------------------------------------------------

def test_d27_config_is_valid(cfg):
    assert cfg.raw["holdings"]["spread"] == 5


@pytest.mark.parametrize("edit, match", [
    (lambda r: r["holdings"].pop("national"), "holdings"),
    (lambda r: r["holdings"]["national"]["shares"].update(dengeli=12), "holdings.national.shares"),
    (lambda r: r["holdings"]["national"]["shares"].pop("dengeli"), "holdings.national.shares"),
    (lambda r: r["holdings"]["profiles"][0].update(match=[]), r"holdings.profiles\[0\]"),
    (lambda r: r["holdings"]["profiles"][1]["shares"].update(hisse=-1, nakit_benzeri=36),
     r"holdings.profiles\[1\].shares"),
    (lambda r: r["holdings"]["text_rules"][0].update(fields=["no_such_field"]),
     r"holdings.text_rules\[0\].fields"),
    (lambda r: r["holdings"]["text_rules"][0].update(range=[90, 60]),
     r"holdings.text_rules\[0\].range"),
    (lambda r: r["holdings"]["text_rules"][0].update({"class": "gayrimenkul"}),
     r"holdings.text_rules\[0\].class"),
    (lambda r: r["holdings"]["text_rules"][1].update(id="mevduat_agirlikli"),
     r"holdings.text_rules\[1\].id"),
    (lambda r: r["holdings"].update(spread=-1), "holdings.spread"),
    (lambda r: r.pop("allocation"), "allocation"),
    (lambda r: r["allocation_gap"].update(scale=0), "allocation_gap.scale"),
    (lambda r: r["allocation_gap"]["source_factor"].pop("persona_text"),
     "allocation_gap.source_factor"),
    (lambda r: r["allocation_gap"].update(max_signals=-1), "allocation_gap.max_signals"),
    (lambda r: r["allocation_gap"].update(signals="x"), "allocation_gap.signals"),
    (lambda r: r["weights"].pop("allocation_gap"), "weights.allocation_gap"),
    (lambda r: r["texts"]["holdings"]["class_labels"].pop("dengeli"), "texts.holdings"),
    (lambda r: r["texts"]["holdings"].pop("to_confirm"), "texts.holdings"),
    (lambda r: r["texts"]["reasons"].pop("allocation_gap_inactive"), "allocation_gap_inactive"),
    (lambda r: r["texts"]["reasons"].update(allocation_gap="{amount}"), "allocation_gap"),
])
def test_bad_d27_config_is_an_error(d27_raw, edit, match):
    edit(d27_raw)
    with pytest.raises(ConfigError, match=match):
        parse_config(d27_raw)
