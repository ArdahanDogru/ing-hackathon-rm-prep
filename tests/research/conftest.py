"""Shared helpers of the research tests: a fake provider and a ready result (no network)."""

import dataclasses
import json
import threading
from datetime import datetime
from pathlib import Path

from rmprep.contracts import TR_TZ, DecisionResult
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, ResearchError, Source

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=TR_TZ)
FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
RECOMMENDED = ("fund:BBF", "fund:AAL", "fund:AKE")


def ready_result(recommended=RECOMMENDED) -> DecisionResult:
    r = DecisionResult.from_dict(json.loads((FIX / "decision_p02_ready.json").read_text(encoding="utf-8")))
    return dataclasses.replace(r, recommended=recommended)


class FakeProvider:
    """fail: a ResearchError kind to raise, or an Exception instance; gate: an Event the call waits for."""

    def __init__(self, name="exa", fail=None, cost=0.01, gate: threading.Event | None = None,
                 fail_cost=0.0):
        self.name, self.fail, self.cost, self.gate = name, fail, cost, gate
        self.fail_cost = fail_cost       # the cost of a failed call (a paid call with a bad reply)
        self.calls: list[tuple] = []

    def _maybe_fail(self):
        if self.gate is not None:
            self.gate.wait(5)
        if isinstance(self.fail, Exception):
            raise self.fail
        if self.fail:
            raise ResearchError(self.fail, "fake", self.fail_cost)

    def research_product(self, option, lang):
        self.calls.append(("product", option.option_id, lang))
        self._maybe_fail()
        src = Source(f"https://{self.name}.example/{option.option_id}", "x")
        return ProductResearch(option.option_id, option.label, "Şirket A.Ş.", "Özet.",
                               (Finding("Bulgu.", "urun", (src,), "high"),), lang, self.name, NOW, self.cost)

    def answer_question(self, question, products, lang):
        self.calls.append(("question", question, lang, tuple(p.option_id for p in products)))
        self._maybe_fail()
        src = Source(f"https://{self.name}.example/q", "x")
        return QuestionAnswer(question, "Yanıt.", (Finding("Bulgu.", "soru", (src,)),), lang,
                              self.name, NOW, self.cost)
