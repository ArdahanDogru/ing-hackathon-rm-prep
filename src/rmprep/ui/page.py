"""The one page of the UI (docs/ui.md section 1). All backend calls go through
the Backend in st.session_state["backend"]; a run is made only when its inputs
(views.RunInputs) change, so a plain rerun (any click) does not call the engine
again. Widget state is put in st.session_state before the widget is made, so no
widget gets both a default value and a session-state value."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import streamlit as st
import yaml

from rmprep import grouping
from rmprep.backend import RealBackend
from rmprep.contracts import (
    Backend,
    DecisionResult,
    DecisionState,
    EvidenceSet,
    NarrativeDraft,
    NarrativeStatus,
    Persona,
    RmStatus,
    ScoredOption,
)
from rmprep.narrator import template
from rmprep.ui import card, views
from rmprep.ui.fake import FakeBackend
from rmprep.ui.i18n import LANGS, t

PROTOTYPE = Path(__file__).resolve().parents[3]
FIXTURES = PROTOTYPE / "tests" / "contracts" / "fixtures"
DECISION_CONFIG = PROTOTYPE / "config" / "decision.yaml"
_EDIT = "edit:"
_TEXT_FIELDS = ("profil", "durum", "yatirim_amaci", "rm_notu")
_OPEN_REJECTED = 10   # more rejected options than this start closed


def default_backend() -> Backend:
    """RealBackend on $RMPREP_ROOT (the prototype folder) if it is set, else the
    FakeBackend on the contract fixtures (docs/ui.md, "Real backend")."""
    root = os.environ.get("RMPREP_ROOT")
    if root:
        return RealBackend(root)
    return FakeBackend(FIXTURES)


def _backend() -> Backend:
    if "backend" not in st.session_state:
        st.session_state["backend"] = default_backend()
    return st.session_state["backend"]


def _lang() -> str:
    return st.session_state.get("lang", "TR")


def _default(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


@st.cache_data
def _config_raw() -> dict:
    """config/decision.yaml as parsed, read only for the level pick lists."""
    if not DECISION_CONFIG.exists():
        return {}
    return yaml.safe_load(DECISION_CONFIG.read_text(encoding="utf-8")) or {}


# --- sidebar: persona, persona edit, snapshot, sources ------------------------

def _persona_card(p: Persona, lang: str) -> None:
    with st.container(border=True):
        for f in dataclasses.fields(p):
            v = getattr(p, f.name)
            if f.name in views.LIST_FIELDS:
                v = ", ".join(v) if v else "—"
            if v == "":
                continue
            st.markdown(f"**{t('f_' + f.name, lang)}:** {v}")


def _drop_edit_state() -> None:
    for k in [k for k in st.session_state.keys() if str(k).startswith(_EDIT)]:
        del st.session_state[k]


def _reset_persona(pid: str) -> None:
    """A persona pick: answers, the test persona and the run history start again."""
    st.session_state["pid"] = pid
    st.session_state["answers"] = {}
    st.session_state["edited"] = None
    st.session_state["history"] = []
    _drop_edit_state()


def _init_edit_state(p: Persona, levels: dict[str, list[str]]) -> None:
    for f in dataclasses.fields(p):
        key, v = _EDIT + f.name, getattr(p, f.name)
        if f.name == "persona_id" or key in st.session_state:
            continue
        if f.name in views.LIST_FIELDS:
            st.session_state[key] = "\n".join(v)
        elif f.name in views.LEVEL_FIELDS:
            known = v in levels[f.name]
            st.session_state[key] = v if known else views.OTHER
            st.session_state[key + ":other"] = "" if known else v
        else:
            st.session_state[key] = v


def _apply_edit(original: Persona) -> None:
    ss = st.session_state
    d: dict = {"persona_id": original.persona_id, "yas": int(ss[_EDIT + "yas"])}
    for name in _TEXT_FIELDS:
        d[name] = ss[_EDIT + name]
    for name in views.LEVEL_FIELDS:
        v = ss[_EDIT + name]
        d[name] = ss[_EDIT + name + ":other"].strip() if v == views.OTHER else v
    for name in views.LIST_FIELDS:
        d[name] = tuple(x.strip() for x in ss[_EDIT + name].splitlines() if x.strip())
    try:
        edited = Persona(**d)
    except ValueError as e:
        ss["edit_error"] = str(e)
        return
    ss["edited"] = None if edited == original else edited


def _reset_edit() -> None:
    st.session_state["edited"] = None
    _drop_edit_state()


def _edit_form(original: Persona, current: Persona, levels: dict[str, list[str]],
               lang: str) -> None:
    """ "Düzenle": every schema field; "Uygula" makes a test run (docs/ui.md section 2)."""
    _init_edit_state(current, levels)
    with st.expander(t("edit", lang), expanded=st.session_state["edited"] is not None):
        with st.form("edit_form", border=False):
            st.number_input(t("f_yas", lang), min_value=0, max_value=120, step=1, key=_EDIT + "yas")
            for f in dataclasses.fields(Persona):
                name, label = f.name, t("f_" + f.name, lang)
                if name in _TEXT_FIELDS:
                    st.text_input(label, key=_EDIT + name)
                elif name in views.LEVEL_FIELDS:
                    st.selectbox(label, [*levels[name], views.OTHER], key=_EDIT + name)
                    st.text_input(t("other_text", lang, field=label), key=_EDIT + name + ":other")
                elif name in views.LIST_FIELDS:
                    st.text_area(t("one_per_line", lang, field=label), key=_EDIT + name)
            st.form_submit_button(t("apply", lang), key="edit_apply", on_click=_apply_edit,
                                  args=(original,))
        st.button(t("reset", lang), key="edit_reset", on_click=_reset_edit)
        err = st.session_state.pop("edit_error", None)
        if err:
            st.error(f"{t('edit_invalid', lang)}: {err}")


def _sources(ev: EvidenceSet, lang: str) -> frozenset[str]:
    st.markdown(f"**{t('sources', lang)}**")
    excluded = set()
    for name, status in sorted(ev.source_status.items()):
        label = f"{name} ({status.status})"
        if status.fallback_from:
            label += " · " + t("fallback_from", lang, snapshot=status.fallback_from)
        _default(f"src:{name}", True)
        if not st.checkbox(label, key=f"src:{name}"):
            excluded.add(name)
    return frozenset(excluded)


def _sidebar(backend: Backend, lang: str) -> tuple[Persona, views.RunInputs]:
    """Returns the original persona of the pick and the inputs of the run to show."""
    personas = {p.persona_id: p for p in backend.list_personas()}
    with st.sidebar:
        pid = st.selectbox(t("persona", lang), list(personas), key="persona",
                           format_func=lambda i: f"{i} · {personas[i].profil}")
        original = personas[pid]
        if st.session_state.get("pid") != pid:
            _reset_persona(pid)
        persona = st.session_state["edited"] or original
        _persona_card(persona, lang)
        levels = views.known_levels(_config_raw(), personas.values())
        _edit_form(original, persona, levels, lang)
        snapshot_id = st.selectbox(t("snapshot", lang), backend.list_snapshots(), key="snapshot")
        excluded = _sources(backend.evidence(snapshot_id), lang)
        _default("lang", "TR")
        st.radio(t("lang", lang), LANGS, key="lang", horizontal=True)
    answers = tuple(sorted(st.session_state["answers"].items()))
    return original, views.RunInputs(persona, snapshot_id, excluded, answers)


# --- runs and run history -----------------------------------------------------

def _one_new_answer(prev: views.RunInputs, new: views.RunInputs) -> tuple[str, str] | None:
    """The answer, if one new or changed answer is the only change from prev to new."""
    if dataclasses.replace(prev, answers=new.answers) != new:
        return None
    old, now = dict(prev.answers), dict(new.answers)
    changed = [(q, a) for q, a in new.answers if old.get(q) != a]
    if len(changed) == 1 and set(old) <= set(now):
        return changed[0]
    return None


def _run(backend: Backend, prev: views.RunInputs | None, current: DecisionResult | None,
         inputs: views.RunInputs) -> DecisionResult:
    one = _one_new_answer(prev, inputs) if prev is not None and current is not None else None
    if one is not None:
        return backend.answer_question(current.run_id, *one)
    r = backend.decide(inputs.persona, inputs.snapshot_id, inputs.excluded_sources)
    for qid, answer in inputs.answers:      # answers stay while the persona stays
        if qid in {q.question_id for q in r.questions}:
            r = backend.answer_question(r.run_id, qid, answer)
    return r


def _set_result(r: DecisionResult) -> None:
    st.session_state["result"] = r
    for h in st.session_state.get("history", []):
        if h["run_id"] == r.run_id:
            h["result"], h["status"] = r, r.rm_status


def _current_result(backend: Backend, inputs: views.RunInputs) -> DecisionResult:
    prev = st.session_state.get("inputs")
    if prev == inputs and "result" in st.session_state:
        return st.session_state["result"]
    history = st.session_state["history"]
    r = _run(backend, prev, st.session_state.get("result"), inputs)
    if r.run_id not in {h["run_id"] for h in history}:
        history.append({"run_id": r.run_id, "status": r.rm_status, "result": r, "inputs": inputs,
                        "edited": st.session_state["edited"] is not None,
                        "change": views.describe_change(prev if history else None, inputs)})
    st.session_state["inputs"] = inputs
    _set_result(r)
    return r


def _restore(i: int) -> None:
    """Show run i of the history again, with its inputs in the widgets."""
    ss = st.session_state
    h = ss["history"][i]
    inputs: views.RunInputs = h["inputs"]
    ss["snapshot"] = inputs.snapshot_id
    for k in [k for k in ss.keys() if str(k).startswith("src:")]:
        ss[k] = k[len("src:"):] not in inputs.excluded_sources
    ss["answers"] = dict(inputs.answers)
    ss["edited"] = inputs.persona if h["edited"] else None
    _drop_edit_state()
    ss["inputs"] = inputs
    ss["result"] = h["result"]


def _history_panel(r: DecisionResult, lang: str) -> None:
    st.markdown(f"**{t('runs', lang)}**")
    for i, h in enumerate(st.session_state["history"]):
        mark = "▶ " if h["run_id"] == r.run_id else ""
        st.button(f"{mark}{h['run_id']} · {h['change']} · {h['status'].value}", key=f"hist:{i}",
                  on_click=_restore, args=(i,))


# --- main: header, questions ----------------------------------------------------

def _header(r: DecisionResult, original: Persona, lang: str) -> None:
    p = r.persona
    st.subheader(f"{p.persona_id} · {p.profil} · {p.risk_profili}")
    if r.state == DecisionState.READY:
        st.success(t("state_ready", lang))
    else:
        st.warning(t("state_needs_input", lang))
    if p != original:
        st.warning(t("test_banner", lang, pid=p.persona_id,
                     diff=", ".join(views.persona_diff(original, p, lang))))
    line = f"{t('run', lang)} {r.run_id} · {t('rm_status', lang)}: {r.rm_status.value}"
    if r.excluded_sources:
        line += f" · {t('excluded', lang)}: {', '.join(sorted(r.excluded_sources))}"
    st.caption(line)


def _answer(qid: str) -> None:
    v = st.session_state.get(f"qv:{qid}")
    if v is None or not str(v).strip():
        st.session_state["q_error"] = qid
        return
    st.session_state["answers"] = {**st.session_state["answers"], qid: str(v).strip()}


def _questions(r: DecisionResult, lang: str) -> None:
    qs = views.open_questions(r)
    if not qs:
        return
    st.markdown(f"**{t('questions', lang)}**")
    err = st.session_state.pop("q_error", None)
    for q in qs:
        with st.container(border=True):
            badge = (f":red-badge[{t('blocking', lang)}]" if q.blocking
                     else f":gray-badge[{t('non_blocking', lang)}]")
            st.markdown(f"{badge} {q.text}")
            st.caption(q.reason)
            if q.choices:
                st.radio(t("answer", lang), q.choices, index=None, key=f"qv:{q.question_id}")
            else:
                st.text_input(t("answer", lang), key=f"qv:{q.question_id}")
            st.button(t("apply", lang), key=f"qa:{q.question_id}", on_click=_answer,
                      args=(q.question_id,))
            if err == q.question_id:
                st.error(t("need_answer", lang))


# --- main: tabs -------------------------------------------------------------------

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


def _open_evidence(ids: tuple[str, ...], run_id: str, lang: str) -> None:
    st.session_state["ev_filter"] = (run_id, ids)
    st.session_state[f"tabs:{lang}"] = t("tab_evidence", lang)


def _evidence_button(ids, key: str, r: DecisionResult, lang: str) -> None:
    """One click target for a group of evidence ids: opens "Kanıt" filtered to them."""
    ids = tuple(dict.fromkeys(ids))
    if ids:
        st.button(t("show_evidence", lang, n=len(ids)), key=key, on_click=_open_evidence,
                  args=(ids, r.run_id, lang))


def _open_warning(run_id: str, i: int) -> None:
    st.session_state["warn_open"] = (run_id, i)


def _option_row(title: str, o: ScoredOption, r: DecisionResult, lang: str) -> None:
    oid = o.option.option_id
    with st.expander(title):
        for i, w in enumerate(r.warnings):
            if oid in w.option_ids:
                st.button(f"⚠ {w.code}", key=f"warn:{oid}:{i}", on_click=_open_warning,
                          args=(r.run_id, i))
        st.markdown(f"**{t('score_parts', lang)}**")
        _parts_chart(o, lang)
        for b in views.part_rows(o, lang):
            st.markdown(f"- **{b['part']}** ({b['value']:+.3f}): {b['reason']}")
        if o.constraints:
            st.markdown(f"**{t('constraints', lang)}**")
            for c in o.constraints:
                st.markdown(f"- ✓ `{c.rule_id}`: {c.reason}")
        ids = (*o.evidence_ids, *(i for c in o.constraints for i in c.evidence_ids))
        if ids:
            st.caption(f"{t('evidence_ids', lang)}: {', '.join(dict.fromkeys(ids))}")
            _evidence_button(ids, f"ev:opt:{oid}", r, lang)


def _opened(run_id: str) -> frozenset[str]:
    """The kinds whose alternatives are all shown ("Daha fazla"), for this run."""
    opened = st.session_state.get("opened")
    return opened[1] if opened and opened[0] == run_id else frozenset()


def _more(run_id: str, kind: str) -> None:
    st.session_state["opened"] = (run_id, _opened(run_id) | {kind})


def _shown_options(r: DecisionResult) -> list[ScoredOption]:
    return views.shown_options(r, _opened(r.run_id))


def _shortlist(r: DecisionResult, lang: str) -> None:
    if not r.options:
        st.info(t("no_options", lang))
        return
    w = views.warned(r)
    base = views.baseline(r)
    if base is not None:
        _option_row(views.row_title(t("baseline", lang), base, base.option.option_id in w, lang),
                    base, r, lang)
    pos = views.positions(r)
    opened = _opened(r.run_id)
    for g in grouping.groups(r.options):
        label = views.kind_name(g.key, lang)
        st.markdown(f"#### {t('group_header', lang, label=label, n=1 + len(g.alternatives))}")
        head = g.head
        _option_row(views.row_title(f"{pos[head.option.option_id]}.", head,
                                    head.option.option_id in w, lang), head, r, lang)
        alts = grouping.visible_alternatives(g, g.key in opened)
        for o in alts:
            oid = o.option.option_id
            _option_row(views.row_title(f"↳ {pos[oid]}.", o, oid in w, lang), o, r, lang)
        if len(alts) < len(g.alternatives):
            st.button(t("more", lang), key=f"more:{g.key}", on_click=_more, args=(r.run_id, g.key))


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
    expanded = len(r.rejected) <= _OPEN_REJECTED
    for rj in r.rejected:
        with st.expander(f"{rj.option.label} · {views.kind_label(rj, lang)}", expanded=expanded):
            st.markdown(f"**{t('failed_rules', lang)}**")
            for c in rj.failed:
                st.markdown(f"- ✗ `{c.rule_id}`: {c.reason}")
            ids = tuple(i for c in rj.failed for i in c.evidence_ids)
            if ids:
                st.caption(f"{t('evidence_ids', lang)}: {', '.join(dict.fromkeys(ids))}")
                _evidence_button(ids, f"ev:rej:{rj.option.option_id}", r, lang)


def _clear_evidence_filter() -> None:
    st.session_state.pop("ev_filter", None)


def _evidence_tab(r: DecisionResult, ev: EvidenceSet, lang: str) -> None:
    flt = st.session_state.get("ev_filter")
    if flt and flt[0] == r.run_id:
        ids = flt[1]
        st.info(t("ev_filter", lang, n=len(ids)))
        st.button(t("ev_all", lang), key="ev_all", on_click=_clear_evidence_filter)
    elif st.toggle(t("ev_whole", lang), key="ev_whole"):
        ids = None
    else:
        ids = r.evidence_ids()
        st.caption(t("ev_used", lang, n=len(ids)))
    rows = views.evidence_rows(ev, ids, lang)
    if ids is not None and len(rows) < len(set(ids)):
        st.caption(t("ev_missing", lang, n=len(set(ids)) - len(rows)))
    st.dataframe(rows, hide_index=True, column_config={
        t("col_url", lang): st.column_config.LinkColumn(),
        t("col_flags", lang): st.column_config.MarkdownColumn(),
    })


def _tabs(r: DecisionResult, ev: EvidenceSet, lang: str) -> None:
    short, all_, rejected, evidence = st.tabs(
        [t(k, lang) for k in ("tab_short", "tab_all", "tab_rejected", "tab_evidence")],
        key=f"tabs:{lang}", on_change="rerun")
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
        _evidence_tab(r, ev, lang)


# --- main: RM bar -------------------------------------------------------------------

def _approve(run_id: str, option_ids: tuple[str, ...]) -> None:
    ss = st.session_state
    selected = tuple(o for o in option_ids if ss.get(f"sel:{run_id}:{o}"))
    if not selected:
        ss["rm_error"] = "need_selection"
        return
    r = ss["backend"].approve(run_id, RmStatus.APPROVED, ss.get(f"note:{run_id}", ""), selected)
    _set_result(r)
    _save_card(r)


def _save_card(r: DecisionResult) -> None:
    ss = st.session_state
    lang = _lang()
    md = card.render_markdown(r, ss["evidence"][1], lang, _approved_narrative(r.run_id, lang))
    ss["card_saved"] = (r.run_id, ss["backend"].save_card(r.run_id, md))


def _save_notes(run_id: str, option_ids: tuple[str, ...]) -> None:
    ss = st.session_state
    notes = {o: ss.get(f"card_onote:{run_id}:{o}", "").strip() for o in option_ids}
    r = ss["backend"].annotate(run_id, ss.get(f"card_note:{run_id}", "").strip(),
                               {o: n for o, n in notes.items() if n})
    _set_result(r)
    _save_card(r)


def _reject(run_id: str) -> None:
    ss = st.session_state
    note = ss.get(f"note:{run_id}", "")
    if not note.strip():
        ss["rm_error"] = "need_note"
        return
    _set_result(ss["backend"].approve(run_id, RmStatus.REJECTED, note))


def _rm_bar(r: DecisionResult, original: Persona, lang: str) -> None:
    """Select the options to discuss, then approve or reject (docs/ui.md section 3)."""
    if r.state != DecisionState.READY or not r.options:
        return
    st.divider()
    st.markdown(f"**{t('rm_bar', lang)}**")
    if r.rm_status != RmStatus.PENDING:
        st.success(t("rm_" + r.rm_status.value, lang))
        if r.rm_status == RmStatus.APPROVED:
            _card(r, lang)
        elif r.rm_note:
            st.caption(r.rm_note)
        return
    test = r.persona != original
    shown = _shown_options(r)
    for o in shown:
        st.checkbox(t("discuss", lang, label=o.option.label),
                    key=f"sel:{r.run_id}:{o.option.option_id}", disabled=test)
    st.text_area(t("rm_note", lang), key=f"note:{r.run_id}", disabled=test)
    err = st.session_state.pop("rm_error", None)
    if err:
        st.error(t(err, lang))
    ids = tuple(o.option.option_id for o in shown)
    st.button(t("approve", lang), key="approve", type="primary", disabled=test, on_click=_approve,
              args=(r.run_id, ids))
    st.button(t("reject", lang), key="reject", disabled=test, on_click=_reject, args=(r.run_id,))
    if test:
        st.caption(t("test_no_approve", lang))


def _card(r: DecisionResult, lang: str) -> None:
    """The summary card of an approved run, its downloads and its notes."""
    ev = st.session_state["evidence"][1]
    narrative = _approved_narrative(r.run_id, lang)
    md = card.render_markdown(r, ev, lang, narrative)
    with st.container(border=True):
        st.markdown(md)
    st.download_button(t("dl_md", lang), md, file_name=f"{r.run_id}.md", mime="text/markdown",
                       key="dl_md")
    st.download_button(t("dl_html", lang), card.render_html(r, ev, lang, narrative),
                       file_name=f"{r.run_id}.html", mime="text/html", key="dl_html")
    _default(f"card_note:{r.run_id}", r.rm_note)
    st.text_area(t("card_note", lang), key=f"card_note:{r.run_id}")
    labels = {o.option.option_id: o.option.label for o in r.options}
    for oid in r.rm_selected:
        _default(f"card_onote:{r.run_id}:{oid}", r.rm_option_notes.get(oid, ""))
        st.text_area(t("card_onote", lang, label=labels[oid]), key=f"card_onote:{r.run_id}:{oid}")
    st.button(t("save_notes", lang), key="save_notes", on_click=_save_notes,
              args=(r.run_id, r.rm_selected))
    saved = st.session_state.get("card_saved")
    if saved and saved[0] == r.run_id:
        st.caption(t("card_saved", lang, where=saved[1]))


# --- main: meeting text (narrator, contract v1.2) --------------------------------------

def _narratives() -> dict:
    """(run_id, lang) -> the NarrativeDraft of this session: one per language, made
    when that language is first opened (an LLM call costs money)."""
    return st.session_state.setdefault("narratives", {})


def _approved_narrative(run_id: str, lang: str) -> NarrativeDraft | None:
    d = _narratives().get((run_id, lang))
    return d if d is not None and d.status == NarrativeStatus.APPROVED else None


def _text_key(run_id: str, lang: str) -> str:
    return f"nar_text:{run_id}:{lang}"


def _approve_text(run_id: str, lang: str) -> None:
    ss = st.session_state
    text = ss.get(_text_key(run_id, lang), "")
    if not text.strip():
        ss["nar_error"] = (run_id, lang)
        return
    _narratives()[(run_id, lang)] = ss["backend"].approve_narrative(run_id, lang, text)
    _save_card(ss["result"])


def _meeting_text(backend: Backend, r: DecisionResult, original: Persona, lang: str) -> None:
    """ "Görüşme metni": the narrator draft of an approved run that is not a test
    run; the RM edits it and approves it (docs/narrator.md, "Human control")."""
    if r.rm_status != RmStatus.APPROVED or r.persona != original:
        return
    st.divider()
    st.subheader(t("nar_title", lang))
    key = (r.run_id, lang)
    if key not in _narratives():
        try:
            with st.spinner(t("nar_wait", lang)):
                _narratives()[key] = backend.draft_narrative(r.run_id, lang)
        except Exception as e:   # the backend's narrator: API, budget, config
            st.error(t("nar_error", lang, error=e))
            return
    d = _narratives()[key]
    note = template.banner(d)
    if note:
        st.warning(note)
    labels = {o.option.option_id: o.option.label for o in r.options}
    for i, sec in enumerate(d.sections):
        st.markdown(f"**{template.HEADINGS[sec.key][lang]}**")
        for j, s in enumerate(sec.sentences):
            st.markdown(f"- {s.text}")
            if s.option_ids:
                names = ", ".join(labels.get(o, o) for o in s.option_ids)
                st.caption(t("nar_options", lang, labels=names))
            _evidence_button(s.evidence_ids, f"ev:nar:{lang}:{i}:{j}", r, lang)
    _default(_text_key(r.run_id, lang),
             d.rm_text if d.status == NarrativeStatus.APPROVED else template.to_markdown(d))
    st.text_area(t("nar_edit", lang), key=_text_key(r.run_id, lang), height=320)
    if st.session_state.pop("nar_error", None) == key:
        st.error(t("nar_empty", lang))
    st.button(t("nar_approve", lang), key="nar_approve", type="primary", on_click=_approve_text,
              args=(r.run_id, lang))
    if d.status == NarrativeStatus.APPROVED:
        st.success(t("nar_approved", lang))
    st.caption(t("nar_meta", lang, source=d.source, model=d.model or "—", cost=f"{d.cost_usd:.4f}",
                 version=d.prompt_version, status=t("nar_status_" + d.status.value, lang)))


# --- right pane ---------------------------------------------------------------------

def _pane(r: DecisionResult, lang: str) -> None:
    """"Olası sorunlar": warnings, data-quality notes, assumptions."""
    st.subheader(t("issues", lang))
    labels = {o.option.option_id: o.option.label for o in (*r.options, *r.rejected)}
    opened = st.session_state.get("warn_open")
    open_i = opened[1] if opened and opened[0] == r.run_id else None
    st.markdown(f"**{t('warnings', lang)}**")
    if not r.warnings:
        st.caption(t("none", lang))
    for i, w in enumerate(r.warnings):
        with st.expander(f"⚠ {w.code}", expanded=i == open_i):
            st.markdown(w.message)
            names = ", ".join(labels[o] for o in w.option_ids) or t("whole_result", lang)
            st.caption(f"{t('about_options', lang)}: {names}")
            _evidence_button(w.evidence_ids, f"ev:warn:{i}", r, lang)
    st.markdown(f"**{t('data_quality', lang)}**")
    if not r.data_quality:
        st.caption(t("none", lang))
    for i, n in enumerate(r.data_quality):
        st.markdown(f"ⓘ {n.message}")
        meta = " ".join(filter(None, [views.flag_badges(n.flags), ", ".join(n.sources)]))
        if meta:
            st.caption(meta)
        _evidence_button(n.evidence_ids, f"ev:dq:{i}", r, lang)
    st.markdown(f"**{t('assumptions', lang)}**")
    if not r.assumptions:
        st.caption(t("none", lang))
    for a in r.assumptions:
        st.markdown(f"- {a}")


def _evidence(backend: Backend, snapshot_id: str, excluded: frozenset[str]) -> EvidenceSet:
    key = (snapshot_id, tuple(sorted(excluded)))
    cached = st.session_state.get("evidence")
    if cached is None or cached[0] != key:
        cached = (key, backend.evidence(snapshot_id, excluded))
        st.session_state["evidence"] = cached
    return cached[1]


def main() -> None:
    lang = _lang()
    st.set_page_config(page_title=t("title", lang), layout="wide")
    backend = _backend()
    original, inputs = _sidebar(backend, lang)
    result = _current_result(backend, inputs)
    with st.sidebar:
        _history_panel(result, lang)
    ev = _evidence(backend, inputs.snapshot_id, inputs.excluded_sources)

    main_col, pane = st.columns([3, 1])
    with main_col:
        _header(result, original, lang)
        _questions(result, lang)
        _tabs(result, ev, lang)
        _rm_bar(result, original, lang)
        _meeting_text(backend, result, original, lang)
        st.divider()
        for c in views.citations(result, ev, lang):
            st.caption(c)
        if lang == "EN":
            st.caption(t("en_footer", lang))
    with pane:
        _pane(result, lang)
