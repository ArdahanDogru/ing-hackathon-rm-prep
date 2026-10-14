from datetime import datetime

import pytest

from rmprep.contracts import TR_TZ
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
SRC = Source("https://www.nurolportfoy.com.tr/fon/ppn", "PPN", "2026-10-12")


def test_product_round_trip():
    p = ProductResearch("fund:PPN", "NUROL PORTFÖY PARA PİYASASI (TL) FONU", "Nurol Portföy Yönetimi A.Ş.",
                        "PPN bir para piyasası fonudur.",
                        (Finding("Yönetim ücreti %0,7'dir.", "urun", (SRC,), "high"),),
                        "TR", "exa", NOW, 0.012, ("1 findings without a valid source dropped",))
    assert ProductResearch.from_dict(p.to_dict()) == p
    assert p.to_dict()["created_at"] == "2026-10-14T10:00:00+03:00"


def test_question_round_trip_and_error():
    q = QuestionAnswer("Nurol Portföy son haberler", "", (), "TR", "", NOW, error="exa: credit")
    assert QuestionAnswer.from_dict(q.to_dict()) == q


def test_finding_needs_a_source_a_text_and_known_values():
    with pytest.raises(ValueError):
        Finding("x", "urun", ())
    with pytest.raises(ValueError):
        Finding("  ", "urun", (SRC,))
    with pytest.raises(ValueError):
        Finding("x", "haber", (SRC,))
    with pytest.raises(ValueError):
        Finding("x", "urun", (SRC,), "certain")


def test_created_at_must_be_aware_and_becomes_turkish_time():
    with pytest.raises(ValueError):
        QuestionAnswer("q", "", (), "TR", "exa", datetime(2026, 10, 14, 10, 0))
    utc = datetime.fromisoformat("2026-10-14T07:00:00+00:00")
    assert QuestionAnswer("q", "", (), "TR", "exa", utc).created_at.utcoffset().total_seconds() == 3 * 3600


def test_research_error_kind():
    e = ResearchError("credit", "HTTP 402")
    assert e.kind == "credit" and "402" in str(e)
