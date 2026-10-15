"""A1: the candidates and the data pack (spec section 5)."""

import dataclasses
import json
import re

from rmprep.agent.pack import build_pack, candidates, finding_id
from rmprep.contracts import ScoredOption
from tests.agent.conftest import FakeResearch, cand_ids, finding


def _research(result, fake=None):
    fake = fake or FakeResearch()
    opts = [s.option for s in candidates(result, 10)]
    return {r.option_id: r for r in fake.research_many(opts, "TR")}


def test_candidates_are_the_first_ten_without_the_deposit(ready_p03):
    got = candidates(ready_p03, 10)
    assert len(got) == 10
    assert all(isinstance(s, ScoredOption) and s.option.kind != "deposit" for s in got)
    assert [s.option.option_id for s in got] == cand_ids(ready_p03)
    assert len(candidates(ready_p03, 4)) == 4


def test_fewer_options_give_all_of_them(ready_p01):
    assert len(candidates(ready_p01, 10)) == 10       # 11 options, one is the deposit
    small = dataclasses.replace(ready_p01, options=ready_p01.options[:3], recommended=(),
                                talking_points=(), allocation=(), warnings=())
    assert len(candidates(small, 10)) == 2


def test_pack_has_estimate_flags_and_no_raw_pages(ready_p01, ev, dcfg):
    pack = build_pack(ready_p01, ev, dcfg, _research(ready_p01), "TR")
    json.dumps(pack)                                         # plain JSON
    rows = {p["sinif"]: p for p in pack["portfoy"]}
    assert rows["nakit_benzeri"]["kaynak"] == "musteri_dosyasi"
    assert rows["borclanma"]["kaynak"] == "meslek_tablosu_varsayim"
    assert rows["borclanma"]["tahmin"] is True
    assert rows["borclanma"]["id"] == "portfoy:borclanma"
    assert rows["borclanma"]["hedef_alt"] == 60 and rows["borclanma"]["hedef_ust"] == 70
    text = json.dumps(pack, ensure_ascii=False)
    assert "Özet metni" not in text                          # the provider summary stays out
    assert "https://" not in text                            # domains only, no URLs
    res = pack["arastirma"]["fund:EIL"]
    assert res["durum"] == "var"
    item = res["bulgular"][0]
    assert re.fullmatch(r"F[0-9a-f]{8}", item["id"])
    assert item["kaynak"] == "www.tefas.gov.tr" and item["etiket"] == "doğrulanmamış"
    assert res["haberler"][0]["tarih"] == "2026-09-30"


def test_pack_candidates_carry_scores_reasons_and_evidence(ready_p01, ev, dcfg):
    pack = build_pack(ready_p01, ev, dcfg, _research(ready_p01), "TR")
    assert [c["option_id"] for c in pack["adaylar"]] == cand_ids(ready_p01)
    assert pack["motor_ilk3"] == list(ready_p01.recommended)
    c = next(c for c in pack["adaylar"] if c["option_id"] == "fund:AIS")
    assert c["motor_sirasi"] == 3 and c["motor_ilk3"] is True
    parts = {p["id"]: p for p in c["puan_parcalari"]}
    assert "puan:return" in parts and "puan:penalty_liquidity" in parts
    assert parts["puan:return"]["neden"] and parts["puan:return"]["agirlik"] is not None
    assert "1y" in c["getiri"] and re.fullmatch(r"E[0-9a-f]{8}", c["getiri"]["1y"]["kanit"])
    assert c["getiri"]["1y"]["kanit"] in c["kanitlar"]
    assert 0 <= c["istikrar"] <= 1 and 0 <= c["veri_guveni"] <= 1
    rules = pack["kurallar"]
    assert rules["sinif_kurali"] is False                    # P01 is Muhafazakâr
    assert rules["en_fazla_hisse"] == dcfg.raw["stock"]["max_in_top3"]


def test_class_rule_flag_for_an_agresif_client(ready_p03, ev, dcfg):
    pack = build_pack(ready_p03, ev, dcfg, {}, "TR")
    assert pack["kurallar"]["sinif_kurali"] is True
    assert pack["kurallar"]["sinif_basina_en_fazla"] == dcfg.raw["recommend"]["max_per_class"]


def test_failed_or_missing_research_is_marked(ready_p01, ev, dcfg):
    research = _research(ready_p01, FakeResearch(errors={"fund:BBF"}))
    del research["fund:AAL"]
    pack = build_pack(ready_p01, ev, dcfg, research, "TR")
    assert pack["arastirma"]["fund:BBF"]["durum"] == "yok"
    assert "connection" in pack["arastirma"]["fund:BBF"]["neden"]
    assert pack["arastirma"]["fund:AAL"] == {"durum": "yok", "neden": "araştırma yok",
                                             "bulgular": [], "haberler": []}


def test_finding_id_is_stable_and_uses_the_research_id_when_present():
    f = finding("Metin.")
    assert finding_id("fund:A", f) == finding_id("fund:A", f)
    assert finding_id("fund:A", f) != finding_id("fund:B", f)

    class WithId:
        id = "F0123abcd"
        text = "x"
        date = ""
    assert finding_id("fund:A", WithId()) == "F0123abcd"


def test_the_engine_top3_is_always_among_the_candidates(ready_p03):
    """Eval 20261015-agent (lead, 2026-10-15): for P03 the class rule (D19) took IDY and
    OKT from below place 10, so the agent could not keep them and the A/B judge saw
    "n/a" for them. The candidates are the engine's top 3 first, then the display order."""
    far = [o for o in ready_p03.options if o.option.kind != "deposit"][12:14]
    first = [o for o in ready_p03.options if o.option.kind != "deposit"][0]
    rec = (first.option.option_id, *(o.option.option_id for o in far))
    r = dataclasses.replace(ready_p03, recommended=rec)
    got = [s.option.option_id for s in candidates(r, 10)]
    assert len(got) == 10 and len(set(got)) == 10
    assert set(rec) <= set(got)
    rest = [i for i in got if i not in rec]
    display = [o.option.option_id for o in r.options if o.option.kind != "deposit" and o.option.option_id not in rec]
    assert rest == display[:7]                         # the rest keeps the display order
    assert got[:3] == list(rec) or [i for i in got if i in rec] == list(rec)
