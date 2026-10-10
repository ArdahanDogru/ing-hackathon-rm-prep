import copy
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from rmprep.contracts import TR_TZ, DataPoint, EntityInfo, EvidenceSet, Persona
from rmprep.decision.config import load_raw, parse_config

CONTRACT_FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PERSONA_IDS = ["P01", "P02", "P03", "P04", "P05"]
T0 = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)

_UNITS = {"fund_risk_level": "level", "fund_total_value": "TRY", "fund_investor_count": "count",
          "deposit_rate": "percent", "fund_buyable": "flag", "fund_sell_valor_days": "days",
          "fund_buy_valor_days": "days", "fund_entry_fee": "pct", "fund_exit_fee": "pct"}
_SOURCES = {"fund_total_value": "tefas", "fund_investor_count": "tefas", "fund_price": "tefas",
            "fund_buyable": "tefas_detail", "fund_sell_valor_days": "tefas_detail",
            "fund_buy_valor_days": "tefas_detail", "fund_entry_fee": "tefas_detail",
            "fund_exit_fee": "tefas_detail"}


def dp(quantity: str, entity: str, value: float | None, *, as_of: date = date(2026, 10, 9),
       source: str | None = None, flags=()) -> DataPoint:
    """A hand-made DataPoint; the source defaults to where ingest puts the quantity."""
    if source is None:
        source = _SOURCES.get(quantity, "tefas_web" if quantity.startswith("fund_") else "manual")
    if value is None:
        flags = (*flags, "missing")
    return DataPoint.create(
        quantity=quantity, entity=entity, value=value, unit=_UNITS.get(quantity, "percent"),
        as_of=as_of, source=source, source_url="https://example.test/", fetched_at=T0,
        snapshot_id="S-test", raw_ref=f"S-test/{quantity}/{entity}", flags=flags)


def load_persona(pid: str) -> Persona:
    path = CONTRACT_FIX / "personas" / f"{pid.lower()}.json"
    return Persona.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_evidence(name: str = "evidence_medium.json") -> EvidenceSet:
    return EvidenceSet.from_dict(json.loads((CONTRACT_FIX / name).read_text(encoding="utf-8")))


def strip_d9(raw: dict) -> dict:
    """The config without the D9-D13 additions (real return, real_loss, long
    horizon, deposit quality, return weight 1 + appetite; underperformance, the
    diversity pool; fund detail; constraint rules), so the hand-computed values of
    the D1-D8 tests do not change when the lead adds them to config/decision.yaml."""
    raw = copy.deepcopy(raw)
    for key in ("real_return", "long_horizon", "quality_value", "underperformance",
                "fund_detail", "constraint_rules"):
        raw.pop(key, None)
    for key in ("real_loss", "underperformance"):
        raw["penalties"].pop(key, None)
    for key in ("pool", "diversity_pool_cap"):
        raw["display"].pop(key, None)
    if "time_deposit" in raw:
        raw["time_deposit"].pop("term_days", None)
    raw["weights"]["return"] = {"base": 1.0, "appetite": 1.0}
    return raw


@pytest.fixture(scope="session")
def project_raw() -> dict:
    """config/decision.yaml as it is."""
    return load_raw()


@pytest.fixture(scope="session")
def raw_config(project_raw) -> dict:
    return strip_d9(project_raw)


@pytest.fixture
def raw(raw_config) -> dict:
    """A deep copy of the pre-D9 config (strip_d9) that a test may change."""
    return copy.deepcopy(raw_config)


@pytest.fixture(scope="session")
def config(raw_config):
    return parse_config(raw_config)


DEP = "ING Turuncu Hesap standart, 100.000-249.999 TL"
TD = "ING e-Vadeli Mevduat, 32-45 gün, 99.999,99-250.000 TL"
# config/decision.yaml additions for the time deposit (milestone D8; the lead adds
# them on main). Tests that need them use the `td_config` fixture.
TD_SECTION = {"option_id": "time_deposit:ing_e_vadeli", "label": "ING e-Vadeli Mevduat",
              "source": "manual", "quantity": "deposit_rate",
              "entity_prefix": "ING e-Vadeli Mevduat", "term": "32-45 gün",
              "tier": "99.999,99-250.000 TL"}
