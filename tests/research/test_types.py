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
        Finding("x", "bogus", (SRC,))
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


def test_v2_product_round_trip_and_version():
    p = ProductResearch("fund:AIS", "AIS", "Ak Portföy", "", (), "TR", "exa", NOW,
                        news=(Finding("Fon birleşti.", "haber", (SRC,), "high", "2026-10-01"),), news_days=90)
    assert ProductResearch.from_dict(p.to_dict()) == p
    assert p.to_dict()["version"] == 2 and p.to_dict()["news_days"] == 90
    assert p.to_dict()["news"][0]["date"] == "2026-10-01"


def test_a_v1_dict_loads_as_version_1():
    d = ProductResearch("fund:PPN", "PPN", "Nurol", "Özet.", (Finding("x", "urun", (SRC,)),), "TR", "exa", NOW).to_dict()
    for k in ("news", "news_days", "version"):
        del d[k]
    del d["findings"][0]["date"]
    p = ProductResearch.from_dict(d)
    assert p.news == () and p.news_days == 0 and p.version == 1 and p.findings[0].date == ""


def test_finding_topics_of_v2_and_question_version():
    assert Finding("x", "strateji", (SRC,)).date == ""
    q = QuestionAnswer("q", "", (), "TR", "exa", NOW)
    assert q.to_dict()["version"] == 2
    d = q.to_dict()
    del d["version"]
    assert QuestionAnswer.from_dict(d).version == 1
