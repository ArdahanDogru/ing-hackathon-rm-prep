"""The candidates and the data pack of the agent (spec section 5): one JSON object
with the client, the portfolio split per class (with its source and the flag
`tahmin`), the engine's best candidates with their score parts and reasons, the
checked research bullets of each candidate (data, not instructions), and the
rules that code checks. Pure: reads the result, the evidence and the config."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from rmprep.contracts import DecisionResult, EvidenceSet, ScoredOption
from rmprep.decision.config import DecisionConfig
from rmprep.decision.display import access_text, facts_of
from rmprep.decision.exchange import return_prefix
from rmprep.decision.persona import read_persona
from rmprep.decision.recommend import class_rule_applies
from rmprep.decision.universe import EvidenceIndex

PERIODS = ("1m", "3m", "6m", "1y", "3y", "5y")
DEPOSIT_KINDS = ("deposit",)
# the client's split per class: source of the estimate -> the pack's word (spec section 5)
SOURCE_WORDS = {"persona_text": "musteri_dosyasi", "profile": "meslek_tablosu_varsayim",
                "national": "ulusal_ortalama", "rm": "rm", "rm_confirmed": "rm_onayli"}
NOT_ESTIMATED = ("rm", "rm_confirmed")          # typed or accepted by the RM
WEB_LABEL = "doğrulanmamış"
NO_RESEARCH = "araştırma yok"
PERSONA_FIELDS = ("profil", "yas", "risk_profili", "durum", "yatirim_amaci", "yatirim_ufku",
                  "likidite_ihtiyaci", "gelir_nakit_akisi_ihtiyaci", "anapara_koruma_tercihi",
                  "doviz_maruz_kalma_tercihi", "oncelikler", "acik_kisitlar", "rm_notu")
FEES = (("giris", "fund_entry_fee"), ("cikis", "fund_exit_fee"))


def candidates(result: DecisionResult, n: int) -> list[ScoredOption]:
    """The first n scored options without the deposit baseline, in the engine's
    display order (the group caps of D10/D19 already apply)."""
    return [o for o in result.options if o.option.kind not in DEPOSIT_KINDS][:n]


def part_cite(key: str) -> str:
    """The citation id of a score part: "puan:return", "puan:penalty_liquidity"."""
    return "puan:" + re.sub(r"[^a-z_]", "_", key.lower())


def finding_id(option_id: str, finding) -> str:
    """The id of a research finding: Finding.id of the research service (R3) when it
    has one, else the same rule here: "F" + sha1(option id | date | text)[:8]."""
    fid = getattr(finding, "id", "")
    if fid:
        return fid
    key = "|".join((option_id, finding.date, finding.text))
    return "F" + hashlib.sha1(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]


def _domain(url: str) -> str:
    return urlparse(url).netloc or url


def finding_item(option_id: str, f) -> dict:
    return {"id": finding_id(option_id, f), "metin": f.text, "konu": f.topic, "tarih": f.date,
            "kaynak": ", ".join(dict.fromkeys(_domain(s.url) for s in f.sources)),
            "etiket": WEB_LABEL}


def research_block(option_id: str, research) -> dict:
    """The checked bullets of one product (highlights and news), or `yok` with why.
    The provider summary and the pages stay out."""
    if research is None:
        return {"durum": "yok", "neden": NO_RESEARCH, "bulgular": [], "haberler": []}
    if research.error:
        return {"durum": "yok", "neden": research.error, "bulgular": [], "haberler": []}
    return {"durum": "var", "neden": "",
            "bulgular": [finding_item(option_id, f) for f in research.findings],
            "haberler": [finding_item(option_id, f) for f in research.news]}


def _fact(value: float | None, eid: str, digits: int = 2) -> dict | None:
    return None if value is None else {"deger": round(value, digits), "kanit": eid}


def _round(x: float | None, digits: int = 1) -> float | None:
    return None if x is None else round(x, digits)


def _candidate(o: ScoredOption, place: int, result: DecisionResult, idx: EvidenceIndex,
               evidence: EvidenceSet, config: DecisionConfig, lang: str) -> dict:
    opt = o.option
    shown = facts_of(opt, idx, config)
    weights = result.effective_weights
    returns: dict[str, Any] = {}
    if opt.kind in ("fund", "etf", "stock"):
        for period in PERIODS:
            row = idx.get(f"{return_prefix(opt.kind)}{period}", opt.entity)
            if row is not None and row.value is not None:
                returns[period] = _fact(row.value, row.id)
    else:
        returns = {p: _fact(f.value, f.evidence_id) for p, f in shown.returns.items()}
    fees = {}
    for word, quantity in FEES:
        row = idx.get(quantity, opt.entity)
        if row is not None and row.value is not None:
            fees[word] = _fact(row.value, row.id)
    by_id = {d.id: d for d in evidence.datapoints}
    proofs = {}
    for eid in o.evidence_ids:
        d = by_id.get(eid)
        if d is not None and d.value is not None:
            proofs[eid] = {"olcu": d.quantity, "deger": round(d.value, 4), "birim": d.unit,
                           "tarih": d.as_of.isoformat()}
    return {
        "option_id": opt.option_id, "ad": opt.label, "tur": opt.kind,
        "varlik_sinifi": opt.asset_class, "motor_sirasi": place,
        "motor_ilk3": opt.option_id in result.recommended, "puan": round(o.score, 4),
        "puan_parcalari": [{"id": part_cite(k), "parca": k, "puan": round(v, 4),
                            "agirlik": _round(weights.get(k), 4), "neden": o.reasons.get(k, "")}
                           for k, v in o.score_parts.items()],
        "getiri": returns,
        "reel_getiri_1y": (None if shown.real_1y is None
                           else _fact(shown.real_1y.value, shown.real_1y.evidence_id, 1)),
        "risk": None if shown.risk is None else _fact(shown.risk.value, shown.risk.evidence_id, 0),
        "erisim": access_text(shown, config, lang),
        "satis_valoru_gun": (None if shown.sell_valor_days is None else
                             _fact(shown.sell_valor_days.value, shown.sell_valor_days.evidence_id,
                                   0)),
        "ucret": fees,
        "uyarilar": [{"kod": w.code, "metin": w.message, "kanit": list(w.evidence_ids)}
                     for w in result.warnings if opt.option_id in w.option_ids],
        "istikrar": round(o.stability, 2), "veri_guveni": round(o.confidence, 2),
        "kanitlar": proofs,
    }


def _portfolio(result: DecisionResult) -> list[dict]:
    out = []
    for b in result.allocation:
        out.append({
            "id": f"portfoy:{b.asset_class}", "sinif": b.asset_class,
            "hedef_alt": b.low, "hedef_ust": b.high, "hedef_kaynak": b.source,
            "mevcut": _round(b.current), "mevcut_alt": _round(b.current_low),
            "mevcut_ust": _round(b.current_high), "fark": _round(b.gap),
            "kaynak": SOURCE_WORDS.get(b.current_source, b.current_source or "yok"),
            "aciklama": b.current_ref,
            "tahmin": b.current is not None and b.current_source not in NOT_ESTIMATED,
        })
    return out


def _rules(result: DecisionResult, config: DecisionConfig) -> dict:
    c = config.raw
    answers = {q.question_id: q.answer for q in result.questions if q.answer is not None}
    levels = read_persona(result.persona, config, answers).levels
    rec = c.get("recommend")
    applies = levels is not None and class_rule_applies(levels, config)
    return {"secim_sayisi": 3,
            "en_fazla_hisse": c.get("stock", {}).get("max_in_top3"),
            "sinif_kurali": bool(applies),
            "sinif_basina_en_fazla": rec["max_per_class"] if applies else None,
            "nakit_benzeri_en_fazla": rec["max_cash_like"] if applies else None,
            "nakit_benzeri_sinif": rec["cash_like"] if rec else None}


def build_pack(result: DecisionResult, evidence: EvidenceSet, decision_config: DecisionConfig,
               research: Mapping[str, Any], lang: str, n: int = 10) -> dict:
    """The data pack. `research`: option id -> ProductResearch (a missing or failed
    one is marked `yok`)."""
    idx = EvidenceIndex(evidence)
    cands = candidates(result, n)
    p = result.persona
    return {
        "dil": lang,
        "musteri": {k: (list(v) if isinstance(v, tuple) else v)
                    for k, v in ((f, getattr(p, f)) for f in PERSONA_FIELDS)},
        "portfoy": _portfolio(result),
        "motor_ilk3": list(result.recommended),
        "adaylar": [_candidate(o, i, result, idx, evidence, decision_config, lang)
                    for i, o in enumerate(cands, 1)],
        "arastirma": {o.option.option_id: research_block(o.option.option_id,
                                                         research.get(o.option.option_id))
                      for o in cands},
        "kurallar": _rules(result, decision_config),
    }
