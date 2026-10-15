"""A1: the tool schemas and karsilastir (spec section 5)."""

from rmprep.agent.pack import build_pack
from rmprep.agent.tools import TOOLS, karsilastir


def test_tools_are_strict_and_need_amac():
    assert [t["name"] for t in TOOLS] == ["karsilastir", "arastir", "karar_ver"]
    for t in TOOLS:
        s = t["input_schema"]
        assert t["strict"] is True and s["additionalProperties"] is False
        assert "amac" in s["required"] and set(s["required"]) == set(s["properties"])
    karar = next(t for t in TOOLS if t["name"] == "karar_ver")["input_schema"]
    assert {"secimler", "cikanlar", "ozet"} <= set(karar["required"])


def test_karsilastir_is_deterministic(ready_p01, ev, dcfg):
    pack = build_pack(ready_p01, ev, dcfg, {}, "TR")
    a = karsilastir(pack, "fund:EIL", "fund:BBF")
    assert a == karsilastir(pack, "fund:EIL", "fund:BBF")
    assert [x["option_id"] for x in (a["a"], a["b"])] == ["fund:EIL", "fund:BBF"]
    assert "puan:return" in a["fark"]
    eil = {p["id"]: p["puan"] for p in pack["adaylar"][0]["puan_parcalari"]}
    bbf = {p["id"]: p["puan"] for p in pack["adaylar"][1]["puan_parcalari"]}
    assert a["fark"]["puan:return"] == round(eil["puan:return"] - bbf["puan:return"], 4)


def test_karsilastir_unknown_or_same_id_is_an_error_dict(ready_p01, ev, dcfg):
    pack = build_pack(ready_p01, ev, dcfg, {}, "TR")
    bad = karsilastir(pack, "fund:EIL", "fund:NOPE")
    assert set(bad) == {"hata"} and "fund:NOPE" in bad["hata"]
    assert "hata" in karsilastir(pack, "fund:EIL", "fund:EIL")
