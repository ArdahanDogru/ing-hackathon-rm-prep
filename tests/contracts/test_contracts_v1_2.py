"""Contract v1.2: the narrator types (docs/narrator.md)."""

from datetime import datetime

import pytest

from rmprep.contracts import (
    TR_TZ, Backend, NarrativeDraft, NarrativeSection, NarrativeSentence, NarrativeStatus,
)

T0 = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)


def draft(**kw):
    base = dict(run_id="R1", lang="TR",
                sections=(NarrativeSection("ozet", (NarrativeSentence("Metin.", ("fund:A",), ("E1",)),)),),
                source="llm", model="claude-sonnet-5-5", prompt_version="p1", checks=(), created_at=T0)
    return NarrativeDraft(**(base | kw))


def test_round_trip():
    d = draft(cost_usd=0.04)
    assert NarrativeDraft.from_dict(d.to_dict()) == d
    a = draft(status=NarrativeStatus.APPROVED, rm_text="# Not\nmetin")
    assert NarrativeDraft.from_dict(a.to_dict()) == a


@pytest.mark.parametrize("kw, match", [
    ({"lang": "DE"}, "lang"),
    ({"status": NarrativeStatus.APPROVED}, "rm_text"),
    ({"source": "template"}, "model"),
    ({"source": "llm", "model": ""}, "model"),
    ({"source": "x"}, "source"),
    ({"created_at": datetime(2026, 10, 10)}, "timezone"),
    ({"cost_usd": -1.0}, "cost"),
])
def test_checks(kw, match):
    with pytest.raises(ValueError, match=match):
        draft(**kw)


def test_unknown_section_key():
    with pytest.raises(ValueError, match="section"):
        NarrativeSection("other", ())


def test_template_draft_has_no_model():
    assert draft(source="template", model="").source == "template"


def test_backend_has_the_narrator_methods():
    names = {n for n in dir(Backend) if not n.startswith("_")}
    assert {"draft_narrative", "approve_narrative"} <= names
