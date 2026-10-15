"""JSON API over the Backend protocol (docs/web-ui.md sections 1, 6, 8; lead-owned).

No business rules here: values come from the engine; the view module only
arranges them. The API keeps a registry run_id -> DecisionResult of every
result it returned, because the protocol has no "get run".
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from rmprep import edits
from rmprep.api.ingest_job import IngestControl
from rmprep.api.names import short_name
from rmprep.api import schemas
from rmprep.contracts import (
    BLOCKING_CHECK_KINDS,
    NARRATIVE_LANGS,
    TR_TZ,
    AgentDecision,
    Backend,
    DecisionResult,
    DecisionState,
    NarrativeDraft,
    NarrativeStatus,
    Persona,
    RmStatus,
    _to_json,
)
from rmprep.ingest.pipeline import IngestBusy
from rmprep.narrator.template import to_markdown
from rmprep.ui import card, glossary

GLOSSARY = Path(__file__).resolve().parents[3] / "config" / "glossary.yaml"

# views(result) -> extra RunView keys (docs/web-ui.md section 6); None = the core keys only
ViewFn = Callable[[DecisionResult], dict]


NOT_STARTED = "henüz çalıştırılmadı"    # v1.12: GET /agent before the RM started it


def create_app(backend: Backend, *, views: ViewFn | None = None,
               narrative_timeout_s: float = 120.0,
               glossary_path: Path | str = GLOSSARY,
               static_dir: Path | None = None,
               ingest: IngestControl | None = None,
               research=None, agent=None, action_log=None) -> FastAPI:
    """static_dir: the built web app (web/dist); its index.html answers every
    non-API path, so the client-side routes (/meeting/..., /print/...) work.
    ingest: the data age and refresh (W14); None = /api/ingest answers 404.
    research: a rmprep.research.service.ResearchService (docs/research.md); None = no research routes.
    agent: a rmprep.agent.service.AgentService (docs/agent.md); None = the agent route answers "off".
    action_log: a rmprep.api.action_log.ActionLog (L1); None = no RM action log."""
    app = FastAPI(title="rmprep", docs_url="/api/docs", openapi_url="/api/openapi.json")
    runs: dict[str, DecisionResult] = {}
    texts: dict[tuple[str, str], NarrativeDraft] = {}   # (run_id, lang) -> last draft / approved text
    terms = glossary.load(glossary_path)
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="narrative")

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def _changes(persona: Persona) -> list[dict]:
        orig = next((p for p in backend.list_personas() if p.persona_id == persona.persona_id), None)
        if orig is None:
            return []
        a, b = orig.to_dict(), persona.to_dict()
        return [{"field": k, "original": a[k], "edited": b[k]} for k in a if a[k] != b[k]]

    def _view(result: DecisionResult) -> dict:
        runs[result.run_id] = result
        if research is not None and result.state == DecisionState.READY:
            research.start(result, "TR")      # web research of the top 3 (docs/research.md)
        changes = _changes(result.persona)
        out = {"result": result.to_dict(), "test_run": bool(changes), "persona_changes": changes}
        if views is not None:
            out.update(views(result))
        return out

    def _log(action: str, **kw) -> None:
        """L1: one RM action record; nothing without an action log."""
        if action_log is not None:
            action_log.append(action, **kw)

    def _block_text(d: NarrativeDraft, block_id: str) -> str:
        """L1: the text of a block as the RM sees it (the edit, "" when deleted, else
        the sentences of the draft)."""
        if block_id in d.rm_edits:
            return d.rm_edits[block_id]
        return edits.block_text(d, block_id)

    def _run(run_id: str) -> DecisionResult:
        if run_id not in runs:
            raise HTTPException(404, f"unknown run {run_id} (the server may have restarted)")
        return runs[run_id]

    @app.get("/api/personas")
    def personas():
        return [p.to_dict() for p in backend.list_personas()]

    @app.get("/api/snapshots")
    def snapshots():
        return backend.list_snapshots()

    def _ingest() -> IngestControl:
        if ingest is None:
            raise HTTPException(404, "no data refresh in this server")
        return ingest

    @app.get("/api/ingest")
    def ingest_state():
        return _ingest().status()

    @app.post("/api/ingest", status_code=202)
    def ingest_start():
        try:
            return _ingest().start()
        except IngestBusy as e:
            raise HTTPException(409, str(e)) from e

    @app.get("/api/snapshots/{snapshot_id}/sources")
    def sources(snapshot_id: str):
        if snapshot_id not in backend.list_snapshots():
            raise HTTPException(404, f"unknown snapshot {snapshot_id}")
        return _to_json(backend.evidence(snapshot_id).to_dict()["source_status"])

    @app.post("/api/runs")
    def new_run(req: schemas.RunRequest):
        persona = Persona.from_dict(req.persona)
        snap = req.snapshot_id or backend.list_snapshots()[0]
        result = backend.decide(persona, snap, frozenset(req.exclude_sources))
        view = _view(result)
        _log("run_opened", run=result, details={
            "test_run": view["test_run"], "persona_changes": view["persona_changes"],
            "excluded_sources": sorted(result.excluded_sources), "state": result.state.value})
        return view

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return _view(_run(run_id))

    @app.post("/api/runs/{run_id}/answers")
    def answer(run_id: str, req: schemas.AnswerRequest):
        _run(run_id)
        new = backend.answer_question(run_id, req.question_id, req.answer)
        view = _view(new)
        _log("question_answered", run=new, run_id=run_id, new_run_id=new.run_id,
             details={"question_id": req.question_id, "answer": req.answer})
        return view

    @app.post("/api/runs/{run_id}/holdings")
    def holdings(run_id: str, req: schemas.HoldingsRequest):
        """v1.10 (W18): a new run with the RM's split; a bad split -> 422 (ValueError)."""
        before = _run(run_id)
        new = backend.set_holdings(run_id, req.shares, req.origin)
        view = _view(new)
        if req.shares is None:
            _log("holdings_reset", run=new, run_id=run_id, new_run_id=new.run_id)
        else:
            _log("holdings_set", run=new, run_id=run_id, new_run_id=new.run_id,
                 details={"shares": dict(new.holdings_input.shares), "origin": req.origin,
                          "estimate": {b.asset_class: {"current": b.current, "source": b.current_source,
                                                       "ref": b.current_ref}
                                       for b in before.allocation if b.current is not None}})   # L1b
        return view

    @app.post("/api/runs/{run_id}/approval")
    def approval(run_id: str, req: schemas.ApprovalRequest):
        if _changes(_run(run_id).persona):      # every backend, not only RealBackend
            raise ValueError("a test run (edited persona) cannot be approved or rejected")
        before = _run(run_id)
        decided = backend.approve(run_id, RmStatus(req.status), req.note, tuple(req.selected))
        view = _view(decided)
        for lang in NARRATIVE_LANGS:              # the texts of an earlier decision no longer apply
            texts.pop((run_id, lang), None)
        d = agent.status(run_id) if _agent_on() else None
        _log("decision_approved" if decided.rm_status == RmStatus.APPROVED else "decision_rejected",
             run=decided, details={
                 "engine_top3": list(before.recommended),
                 "agent_top3": [p.option_id for p in d.picks] if d is not None else [],
                 "agent_state": d.state if d is not None else "none",
                 "selected": list(req.selected), "note": req.note})
        return view

    @app.put("/api/runs/{run_id}/notes")
    def notes(run_id: str, req: schemas.NotesRequest):
        _run(run_id)
        view = _view(backend.annotate(run_id, req.note, req.option_notes))
        _save_card(run_id, "TR")
        _log("notes_saved", run=_run(run_id), details={"note": req.note,
                                                       "option_notes": dict(req.option_notes)})
        return view

    # --- meeting text, card, evidence, glossary ----------------------------------

    def _lang(lang: str) -> str:
        if lang not in NARRATIVE_LANGS:
            raise HTTPException(422, f"lang must be one of {NARRATIVE_LANGS}")
        return lang

    def _names(run_id: str) -> dict[str, str]:
        """{option_id: screen name} for the headings of the meeting text (N13)."""
        r = runs.get(run_id)
        if r is None:
            return {}
        out = {}
        for o in r.options:
            issuer, short = short_name(o.option.label)
            out[o.option.option_id] = f"{issuer} {short}".strip()
        return out

    def _text_view(d: NarrativeDraft) -> dict:
        texts[(d.run_id, d.lang)] = d
        names = _names(d.run_id)
        md = (d.rm_text if d.status == NarrativeStatus.APPROVED
              else to_markdown(edits.apply_edits(d), names=names))
        # draft_markdown: the unedited draft, so the web can tell an edited text apart
        plain = to_markdown(dataclasses.replace(d, rm_edits={}), names=names)
        return {**d.to_dict(), "markdown": md, "draft_markdown": plain}

    def _approved_text(run_id: str, lang: str) -> NarrativeDraft | None:
        d = texts.get((run_id, lang))
        return d if d is not None and d.status == NarrativeStatus.APPROVED else None

    def _current_text(run_id: str, lang: str, strict: bool) -> str | None:
        """W19 (2026-10-15): the meeting text as it is now, with the RM's edits, for the
        card (no "Metni onayla" any more). With an open rule finding (BLOCKING_CHECK_KINDS)
        the text stays out: strict -> 422 for a card download, else the card has no text."""
        d = texts.get((run_id, lang))
        if d is None or d.status == NarrativeStatus.APPROVED:
            return None                      # no text yet, or an older approved text
        blocking = [f for found in d.edit_checks.values() for f in found
                    if f.split(":", 1)[0].strip() in BLOCKING_CHECK_KINDS]
        if blocking:
            if strict:
                raise ValueError("Kural bulgusu açık: kartı indirmeden önce düzeltin.")
            return None
        return to_markdown(edits.apply_edits(d), names=_names(run_id))

    def _save_card(run_id: str, lang: str, strict: bool = False) -> str:
        result = _run(run_id)
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run has a card")
        ev = backend.evidence(result.snapshot_id, result.excluded_sources)
        md = card.render_markdown(result, ev, lang, narrative=_approved_text(run_id, lang),
                                  glossary_terms=terms,
                                  current_text=_current_text(run_id, lang, strict),
                                  agent=agent.status(run_id) if _agent_on() else None)
        backend.save_card(run_id, md)
        return md

    @app.get("/api/runs/{run_id}/narrative")
    def narrative(run_id: str, lang: str = "TR"):
        lang = _lang(lang)
        if _run(run_id).rm_status != RmStatus.APPROVED:
            raise ValueError("a meeting text needs an approved run")
        job = pool.submit(backend.draft_narrative, run_id, lang)
        try:
            d = job.result(timeout=narrative_timeout_s)
        except FutureTimeout:
            raise HTTPException(504, "the meeting text is not ready yet; try again") from None
        return _text_view(d)

    @app.post("/api/runs/{run_id}/narrative/{lang}/approval")
    def approve_text(run_id: str, lang: str, req: schemas.TextRequest):
        _run(run_id)
        return _text_view(backend.approve_narrative(run_id, _lang(lang), req.text))

    @app.put("/api/runs/{run_id}/narrative/{lang}/blocks/{block_id}")
    def edit_block(run_id: str, lang: str, block_id: str, req: schemas.BlockRequest):
        result = _run(run_id)
        lang = _lang(lang)
        old = texts.get((run_id, lang))
        before = _block_text(old, block_id) if old is not None else ""
        d = backend.edit_narrative(run_id, lang, block_id, req.text)
        view = _text_view(d)
        after = _block_text(d, block_id)
        action = ("text_block_restored" if req.text is None else
                  "text_block_deleted" if not req.text.strip() else "text_block_edited")
        _log(action, run=result, lang=lang, details={
            "block_id": block_id, "before": before, "after": after,
            "findings": list(d.edit_checks.get(block_id, ()))})
        return view

    @app.get("/api/runs/{run_id}/brief")
    def brief(run_id: str, lang: str = "TR"):
        result = _run(run_id)
        b = backend.brief(run_id, _lang(lang), **_brief_top3(result))
        if b is None:
            return JSONResponse(status_code=202, content={"status": "running"})
        return b.to_dict()

    # --- agentic top 3 (v1.11, docs/agent.md) -------------------------------------

    def _agent_on() -> bool:
        return agent is not None and getattr(agent, "enabled", True)

    def _start_agent(result: DecisionResult, n: int | None = None) -> None:
        agent.start(result, backend.evidence(result.snapshot_id, result.excluded_sources), "TR", n=n)

    def _agent_off(result: DecisionResult, reason: str) -> dict:
        return AgentDecision(result.run_id, "off", (), (), "", tuple(result.recommended), (), "", "",
                             0.0, datetime.now(TR_TZ), fallback_reason=reason).to_dict()

    def _research_shown(result: DecisionResult) -> list[str]:
        """v1.12: the products of the research panel: the engine's top 3, and after an agent
        run the run's N candidates (the engine's top 3 first, as the agent saw them)."""
        top = list(result.recommended)
        d = agent.status(result.run_id) if _agent_on() else None
        if d is None or d.state not in ("done", "fallback") or not d.n_candidates:
            return top
        from rmprep.agent.pack import candidates
        return [s.option.option_id for s in candidates(result, d.n_candidates)]

    def _brief_top3(result: DecisionResult) -> dict:
        """W20c: {"top3": the agent's picks} when the agent is done and changed the top 3
        (and the backend can write a brief for them), else {} (the engine's brief)."""
        if not _agent_on() or "top3" not in inspect.signature(backend.brief).parameters:
            return {}
        d = agent.status(result.run_id)
        if d is None or d.state != "done":
            return {}
        picks = tuple(p.option_id for p in d.picks)
        return {"top3": picks} if set(picks) != set(result.recommended) else {}

    @app.get("/api/runs/{run_id}/agent")
    def agent_decision(run_id: str):
        """202 with the nodes while the agent runs; 200 when it is done, fell back or is off."""
        result = _run(run_id)
        if agent is None:
            return _agent_off(result, "the agent is not configured (config/agent.yaml)")
        if not _agent_on():
            return _agent_off(result, getattr(agent, "off_reason", "") or "the agent is off")
        if result.state != DecisionState.READY:
            return _agent_off(result, "the run is not ready: an RM question is open")
        d = agent.status(run_id)
        if d is None:                      # v1.12: the agent runs only on the RM's request
            return _agent_off(result, NOT_STARTED)
        if d.state == "running":
            return JSONResponse(status_code=202, content=d.to_dict())
        return d.to_dict()

    @app.post("/api/runs/{run_id}/agent")
    def agent_start(run_id: str, req: schemas.AgentStartRequest):
        """v1.12: the RM starts the agent with N candidates (default in config/agent.yaml)."""
        result = _run(run_id)
        if not _agent_on():
            raise ValueError("the agent is off: " + (getattr(agent, "off_reason", "") if agent else
                                                     "not configured"))
        if result.state != DecisionState.READY:
            raise ValueError("the run is not ready: an RM question is open")
        if hasattr(agent, "check_n"):
            agent.check_n(req.n)           # ValueError for n out of range -> 422, before any work
        _start_agent(result, req.n)
        marks = dict(research.marks()) if research is not None and hasattr(research, "marks") else {}
        _log("agent_started", run=result, details={
            "n": req.n if req.n is not None else getattr(getattr(agent, "config", None), "candidates", None),
            "marks_ok": sum(1 for m in marks.values() if m == "ok"),
            "marks_wrong": sum(1 for m in marks.values() if m == "wrong")})
        d = agent.status(run_id)
        body = d.to_dict() if d is not None else _agent_off(result, "starting") | {"state": "running"}
        return JSONResponse(status_code=202, content=body)

    @app.get("/api/runs/{run_id}/card.md")
    def card_md(run_id: str, lang: str = "TR"):
        lang = _lang(lang)
        try:
            md = _save_card(run_id, lang, strict=True)
        except ValueError:
            _log("card_downloaded", run=runs.get(run_id), run_id=run_id, lang=lang,
                 details={"format": "md", "has_text": False, "refused": True})
            raise
        _log("card_downloaded", run=_run(run_id), lang=lang, details={
            "format": "md", "has_text": f"## {card.t('nar_title', lang)}" in md, "refused": False})
        return Response(md, media_type="text/markdown; charset=utf-8")

    @app.get("/api/evidence/{snapshot_id}/{evidence_id}")
    def evidence_item(snapshot_id: str, evidence_id: str):
        if snapshot_id not in backend.list_snapshots():
            raise HTTPException(404, f"unknown snapshot {snapshot_id}")
        ev = backend.evidence(snapshot_id)
        dp = next((d for d in ev.datapoints if d.id == evidence_id), None)
        if dp is None:
            raise HTTPException(404, f"unknown evidence id {evidence_id}")
        info = ev.entities.get(dp.entity)
        return {**_to_json(dp), "entity_name": info.name if info else ""}

    @app.get("/api/glossary")
    def glossary_terms(lang: str = "TR", run_id: str | None = None):
        lang = _lang(lang)
        d = texts.get((run_id, lang)) if run_id else None
        if d is None:
            return []
        text = d.rm_text if d.status == NarrativeStatus.APPROVED else to_markdown(d)
        return [{"term": f.term.key, "form": f.form, "explanation": f.explanation}
                for f in glossary.find_terms(text, terms, lang)]

    if research is not None:      # before the web app's catch-all route
        from rmprep.api.research import research_router
        app.include_router(research_router(research, _run, log=_log, shown=_research_shown))

    if static_dir is not None:
        static = Path(static_dir)
        if (static / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def web_app(path: str):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, f"unknown API path /{path}")
            f = static / path
            if path and f.is_file() and static in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(static / "index.html")

    app.state.runs = runs
    return app
