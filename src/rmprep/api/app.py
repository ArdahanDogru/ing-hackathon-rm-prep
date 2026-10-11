"""JSON API over the Backend protocol (docs/web-ui.md sections 1, 6, 8; lead-owned).

No business rules here: values come from the engine; the view module only
arranges them. The API keeps a registry run_id -> DecisionResult of every
result it returned, because the protocol has no "get run".
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from rmprep.api import schemas
from rmprep.contracts import Backend, DecisionResult, Persona, RmStatus, _to_json

# views(result) -> extra RunView keys (docs/web-ui.md section 6); None = the core keys only
ViewFn = Callable[[DecisionResult], dict]


def create_app(backend: Backend, *, views: ViewFn | None = None) -> FastAPI:
    app = FastAPI(title="rmprep", docs_url="/api/docs", openapi_url="/api/openapi.json")
    runs: dict[str, DecisionResult] = {}

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
        return _view(backend.approve(run_id, RmStatus(req.status), req.note, tuple(req.selected)))

    @app.put("/api/runs/{run_id}/notes")
    def notes(run_id: str, req: schemas.NotesRequest):
        _run(run_id)
        return _view(backend.annotate(run_id, req.note, req.option_notes))

    app.state.runs = runs
    return app