TD_KIND = {"liquidity": 0.6, "income": 0.9, "simplicity": 1.0}
TD_MISSING_TEXT = ("ING e-Vadeli Mevduat oranı ({entity}) kanıtlarda yok; "
                   "vadeli mevduat seçeneği eklenmedi.")


def add_time_deposit(raw: dict) -> dict:
    """Add the D8 config section to a raw config (in place) and return it."""
    raw.setdefault("time_deposit", dict(TD_SECTION))
    raw["kinds"].setdefault("time_deposit", dict(TD_KIND))
    raw["texts"]["data_quality"].setdefault("time_deposit_missing", TD_MISSING_TEXT)
    return raw


@pytest.fixture
def td_raw(raw) -> dict:
    return add_time_deposit(raw)


@pytest.fixture
def td_config(td_raw):
    return parse_config(td_raw)


# --- D9: real return after tax (the lead adds the same config on main) ---------------

CPI = "TÜFE yıllık değişim (TÜİK)"
STOPAJ = {"deposit": "TL vadesiz mevduat ve günlük hesap (Turuncu Hesap türü)",
          "time_deposit": "TL vadeli mevduat, 6 aya kadar vadeli",
          "fund_default": "Yatırım fonu, diğer fonlar (değişken, borçlanma araçları, fon sepeti)",
          "money_market": "Yatırım fonu, para piyasası fonu"}
D9_TEXTS = {
    "reasons": {
        "return_real": "Yıllık getiri %{nominal:.1f}, stopaj sonrası %{net:.1f}, enflasyon "
                       "sonrası reel %{real:+.1f} ({period}); adayların %{pct:.0f}'inden iyi.",
        "return_net": "Yıllık getiri %{nominal:.1f}, stopaj sonrası %{net:.1f} ({period}); reel "
                      "getiri hesaplanmadı (TÜFE yok); adayların %{pct:.0f}'inden iyi.",
        "penalty:real_loss": "Enflasyon sonrası reel kayıp %{loss:.1f}; müşteri anaparanın "
                             "korunmasını istiyor.",
    },
    "assumptions": {
        "real_return_cpi": "Getiriler stopaj sonrası ve yıllık TÜFE'ye (%{cpi:.2f}, "
                           "{cpi_date}) göre reel olarak hesaplandı.",
        "real_return_no_cpi": "Yıllık TÜFE verisi yok; getiriler stopaj sonrası nominal "
                              "olarak hesaplandı.",
        "stopaj_equity": "Hisse senedi yoğun fonlarda stopaj %0'dır; ihtiyatlı olmak için para "
                         "piyasası dışındaki tüm fonlarda 'diğer fonlar' oranı kullanıldı.",
        "time_deposit_renewal": "{term_days} günlük vade her ay yenilenir; oranlar "
                                "değişebilir.",
    },
    "data_quality": {
        "cpi_missing": "Yıllık TÜFE ({entity}) kanıtlarda yok; reel getiri ve reel kayıp "
                       "cezası hesaplanmadı.",
        "stopaj_missing": "Stopaj oranı kanıtlarda yok: \"{entity}\"; {count} seçenek için "
                          "stopaj %0 alındı.",
    },
}


def add_d9(raw: dict) -> dict:
    """Add the D9 config (exactly the lead's structure) and texts, in place."""
    add_time_deposit(raw)
    raw["real_return"] = {
        "cpi": {"source": "manual", "quantity": "cpi_annual", "entity": CPI},
        "stopaj": {"source": "manual", "quantity": "withholding_tax_rate",
                   "deposit": STOPAJ["deposit"], "time_deposit": STOPAJ["time_deposit"],
                   "fund_default": STOPAJ["fund_default"],
                   "fund_by_kind": {"money_market": STOPAJ["money_market"]}},
        "loss_scale": 0.10,
    }
    raw["time_deposit"]["term_days"] = 32
    raw["penalties"]["real_loss"] = 0.3
    raw["long_horizon"] = {"period": "3y", "liquidity_factor": 0.5, "return_add": 1.0}
    raw["quality_value"] = {"deposit": 0.5, "time_deposit": 0.5}
    raw["weights"]["return"] = {"base": 2.0, "appetite": 2.0}
    for section, texts in D9_TEXTS.items():
        raw["texts"][section].update(texts)
    return raw


@pytest.fixture
def d9_raw(raw) -> dict:
    return add_d9(raw)


