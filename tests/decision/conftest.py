import copy
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from rmprep.contracts import TR_TZ, DataPoint, EvidenceSet, Persona
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
