import dataclasses
from datetime import date, datetime

from rmprep.contracts import TR_TZ
from rmprep.research.config import load_config
from rmprep.research.shape import cut_words, shape_answer, shape_product
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, Source

CFG = load_config().shape
NOW = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)
TODAY = NOW.date()
S1 = Source("https://www.akportfoy.com.tr/tr/fund/AIS", "AIS")
S2 = Source("https://www.akportfoy.com.tr/doc/5787", "Yatırımcı Bilgi Formu")


def f(text, topic="strateji", conf="high", d="", src=S1):
    return Finding(text, topic, (src,), conf, d)


def product(findings=(), news=(), **kw):
    return ProductResearch("fund:AIS", "AK PORTFÖY PARA PİYASASI KATILIM FONU", "Ak Portföy Yönetimi A.Ş.",
                           "Uzun özet.", tuple(findings), "TR", "exa", NOW, 0.019, (), "", tuple(news), **kw)


def test_cut_words():
    assert cut_words("bir iki üç", 5) == "bir iki üç"
    assert cut_words("bir, iki, üç, dört", 2) == "bir, iki…"


def test_isin_in_upper_case_is_a_known_fact():
    p = shape_product(product([f("ISIN kodu TRYAKBK00847 olarak kayıtlıdır.")]), CFG, TODAY)
    assert p.findings == () and "1 bullets dropped (known facts)" in p.checks


def test_the_ais_example_loses_known_facts_and_repeats():
    p = shape_product(product([
        f("Fon, katılım finans ilkelerine uygun, vadesi en fazla 184 gün kalmış likit araçlara yatırım yapar."),
        f("Fonun yöneticisi Ak Portföy Yönetimi A.Ş.'dir ve şirket bir Akbank iştirakidir.", "yonetici_sirket", src=S2),
        f("Fonun kodu AIS, ISIN kodu TRYAKBK00847'dir; satışına 26 Mart 2013'te başlanmıştır.", src=S2),
        f("Fon şemsiye fona bağlıdır; portföy saklayıcısı Ak Yatırım'dır.", src=S2),
        f("Ak Portföy Yönetimi A.Ş. bir Akbank iştirakidir ve fonun yöneticisidir.", src=S2),   # a repeat of the company bullet
    ]), CFG, TODAY)
    assert [x.topic for x in p.findings] == ["strateji", "yonetici_sirket"]
    assert p.summary == "" and p.news_days == 90 and p.version == 2
    assert "2 bullets dropped (known facts)" in p.checks
    assert "1 bullets dropped (repeats)" in p.checks


def test_one_company_bullet_word_cut_and_cap():
    long = " ".join(f"kelime{i}" for i in range(30))
    p = shape_product(product([f(long), f("Şirket A bilgisi burada yazıyor.", "yonetici_sirket"),
                               f("Şirket B farklı bir bilgi veriyor.", "yonetici_sirket"),
                               f("Dikkat: fon birleşmesi onaylandı.", "dikkat"),
                               f("Strateji iki: kira sertifikası ağırlıklı.", "strateji"),
                               f("Strateji üç: katılma hesabı da kullanılır.", "strateji")]), CFG, TODAY)
    assert len(p.findings) == 4
    assert [x.topic for x in p.findings].count("yonetici_sirket") == 1
    assert p.findings[0].text.endswith("…") and len(p.findings[0].text.split()) == 20
    assert "1 bullets over the cap" in p.checks
    assert "1 company bullets dropped (one allowed)" in p.checks


def test_news_window_order_and_cap():
    news = [f("Eski haber metni burada.", "haber", d="2026-06-01"),
            f("Tarihsiz haber metni burada.", "haber"),
            f("Gelecek tarihli haber metni.", "haber", d="2026-11-01"),
            f("Birinci haber: fon birleşmesi.", "haber", d="2026-09-01"),
            f("İkinci haber: yönetici değişti.", "haber", d="2026-10-10"),
            f("Üçüncü haber: SPK onayı geldi.", "haber", d="2026-08-01"),
            f("Dördüncü haber: yeni fon kuruldu.", "haber", d="2026-07-20")]
    p = shape_product(product(news=news), CFG, TODAY)
    assert [n.date for n in p.news] == ["2026-10-10", "2026-09-01", "2026-08-01"]
    assert "3 news items undated or outside 90 days dropped" in p.checks
    assert "1 news items over the cap" in p.checks


