"""Contract v1.7: approval times in the decision record (deliverable 6, brief
rule "RM onayı kaydı")."""

import dataclasses
import json
from datetime import datetime
from pathlib import Path

import pytest

from rmprep.contracts import TR_TZ, DecisionResult, NarrativeDraft, NarrativeStatus, RmStatus
from tests.contracts.test_contracts_v1_2 import draft

FIX = Path(__file__).resolve().parent / "fixtures"
T1 = datetime(2026, 10, 12, 21, 0, tzinfo=TR_TZ)


def _ready() -> DecisionResult:
    return DecisionResult.from_dict(
        json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))


def test_defaults_and_old_json():
    r = _ready()
    assert r.rm_decided_at is None
    assert draft().approved_at is None


def test_decision_time_round_trip_and_checks():
    r = _ready()
    first = r.options[1].option.option_id
    ok = dataclasses.replace(r, rm_status=RmStatus.APPROVED, rm_selected=(first,), rm_decided_at=T1)
    assert DecisionResult.from_dict(json.loads(json.dumps(ok.to_dict()))) == ok
    with pytest.raises(ValueError, match="pending"):
        dataclasses.replace(r, rm_decided_at=T1)                       # pending has no decision time
    with pytest.raises(ValueError, match="timezone"):
        dataclasses.replace(ok, rm_decided_at=datetime(2026, 10, 12, 21, 0))


def test_text_approval_time():
    d = draft(status=NarrativeStatus.APPROVED, rm_text="# Metin", approved_at=T1)
    assert NarrativeDraft.from_dict(json.loads(json.dumps(d.to_dict()))) == d
    with pytest.raises(ValueError, match="draft"):
        draft(approved_at=T1)                                          # a draft has no approval time
