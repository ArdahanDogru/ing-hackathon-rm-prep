"""What the page shows, as plain data (no streamlit), so tests can check it
without a browser: the shortlist split, the paging steps, the score bars, the
row titles and table rows."""

from __future__ import annotations

from rmprep.contracts import (
    DecisionResult,
    DecisionWarning,
    EvidenceSet,
    RejectedOption,
    ScoredOption,
)
from rmprep.ui.i18n import LABELS, t

FIRST_PAGE = 3
SECOND_PAGE = 10
PAGE_STEP = 10
PENALTY = "penalty:"


def baseline(r: DecisionResult) -> ScoredOption | None:
    """The deposit baseline ("Karşılaştırma"): options[0] if it is a deposit."""
    if r.options and r.options[0].option.kind == "deposit":
        return r.options[0]
    return None


def ranked(r: DecisionResult) -> tuple[ScoredOption, ...]:
    """The options after the baseline, in display order."""
    return r.options[1:] if baseline(r) is not None else r.options


def next_count(shown: int) -> int:
    return SECOND_PAGE if shown < SECOND_PAGE else shown + PAGE_STEP


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


def kind_key(o: ScoredOption | RejectedOption) -> str:
    return o.option.kind if o.option.kind == "deposit" else o.option.fund_kind


def kind_name(key: str, lang: str = "TR") -> str:
    k = "fk_" + key
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
