"""The client's current split over the asset classes and the allocation gap
(docs/decision.md section 17, D27; spec
docs/superpowers/specs/2026-10-14-portfolio-projection-design.md sections 4-5).

Pure: reads the persona, the config and the RM input. Only the sources rm,
rm_confirmed and persona_text are active (the brief: no made-up client
information); job and national values are a proposal and do not change the
ranking.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from rmprep.contracts import ACTIVE_HOLDINGS_SOURCES, ALLOCATION_CLASSES, HoldingsInput, Persona
from rmprep.decision.config import DecisionConfig
from rmprep.decision.persona import Levels
from rmprep.decision.text import normalize

SIGNAL_FIELDS = ("oncelikler", "acik_kisitlar", "yatirim_amaci", "rm_notu")


@dataclass(frozen=True)
class ClassEstimate:
    asset_class: str
    point: float            # % of the financial portfolio
    low: float
    high: float
    source: str             # HOLDINGS_SOURCES
    ref: str                # text rule id / profile label / national label ("" for RM input)


def field_text(persona: Persona, field: str) -> str:
    """A persona text field, normalised; a list field is joined."""
    value = getattr(persona, field)
    if isinstance(value, (list, tuple)):
        value = " ".join(value)
    return normalize(str(value or ""))


def _round(points: dict[str, float], free: Sequence[str]) -> dict[str, float]:
    """Points to one decimal that add up to 100; the rounding rest goes to the
    largest class of `free` (else the largest class)."""
    out = {k: round(v, 1) for k, v in points.items()}
    rest = round(100.0 - sum(out.values()), 1)
    if rest:
        pool = list(free) or list(out)
        big = max(pool, key=lambda k: (out[k], k))
        out[big] = round(out[big] + rest, 1)
    return out


def _base(persona: Persona, h: Mapping) -> tuple[Mapping[str, float], str, str]:
    """(shares, label, source) of the first profile row whose words are in the
    persona's profil, else the national default."""
    profil = field_text(persona, "profil")
    for row in h["profiles"]:
        if any(normalize(w) in profil for w in row["match"]):
            return row["shares"], row["label"], "profile"
    return h["national"]["shares"], h["national"]["label"], "national"


def estimate(persona: Persona, config: DecisionConfig,
             holdings: HoldingsInput | None) -> tuple[ClassEstimate, ...]:
    """The current split, one estimate per class of ALLOCATION_CLASSES (in that
    order); () without the holdings section. RM input replaces everything; else
    the text rules fix their classes (config order, the first rule of a class
    wins, the text points are capped at 100) and the rest goes to the other
    classes in the proportions of the base (profile row or national default)."""
    h = config.raw.get("holdings")
    if h is None:
        return ()
    if holdings is not None:
        points = _round(dict(holdings.shares), ())
        return tuple(ClassEstimate(c, points[c], points[c], points[c], holdings.origin, "")
                     for c in ALLOCATION_CLASSES)
    base, label, source = _base(persona, h)
    fixed: dict[str, tuple[float, float, float, str]] = {}      # class -> point, low, high, id
    used = 0.0
    for rule in h["text_rules"]:
        cls = rule["class"]
        if cls in fixed or not any(normalize(rule["match"]) in field_text(persona, f)
                                   for f in rule["fields"]):
            continue
        lo, hi = rule["range"]
        point = min((lo + hi) / 2, 100.0 - used)
        fixed[cls] = (point, min(lo, point), hi, rule["id"])
        used += point
    free = [c for c in ALLOCATION_CLASSES if c not in fixed]
    total = sum(base[c] for c in free)
    points = {c: fixed[c][0] for c in fixed}
    for c in free:
        points[c] = ((100.0 - used) * base[c] / total if total > 0
                     else (100.0 - used) / len(free))
    points = _round(points, free)
    spread = h["spread"]
    out = []
    for c in ALLOCATION_CLASSES:
        p = points[c]
        if c in fixed:
            _, lo, hi, rid = fixed[c]
            out.append(ClassEstimate(c, p, min(lo, p), max(hi, p), "persona_text", rid))
        else:
            out.append(ClassEstimate(c, p, round(max(0.0, p - spread), 1),
                                     round(min(100.0, p + spread), 1), source, label))
    return tuple(out)


