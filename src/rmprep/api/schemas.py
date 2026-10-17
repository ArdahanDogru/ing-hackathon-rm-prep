"""Request bodies of the API (docs/web-ui.md section 6)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RunRequest(BaseModel):
    persona: dict
    snapshot_id: str | None = None
    exclude_sources: list[str] = []


class PersonaUploadRequest(BaseModel):     # W31
    persona: dict


class AnswerRequest(BaseModel):
    question_id: str
    answer: str


class HoldingsRequest(BaseModel):
    """v1.10: the RM's current split (class -> %); null removes it."""
    shares: dict[str, float] | None
    origin: str = "rm"


class AgentStartRequest(BaseModel):
    """v1.12: the RM starts the agent; n = number of candidates (None = config default)."""
    n: int | None = None


class ApprovalRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str = ""
    selected: list[str] = []


class NotesRequest(BaseModel):
    note: str
    option_notes: dict[str, str] = {}


class TextRequest(BaseModel):
    text: str


class BlockRequest(BaseModel):
    text: str | None          # None restores the original block (v1.5)
