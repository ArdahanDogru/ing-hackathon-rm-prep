"""What the page shows, as plain data (no streamlit), so tests can check it
without a browser: the baseline and the fund_kind groups, the score bars, the
row titles and table rows, the evidence rows and citations, and the RM loop
helpers (run inputs, change texts, persona diff)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass

from rmprep.contracts import (
    ClarificationQuestion,
    DecisionResult,
    DecisionWarning,
    EvidenceSet,
    Persona,
    RejectedOption,
    ScoredOption,
)
from rmprep.ui.i18n import LABELS, t

POOL_SIZE = 20      # the groups are made from the first 20 non-deposit options
MAX_GROUPS = 5
ALTERNATIVES = 3    # visible alternatives per group; the rest behind "Daha fazla"
PENALTY = "penalty:"


def baseline(r: DecisionResult) -> ScoredOption | None:
    """The deposit baseline ("Karşılaştırma"): options[0] if it is a deposit."""
    if r.options and r.options[0].option.kind == "deposit":
        return r.options[0]
    return None


def ranked(r: DecisionResult) -> tuple[ScoredOption, ...]:
    """The options after the baseline, in display order."""
    return r.options[1:] if baseline(r) is not None else r.options


def positions(r: DecisionResult) -> dict[str, int]:
    """option_id -> position in the ranked options (1 = first after the baseline)."""
    return {o.option.option_id: i for i, o in enumerate(ranked(r), start=1)}


@dataclass(frozen=True)
class KindGroup:
    """One block of "Kısa liste": the best option of a fund_kind and its alternatives."""

    kind: str
    head: ScoredOption
    alternatives: tuple[ScoredOption, ...]     # score order

    @property
    def count(self) -> int:
        return 1 + len(self.alternatives)


def _best_first(o: ScoredOption) -> tuple[float, str]:
    return (-o.score, o.option.option_id)


def kind_groups(r: DecisionResult) -> list[KindGroup]:
    """Groups by fund_kind of the first POOL_SIZE non-deposit options, at most
    MAX_GROUPS, ordered by the score of their best option (ties: option_id)."""
    pool = [o for o in r.options if o.option.kind != "deposit"][:POOL_SIZE]
    by_kind: dict[str, list[ScoredOption]] = {}
    for o in pool:
        by_kind.setdefault(kind_key(o), []).append(o)
    groups = []
    for kind, opts in by_kind.items():
        best = sorted(opts, key=_best_first)
        groups.append(KindGroup(kind, best[0], tuple(best[1:])))
    groups.sort(key=lambda g: _best_first(g.head))
    return groups[:MAX_GROUPS]


def visible_alternatives(g: KindGroup, opened: bool) -> tuple[ScoredOption, ...]:
    return g.alternatives if opened else g.alternatives[:ALTERNATIVES]


def shown_options(r: DecisionResult, opened: frozenset[str] = frozenset()) -> list[ScoredOption]:
    """What "Kısa liste" shows: the baseline, then per group the head and its
    visible alternatives (all of them for the kinds in opened)."""
    base = baseline(r)
    out = [base] if base is not None else []
    for g in kind_groups(r):
        out += [g.head, *visible_alternatives(g, g.kind in opened)]
    return out


def warned(r: DecisionResult) -> dict[str, list[DecisionWarning]]:
    """option_id -> the warnings that name it."""
    out: dict[str, list[DecisionWarning]] = {}
    for w in r.warnings:
        for oid in w.option_ids:
            out.setdefault(oid, []).append(w)
    return out


def part_label(key: str, lang: str = "TR") -> str:
    if key.startswith(PENALTY):
        return t("penalty", lang, rule=key[len(PENALTY):])
    k = "p_" + key
    return t(k, lang) if k in LABELS else key


def part_rows(o: ScoredOption, lang: str = "TR") -> list[dict]:
    """One bar per score part, in the engine's order; the values sum to the score."""
    return [{"key": k, "part": part_label(k, lang), "value": v, "reason": o.reasons[k]}
            for k, v in o.score_parts.items()]


MAIN_PARTS = 3