@pytest.fixture
def d9_config(d9_raw):
    return parse_config(d9_raw)


# --- D10: underperformance and the diversity pool ----------------------------------------

MARKET = "TRY savings deposit rate up to 3M, weighted average (new deposits)"
D10_TEXTS = {
    "reasons": {
        "penalty:underperformance": "Stopaj sonrası getiri %{net:.1f}, piyasa mevduat "
                                    "ortalamasının (stopaj sonrası %{benchmark:.1f}) altında; "
                                    "müşteri getiri bekliyor.",
    },
    "data_quality": {
        "benchmark_missing": "Piyasa mevduat ortalaması ({entity}) kanıtlarda yok; düşük "
                             "getiri cezası hesaplanmadı.",
    },
}


def add_d10(raw: dict, *, pool: bool = True) -> dict:
    """Add the D10 config (the lead's values) and texts, in place."""
    raw["penalties"]["underperformance"] = 0.3
    raw["underperformance"] = {"scale": 0.20}
    if pool:
        raw["display"].update(pool=20, diversity_pool_cap=4)
    for section, texts in D10_TEXTS.items():
        raw["texts"][section].update(texts)
    return raw


@pytest.fixture
def d10_raw(raw) -> dict:
    return add_d10(add_d9(raw))


@pytest.fixture
def d10_config(d10_raw):
    return parse_config(d10_raw)


# --- D12: fund detail (buyable, sell valör, fees) -------------------------------------------

D12_SECTION = {
    "buyable_quantity": "fund_buyable",
    "sell_valor_quantity": "fund_sell_valor_days",
    "entry_fee_quantity": "fund_entry_fee",
    "exit_fee_quantity": "fund_exit_fee",
    "liquidity_by_sell_valor": [
        {"max_days": 0, "value": 1.0}, {"max_days": 1, "value": 0.9},
        {"max_days": 2, "value": 0.8}, {"max_days": 3, "value": 0.7},
        {"max_days": 5, "value": 0.6}, {"max_days": 10, "value": 0.4},
        {"max_days": None, "value": 0.2},
    ],
}
D12_TEXTS = {
    "constraint": {
        "not_buyable": "Alıma kapalı (TEFAS'ta işlem görmüyor veya alıma kapalı).",
        "buyable": "TEFAS'ta alıma açık.",
    },
    "reasons": {
        "liquidity_valor": "Satış valörü {valor:.0f} gün; likidite {value:.1f}.",
        "fees": "Giriş + çıkış komisyonu %{fees:.2f}, {years:g} yıla yayılarak getiriden "
                "düşüldü.",
    },
    "assumptions": {
        "kind_proxy_valor": "Fonlarda likidite satış valöründen (valör yoksa ürün türünden), "
                            "gelir uygunluğu ürün türünden türetildi.",
    },
    "data_quality": {
        "buyable_missing": "{count} fonun TEFAS alım durumu kanıtlarda yok; bu fonlar alıma "
                           "açık sayıldı.",
    },
}


def add_d12(raw: dict) -> dict:
    """Add the D12 config and texts, in place."""
    raw["fund_detail"] = copy.deepcopy(D12_SECTION)
    for section, texts in D12_TEXTS.items():
        raw["texts"][section].update(texts)
    return raw


@pytest.fixture
def d12_raw(raw) -> dict:
    return add_d12(add_d10(add_d9(raw)))


@pytest.fixture
def d12_config(d12_raw):
    return parse_config(d12_raw)


# --- D13: explicit constraints as hard rules -------------------------------------------------

D13_SECTION = {
    "fx_limit": {"override_choices": ["uygula", "gerekçeyle kaldır"],
                 "override_lifts": "gerekçeyle kaldır"},
    "liquidity_need": {"max_sell_valor_days": 3, "max_lock_days": 91},
}
D13_TEXTS = {
    "constraint": {
        "fx_limit": "Döviz fonu; müşterinin açık kısıtı: döviz maruziyetini gerekçesiz "
                    "artırmama.",
        "liquidity_need_valor": "Satış valörü {valor:.0f} gün, üst sınır {max_days} gün "
                                "(müşterinin açık kısıtı: düşük likiditeden kaçınma).",
        "liquidity_need_lock": "Vade {days} gün, üst sınır {max_days} gün (müşterinin açık "
                               "kısıtı: uzun süre kilitlenmekten kaçınma).",
    },
    "questions": {
        "override_fx_limit": "Döviz fonları müşterinin açık kısıtı nedeniyle elendi. Kısıt "
                             "gerekçeyle kaldırılsın mı?",
        "override_reason": "Kısıt \"gerekçesiz\" diyor; RM gerekçe yazarak kaldırabilir.",
    },
    "assumptions": {
        "fx_override": "RM döviz fonları kısıtını gerekçeyle kaldırdı (gerekçe RM notunda); "
                       "döviz fonları ceza ile listede.",
    },
    "data_quality": {
        "valor_missing": "{count} fonun satış valörü kanıtlarda yok; likidite kısıtı bu "
                         "fonlara uygulanamadı.",
    },
}


