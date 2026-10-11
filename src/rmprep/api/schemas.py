"""Request bodies of the API (docs/web-ui.md section 6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RunRequest(BaseModel):
    persona: dict
    snapshot_id: str | None = None
    exclude_sources: list[str] = []


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


class ApprovalRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = ""
    selected: list[str] = []


class NotesRequest(BaseModel):
    note: str
    option_notes: dict[str, str] = {}


class TextRequest(BaseModel):
    text: str
