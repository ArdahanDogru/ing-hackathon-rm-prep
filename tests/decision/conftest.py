import copy
import json
from pathlib import Path

import pytest

from rmprep.contracts import EvidenceSet, Persona
from rmprep.decision.config import load_raw, parse_config

CONTRACT_FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PERSONA_IDS = ["P01", "P02", "P03", "P04", "P05"]


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
