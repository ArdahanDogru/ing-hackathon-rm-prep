"""Contract v1.4 (docs/web-ui.md "LLM brief"): NarrativeBrief and Backend.brief."""

import json
from datetime import datetime

import pytest

from rmprep.contracts import TR_TZ, Backend, NarrativeBrief

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=TR_TZ)


def _b(**kw):
    base = dict(run_id="R1", lang="TR", text="Kısa özet.", source="template", model="",
                prompt_version="b1", checks=(), created_at=T0)
    return NarrativeBrief(**(base | kw))


def test_round_trip():
    b = _b(source="llm", model="claude-haiku-5-5", cite=("E1", "fund:PPN"), cost_usd=0.003)
    assert NarrativeBrief.from_dict(json.loads(json.dumps(b.to_dict()))) == b


@pytest.mark.parametrize("kw", [dict(lang="DE"), dict(source="x"), dict(text=" "),
                                dict(text="x" * 281), dict(source="llm", model=""),
                                dict(source="template", model="claude-haiku-5-5"),
                                dict(cost_usd=-1.0),
                                dict(created_at=datetime(2026, 10, 12, 9, 0))])
def test_checks(kw):
    with pytest.raises(ValueError):
        _b(**kw)


def test_backend_has_brief():
    assert hasattr(Backend, "brief")
