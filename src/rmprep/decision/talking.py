"""Talking points "Müşteriyle konuşulacaklar" (contract v1.3; docs/decision.md
section 9, D18). Deterministic: the dashboard shows them before approval, so
they come from the engine, not from the narrator. Texts in config."""

from __future__ import annotations

from collections.abc import Sequence

from rmprep.contracts import EvidenceSet, Persona, ScoredOption, TalkingPoint
from rmprep.decision.config import DEPOSIT_KINDS, DecisionConfig
from rmprep.decision.display import DisplayFacts, access_text, facts_of, tr_percent
from rmprep.decision.persona import Levels
from rmprep.decision.text import normalize
from rmprep.decision.universe import EvidenceIndex, stopaj_entity
from rmprep.grouping import top_heads

MAX_POINTS = 3


def _real_rows(idx: EvidenceIndex, config: DecisionConfig, stopaj_entity: str) -> list:
    """The CPI row and a stopaj row (if any) of a real-return figure."""
    rr = config.raw["real_return"]
    rows = [idx.get(rr["cpi"]["quantity"], rr["cpi"]["entity"]),
            idx.get(rr["stopaj"]["quantity"], stopaj_entity)]
    return [r for r in rows if r is not None]


def _deposit_real(idx: EvidenceIndex, config: DecisionConfig):
    """(figure, evidence ids) of the EVDS market deposit rate after the deposit
    stopaj and CPI; never an ING row. None without the rows."""
    c = config.raw
    rr = c.get("real_return")
    market = idx.get(c["deposit"]["quantity"], c["deposit"]["market_entity"])
    if rr is None or market is None:
        return None
    cpi = idx.get(rr["cpi"]["quantity"], rr["cpi"]["entity"])
    if cpi is None:
        return None
    st = idx.get(rr["stopaj"]["quantity"], rr["stopaj"]["deposit"])
    net = market.value / 100 * (1 - (st.value / 100 if st is not None else 0.0))
    real = ((1 + net) / (1 + cpi.value / 100) - 1) * 100
    ids = [market.id, cpi.id] + ([st.id] if st is not None else [])
    return tr_percent(real), tuple(sorted(ids))


def _days(f: DisplayFacts) -> float | None:
    if f.lock_days is not None:
        return f.lock_days
    return f.sell_valor_days.value if f.sell_valor_days is not None else None


def _access_ids(f: DisplayFacts) -> list[str]:
    if f.sell_valor_days is not None:
        return [f.sell_valor_days.evidence_id]
    return [f.returns["1y"].evidence_id] if "1y" in f.returns else []   # the term's rate row


def talking_points(options: Sequence[ScoredOption], persona: Persona, levels: Levels,
                   evidence: EvidenceSet, config: DecisionConfig) -> tuple[TalkingPoint, ...]:
    """At most 3 points in talking_points.order, each only if its condition holds
    and its figure has evidence; () without the config section."""
    c = config.raw
    tp = c.get("talking_points")
    if tp is None:
        return ()
    idx = EvidenceIndex(evidence)
    top = top_heads(options, 3)
    facts = {o.option.option_id: facts_of(o.option, idx, config) for o in top}
    texts = tp["texts"]
    out: list[TalkingPoint] = []

    def add(code: str, figure: str, ids, option_ids=(), **fields) -> None:
        t = texts[code]
        out.append(TalkingPoint(code=code, label=t["label"], figure=figure,
                                text=t["text"].format(figure=figure, **fields),
                                evidence_ids=tuple(sorted(set(ids))),
                                option_ids=tuple(option_ids)))

    for code in tp["order"]:
        if len(out) >= MAX_POINTS:
            break
        if code == "deposit_real":
            durum = normalize(persona.durum)
            if not any(normalize(k) in durum for k in tp["deposit_keywords"]):
                continue
            got = _deposit_real(idx, config)
            if got is not None:
                add(code, got[0], got[1])
        elif code == "best_alternative":
            if not top:
                continue
            head = top[0]
            real = facts[head.option.option_id].real_1y
            if real is None:
                continue
            rows = _real_rows(idx, config, stopaj_entity(head.option, config))
            add(code, tr_percent(real.value), [real.evidence_id, *(r.id for r in rows)],
                (head.option.option_id,), label=head.option.label)
        elif code == "access":
            if not top or not (levels.liquidity > 0 or levels.boosts.get("liquidity")):
                continue
            fs = [facts[o.option.option_id] for o in top]
            if any(_days(f) is None for f in fs):
                continue                # "at the latest" needs the data of all three
            slowest = max(fs, key=_days)
            ids = [i for f in fs for i in _access_ids(f)]
            add(code, access_text(slowest, config), ids,
                [o.option.option_id for o in top])
        elif code == "risk_fit":
            if not top:
                continue
            risks, ids = [], []
            for o in top:
                f = facts[o.option.option_id]
                if f.risk is not None:
                    risks.append(f.risk.value)
                    ids.append(f.risk.evidence_id)
                elif o.option.kind in DEPOSIT_KINDS and "1y" in f.returns:
                    risks.append(1.0)   # a deposit counts as risk 1 (section 2)
                    ids.append(f.returns["1y"].evidence_id)
                else:
                    risks = []
                    break               # a fund without a risk row: no claim
            if not risks:
                continue
            highest = f"{max(risks):.0f}"
            figure = texts[code]["figure"].format(max=highest)
            add(code, figure, ids, [o.option.option_id for o in top],
                max=highest, ceiling=levels.ceiling)
    return tuple(out)
