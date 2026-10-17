"""Display categories (W32, approved by the user 2026-10-17; docs/web-ui.md; lead-owned).

The screen groups products by what they invest in, not by the TEFAS legal type
("şemsiye fon"): first the asset class of the "Dağılım" view (D20/D26:
nakit_benzeri, borclanma, hisse, altin_doviz, dengeli), then a sub-type from the
fund name. "Katılım" (interest-free) and FX are badges, not categories.
Display only: the engine, its kinds (fund_kind, group_key) and the scores do not change.
"""

from __future__ import annotations

from collections.abc import Sequence

from rmprep.contracts import ProductOption

CLASS_ORDER = ("nakit_benzeri", "borclanma", "hisse", "altin_doviz", "dengeli")
CLASS_LABELS = {
    "nakit_benzeri": {"TR": "Nakit benzeri", "EN": "Cash-like"},
    "borclanma": {"TR": "Borçlanma", "EN": "Bonds"},
    "hisse": {"TR": "Hisse", "EN": "Equity"},
    "altin_doviz": {"TR": "Altın / döviz", "EN": "Gold / FX"},
    "dengeli": {"TR": "Dengeli", "EN": "Balanced"},
}
# sub-types in the order of the checks: the first rule that matches the name wins
SUBTYPE_LABELS = {
    "mevduat": {"TR": "ING mevduat", "EN": "ING deposits"},
    "para_piyasasi": {"TR": "Para piyasası", "EN": "Money market"},
    "kira_sertifikasi": {"TR": "Kira sertifikası", "EN": "Lease certificates (sukuk)"},
    "kisa_vadeli": {"TR": "Kısa vadeli borçlanma", "EN": "Short-term bonds"},
    "eurobond_doviz": {"TR": "Eurobond / döviz", "EN": "Eurobond / FX"},
    "altin": {"TR": "Altın / kıymetli maden", "EN": "Gold / precious metals"},
    "fon_sepeti": {"TR": "Fon sepeti", "EN": "Fund of funds"},
    "hisse": {"TR": "Hisse", "EN": "Equity"},
    "degisken": {"TR": "Değişken / karma", "EN": "Variable / mixed"},
    "borclanma": {"TR": "Borçlanma (TL)", "EN": "Bonds (TRY)"},
    "diger": {"TR": "Diğer", "EN": "Other"},
}
BADGE_LABELS = {"katilim": {"TR": "Katılım", "EN": "Participation"},
                "fx": {"TR": "Döviz", "EN": "FX"}}

_FX_WORDS = ("EUROBOND", "DÖVİZ", "(USD)", "(EUR)", "DOLAR", "AVRO", "YABANCI PARA",
             "YABANCI BORÇLANMA")
_GOLD_WORDS = ("ALTIN", "GÜMÜŞ", "KIYMETLİ MADEN", "PLATİN")


def _upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


def subtype(o: ProductOption) -> str:
    """The sub-type of a fund, ETF or share from its name and kind."""
    if o.kind in ("deposit", "time_deposit"):
        return "mevduat"
    if o.kind == "stock":
        return "hisse"
    name, kind = _upper(o.label), o.fund_kind or ""
    if "PARA PİYASASI" in name or "TLREF" in name or kind == "money_market":   # TLREF: the overnight TL rate
        return "para_piyasasi"
    if "KİRA SERTİFİKA" in name:
        return "kira_sertifikasi"
    if "KISA VADELİ" in name:
        return "kisa_vadeli"
    if any(w in name for w in _FX_WORDS) or (o.fx and kind in ("debt", "participation")):
        return "eurobond_doviz"
    if any(w in name for w in _GOLD_WORDS) or kind == "precious_metals":
        return "altin"
    if "FON SEPETİ" in name or kind == "fund_of_funds":
        return "fon_sepeti"
    if "HİSSE" in name or kind == "equity":
        return "hisse"
    if "DEĞİŞKEN" in name or "KARMA" in name or kind in ("variable", "mixed"):
        return "degisken"
    if "BORÇLANMA" in name or kind == "debt":
        return "borclanma"
    if kind == "participation":     # a Katılım fund without a type word: mixed or thematic
        return "degisken"
    return "diger"


def asset_class(o: ProductOption) -> str:
    """The asset class of the "Dağılım" view; a share is equity, an ING deposit cash-like."""
    if o.kind in ("deposit", "time_deposit"):
        return "nakit_benzeri"
    if o.kind == "stock":
        return "hisse"
    return o.asset_class if o.asset_class in CLASS_ORDER else "dengeli"


def badges(o: ProductOption) -> list[str]:
    out = []
    if o.fund_kind == "participation" or "KATILIM" in _upper(o.label):
        out.append("katilim")
    if o.fx:
        out.append("fx")
    return out


def peer_key(o: ProductOption) -> str:
    """The peer group of a product (its rank and the category average): the
    sub-type, e.g. every money market fund, interest-free or not."""
    return subtype(o)


def tree(options: Sequence[ProductOption], best_1y: dict[str, float | None],
         lang: str) -> list[dict]:
    """The categories of the candidates: classes (in CLASS_ORDER) with their
    sub-types; every option once, in the given order (the caller gives the best score first).
    best_1y: option id -> 1-year return for the sub-type's best figure."""
    by_class: dict[str, dict[str, list[str]]] = {}
    for o in options:
        by_class.setdefault(asset_class(o), {}).setdefault(subtype(o), []).append(o.option_id)
    out = []
    for cls in CLASS_ORDER:
        subs = by_class.get(cls)
        if not subs:
            continue
        rows = []
        for key in SUBTYPE_LABELS:
            ids = subs.get(key)
            if not ids:
                continue
            values = [v for v in (best_1y.get(i) for i in ids) if v is not None]
            rows.append({"key": key, "label": SUBTYPE_LABELS[key][lang], "count": len(ids),
                         "best_return_1y": max(values) if values else None, "option_ids": ids})
        out.append({"key": cls, "label": CLASS_LABELS[cls][lang],
                    "count": sum(r["count"] for r in rows), "subtypes": rows})
    return out
