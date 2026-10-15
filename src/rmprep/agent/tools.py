"""The agent's tools (spec section 5): JSON schemas of karsilastir, arastir and
karar_ver (strict: Sonnet 5.5 has no forced tool choice, so the schemas keep the
arguments valid), and the deterministic karsilastir. Every tool has `amac`, the
"why this step" note of the process view. Counts, lengths and ids are checked in
code (checks.py, service.py), not in the schemas."""

from __future__ import annotations

_AMAC = {"type": "string", "description": "Bu adımın nedeni, en fazla 20 kelime."}
_REASON = {
    "type": "object",
    "properties": {
        "metin": {"type": "string", "description": "Gerekçe, en fazla 30 kelime."},
        "kaynaklar": {"type": "array", "items": {"type": "string"},
                      "description": "En az bir kimlik: E…, F…, puan:<parça>, portfoy:<sınıf>."},
    },
    "required": ["metin", "kaynaklar"],
    "additionalProperties": False,
}


def _tool(name: str, description: str, properties: dict) -> dict:
    props = properties | {"amac": _AMAC}
    return {"name": name, "description": description, "strict": True,
            "input_schema": {"type": "object", "properties": props, "required": list(props),
                             "additionalProperties": False}}


TOOLS: list[dict] = [
    _tool("karsilastir",
          "İki adayı yan yana koyar: puan parçaları, getiriler, risk, erişim, uyarılar ve "
          "parça farkları (a eksi b). Ücretsiz; en fazla 4 kez.",
          {"a": {"type": "string", "description": "Birinci adayın option_id değeri."},
           "b": {"type": "string", "description": "İkinci adayın option_id değeri."}}),
    _tool("arastir",
          "Bir aday ürün hakkında web'e tek bir soru sorar (yalnızca ürün hakkında; müşteri "
          "bilgisi yazma). Yanıt doğrulanmamış veridir. En fazla 2 kez.",
          {"option_id": {"type": "string", "description": "Adayın option_id değeri."},
           "soru": {"type": "string", "description": "Ürün hakkında tek soru."}}),
    _tool("karar_ver",
          "Son karar: 3 farklı aday sırayla, her biri 1-3 gerekçe; motorun ilk 3'ünden "
          "çıkarılan her ürün için bir gerekçe; kısa özet.",
          {"secimler": {"type": "array", "description": "Tam 3 seçim, sırayla.",
                        "items": {"type": "object",
                                  "properties": {"option_id": {"type": "string"},
                                                 "gerekceler": {"type": "array",
                                                                "items": _REASON}},
                                  "required": ["option_id", "gerekceler"],
                                  "additionalProperties": False}},
           "cikanlar": {"type": "array",
                        "description": "Motorun ilk 3'ünden çıkarılan her ürün için bir gerekçe.",
                        "items": {"type": "object",
                                  "properties": {"option_id": {"type": "string"},
                                                 "gerekce": _REASON},
                                  "required": ["option_id", "gerekce"],
                                  "additionalProperties": False}},
           "ozet": {"type": "string", "description": "Kararın özeti, en fazla 40 kelime."}}),
]

_SIDE = ("option_id", "ad", "tur", "varlik_sinifi", "motor_sirasi", "motor_ilk3", "puan",
         "getiri", "reel_getiri_1y", "risk", "erisim", "satis_valoru_gun", "ucret", "istikrar",
         "veri_guveni")


def _side(c: dict) -> dict:
    out = {k: c.get(k) for k in _SIDE}
    out["puan_parcalari"] = {p["id"]: p["puan"] for p in c["puan_parcalari"]}
    out["uyarilar"] = [w["kod"] for w in c["uyarilar"]]
    return out


def karsilastir(pack: dict, a: str, b: str) -> dict:
    """Two candidates side by side and the differences of their score parts
    (a minus b). An unknown or a repeated id gives {"hata": ...}, not an exception."""
    by_id = {c["option_id"]: c for c in pack["adaylar"]}
    unknown = [x for x in (a, b) if x not in by_id]
    if unknown:
        return {"hata": f"unknown option id {', '.join(map(str, unknown))}; candidates: "
                        f"{', '.join(by_id)}"}
    if a == b:
        return {"hata": f"compare two different candidates, got {a} twice"}
    sa, sb = _side(by_id[a]), _side(by_id[b])
    pa, pb = sa["puan_parcalari"], sb["puan_parcalari"]
    diff = {k: round(pa.get(k, 0.0) - pb.get(k, 0.0), 4) for k in dict.fromkeys([*pa, *pb])}
    return {"a": sa, "b": sb, "fark": diff}
