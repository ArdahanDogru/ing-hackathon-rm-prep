"""Decision layer: one EvidenceSet + one Persona -> one DecisionResult
(docs/decision.md)."""

from rmprep.decision.config import DecisionConfig, load_config
from rmprep.decision.engine import decide
from rmprep.decision.report import render

__all__ = ["DecisionConfig", "decide", "load_config", "render"]
