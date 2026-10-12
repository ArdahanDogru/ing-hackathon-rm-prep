"""Contract v1.5 (docs/web-ui.md "Section-by-section editing"): per-block edits
of the meeting text and their findings."""

import json

from rmprep.contracts import BLOCKING_CHECK_KINDS, Backend, NarrativeDraft
from tests.contracts.test_contracts_v1_2 import draft


def test_defaults_and_old_json():
    d = draft()
    assert d.rm_edits == {} and d.edit_checks == {} and d.blocking_findings() == {}
    old = d.to_dict()
    old.pop("rm_edits")
    old.pop("edit_checks")
    assert NarrativeDraft.from_dict(old) == d


def test_round_trip_and_blocking_findings():
    d = draft(rm_edits={"ozet": "Yeni."},
              edit_checks={"ozet": ("phrase: 'kesin getiri'", "number: 99,9 yok"),
                           "dikkat": ("number: 12 yok",)})
    assert NarrativeDraft.from_dict(json.loads(json.dumps(d.to_dict()))) == d
    assert d.blocking_findings() == {"ozet": ("phrase: 'kesin getiri'",)}
    assert BLOCKING_CHECK_KINDS == ("phrase", "option", "internal", "label")


def test_backend_has_edit_narrative():
    assert hasattr(Backend, "edit_narrative")
