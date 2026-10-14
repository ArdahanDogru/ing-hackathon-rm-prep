from rmprep.research.checks import is_excluded, is_web_url, norm_url, sources_for, tr_lower
from rmprep.research.types import Source

RESULTS = {norm_url(u): Source(u, t, d) for u, t, d in [
    ("https://www.nurolportfoy.com.tr/fon/ppn", "PPN", "2026-10-12"),
    ("https://fonoloji.com/ppn/", "Fonoloji", ""),
    ("https://www.kap.org.tr/tr/Bildirim/1", "KAP", ""),
]}


def g(field, *urls, conf="high"):
    return {"field": field, "citations": [{"url": u, "title": "x"} for u in urls], "confidence": conf}


def test_norm_url_matches_two_forms_of_one_page():
    assert norm_url("HTTPS://WWW.Fonoloji.com/ppn/") == norm_url("https://www.fonoloji.com/ppn#top")
    assert norm_url("https://a.com/x?y=1") != norm_url("https://a.com/x")


def test_excluded_domain_and_subdomain():
    assert is_excluded("https://www.kap.org.tr/tr/x", ["kap.org.tr"])
    assert is_excluded("https://kap.org.tr/", ["kap.org.tr"])
    assert not is_excluded("https://kapatt.matriksdata.com/x", ["kap.org.tr"])


def test_is_web_url_accepts_only_http_and_https():
    assert is_web_url("https://a.com/x")
    assert is_web_url("http://a.com")
    assert not is_web_url("javascript:alert(1)")
    assert not is_web_url("data:text/html,x")
    assert not is_web_url("ftp://a.com/x")
    assert not is_web_url("")


def test_tr_lower():
    assert tr_lower("MÜŞTERİM IŞIK") == "müşterim ışık"


def test_sources_of_a_field_and_its_subfields():
    grounding = [g("bulgular[0].metin", "https://www.nurolportfoy.com.tr/fon/ppn/"),
                 g("bulgular[0].konu", "https://fonoloji.com/ppn", conf="low")]
    sources, conf = sources_for("bulgular[0]", grounding, RESULTS, ["kap.org.tr"])
    assert [s.url for s in sources] == ["https://www.nurolportfoy.com.tr/fon/ppn", "https://fonoloji.com/ppn/"]
    assert conf == "high"


def test_whole_item_path_and_no_two_digit_sibling():
    grounding = [g("bulgular[1]", "https://fonoloji.com/ppn"),
                 g("bulgular[10].metin", "https://www.nurolportfoy.com.tr/fon/ppn")]
    sources, _ = sources_for("bulgular[1]", grounding, RESULTS, ["kap.org.tr"])
    assert [s.url for s in sources] == ["https://fonoloji.com/ppn/"]


def test_foreign_and_excluded_citations_do_not_count():
    grounding = [g("ozet", "https://example.org/not-a-result", "https://www.kap.org.tr/tr/Bildirim/1")]
    assert sources_for("ozet", grounding, RESULTS, ["kap.org.tr"]) == ((), "high")


def test_no_grounding_gives_medium_and_no_source():
    assert sources_for("ozet", [], RESULTS, []) == ((), "medium")