def main_parts(o: ScoredOption, lang: str = "TR") -> list[dict]:
    """The MAIN_PARTS largest score parts by size (penalties count by their size)."""
    return sorted(part_rows(o, lang), key=lambda b: -abs(b["value"]))[:MAIN_PARTS]


def kind_key(o: ScoredOption | RejectedOption) -> str:
    return o.option.kind if o.option.kind == "deposit" else o.option.fund_kind


def kind_name(key: str, lang: str = "TR") -> str:
    k = "kind." + key
    return t(k, lang) if k in LABELS else key


def kind_label(o: ScoredOption | RejectedOption, lang: str = "TR") -> str:
    return kind_name(kind_key(o), lang)


def kind_keys(options) -> list[str]:
    return sorted({kind_key(o) for o in options})


def row_title(prefix: str, o: ScoredOption, has_warning: bool, lang: str = "TR") -> str:
    bits = [f"{prefix} {o.option.label}", kind_label(o, lang)]
    if o.option.fx:
        bits.append("FX")
    bits += [f"{t('score', lang)} {o.score:.2f}", f"{t('confidence', lang)} {o.confidence:.2f}",
             f"{t('stability', lang)} {o.stability:.2f}"]
    if has_warning:
        bits.append("⚠")
    return " · ".join(bits)


def table_rows(r: DecisionResult, kinds: list[str] = (), lang: str = "TR") -> list[dict]:
    """Rows of "Tüm puanlananlar"; kinds = the fund_kind filter (empty = all)."""
    w = warned(r)
    rows = []
    for pos, o in enumerate(r.options, start=1):
        if kinds and kind_key(o) not in kinds:
            continue
        rows.append({
            t("col_pos", lang): pos,
            t("col_label", lang): o.option.label,
            t("col_kind", lang): kind_label(o, lang),
            "FX": "FX" if o.option.fx else "",
            t("score", lang): round(o.score, 3),
            t("confidence", lang): round(o.confidence, 2),
            t("stability", lang): round(o.stability, 2),
            "⚠": "⚠" if o.option.option_id in w else "",
        })
    return rows


# --- evidence (docs/ui.md section 5) and citations (section 4) -------------------

_FLAG_COLORS = {"missing": "red", "out_of_range": "red", "conflict": "red", "stale": "orange",
                "needs_check": "orange", "fallback_snapshot": "orange",
                "unverified_series": "gray", "manual_entry": "blue"}


def flag_badges(flags) -> str:
    """Flags as streamlit badges, e.g. ":orange-badge[stale]"."""
    return " ".join(f":{_FLAG_COLORS.get(f, 'gray')}-badge[{f}]" for f in sorted(flags))


def _value(dp) -> str:
    return "—" if dp.value is None else f"{dp.value:,.6g} {dp.unit}"


def evidence_rows(ev: EvidenceSet, ids=None, lang: str = "TR") -> list[dict]:
    """One row per DataPoint of ev, only those in ids if ids is given, sorted by id."""
    keep = None if ids is None else set(ids)
    rows = []
    for dp in ev.datapoints:
        if keep is not None and dp.id not in keep:
            continue
        info = ev.entities.get(dp.entity)
        rows.append({
            t("col_id", lang): dp.id,
            t("col_quantity", lang): dp.quantity,
            t("col_entity", lang): f"{dp.entity} · {info.name}" if info else dp.entity,
            t("col_value", lang): _value(dp),
            t("col_as_of", lang): dp.as_of.isoformat(),
            t("col_source", lang): dp.source,
            t("col_url", lang): dp.source_url,
            t("col_flags", lang): flag_badges(f.value for f in dp.flags),
            t("col_note", lang): dp.note,
        })
    return sorted(rows, key=lambda row: row[t("col_id", lang)])


