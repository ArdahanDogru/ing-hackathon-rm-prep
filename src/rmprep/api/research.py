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


def research_router(service: ResearchService, get_run: Callable[[str], DecisionResult],
                    log: Callable[..., None] | None = None) -> APIRouter:
    """get_run: the app's run registry (404 for an unknown run). log: the RM action log
    (L1): every research question, also a refused one."""
    router = APIRouter()

    def _lang(lang: str) -> str:
        if lang not in NARRATIVE_LANGS:
            raise HTTPException(422, f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
        return lang

    @router.get("/api/runs/{run_id}/research")
    def research(run_id: str, lang: str = "TR"):
        status = service.status(get_run(run_id), _lang(lang))
        if status["state"] == "running":
            return JSONResponse(status_code=202, content=status)
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

    return router