def test_news_keep_known_terms_and_answers_keep_fees():
    p = shape_product(product(news=[f("Fon yönetim ücretini düşürdü.", "haber", d="2026-10-01")]), CFG, TODAY)
    assert len(p.news) == 1
    a = shape_answer(QuestionAnswer("Ücret ne?", "Uzun özet.", (f("Yönetim ücreti yıllık yüzde 0,7.", "soru"),
                                                               f("Yönetim ücreti yıllık yüzde 0,7'dir.", "soru")),
                                    "TR", "exa", NOW), CFG)
    assert [x.text for x in a.findings] == ["Yönetim ücreti yıllık yüzde 0,7."]
    assert a.summary == "" and a.version == 2


def test_an_error_product_keeps_its_error():
    p = shape_product(ProductResearch("fund:AIS", "AIS", "", "", (), "TR", "", NOW, error="daily limit"), CFG, TODAY)
    assert p.error == "daily limit" and p.news_days == 90 and p.version == 2


def test_a_known_fact_company_bullet_does_not_block_a_valid_one():
    p = shape_product(product([
        f("Fon, vadesi kısa likit araçlara yatırım yapar."),
        f("Fonun kurucusu Ak Portföy Yönetimi A.Ş.'dir.", "yonetici_sirket"),
        f("Ak Portföy bir Akbank iştirakidir ve 2000 yılında kuruldu.", "yonetici_sirket"),
    ]), CFG, TODAY)
    assert [x.topic for x in p.findings] == ["strateji", "yonetici_sirket"]
    assert p.findings[1].text.startswith("Ak Portföy bir Akbank")
    assert "1 bullets dropped (known facts)" in p.checks
    assert not any("company bullets dropped" in c for c in p.checks)


def test_a_failed_news_call_hides_the_news_section_for_both_providers():
    for provider_name, check in (("exa", "news: server"), ("exa", "news: credit"), ("exa", "news: connection"),
                                 ("exa", "news: request"), ("claude", "news: not available from the fallback")):
        p = dataclasses.replace(product([f("Strateji maddesi.")]), provider=provider_name, checks=(check,))
        assert shape_product(p, CFG, TODAY).news_days == 0, check


def test_an_exa_product_without_a_news_check_keeps_the_window():
    p = dataclasses.replace(product([f("Strateji maddesi.")]), provider="exa", checks=("1 findings dropped",))
    assert shape_product(p, CFG, TODAY).news_days == 90
    assert shape_product(product([f("Strateji maddesi.")]), CFG, TODAY).news_days == 90


# --- a broken model answer (found 2026-10-18 in the demo recording) -------------------------------

BROKEN = ("Nurol Portföy'ün yönettiği yatırım fonları, OSTİM paylarında alım yaparak pay oranını yüzde "
          "5,58274 seviyesine çıkarmıştır.\"}},{metin:{citations:[6],confidence:")


def test_a_broken_json_tail_is_cut_and_counted():
    from rmprep.research.shape import strip_broken
    assert strip_broken(BROKEN).endswith("seviyesine çıkarmıştır.")
    p = shape_product(product(news=[f(BROKEN, "haber", d="2026-10-08")]), CFG, TODAY)
    assert p.news[0].text.endswith("seviyesine çıkarmıştır.") and "{" not in p.news[0].text
    assert "1 bullets cut (broken model output)" in p.checks


def test_a_bullet_that_is_only_a_broken_piece_is_dropped_and_normal_text_stays():
    from rmprep.research.shape import strip_broken
    assert strip_broken('"}},{metin:{citations:[2]') == ""
    normal = "Fon, \"kısa vadeli\" araçlara yatırım yapar; getirisi faize bağlıdır."
    assert strip_broken(normal) == normal
    p = shape_product(product(news=[f('ok."}},{citations:[1]', "haber", d="2026-10-08"),
                                    f(normal, "haber", d="2026-10-09")]), CFG, TODAY)
    assert [x.text for x in p.news] == [normal] and "1 bullets dropped (broken model output)" in p.checks


def test_a_stored_result_is_repaired_on_read(tmp_path):
    import json
    from rmprep.research.service import _read
    stored = product(news=[f(BROKEN, "haber", d="2026-10-08")])
    path = tmp_path / "p.json"
    path.write_text(json.dumps(stored.to_dict(), ensure_ascii=False), encoding="utf-8")
    got = _read(path, ProductResearch)
    assert got.news[0].text.endswith("seviyesine çıkarmıştır.")
