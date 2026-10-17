"""AI check of the client profile (W43 layer 3, approved by the user 2026-10-17;
docs/web-ui.md W43; lead-owned).

The fixed rules (profile_checks, layer 1) see only what the engine can read into
fixed values. This check gives Claude the whole profile and the engine's reading
of it, and asks for contradictions between fields (a free-text field such as
`durum` or `rm_notu` against a level field, a number in a text against `yas`, ...)
and for values the engine could not read. Every finding must quote the exact
words of each side; the server keeps a finding only when each quote appears word
for word (case and spacing aside) in the named field. One call per profile
content, cached; a daily cost limit; never raises (an error is a state).
Display only: the engine and the scores do not change.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from rmprep.contracts import PERSONA_REQUIRED, TR_TZ, Persona
from rmprep.decision.config import DecisionConfig
from rmprep.decision.persona import read_persona

log = logging.getLogger(__name__)
WORKSPACE_HEADER = "anthropic-workspace-id"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FIELDS = (*PERSONA_REQUIRED, "rm_notu")
MAX_FINDINGS = 5
MAX_QUOTE = 240

SYSTEM = """You check one client profile of a private-banking relationship manager \
(RM) tool for conflicting or unreadable information, before the RM meets the client.

You get the profile (Turkish field names and values) and the engine's reading of it \
(how the scoring understood each field: levels, the priorities and constraints it \
matched, the ones it did not match, and the fields it could not read and replaced \
with a safe level).

Report only real problems the RM should resolve with the client:
- conflict: two statements that cannot both hold, between fields or inside one \
field (for example a free-text field says the client needs cash soon while the \
liquidity need is "Düşük"; an age in a text differs from "yas"; the RM note asks \
for high returns while the risk profile is cautious);
- confirm: a value the engine could not read or did not use (a priority or \
constraint it did not match, a field read with a safe level), or a strong tension \
worth one question.

Rules:
- Quote the exact words of each side from the profile, copied character for \
character from the named field (a quote that is not in the field is discarded). \
Give 2 quotes for a conflict (they may come from the same field); 1 or 2 for confirm.
- Do not report what is consistent, do not judge products or returns, do not \
invent facts, do not repeat the same problem twice. At most 5 findings; none is a \
valid answer.
- explanation_tr in plain Turkish, explanation_en in plain English: one or two \
short sentences each, saying what conflicts and what to ask the client."""

SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["conflict", "confirm"]},
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"field": {"type": "string", "enum": list(FIELDS)},
                                           "text": {"type": "string"}},
                            "required": ["field", "text"],
                            "additionalProperties": False,
                        },
                    },
                    "explanation_tr": {"type": "string"},
                    "explanation_en": {"type": "string"},
                },
                "required": ["kind", "quotes", "explanation_tr", "explanation_en"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class AIConfig:
    enabled: bool
    model: str
    effort: str
    max_tokens: int
    prompt_version: str
    max_cost_usd_per_day: float
    price_in_per_mtok: float
    price_out_per_mtok: float
    timeout_s: float
    api_key_env: str
    workspace_id_env: str
    cache_dir: str


def load_ai_config(path: Path | str) -> AIConfig | None:
    """The `ai` section of config/profile_checks.yaml (strict keys); None without it."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    ai = raw.get("ai")
    if ai is None:
        return None
    want = set(AIConfig.__dataclass_fields__)
    if not isinstance(ai, Mapping) or set(ai) != want:
        raise ValueError(f"profile_checks.ai: keys must be exactly {sorted(want)}")
    return AIConfig(**{k: ai[k] for k in want})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).replace("İ", "i").replace("I", "ı").casefold()).strip()


def field_texts(persona: Persona) -> dict[str, str]:
    """Each profile field as the text a quote must come from (lists joined with " | ")."""
    d = persona.to_dict()
    return {f: (" | ".join(d[f]) if isinstance(d.get(f), list) else str(d.get(f, "")))
            for f in FIELDS}