def add_d13(raw: dict) -> dict:
    """Add the D13 config and texts, in place (needs fund_detail of D12)."""
    raw["constraint_rules"] = copy.deepcopy(D13_SECTION)
    for section, texts in D13_TEXTS.items():
        raw["texts"][section].update(texts)
    return raw


@pytest.fixture
def d13_raw(raw) -> dict:
    return add_d13(add_d12(add_d10(add_d9(raw))))


@pytest.fixture
def d13_config(d13_raw):
    return parse_config(d13_raw)


def market_row(value=43.82):
    return dp("deposit_rate", MARKET, value, source="evds", as_of=date(2026, 10, 2))


def d9_rows(cpi=29.73, deposit=17.5, time_deposit=15.0, fund_default=10.0, money_market=17.5):
    """CPI and stopaj rows (in %); None leaves a row out."""
    rows = []
    if cpi is not None:
        rows.append(dp("cpi_annual", CPI, cpi, as_of=date(2026, 9, 30)))
    for key, v in (("deposit", deposit), ("time_deposit", time_deposit),
                   ("fund_default", fund_default), ("money_market", money_market)):
        if v is not None:
            rows.append(dp("withholding_tax_rate", STOPAJ[key], v))
    return rows


CATS = {"money_market": "Para Piyasası Şemsiye Fonu", "equity": "Hisse Senedi Şemsiye Fonu",
        "debt": "Borçlanma Araçları Şemsiye Fonu", "mixed": "Karma Şemsiye Fonu",
        "participation": "Katılım Şemsiye Fonu"}


def make_evidence(funds, deposit=23.0, deposit_flags=("manual_entry",), time_deposit=None,
                  extra=()):
    """funds: code -> dict(kind, name, risk, returns={period: %}, size, investors,
    flags=(...) for every row of the fund; buyable, sell_valor, entry_fee, exit_fee
    give tefas_detail rows). time_deposit: the e-Vadeli rate, if any.
    extra: more rows (e.g. d9_rows())."""
    rows, ents = [], {}
    if deposit is not None:
        rows.append(dp("deposit_rate", DEP, deposit, flags=deposit_flags))
    if time_deposit is not None:
        rows.append(dp("deposit_rate", TD, time_deposit, flags=("manual_entry",)))
    for code, f in funds.items():
        ents[code] = EntityInfo(name=f.get("name", f"{code} FONU"), category=CATS[f["kind"]],
                                source="tefas_web")
        if f.get("risk") is not None:
            rows.append(dp("fund_risk_level", code, f["risk"], flags=f.get("flags", ())))
        for period, r in f.get("returns", {}).items():
            rows.append(dp(f"fund_return_{period}", code, r, flags=f.get("flags", ())))
        if f.get("size") is not None:
            rows.append(dp("fund_total_value", code, f["size"], flags=f.get("flags", ())))
        if f.get("investors") is not None:
            rows.append(dp("fund_investor_count", code, f["investors"], flags=f.get("flags", ())))
        for key, quantity in (("buyable", "fund_buyable"), ("sell_valor", "fund_sell_valor_days"),
                              ("entry_fee", "fund_entry_fee"), ("exit_fee", "fund_exit_fee")):
            if f.get(key) is not None:
                rows.append(dp(quantity, code, f[key], flags=("needs_check",)))
    rows.extend(extra)
    return EvidenceSet(snapshot_id="S-test", created_at=T0, excluded_sources=frozenset(),
                       source_status={}, datapoints=tuple(sorted(rows, key=lambda d: d.id)),
                       entities=ents)
