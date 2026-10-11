"""Narrator.draft: the meeting text of an approved run in one language
(docs/narrator.md): facts -> LLM -> validator -> one retry with the findings ->
template text with a banner. Cached per (run_id, lang, prompt_version, model);
every LLM call is priced and appended to the cost ledger; over the daily limit
no call is made."""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rmprep.contracts import (
    NARRATIVE_LANGS,
    TR_TZ,
    DecisionResult,
    EvidenceSet,
    NarrativeDraft,
)
from rmprep.narrator.config import NarratorConfig, load_config
from rmprep.narrator.facts import Facts, build_facts
from rmprep.narrator.llm import LlmClient, LlmError, LlmReply, client_from_env
from rmprep.narrator.prompt import build_request, parse_need_tags, parse_sections
from rmprep.narrator.template import template_draft
from rmprep.narrator.validator import persona_wording, validate

ATTEMPTS = 2                    # the first text and one retry with the findings
CACHE_WRITE_FACTOR = 1.25       # 5-minute cache write, times the input price
CACHE_READ_FACTOR = 0.1
LEDGER = "costs.jsonl"


class Narrator:
    def __init__(self, config: NarratorConfig, client: LlmClient | None, cache_dir: Path | str,
                 *, clock: Callable[[], datetime] | None = None):
        self.config = config
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.clock = clock or (lambda: datetime.now(TR_TZ))

    # --- public -----------------------------------------------------------------

    def draft(self, r: DecisionResult, ev: EvidenceSet, lang: str) -> NarrativeDraft:
        f = build_facts(r, ev)              # raises for a result that is not approved
        if lang not in NARRATIVE_LANGS:
            raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
        path = self._path(r.run_id, lang)
        if path.exists():
            return NarrativeDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if self.client is None:
            return self._template(f, lang, (f"llm: no API key ({self.config.api_key_env})",), 0.0)

        cost, previous, findings = 0.0, None, ()
        for _ in range(ATTEMPTS):
            spent, limit = self.spent_today(), self.config.max_cost_usd_per_day
            if spent >= limit:
                budget = f"budget: daily limit ${limit:.2f} reached (${spent:.2f} spent today)"
                return self._template(f, lang, (*findings, budget), cost)
            request = build_request(f, lang, self.config, previous=previous, findings=findings)
            try:
                reply = self.client.complete(request)
            except LlmError as e:
                return self._template(f, lang, (*findings, f"llm: {e.kind}: {e.message}"), cost)
            cost += self._ledger_add(run_id=r.run_id, lang=lang, reply=reply)
            sections, tags, findings = self._check(reply, f, r, lang)
            if not findings:
                draft = NarrativeDraft(
                    run_id=r.run_id, lang=lang, sections=sections, source="llm",
                    model=reply.model, prompt_version=self.config.prompt_version, checks=(),
                    created_at=self.clock(), cost_usd=cost,
                    need_tags=persona_wording(tags, r.persona))
                return self._save(path, draft)
            previous = reply.text or ""
        return self._save(path, self._template(f, lang, findings, cost))

    def spent_today(self) -> float:
        today = self.clock().astimezone(TR_TZ).date().isoformat()
        ledger = self.cache_dir / LEDGER
        if not ledger.exists():
            return 0.0
        rows = (json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x)
        return sum(row["cost_usd"] for row in rows if row["date"] == today)

    # --- helpers ----------------------------------------------------------------

    def _path(self, run_id: str, lang: str) -> Path:
        return self.cache_dir / f"{run_id}-{lang}-{self.config.prompt_version}-{self.config.model}.json"

    def _check(self, reply: LlmReply, f: Facts, r: DecisionResult, lang: str):
        """(sections, need tags, findings) of a reply."""
        if reply.stop_reason == "refusal":
            return (), {}, (f"llm: refusal ({reply.refusal_category or 'no category'})",)
        if reply.stop_reason == "max_tokens":
            return (), {}, ("llm: the text was cut off (max_tokens)",)
        if not reply.text:
            return (), {}, ("llm: the reply has no text",)
        try:
            sections = parse_sections(reply.text)
            tags = parse_need_tags(reply.text)
        except ValueError as e:
            return (), {}, (f"format: {e}",)
        return sections, tags, validate(sections, f, r, self.config, lang, need_tags=tags)

    def _cost(self, reply: LlmReply) -> float:
        c = self.config
        tokens_in = (reply.input_tokens + CACHE_WRITE_FACTOR * reply.cache_write_tokens
                     + CACHE_READ_FACTOR * reply.cache_read_tokens)
        return (tokens_in * c.price_input_per_mtok + reply.output_tokens * c.price_output_per_mtok) / 1e6

    def _ledger_add(self, *, run_id: str, lang: str, reply: LlmReply) -> float:
        now = self.clock().astimezone(TR_TZ)
        cost = self._cost(reply)
        row = {"date": now.date().isoformat(), "at": now.isoformat(), "run_id": run_id,
               "lang": lang, "model": reply.model, "input_tokens": reply.input_tokens,
               "output_tokens": reply.output_tokens,
               "cache_write_tokens": reply.cache_write_tokens,
               "cache_read_tokens": reply.cache_read_tokens, "cost_usd": cost}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cache_dir / LEDGER, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row) + "\n")
        return cost

    def _template(self, f: Facts, lang: str, checks, cost: float) -> NarrativeDraft:
        d = template_draft(f, lang, self.config, created_at=self.clock(), checks=tuple(checks))
        return dataclasses.replace(d, cost_usd=cost)

    def _save(self, path: Path, d: NarrativeDraft) -> NarrativeDraft:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d.to_dict(), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        return d


def narrator_from_root(root: Path | str) -> Narrator:
    """The narrator of a prototype root: config/narrator.yaml, the API key from
    the environment or root/.env (environment wins), cache under root."""
    from dotenv import dotenv_values

    root = Path(root)
    config = load_config(root / "config" / "narrator.yaml")
    env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
    env.update(os.environ)
    return Narrator(config, client_from_env(config, env), root / config.cache_dir)