def reading_summary(persona: Persona, config: DecisionConfig,
                    answers: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The engine's reading, in plain values (what the model compares the text with)."""
    r = read_persona(persona, config, dict(answers or {}))
    c = config.raw
    prio = {k.casefold(): v for k, v in c["priorities"].items()}
    cons = {k.casefold(): v for k, v in c["constraints"].items()}
    out: dict[str, Any] = {
        "priorities_matched": [p for p in persona.oncelikler if p.casefold() in prio],
        "priorities_not_matched": [p for p in persona.oncelikler if p.casefold() not in prio],
        "constraints_matched": [x for x in persona.acik_kisitlar if x.casefold() in cons],
        "constraints_not_matched": [x for x in persona.acik_kisitlar if x.casefold() not in cons],
        "open_questions": [q.text for q in r.questions if q.answer is None],
        "assumptions": list(r.assumptions),
    }
    lv = r.levels
    if lv is not None:
        names = {v: k for k, v in c["levels"].items()}
        out.update({"risk_profile": lv.risk_profile, "fund_risk_ceiling": lv.ceiling,
                    "horizon_period": lv.period, "fx_level": lv.fx_level,
                    "liquidity": names.get(lv.liquidity, lv.liquidity),
                    "income": names.get(lv.income, lv.income),
                    "principal_protection": names.get(lv.principal, lv.principal)})
    return out


def validate(raw: Mapping[str, Any], persona: Persona, rule_fields: list[set[str]] | None = None
             ) -> tuple[list[dict], int]:
    """The findings whose every quote is in its field (word for word, case and spacing
    aside); (kept, dropped). A finding with the same fields as a rule finding is
    dropped as a repeat."""
    texts = {f: _norm(t) for f, t in field_texts(persona).items()}
    kept, dropped = [], 0
    for f in list(raw.get("findings") or [])[:MAX_FINDINGS]:
        quotes = [q for q in f.get("quotes") or [] if isinstance(q, Mapping)]
        need = 2 if f.get("kind") == "conflict" else 1
        ok = (f.get("kind") in ("conflict", "confirm") and need <= len(quotes) <= 3
              and all(q.get("field") in texts and 0 < len(str(q.get("text", ""))) <= MAX_QUOTE
                      and _norm(q["text"]) in texts[q["field"]] for q in quotes)
              and str(f.get("explanation_tr", "")).strip() and str(f.get("explanation_en", "")).strip())
        fields = {q["field"] for q in quotes} if ok else set()
        if ok and rule_fields and any(fields <= rf for rf in rule_fields):
            ok = False
        if not ok:
            dropped += 1
            continue
        kept.append({"kind": f["kind"], "fields": sorted(fields, key=FIELDS.index),
                     "quotes": [{"field": q["field"], "text": str(q["text"]).strip()} for q in quotes],
                     "explanation": {"TR": f["explanation_tr"].strip(), "EN": f["explanation_en"].strip()}})
    return kept, dropped


class ProfileAI:
    """One check per profile content (the persona, the engine's reading, the prompt
    version and the model), in a background thread; cached on disk per content."""

    def __init__(self, config: AIConfig, decision_config: DecisionConfig, cache_root: Path,
                 *, api_key: str | None, workspace_id: str | None = None, sdk=None,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        self.config, self._dc, self._root = config, decision_config, Path(cache_root)
        self._sdk_obj, self._args = sdk, (api_key, workspace_id)
        self.enabled = config.enabled and (sdk is not None or bool(api_key))
        self.off_reason = "" if self.enabled else ("ai check off" if not config.enabled
                                                   else f"no {config.api_key_env}")
        self._now = now
        self._jobs: dict[str, Future] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="profile-ai")

    @property
    def _sdk(self):
        if self._sdk_obj is None:          # made on first use (the SDK import is slow)
            import anthropic
            api_key, workspace_id = self._args
            extra = {"default_headers": {WORKSPACE_HEADER: workspace_id}} if workspace_id else {}
            self._sdk_obj = anthropic.Anthropic(api_key=api_key, timeout=self.config.timeout_s,
                                                max_retries=1, **extra)
        return self._sdk_obj

    # --- public ------------------------------------------------------------------

    def key(self, persona: Persona, answers: Mapping[str, str] | None = None) -> str:
        body = json.dumps({"p": persona.to_dict(), "r": reading_summary(persona, self._dc, answers),
                           "v": self.config.prompt_version, "m": self.config.model},
                          ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]

    def start(self, persona: Persona, answers: Mapping[str, str] | None = None) -> str:
        k = self.key(persona, answers)
        if not self.enabled or self._read(k) is not None:
            return k
        with self._lock:
            job = self._jobs.get(k)
            if job is None or (job.done() and job.exception() is not None):
                self._jobs[k] = self._pool.submit(self._check, k, persona, dict(answers or {}))
        return k

    def status(self, persona: Persona, answers: Mapping[str, str] | None = None,
               rule_fields: list[set[str]] | None = None) -> dict:
        """{state: off|running|done|failed, findings, dropped, model, cost_usd, reason}."""
        if not self.enabled:
            return {"state": "off", "findings": [], "reason": self.off_reason}
        k = self.start(persona, answers)
        stored = self._read(k)
        if stored is None:
            job = self._jobs.get(k)
            if job is not None and job.done() and job.exception() is not None:
                return {"state": "failed", "findings": [], "reason": type(job.exception()).__name__}
            return {"state": "running", "findings": [], "reason": ""}
        if stored.get("error"):
            return {"state": "failed", "findings": [], "reason": stored["error"]}
        kept, dropped = validate(stored["raw"], persona, rule_fields)
        return {"state": "done", "findings": kept, "dropped": dropped, "model": stored["model"],
                "cost_usd": stored["cost_usd"], "reason": ""}

    def spent_today(self) -> float:
        day = self._now().date().isoformat()
        try:
            rows = (self._root / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0.0
        return sum(json.loads(r)["cost_usd"] for r in rows if r.strip() and json.loads(r)["day"] == day)

    # --- the call ----------------------------------------------------------------

    def _check(self, k: str, persona: Persona, answers: dict) -> None:
        c = self.config
        if self.spent_today() >= c.max_cost_usd_per_day:
            self._write(k, {"error": f"daily limit ({c.max_cost_usd_per_day:.2f} USD) reached"}, keep=False)
            return
        payload = {"profile": field_texts(persona), "engine_reading": reading_summary(persona, self._dc, answers)}
        try:
            resp = self._sdk.beta.messages.create(
                model=c.model, max_tokens=c.max_tokens, system=SYSTEM,
                betas=[FALLBACK_BETA], fallbacks="default",          # refusal fallback (Opus 5.5)
                output_config={"effort": c.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=1)}],
            )
        except Exception as e:          # an API or network error: failed, not cached (no SDK import here)
            log.warning("profile ai check failed: %s", type(e).__name__)
            self._write(k, {"error": f"model error ({type(e).__name__})"}, keep=False)
            return
        u = resp.usage
        cost = (u.input_tokens * c.price_in_per_mtok + u.output_tokens * c.price_out_per_mtok) / 1e6
        self._ledger(cost)
        if resp.stop_reason == "refusal":
            self._write(k, {"error": "the model declined", "cost_usd": round(cost, 6)}, keep=False)
            return
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            raw = json.loads(text)
        except ValueError:
            self._write(k, {"error": "no valid answer", "cost_usd": round(cost, 6)}, keep=False)
            return
        self._write(k, {"raw": raw, "model": resp.model, "cost_usd": round(cost, 6),
                        "created_at": self._now().isoformat()}, keep=True)

    # --- storage -----------------------------------------------------------------

    def _path(self, k: str) -> Path:
        return self._root / f"{k}.json"

    def _read(self, k: str) -> dict | None:
        mem = getattr(self, "_errors", {}).get(k)
        if mem is not None:
            return mem
        try:
            return json.loads(self._path(k).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write(self, k: str, data: dict, keep: bool) -> None:
        """A result is cached on disk; an error only in memory (a later start retries)."""
        if not keep:
            self.__dict__.setdefault("_errors", {})[k] = data
            return
        self.__dict__.setdefault("_errors", {}).pop(k, None)
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._path(k).write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8", newline="\n")
        except OSError:
            log.warning("cannot write the profile check %s", k)

    def _ledger(self, cost: float) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            with (self._root / "costs.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps({"day": self._now().date().isoformat(), "cost_usd": round(cost, 6)}) + "\n")
        except OSError:
            log.warning("cannot write the profile check cost")


def profile_ai_from_root(root: Path | str, decision_config: DecisionConfig,
                         env: Mapping[str, str] | None = None) -> ProfileAI | None:
    """The check of a prototype root (config/profile_checks.yaml `ai`, the key from
    the environment or root/.env); None when the config has no `ai` section."""
    root = Path(root)
    f = root / "config" / "profile_checks.yaml"
    cfg = load_ai_config(f) if f.is_file() else None
    if cfg is None:
        return None
    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
        env.update(os.environ)
    return ProfileAI(cfg, decision_config, root / cfg.cache_dir,
                     api_key=(env.get(cfg.api_key_env) or "").strip() or None,
                     workspace_id=(env.get(cfg.workspace_id_env) or "").strip() or None)


class ProfileCheck:
    """The API side: starts the check when a run opens and answers the route with
    the findings in the RM's language (repeats of a rule finding left out)."""

    def __init__(self, ai: ProfileAI, decision_config: DecisionConfig, texts: Mapping | None) -> None:
        self._ai, self._dc, self._texts = ai, decision_config, texts

    @staticmethod
    def _answers(result) -> dict[str, str]:
        return {q.question_id: q.answer for q in result.questions if q.answer is not None}

    def start(self, result) -> None:
        try:
            self._ai.start(result.persona, self._answers(result))
        except Exception as e:          # never breaks the run view
            log.warning("profile ai start: %s", type(e).__name__)

    def status(self, result, lang: str = "TR") -> dict:
        from rmprep.api.profile_checks import check_run
        rules = check_run(result, self._dc, self._texts, lang) if self._texts else []
        out = self._ai.status(result.persona, self._answers(result), [set(r["fields"]) for r in rules])
        out["findings"] = [{"kind": f["kind"], "fields": f["fields"], "quotes": f["quotes"],
                            "text": f["explanation"].get(lang, f["explanation"]["TR"])}
                           for f in out.get("findings", [])]
        return out
