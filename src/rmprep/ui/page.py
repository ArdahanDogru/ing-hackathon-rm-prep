"""The one page of the UI (docs/ui.md section 1). All backend calls go through
the Backend in st.session_state["backend"]; a run is made only when its inputs
change, so a plain rerun (any click) does not call the engine again."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import streamlit as st

from rmprep.contracts import (
    Backend,
    DecisionResult,
    DecisionState,
    EvidenceSet,
    Persona,
    ScoredOption,
)
from rmprep.ui import views
from rmprep.ui.i18n import t

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "contracts" / "fixtures"
_LIST_FIELDS = ("oncelikler", "acik_kisitlar")


def default_backend() -> Backend:
    from rmprep.ui.fake import FakeBackend

    return FakeBackend(FIXTURES)


def _backend() -> Backend:
    if "backend" not in st.session_state:
        st.session_state["backend"] = default_backend()
    return st.session_state["backend"]


def _lang() -> str:
    return st.session_state.get("lang", "TR")


# --- sidebar ------------------------------------------------------------------

def _persona_card(p: Persona, lang: str) -> None:
    with st.container(border=True):
        for f in dataclasses.fields(p):
            v = getattr(p, f.name)
            if f.name in _LIST_FIELDS:
                v = ", ".join(v) if v else "—"
            if v == "":
                continue
            st.markdown(f"**{t('f_' + f.name, lang)}:** {v}")


def _sources(ev: EvidenceSet, lang: str) -> frozenset[str]:
    st.markdown(f"**{t('sources', lang)}**")
    excluded = set()
    for name, status in sorted(ev.source_status.items()):
        label = f"{name} ({status.status})"
        if status.fallback_from:
            label += " · " + t("fallback_from", lang, snapshot=status.fallback_from)
        if not st.checkbox(label, value=True, key=f"src:{name}"):
            excluded.add(name)
    return frozenset(excluded)


def _sidebar(backend: Backend, lang: str) -> tuple[Persona, str, frozenset[str]]:
    personas = {p.persona_id: p for p in backend.list_personas()}
    with st.sidebar:
        pid = st.selectbox(t("persona", lang), list(personas), key="persona",
                           format_func=lambda i: f"{i} · {personas[i].profil}")
        persona = personas[pid]
        _persona_card(persona, lang)
        snapshot_id = st.selectbox(t("snapshot", lang), backend.list_snapshots(), key="snapshot")
        excluded = _sources(backend.evidence(snapshot_id), lang)
    return persona, snapshot_id, excluded


# --- runs ---------------------------------------------------------------------

def _current_result(backend: Backend, persona: Persona, snapshot_id: str,
                    excluded: frozenset[str]) -> DecisionResult:
    inputs = json.dumps([persona.to_dict(), snapshot_id, sorted(excluded)], sort_keys=True)
    if st.session_state.get("inputs") != inputs or "result" not in st.session_state:
        st.session_state["result"] = backend.decide(persona, snapshot_id, excluded)
        st.session_state["inputs"] = inputs
    return st.session_state["result"]


# --- main ---------------------------------------------------------------------

def _header(r: DecisionResult, lang: str) -> None:
    p = r.persona
    st.subheader(f"{p.persona_id} · {p.profil} · {p.risk_profili}")
    if r.state == DecisionState.READY:
        st.success(t("state_ready", lang))
    else:
        st.warning(t("state_needs_input", lang))
    line = f"{t('run', lang)} {r.run_id} · {t('rm_status', lang)}: {r.rm_status.value}"
    if r.excluded_sources:
        line += f" · {t('excluded', lang)}: {', '.join(sorted(r.excluded_sources))}"
    st.caption(line)


_POS_COLOR = "#2a78d6"   # diverging pair (blue / red), validated light and dark
_NEG_COLOR = "#e34948"


def _parts_chart(o: ScoredOption, lang: str) -> None:
    bars = views.part_rows(o, lang)
    spec = {
        "data": {"values": bars},
        "height": 28 * len(bars),
        "mark": {"type": "bar", "cornerRadiusEnd": 4, "height": {"band": 0.6}},
        "encoding": {
            "y": {"field": "part", "type": "nominal", "sort": None, "title": None},
            "x": {"field": "value", "type": "quantitative", "title": t("score", lang),
                  "axis": {"grid": False}},
            "color": {"condition": {"test": "datum.value < 0", "value": _NEG_COLOR},
                      "value": _POS_COLOR},
            "tooltip": [{"field": "part", "title": t("col_part", lang)},
                        {"field": "value", "title": t("col_value", lang), "format": "+.3f"},
                        {"field": "reason", "title": ""}],
        },
    }
    st.vega_lite_chart(spec)


def _option_row(title: str, o: ScoredOption, lang: str) -> None:
    with st.expander(title):
        st.markdown(f"**{t('score_parts', lang)}**")
        _parts_chart(o, lang)
        for b in views.part_rows(o, lang):
            st.markdown(f"- **{b['part']}** ({b['value']:+.3f}): {b['reason']}")
        if o.constraints:
            st.markdown(f"**{t('constraints', lang)}**")
            for c in o.constraints:
                st.markdown(f"- ✓ `{c.rule_id}`: {c.reason}")
        if o.evidence_ids:
            st.caption(f"{t('evidence_ids', lang)}: {', '.join(o.evidence_ids)}")


def _shown(run_id: str) -> int:
    shown = st.session_state.get("shown")
    return shown[1] if shown and shown[0] == run_id else views.FIRST_PAGE


def _more(run_id: str) -> None:
    st.session_state["shown"] = (run_id, views.next_count(_shown(run_id)))


def _shortlist(r: DecisionResult, lang: str) -> None:
    if not r.options:
        st.info(t("no_options", lang))
        return
    w = views.warned(r)
    base = views.baseline(r)
    if base is not None:
        _option_row(views.row_title(t("baseline", lang), base, base.option.option_id in w, lang),
                    base, lang)
    rest = views.ranked(r)
    shown = _shown(r.run_id)
    for pos, o in enumerate(rest[:shown], start=1):
        _option_row(views.row_title(f"{pos}.", o, o.option.option_id in w, lang), o, lang)
    if shown < len(rest):
        st.button(t("more", lang), key="more", on_click=_more, args=(r.run_id,))


def _all_scored(r: DecisionResult, lang: str) -> None:
    keys = views.kind_keys(r.options)
    if "kind_filter" in st.session_state:   # drop kinds the new result does not have
        st.session_state["kind_filter"] = [k for k in st.session_state["kind_filter"] if k in keys]
    kinds = st.multiselect(t("kind_filter", lang), keys, key="kind_filter",
                           format_func=lambda k: views.kind_name(k, lang))
    st.dataframe(views.table_rows(r, kinds, lang), hide_index=True)


def _rejected(r: DecisionResult, lang: str) -> None:
    if not r.rejected:
        st.info(t("no_rejected", lang))
        return
    for rj in r.rejected:
        with st.expander(f"{rj.option.label} · {views.kind_label(rj, lang)}", expanded=True):
            st.markdown(f"**{t('failed_rules', lang)}**")
            for c in rj.failed:
                st.markdown(f"- ✗ `{c.rule_id}`: {c.reason}")
                if c.evidence_ids:
                    st.caption(f"{t('evidence_ids', lang)}: {', '.join(c.evidence_ids)}")


def _tabs(r: DecisionResult, lang: str) -> None:
    short, all_, rejected, evidence = st.tabs(
        [t(k, lang) for k in ("tab_short", "tab_all", "tab_rejected", "tab_evidence")])
    if r.state == DecisionState.NEEDS_RM_INPUT:
        for tab in (short, all_, rejected):
            with tab:
                st.info(t("answer_first", lang))
    else:
        with short:
            _shortlist(r, lang)
        with all_:
            _all_scored(r, lang)
        with rejected:
            _rejected(r, lang)
    with evidence:
        st.caption(t("coming_later", lang))


def main() -> None:
    lang = _lang()
    st.set_page_config(page_title=t("title", lang), layout="wide")
    backend = _backend()
    persona, snapshot_id, excluded = _sidebar(backend, lang)
    result = _current_result(backend, persona, snapshot_id, excluded)

    main_col, pane = st.columns([3, 1])
    with main_col:
        _header(result, lang)
        _tabs(result, lang)
    with pane:
        st.subheader(t("issues", lang))
        st.caption(t("coming_later", lang))
