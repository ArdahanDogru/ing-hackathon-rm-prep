"""A1: code checks of a karar_ver answer (spec section 6)."""

import copy

import pytest

from rmprep.agent.checks import check_decision
from rmprep.agent.pack import build_pack
from tests.agent.conftest import FakeResearch, cand_ids, karar, reason, valid_picks


@pytest.fixture
def pack01(ready_p01, ev, dcfg):
    from rmprep.agent.pack import candidates

    opts = [s.option for s in candidates(ready_p01, 10)]
    research = {r.option_id: r for r in FakeResearch().research_many(opts, "TR")}
    return build_pack(ready_p01, ev, dcfg, research, "TR")


def _check(raw, pack, dcfg, phrases, lang="TR"):
    return check_decision(raw, pack, dcfg, phrases, lang)


def _problems(raw, pack, dcfg, phrases):
    return _check(raw, pack, dcfg, phrases)[3]


def test_valid_answer_passes_and_gets_labels(ready_p01, pack01, dcfg, phrases):
    raw = karar(ready_p01, valid_picks(ready_p01))
    fid = pack01["arastirma"]["fund:AAL"]["bulgular"][0]["id"]
    raw["secimler"][1]["gerekceler"].append(reason("Fon para piyasası araçlarına yatırım yapar.",
                                                   fid))
    picks, dropped, summary, problems = _check(raw, pack01, dcfg, phrases)
    assert problems == []
    assert [p.option_id for p in picks] == valid_picks(ready_p01)
    assert picks[0].uses_estimate and picks[0].reasons[1].labels == ("(tahmini dağılıma göre)",)
    assert picks[1].uses_web and picks[1].reasons[1].labels == ("(web, doğrulanmamış)",)
    assert not picks[2].uses_estimate and not picks[2].uses_web
    assert [d.option_id for d in dropped] == ["fund:AIS"]
    assert summary.startswith("Borçlanma")


def test_bad_pick_count_and_duplicates(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    assert any("3 picks" in p for p in _problems(karar(ready_p01, picks[:2]), pack01, dcfg,
                                                   phrases))
    assert any("3 picks" in p for p in _problems(karar(ready_p01, picks + [cand_ids(ready_p01)[4]]),
                                                   pack01, dcfg, phrases))
    dup = karar(ready_p01, [picks[0], picks[0], picks[1]])
    assert any("twice" in p for p in _problems(dup, pack01, dcfg, phrases))


def test_unknown_id_is_refused(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    raw = karar(ready_p01, [picks[0], picks[1], "fund:AFS"])   # option 11 is not a candidate
    if "fund:AFS" in cand_ids(ready_p01):
        raw = karar(ready_p01, [picks[0], picks[1], "fund:ZZZ"])
    assert any("not a candidate" in p for p in _problems(raw, pack01, dcfg, phrases))


def test_stock_cap(ready_p01, pack01, dcfg, phrases):
    pack = copy.deepcopy(pack01)
    picks = valid_picks(ready_p01)
    for c in pack["adaylar"]:
        if c["option_id"] in picks[:2]:
            c["tur"] = "stock"
    cap = dcfg.raw["stock"]["max_in_top3"]
    problems = _problems(karar(ready_p01, picks), pack, dcfg, phrases)
    assert any("shares" in p for p in problems) == (cap < 2)


def test_d19_class_caps_when_the_candidates_allow_it(ready_p03, ev, dcfg, phrases):
    pack = build_pack(ready_p03, ev, dcfg, {}, "TR")
    assert pack["kurallar"]["sinif_kurali"]
    by_class: dict[str, list[str]] = {}
    for c in pack["adaylar"]:
        by_class.setdefault(c["varlik_sinifi"], []).append(c["option_id"])
    cls, ids = next((k, v) for k, v in by_class.items() if len(v) >= 2)
    other = next(v[0] for k, v in by_class.items() if k != cls)
    picks = [ids[0], ids[1], other]
    raw = karar(ready_p03, picks)
    for s in raw["secimler"]:                     # P03 has no "borclanma" estimate cite rule
        s["gerekceler"] = [reason("Getiri puanı güçlü.", "puan:return")]
    problems = _problems(raw, pack, dcfg, phrases)
    assert any("per class" in p for p in problems)
    # one class only among the candidates: the cap does not apply
    only = copy.deepcopy(pack)
    for c in only["adaylar"]:
        c["varlik_sinifi"] = "hisse"
    assert not any("per class" in p for p in _problems(raw, only, dcfg, phrases))


def test_numbers_must_match_cited_data(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    c = next(c for c in pack01["adaylar"] if c["option_id"] == picks[0])
    e1y = c["getiri"]["1y"]["kanit"]
    v = c["getiri"]["1y"]["deger"]
    ok = karar(ready_p01, picks)
    ok["secimler"][0]["gerekceler"][0] = reason(f"Yıllık getiri %{v:.1f}".replace(".", ","), e1y)
    assert _problems(ok, pack01, dcfg, phrases) == []
    bad = karar(ready_p01, picks)
    bad["secimler"][0]["gerekceler"][0] = reason("Yıllık getiri %999 oldu.", e1y)
    assert any("number" in p and "999" in p for p in _problems(bad, pack01, dcfg, phrases))


def test_forbidden_phrase_refused(ready_p01, pack01, dcfg, phrases):
    raw = karar(ready_p01, valid_picks(ready_p01))
    raw["secimler"][2]["gerekceler"][0] = reason("Garanti getiri sunar.", "puan:return")
    assert any("forbidden" in p for p in _problems(raw, pack01, dcfg, phrases))


def test_finding_must_belong_to_the_option(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    other = pack01["arastirma"][picks[1]]["bulgular"][0]["id"]
    raw = karar(ready_p01, picks)
    raw["secimler"][0]["gerekceler"].append(reason("Web bulgusu.", other))
    assert any(other in p and "belong" in p for p in _problems(raw, pack01, dcfg, phrases))


def test_citation_forms_and_unknown_ids(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    for cites in ([], ["bogus"], ["E00000000"], ["puan:nope"], ["portfoy:yok"]):
        raw = karar(ready_p01, picks)
        raw["secimler"][2]["gerekceler"][0] = reason("Metin.", *cites)
        assert _problems(raw, pack01, dcfg, phrases), cites


def test_word_limits_and_dropped_reasons(ready_p01, pack01, dcfg, phrases):
    picks = valid_picks(ready_p01)
    raw = karar(ready_p01, picks)
    raw["secimler"][0]["gerekceler"][0] = reason(" ".join(["kelime"] * 31), "puan:return")
    assert any("30 words" in p for p in _problems(raw, pack01, dcfg, phrases))
    raw = karar(ready_p01, picks, ozet=" ".join(["kelime"] * 41))
    assert any("40 words" in p for p in _problems(raw, pack01, dcfg, phrases))
    raw = karar(ready_p01, picks, cikanlar=[])
    assert any("fund:AIS" in p and "dropped" in p for p in _problems(raw, pack01, dcfg, phrases))
    raw = karar(ready_p01, picks)
    raw["secimler"][0]["gerekceler"] = raw["secimler"][0]["gerekceler"] * 2
    assert any("1-3 reasons" in p for p in _problems(raw, pack01, dcfg, phrases))


def test_malformed_input_never_raises(pack01, dcfg, phrases):
    for raw in ({}, {"secimler": "x"}, {"secimler": [1, 2, 3]}, {"secimler": [{"option_id": 1}]}):
        assert _check(raw, pack01, dcfg, phrases)[3]
