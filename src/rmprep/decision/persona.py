"""Persona text -> levels, questions and assumptions (docs/decision.md section 3).

Text is matched exactly after `normalize`. Unknown text becomes a question for
the RM: blocking for `risk_profili` and `acik_kisitlar[i]` (no levels until
answered), non-blocking for the level fields (a safe level and an assumption
until answered). Unknown `oncelikler` only become an assumption.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from rmprep.contracts import ClarificationQuestion, Persona
from rmprep.decision.config import LEVEL_FIELDS, DecisionConfig
from rmprep.decision.text import normalize

__all__ = ["Levels", "PersonaReading", "normalize", "read_persona"]

_RANGE_RE = re.compile(r"^(\d+)\s*-\s*(\d+) yıl$")
_PLUS_RE = re.compile(r"^(\d+)\+ yıl$")
LEVEL_ATTR = {"likidite_ihtiyaci": "liquidity", "gelir_nakit_akisi_ihtiyaci": "income",
               "anapara_koruma_tercihi": "principal"}
_FX = "doviz_maruz_kalma_tercihi"
_HORIZON = "yatirim_ufku"


@dataclass(frozen=True)
class Levels:
    ceiling: int                    # highest acceptable fund risk level (1..7)
    appetite: float                 # 0..1
    period: str                     # return period of the horizon: 6m | 1y | 3y
    liquidity: float                # levels 0..1 of the three level fields
    income: float
    principal: float
    fx_intensity: float             # 0..1, intensity of the fx_exposure penalty
    liquidity_intensity: float      # 0..1, intensity of the liquidity penalty
    liquidity_weight: float | None  # raw liquidity weight override (no_liquidity_need)
    diversity: bool                 # diversity cap in positions 1-10
    boosts: Mapping[str, int] = field(default_factory=dict)  # criterion -> matched priorities
    effects: tuple[str, ...] = ()   # constraint effects applied, in order


@dataclass(frozen=True)
class PersonaReading:
    levels: Levels | None           # None while a blocking question is open
    questions: tuple[ClarificationQuestion, ...]
    assumptions: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return self.levels is None


def _lookup(table: Mapping[str, object], text: str) -> str | None:
    """Table key whose normalized form equals the normalized text."""
    n = normalize(text)
    for key in table:
        if normalize(key) == n:
            return key
    return None


def _horizon_years(text: str) -> int | None:
    n = normalize(text)
    if m := _RANGE_RE.match(n):
        return int(m.group(2))
    if m := _PLUS_RE.match(n):
        return int(m.group(1))
    return None


def _period_of(years: float, config: DecisionConfig) -> str:
    for p in config.raw["horizon"]["periods"]:
        if p["max_years"] is None or years <= p["max_years"]:
            return p["period"]
    raise AssertionError("the config check guarantees a last open period")


def read_persona(persona: Persona, config: DecisionConfig,
                 answers: Mapping[str, str] = {}) -> PersonaReading:
    """Map the persona text to levels. `answers` maps question_id -> choice; an
    answer to a question that does not exist or not in its choices -> ValueError."""
    c = config.raw
    texts = c["texts"]
    q_texts = texts["questions"]
    questions: list[ClarificationQuestion] = []
    assumptions: list[str] = []
    used_answers: set[str] = set()

    def ask(qid: str, about: str, text: str, raw_text: str, choices: tuple[str, ...],
            blocking: bool) -> str | None:
        answer = answers.get(qid)
        if answer is not None:
            used_answers.add(qid)
            if answer not in choices:
                raise ValueError(f"answer {answer!r} to {qid} is not one of the choices {choices}")
        questions.append(ClarificationQuestion(
            question_id=qid, text=text, reason=q_texts["reason"].format(text=raw_text),
            about=about, choices=choices, answer=answer, blocking=blocking))
        return answer

    def safe(field_name: str, raw_text: str, choices: tuple[str, ...]) -> str:
        """Matched key, else the answer, else the safe level (with an assumption)."""
        answer = ask(f"q:{field_name}", field_name, q_texts[field_name], raw_text, choices,
                     blocking=False)
        if answer is not None:
            return answer
        level = c["safe_levels"][field_name]
        assumptions.append(texts["assumptions"]["safe_level"].format(
            field=field_name, text=raw_text, level=level))
        return level

    blocked = False

    # risk_profili (blocking)
    profiles = c["risk_profiles"]
    profile = _lookup(profiles, persona.risk_profili)
    if profile is None:
        profile = ask("q:risk_profili", "risk_profili", q_texts["risk_profili"],
                      persona.risk_profili, tuple(profiles), blocking=True)
        blocked |= profile is None

    # yatirim_ufku
    years = _horizon_years(persona.yatirim_ufku)
    if years is not None:
        period = _period_of(years, config)
    else:
        choices = tuple(dict.fromkeys(p["period"] for p in c["horizon"]["periods"]))
        period = safe(_HORIZON, persona.yatirim_ufku, choices)

    # the three level fields
    level_values: dict[str, float] = {}
    for f in LEVEL_FIELDS:
        text = getattr(persona, f)
        key = _lookup(c["levels"], text) or safe(f, text, tuple(c["levels"]))
        level_values[LEVEL_ATTR[f]] = c["levels"][key]

    # doviz_maruz_kalma_tercihi
    fx_key = (_lookup(c["fx_levels"], persona.doviz_maruz_kalma_tercihi)
              or safe(_FX, persona.doviz_maruz_kalma_tercihi, tuple(c["fx_levels"])))

    # oncelikler
    boosts: dict[str, int] = {}
    diversity = False
    for text in persona.oncelikler:
        key = _lookup(c["priorities"], text)
        if key is None:
            assumptions.append(texts["assumptions"]["unused_priority"].format(text=text))
            continue
        kind, _, arg = c["priorities"][key].partition(":")
        if kind == "boost":
            boosts[arg] = boosts.get(arg, 0) + 1
        elif kind == "note":
            assumptions.append(texts["assumptions"][arg])
        else:
            diversity = True

    # acik_kisitlar (blocking)
    effects: list[str] = []
    labels = texts["effect_labels"]
    by_label = {label: effect for effect, label in labels.items()}
    for i, text in enumerate(persona.acik_kisitlar):
        key = _lookup(c["constraints"], text)
        if key is not None:
            effects.append(c["constraints"][key])
            continue
        qid = f"q:acik_kisitlar[{i}]"
        answer = ask(qid, f"acik_kisitlar[{i}]", q_texts["acik_kisitlar"].format(text=text),
                     text, tuple(labels.values()), blocking=True)
        if answer is None:
            blocked = True
        else:
            effects.append(by_label[answer])

    unknown = sorted(set(answers) - used_answers)
    if unknown:
        raise ValueError(f"answers to unknown questions: {unknown}")

    if blocked:
        return PersonaReading(None, tuple(questions), tuple(assumptions))

    ceiling = profiles[profile]["ceiling"]
    fx_intensity = c["fx_levels"][fx_key]
    liquidity_intensity = level_values["liquidity"]
    liquidity_weight: float | None = None
    applied: list[str] = []
    for name in effects:
        if name == "ignore":
            continue
        e = c["constraint_effects"][name]
        if "max_ceiling" in e:
            ceiling = min(ceiling, e["max_ceiling"])
        if "min_fx_intensity" in e:
            fx_intensity = max(fx_intensity, e["min_fx_intensity"])
        if "liquidity_weight" in e:
            liquidity_weight = e["liquidity_weight"]
        if "liquidity_intensity" in e:
            liquidity_intensity = e["liquidity_intensity"]
        if "min_liquidity_intensity" in e:
            liquidity_intensity = max(liquidity_intensity, e["min_liquidity_intensity"])
        if e.get("diversity"):
            diversity = True
        applied.append(name)

    levels = Levels(
        ceiling=ceiling, appetite=profiles[profile]["appetite"], period=period,
        fx_intensity=fx_intensity, liquidity_intensity=liquidity_intensity,
        liquidity_weight=liquidity_weight, diversity=diversity, boosts=boosts,
        effects=tuple(applied), **level_values)
    return PersonaReading(levels, tuple(questions), tuple(assumptions))
