"""The one page of the UI (docs/ui.md section 1). All backend calls go through
the Backend in st.session_state["backend"]; a run is made only when its inputs
change, so a plain rerun (any click) does not call the engine again."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import streamlit as st

from rmprep.contracts import Backend, DecisionResult, DecisionState, EvidenceSet, Persona
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


def main() -> None:
    lang = _lang()
    st.set_page_config(page_title=t("title", lang), layout="wide")
    backend = _backend()
    persona, snapshot_id, excluded = _sidebar(backend, lang)
    result = _current_result(backend, persona, snapshot_id, excluded)

    main_col, pane = st.columns([3, 1])
    with main_col:
        _header(result, lang)
    with pane:
        st.subheader(t("issues", lang))
        st.caption(t("coming_later", lang))
