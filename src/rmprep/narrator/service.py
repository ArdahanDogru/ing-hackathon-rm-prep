"""Narrator.draft: the meeting text of an approved run in one language
(docs/narrator.md): facts -> LLM -> validator -> one retry with the findings ->
template text with a banner. Cached per (run_id, lang, prompt_version, model);
every LLM call is priced and appended to the cost ledger; over the daily limit
no call is made."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rmprep.brief import template_brief
from rmprep.contracts import (
    NARRATIVE_LANGS,
    TR_TZ,
    BRIEF_MAX_CHARS,
    DecisionState,
    NarrativeBrief,
    DecisionResult,
    EvidenceSet,
    NarrativeDraft,
)
from rmprep.narrator.brief import (
    brief_request,
    build_brief_facts,
    fit_sentences,
    parse_brief,
    validate_brief,
)
from rmprep.narrator.config import NarratorConfig, load_config
from rmprep.narrator.facts import Facts, build_facts
from rmprep.narrator.llm import LlmClient, LlmError, LlmReply, client_from_env
from rmprep.narrator.market import with_market_note
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
        path = self._path(r.run_id, lang, f)
        if path.exists():
            return NarrativeDraft.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if self.client is None:
            return self._template(f, ev, lang,
                                  (f"llm: no API key ({self.config.api_key_env})",), 0.0)

        cost, previous, findings = 0.0, None, ()
        for attempt in range(1, ATTEMPTS + 1):
            spent, limit = self.spent_today(), self.config.max_cost_usd_per_day
            if spent >= limit:
                budget = f"budget: daily limit ${limit:.2f} reached (${spent:.2f} spent today)"
                return self._template(f, ev, lang, (*findings, budget), cost)
            request = build_request(f, lang, self.config, previous=previous, findings=findings)
            try:
                reply = self.client.complete(request)
            except LlmError as e:
                return self._template(f, ev, lang, (*findings, f"llm: {e.kind}: {e.message}"),
                                      cost)
            sections, tags, findings = self._check(reply, f, r, lang)
            cost += self._ledger_add(run_id=r.run_id, lang=lang, reply=reply,
                                     attempt=attempt, findings=findings)
            if not findings:
                draft = NarrativeDraft(
                    run_id=r.run_id, lang=lang, sections=sections, source="llm",
                    model=reply.model, prompt_version=self.config.prompt_version, checks=(),
                    created_at=self.clock(), cost_usd=cost,
                    need_tags=persona_wording(tags, r.persona))
                return self._save(path, with_market_note(draft, ev, self.config))
            previous = reply.text or ""
        return self._save(path, self._template(f, ev, lang, findings, cost))

    def brief(self, r: DecisionResult, ev: EvidenceSet, lang: str) -> NarrativeBrief:
        """The dashboard brief of a ready run (contract v1.4, docs/web-ui.md "LLM
        brief"): one LLM call, no retry; any failure gives the plain sentence.
        Cached per (run_id, lang, brief prompt version, model): LLM briefs and
        validator failures, not API errors or budget stops. Never raises for a
        ready run."""
        if lang not in NARRATIVE_LANGS:
            raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
        if r.state != DecisionState.READY:
            raise ValueError("a brief needs a ready run")
        cfg = self.config.brief
        if cfg is None:
            return self._plain(r, lang, ("brief: no brief section in the config",))
        path = self.cache_dir / f"{r.run_id}-{lang}-brief-{cfg.prompt_version}-{cfg.model}.json"
        if path.exists():
            return NarrativeBrief.from_dict(json.loads(path.read_text(encoding="utf-8")))
        try:
            return self._brief(r, ev, lang, path)
        except Exception as e:                  # the dashboard never fails: the plain sentence
            return self._plain(r, lang, (f"brief: {type(e).__name__}: {e}",))

    def _brief(self, r: DecisionResult, ev: EvidenceSet, lang: str, path: Path) -> NarrativeBrief:
        cfg = self.config.brief
        try:
            bf = build_brief_facts(r, ev)
        except ValueError as e:
            return self._plain(r, lang, (f"brief: {e}",))
        if self.client is None:
            return self._plain(r, lang, (f"llm: no API key ({self.config.api_key_env})",))
        spent, limit = self.spent_today(), self.config.max_cost_usd_per_day
        if spent >= limit:
            return self._plain(r, lang, (f"budget: daily limit ${limit:.2f} reached "
                                         f"(${spent:.2f} spent today)",))
        try:
            reply = self.client.complete(brief_request(bf, lang, self.config))
        except LlmError as e:
            return self._plain(r, lang, (f"llm: {e.kind}: {e.message}",))
        if reply.stop_reason == "refusal":
            findings = (f"llm: refusal ({reply.refusal_category or 'no category'})",)
        elif reply.stop_reason == "max_tokens":
            findings = ("llm: the text was cut off (max_tokens)",)
        elif not reply.text:
            findings = ("llm: the reply has no text",)
        else:
            try:
                text, cite = parse_brief(reply.text)
                text = fit_sentences(text, min(cfg.max_chars, BRIEF_MAX_CHARS))
                findings = validate_brief(text, cite, bf, r, self.config, lang)
            except ValueError as e:
                findings = (f"format: {e}",)
        cost = self._ledger_add(run_id=r.run_id, lang=lang, reply=reply, kind="brief",
                                prices=(cfg.price_input_per_mtok, cfg.price_output_per_mtok),
                                attempt=1, findings=findings)
        if findings:
            return self._save_brief(path, self._plain(r, lang, findings, cost))
        return self._save_brief(path, NarrativeBrief(
            run_id=r.run_id, lang=lang, text=text, source="llm", model=reply.model,
            prompt_version=cfg.prompt_version, checks=(), created_at=self.clock(),
            cost_usd=cost, cite=cite))

    def _plain(self, r: DecisionResult, lang: str, checks, cost: float = 0.0) -> NarrativeBrief:
        b = template_brief(r, lang, self.clock(), tuple(checks))
        return dataclasses.replace(b, cost_usd=cost)

    def _save_brief(self, path: Path, b: NarrativeBrief) -> NarrativeBrief:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(b.to_dict(), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        return b

    def spent_today(self) -> float:
        today = self.clock().astimezone(TR_TZ).date().isoformat()
        ledger = self.cache_dir / LEDGER
        if not ledger.exists():
            return 0.0
        rows = (json.loads(x) for x in ledger.read_text(encoding="utf-8").splitlines() if x)
        return sum(row["cost_usd"] for row in rows if row["date"] == today)

    # --- helpers ----------------------------------------------------------------

    def _path(self, run_id: str, lang: str, f: Facts) -> Path:
        """N12: the facts hash is in the key, so another selection or note of the
        same run id gets its own text (the old key served the old text)."""
        c = self.config
        return self.cache_dir / f"{run_id}-{lang}-{c.prompt_version}-{c.model}-{facts_hash(f)}.json"

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

    def _cost(self, reply: LlmReply, prices: tuple[float, float] | None = None) -> float:
        """USD of one call; prices = (input, output) per 1M tokens, default the llm prices."""
        c = self.config
        p_in, p_out = prices or (c.price_input_per_mtok, c.price_output_per_mtok)
        tokens_in = (reply.input_tokens + CACHE_WRITE_FACTOR * reply.cache_write_tokens
                     + CACHE_READ_FACTOR * reply.cache_read_tokens)
        return (tokens_in * p_in + reply.output_tokens * p_out) / 1e6

    def _ledger_add(self, *, run_id: str, lang: str, reply: LlmReply,
                    prices: tuple[float, float] | None = None, kind: str = "text",
                    attempt: int = 1, findings=()) -> float:
        """Append one call to the ledger; N13d: with its attempt number and the
        validator findings of its text ([] = passed), so a retry shows why."""
        now = self.clock().astimezone(TR_TZ)
        cost = self._cost(reply, prices)
        row = {"date": now.date().isoformat(), "at": now.isoformat(), "run_id": run_id,
               "kind": kind, "lang": lang, "model": reply.model,
               "input_tokens": reply.input_tokens,
               "output_tokens": reply.output_tokens,
               "cache_write_tokens": reply.cache_write_tokens,
               "cache_read_tokens": reply.cache_read_tokens, "cost_usd": cost,
               "attempt": attempt, "findings": list(findings)}
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cache_dir / LEDGER, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row) + "\n")
        return cost

    def _template(self, f: Facts, ev: EvidenceSet, lang: str, checks,
                  cost: float) -> NarrativeDraft:
        d = template_draft(f, lang, self.config, created_at=self.clock(), checks=tuple(checks))
        return with_market_note(dataclasses.replace(d, cost_usd=cost), ev, self.config)

    def _save(self, path: Path, d: NarrativeDraft) -> NarrativeDraft:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d.to_dict(), ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")
        return d


def findings_by_kind(ledger: Path | str, attempt: int = 1, kind: str = "text") -> dict[str, int]:
    """N13d: over the cost ledger, the attempts of one number (1 = first) of one
    kind ("text" | "brief"): how many there were, how many failed, and per
    finding kind ("phrase", "number", ...) how many attempts had it. Rows from
    before N13d (no attempt field) are left out."""
    out = {"attempts": 0, "failed": 0}
    path = Path(ledger)
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line) if line.strip() else {}
        if row.get("attempt") != attempt or row.get("kind", "text") != kind:
            continue
        out["attempts"] += 1
        found = row.get("findings") or []
        if found:
            out["failed"] += 1
        for k in dict.fromkeys(x.split(":", 1)[0].strip() for x in found):
            out[k] = out.get(k, 0) + 1
    return out


def facts_hash(f: Facts) -> str:
    """First 10 hex digits of the sha256 of the facts (sorted JSON): the
    selection, the notes and every fact the text rests on."""
    data = json.dumps(f.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:10]


def narrator_from_root(root: Path | str) -> Narrator:
    """The narrator of a prototype root: config/narrator.yaml, the API key from
    the environment or root/.env (environment wins), cache under root."""
    from dotenv import dotenv_values

    root = Path(root)
    config = load_config(root / "config" / "narrator.yaml")
    env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
    env.update(os.environ)
    return Narrator(config, client_from_env(config, env), root / config.cache_dir)
