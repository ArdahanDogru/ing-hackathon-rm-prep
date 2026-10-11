"""Shared helpers of the narrator tests: approved fixture results and the
evidence they cite (tests/contracts/fixtures/)."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path

import pytest

from rmprep.contracts import TR_TZ, DecisionResult, EvidenceSet, RmStatus
from rmprep.narrator.config import NarratorConfig, load_config

CONTRACT_FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CREATED = datetime(2026, 10, 10, 10, 0, tzinfo=TR_TZ)


def _read(name: str) -> dict:
    return json.loads((CONTRACT_FIX / name).read_text(encoding="utf-8"))


def result(name: str) -> DecisionResult:
    return DecisionResult.from_dict(_read(f"{name}.json"))


def approved(name: str, selected: tuple[str, ...], note: str = "",
             option_notes: dict[str, str] | None = None) -> DecisionResult:
    """A fixture result as the RM approved it with this selection."""
    return dataclasses.replace(result(name), rm_status=RmStatus.APPROVED, rm_selected=selected,
                               rm_note=note, rm_option_notes=option_notes or {})


def evidence() -> EvidenceSet:
    return EvidenceSet.from_dict(_read("evidence_medium.json"))


def p02() -> DecisionResult:
    """P02, BBF (debt; AKE is its group alternative) and AAL selected; AAV rejected."""
    return approved("decision_p02_ready", ("fund:BBF", "fund:AAL"),
                    note="Şirket nakdini ayrıca konuşalım.",
                    option_notes={"fund:BBF": "Vade ufkuna uygun."})


def p03() -> DecisionResult:
    return approved("decision_p03_ready", ("fund:AAV", "fund:AFO"))


@pytest.fixture(scope="session")
def config() -> NarratorConfig:
    return load_config()


def persona(pid: str):
    from rmprep.contracts import Persona

    return Persona.from_dict(_read(f"personas/{pid}.json"))


def engine_result(pid: str, selected_n: int = 2, note: str = "") -> DecisionResult:
    """A real decision engine run on evidence_medium (v1.3: warning audience,
    talking points), approved with the first selected_n non-deposit options."""
    from rmprep.decision.config import load_config as load_decision_config
    from rmprep.decision.engine import decide

    r = decide(evidence(), persona(pid), load_decision_config(), created_at=CREATED)
    chosen = tuple(o.option.option_id for o in r.options if o.option.kind != "deposit")
    return dataclasses.replace(r, rm_status=RmStatus.APPROVED,
                               rm_selected=chosen[:selected_n], rm_note=note)


@pytest.fixture(scope="session")
def approved_p01() -> DecisionResult:
    return engine_result("p01", note="Faiz geliri önemli; aylık ödeme sorulacak.")