def citations(r: DecisionResult, ev: EvidenceSet, lang: str = "TR") -> list[str]:
    """One citation per source of the evidence rows the result used, by source name."""
    used = r.evidence_ids()
    rows = [dp for dp in ev.datapoints if dp.id in used]
    out: list[str] = []
    for source in sorted({dp.source for dp in rows}):
        if source == "evds":
            text = t("cite_evds", lang)
        elif source in ("tefas", "tefas_web"):
            text = t("cite_tefas", lang)
        elif source == "manual" and any(dp.entity.startswith("ING") for dp in rows
                                        if dp.source == "manual"):
            as_of = max(dp.as_of for dp in rows if dp.source == "manual")
            text = t("cite_manual_ing", lang, as_of=as_of.isoformat())
        else:
            text = t("cite_other", lang, source=source)
        if text not in out:
            out.append(text)
    return out


# --- RM loop (docs/ui.md sections 2 and 3) ---------------------------------------

OTHER = "diğer"
LIST_FIELDS = ("oncelikler", "acik_kisitlar")
LEVEL_FIELDS = ("risk_profili", "yatirim_ufku", "likidite_ihtiyaci", "doviz_maruz_kalma_tercihi",
                "gelir_nakit_akisi_ihtiyaci", "anapara_koruma_tercihi")
_QID_SHORT = 12


@dataclass(frozen=True)
class RunInputs:
    """The inputs of one run: a change of any of them makes a new run."""

    persona: Persona
    snapshot_id: str
    excluded_sources: frozenset[str]
    answers: tuple[tuple[str, str], ...]     # sorted (question_id, answer)


def open_questions(r: DecisionResult) -> list[ClarificationQuestion]:
    """Unanswered questions, blocking ones first (else in engine order)."""
    return sorted((q for q in r.questions if q.answer is None), key=lambda q: not q.blocking)


def _field_text(p: Persona, name: str) -> str:
    v = getattr(p, name)
    return ", ".join(v) if name in LIST_FIELDS else str(v)


def persona_diff(old: Persona, new: Persona, lang: str = "TR") -> list[str]:
    """One "field old → new" text per changed field, e.g. "yaş 62 → 45"."""
    out = []
    for f in dataclasses.fields(Persona):
        if getattr(old, f.name) != getattr(new, f.name):
            out.append(f"{t('f_' + f.name, lang).lower()} {_field_text(old, f.name)} → "
                       f"{_field_text(new, f.name)}")
    return out


def _short_qid(qid: str) -> str:
    return qid if len(qid) <= _QID_SHORT else qid[:_QID_SHORT] + "…"


def describe_change(prev: RunInputs | None, new: RunInputs, lang: str = "TR") -> str:
    """What changed from the previous run, for the run history."""
    if prev is None:
        return t("ch_first", lang)
    bits = []
    if prev.persona != new.persona:
        bits.append(t("ch_test", lang, diff=", ".join(persona_diff(prev.persona, new.persona, lang))))
    if prev.snapshot_id != new.snapshot_id:
        bits.append(t("ch_snapshot", lang, snapshot=new.snapshot_id))
    for s in sorted(new.excluded_sources - prev.excluded_sources):
        bits.append(t("ch_excluded", lang, source=s))
    for s in sorted(prev.excluded_sources - new.excluded_sources):
        bits.append(t("ch_included", lang, source=s))
    old_answers = dict(prev.answers)
    for qid, a in new.answers:
        if old_answers.get(qid) != a:
            bits.append(t("ch_answer", lang, question=_short_qid(qid), answer=a))
    return "; ".join(bits) or t("ch_none", lang)


def known_levels(raw_config: Mapping, personas) -> dict[str, list[str]]:
    """Pick-list values per level field: the levels of config/decision.yaml, then
    the values the personas use (so every persona can be shown unchanged)."""
    levels = list(raw_config.get("levels", {}))
    out = {
        "risk_profili": list(raw_config.get("risk_profiles", {})),
        "yatirim_ufku": [],
        "likidite_ihtiyaci": list(levels),
        "doviz_maruz_kalma_tercihi": list(raw_config.get("fx_levels", {})),
        "gelir_nakit_akisi_ihtiyaci": list(levels),
        "anapara_koruma_tercihi": list(levels),
    }
    for p in personas:
        for name, values in out.items():
            v = getattr(p, name)
            if v not in values:
                values.append(v)
    return out
