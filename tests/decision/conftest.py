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
          "deposit_rate": "percent"}
_SOURCES = {"fund_total_value": "tefas", "fund_investor_count": "tefas", "fund_price": "tefas"}


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


@pytest.fixture(scope="session")
def raw_config() -> dict:
    return load_raw()


@pytest.fixture
def raw(raw_config) -> dict:
    """A deep copy of the parsed config/decision.yaml that a test may change."""
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


CATS = {"money_market": "Para Piyasası Şemsiye Fonu", "equity": "Hisse Senedi Şemsiye Fonu",
        "debt": "Borçlanma Araçları Şemsiye Fonu", "mixed": "Karma Şemsiye Fonu",
        "participation": "Katılım Şemsiye Fonu"}


def make_evidence(funds, deposit=23.0, deposit_flags=("manual_entry",), time_deposit=None):
    """funds: code -> dict(kind, name, risk, returns={period: %}, size, investors,
    flags=(...) for every row of the fund). time_deposit: the e-Vadeli rate, if any."""
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
    return EvidenceSet(snapshot_id="S-test", created_at=T0, excluded_sources=frozenset(),
                       source_status={}, datapoints=tuple(sorted(rows, key=lambda d: d.id)),
                       entities=ents)
