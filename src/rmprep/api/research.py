"""Web research endpoints (docs/research.md section 10). The research is
information for the RM; nothing here changes a run."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from rmprep.contracts import NARRATIVE_LANGS, DecisionResult
from rmprep.research.service import QuestionRefused, ResearchService


class QuestionRequest(BaseModel):
    question: str
    lang: str = "TR"


class MarkRequest(BaseModel):
    finding_id: str
    option_id: str
    mark: str | None                # "ok" | "wrong" | null (removes); required: a missing key is 422
    run_id: str


def research_router(service: ResearchService, get_run: Callable[[str], DecisionResult],
                    log: Callable[..., None] | None = None,
                    shown: Callable[[DecisionResult], list[str]] | None = None) -> APIRouter:
    """get_run: the app's run registry (404 for an unknown run). log: the RM action log
    (L1): every research question, also a refused one, and every RM mark. shown (v1.12):
    the product ids the panel shows for a run (the engine's top 3, after an agent run
    its N candidates); None = all products of the status."""
    router = APIRouter()

    def _lang(lang: str) -> str:
        if lang not in NARRATIVE_LANGS:
            raise HTTPException(422, f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
        return lang

    @router.get("/api/runs/{run_id}/research")
    def research(run_id: str, lang: str = "TR"):
        result = get_run(run_id)
        status = service.status(result, _lang(lang))
        if status["state"] == "running":
            return JSONResponse(status_code=202, content=status)
        if shown is not None and "products" in status:
            keep = shown(result)
            by_id = {p["option_id"]: p for p in status["products"]}
            status = {**status, "products": [by_id[i] for i in keep if i in by_id]}
        return status

    @router.post("/api/runs/{run_id}/research/questions")
    def ask(run_id: str, req: QuestionRequest):
        result = get_run(run_id)
        lang = _lang(req.lang)
        try:
            answer = service.ask(result, req.question, lang)
        except QuestionRefused as e:
            if log is not None:
                log("research_question", run=result, lang=lang,
                    details={"question": req.question, "refused": True, "findings": 0})
            raise HTTPException(422, str(e)) from e
        if log is not None:
            log("research_question", run=result, lang=lang,
                details={"question": req.question, "refused": False,
                         "findings": len(getattr(answer, "findings", ()) or ())})
        return answer.to_dict()

    @router.post("/api/research/marks")
    def set_mark(req: MarkRequest):
        try:
            service.set_mark(req.finding_id, req.mark, req.run_id, req.option_id)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if log is not None:
            try:
                run = get_run(req.run_id)
            except HTTPException:       # an unknown run still logs, with its run_id
                run = None
            log("research_marked", run=run, run_id=req.run_id,
                details={"finding_id": req.finding_id, "option_id": req.option_id, "mark": req.mark})
        return {"finding_id": req.finding_id, "mark": req.mark}

    return router
