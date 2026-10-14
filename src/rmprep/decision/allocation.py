"""Model allocation bands per asset class (docs/decision.md section 11, D20).

Strategic bands for the client's risk profile and the best option of each
class for this client. No current shares and no amounts (the personas do not
give the client's holdings); the holding hints are qualitative only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from rmprep.contracts import (
    ACTIVE_HOLDINGS_SOURCES,
    AllocationBand,
    Persona,
    RejectedOption,
    ScoredOption,
)
from rmprep.decision.config import DecisionConfig
from rmprep.decision.holdings import ClassEstimate, class_gap
from rmprep.decision.persona import Levels
from rmprep.decision.text import normalize


def allocation(options: Sequence[ScoredOption], rejected: Sequence[RejectedOption],
               levels: Levels, config: DecisionConfig,
               real_of: Callable[[ScoredOption], float | None],
               estimates: Mapping[str, int] = {},
               current: Sequence[ClassEstimate] = ()) -> tuple[AllocationBand, ...]:
    """One band per class of allocation.classes (config order); () without the
    section. Best option = the first scored option of the class in score order
    (the deposit baseline is not a pick; a fund whose risk is only estimated and
    the estimate is above the client's ceiling is not a pick either: it is listed
    only through the risk_unknown rule). Note, first that applies: ceiling (no
    pick, and a fund of the class failed the risk ceiling or was skipped for its
    estimate), none (no scored option), negative_real (the best option has a
    real 1-year return < 0; the option stays). current (D27, holdings.estimate):
    the client's current split; each row gets its point, range, source, gap to
    the band and whether it is active. A share is never the example of a
    class (D26b: one company is no example of a class); its class can have none."""
    al = config.raw.get("allocation")
    if al is None:
        return ()
    profile = al["profiles"][levels.risk_profile]
    ranked = sorted((o for o in options if o.option.kind not in ("deposit", "stock")),
                    key=lambda o: (-o.score, o.option.option_id))
    rejected = [x for x in rejected if x.option.kind != "stock"]
    above = {o.option.option_id for o in ranked
             if estimates.get(o.option.option_id, 0) > levels.ceiling}
    by_class = {e.asset_class: e for e in current}
    out = []
    for cls in al["classes"]:
        members = [o for o in ranked if o.option.asset_class == cls]
        best = next((o for o in members if o.option.option_id not in above), None)
        if best is None:
            ceiling = any(o.option.option_id in above for o in members) or any(
                x.option.asset_class == cls
                and any(c.rule_id == "risk_ceiling" for c in x.failed) for x in rejected)
            note = "ceiling" if ceiling else "none"
        else:
            real = real_of(best)
            note = "negative_real" if real is not None and real < 0 else ""
        band = profile["bands"].get(cls)
        now = {}
        e = by_class.get(cls)
        if e is not None:
            now = dict(current=e.point, current_low=e.low, current_high=e.high,
                       current_source=e.source, current_ref=e.ref,
                       gap=class_gap(e.point, (band[0], band[1]) if band else None),
                       active=e.source in ACTIVE_HOLDINGS_SOURCES)
        out.append(AllocationBand(
            asset_class=cls, low=band[0] if band else None, high=band[1] if band else None,
            source=profile["source"], inferred=profile["inferred"],
            option_id=best.option.option_id if best is not None else None, note=note,
            **now))
    return tuple(out)


def holding_notes(persona: Persona, config: DecisionConfig) -> tuple[str, ...]:
    """Holding hints of allocation.holding_hints whose keyword is in the
    persona's durum (Turkish normalization), in config order."""
    al = config.raw.get("allocation")
    if al is None:
        return ()
    durum = normalize(persona.durum)
    return tuple(text for keyword, text in al["holding_hints"].items()
                 if normalize(keyword) in durum)