def holdings_status(estimates: Sequence[ClassEstimate]) -> str:
    """"rm" | "rm_confirmed" | "persona_text" | "estimate" (nothing active)."""
    sources = {e.source for e in estimates}
    for s in ("rm", "rm_confirmed", "persona_text"):
        if s in sources:
            return s
    return "estimate"


def class_gap(point: float, band: tuple[float, float] | None) -> float | None:
    """Points to the nearest band edge: + below the band (under-weight), - above
    it (over-weight), 0 inside; None without a band (dengeli)."""
    if band is None:
        return None
    low, high = band
    if point < low:
        return low - point
    if point > high:
        return high - point
    return 0.0


def gap_value(gap: float | None, active: bool, config: DecisionConfig) -> float:
    """Criterion value in [-1, 1]: clamp(gap / scale), a negative value x
    overweight_factor; 0 for an inactive class, no gap or no allocation_gap."""
    ag = config.raw.get("allocation_gap")
    if ag is None or not active or gap is None:
        return 0.0
    v = max(-1.0, min(1.0, gap / ag["scale"]))
    return v * ag["overweight_factor"] if v < 0 else v


def gap_weight_factor(persona: Persona, estimates: Sequence[ClassEstimate],
                      config: DecisionConfig) -> float:
    """Factor of weights.allocation_gap.base: the source factor of the active
    source x (1 + per_signal x change signals, at most max_signals); 0 when no
    class is active (the criterion is then left out)."""
    ag = config.raw.get("allocation_gap")
    active = {e.source for e in estimates if e.source in ACTIVE_HOLDINGS_SOURCES}
    if ag is None or not active:
        return 0.0
    factor = max(ag["source_factor"][s] for s in active)
    text = " | ".join(field_text(persona, f) for f in SIGNAL_FIELDS)
    signals = sum(1 for s in ag["signals"] if normalize(s) in text)
    return factor * (1 + ag["per_signal"] * min(signals, ag["max_signals"]))


def band_of(cls: str, levels: Levels, config: DecisionConfig) -> tuple[float, float] | None:
    """The D20 model band of a class for the client's risk profile."""
    al = config.raw.get("allocation")
    if al is None:
        return None
    band = al["profiles"][levels.risk_profile]["bands"].get(cls)
    return (band[0], band[1]) if band else None


def with_gap(levels: Levels, persona: Persona, config: DecisionConfig,
             estimates: Sequence[ClassEstimate]) -> Levels:
    """Levels with the allocation_gap weight factor and, per class, the criterion
    value and its reason text. Unchanged when no class is active."""
    factor = gap_weight_factor(persona, estimates, config)
    if factor <= 0:
        return levels
    texts = config.raw["texts"]
    labels = texts["holdings"]["class_labels"]
    sources = texts["holdings"]["source_labels"]
    gap: dict[str, tuple[float, str]] = {}
    for e in estimates:
        band = band_of(e.asset_class, levels, config)
        active = e.source in ACTIVE_HOLDINGS_SOURCES
        label = labels[e.asset_class]
        if band is None:
            reason = texts["reasons"]["allocation_gap_no_band"].format(class_label=label)
        elif not active:
            reason = texts["reasons"]["allocation_gap_inactive"].format(class_label=label)
        else:
            reason = texts["reasons"]["allocation_gap"].format(
                class_label=label, source_label=sources[e.source], current=e.point,
                profile=levels.risk_profile, low=band[0], high=band[1])
        gap[e.asset_class] = (gap_value(class_gap(e.point, band), active, config), reason)
    return dataclasses.replace(levels, gap_weight=factor, gap=gap)
