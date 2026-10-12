"""JSON API over the Backend protocol (docs/web-ui.md sections 1, 6, 8; lead-owned).

No business rules here: values come from the engine; the view module only
arranges them. The API keeps a registry run_id -> DecisionResult of every
result it returned, because the protocol has no "get run".
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from rmprep import edits
from rmprep.api.names import short_name
from rmprep.api import schemas
from rmprep.contracts import (
    NARRATIVE_LANGS,
    Backend,
    DecisionResult,
    NarrativeDraft,
    NarrativeStatus,
    Persona,
    RmStatus,
    _to_json,
)
from rmprep.narrator.template import to_markdown
from rmprep.ui import card, glossary

GLOSSARY = Path(__file__).resolve().parents[3] / "config" / "glossary.yaml"

# views(result) -> extra RunView keys (docs/web-ui.md section 6); None = the core keys only
ViewFn = Callable[[DecisionResult], dict]


def create_app(backend: Backend, *, views: ViewFn | None = None,
               narrative_timeout_s: float = 120.0,
               glossary_path: Path | str = GLOSSARY,
               static_dir: Path | None = None) -> FastAPI:
    """static_dir: the built web app (web/dist); its index.html answers every
    non-API path, so the client-side routes (/meeting/..., /print/...) work."""
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
        changes = _changes(result.persona)
        out = {"result": result.to_dict(), "test_run": bool(changes), "persona_changes": changes}
        if views is not None:
            out.update(views(result))
        return out

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

    @app.get("/api/snapshots/{snapshot_id}/sources")
    def sources(snapshot_id: str):
        if snapshot_id not in backend.list_snapshots():
            raise HTTPException(404, f"unknown snapshot {snapshot_id}")
        return _to_json(backend.evidence(snapshot_id).to_dict()["source_status"])

    @app.post("/api/runs")
    def new_run(req: schemas.RunRequest):
        persona = Persona.from_dict(req.persona)
        snap = req.snapshot_id or backend.list_snapshots()[0]
        return _view(backend.decide(persona, snap, frozenset(req.exclude_sources)))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return _view(_run(run_id))

    @app.post("/api/runs/{run_id}/answers")
    def answer(run_id: str, req: schemas.AnswerRequest):
        _run(run_id)
        return _view(backend.answer_question(run_id, req.question_id, req.answer))

    @app.post("/api/runs/{run_id}/approval")
    def approval(run_id: str, req: schemas.ApprovalRequest):
        if _changes(_run(run_id).persona):      # every backend, not only RealBackend
            raise ValueError("a test run (edited persona) cannot be approved or rejected")
        view = _view(backend.approve(run_id, RmStatus(req.status), req.note, tuple(req.selected)))
        for lang in NARRATIVE_LANGS:              # the texts of an earlier decision no longer apply
            texts.pop((run_id, lang), None)
        return view

    @app.put("/api/runs/{run_id}/notes")
    def notes(run_id: str, req: schemas.NotesRequest):
        _run(run_id)
        view = _view(backend.annotate(run_id, req.note, req.option_notes))
        _save_card(run_id, "TR")
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

    def _save_card(run_id: str, lang: str) -> str:
        result = _run(run_id)
        if result.rm_status != RmStatus.APPROVED:
            raise ValueError("only an approved run has a card")
        ev = backend.evidence(result.snapshot_id, result.excluded_sources)
        md = card.render_markdown(result, ev, lang, narrative=_approved_text(run_id, lang),
                                  glossary_terms=terms)
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
        _run(run_id)
        return _text_view(backend.edit_narrative(run_id, _lang(lang), block_id, req.text))

    @app.get("/api/runs/{run_id}/brief")
    def brief(run_id: str, lang: str = "TR"):
        _run(run_id)
        b = backend.brief(run_id, _lang(lang))
        if b is None:
            return JSONResponse(status_code=202, content={"status": "running"})
        return b.to_dict()

    @app.get("/api/runs/{run_id}/card.md")
    def card_md(run_id: str, lang: str = "TR"):
        md = _save_card(run_id, _lang(lang))
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
