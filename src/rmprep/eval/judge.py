"""The LLM judge (docs/eval.md): grades only what code cannot - is the meeting
text tailored to this client, clear for the RM, balanced. Fixed choices per
rubric item (yes | partly | no) and a one-line reason, through structured
output. The rule checks stay in code.

Judge is a small protocol, so another grader (Jev, later) can replace it or
grade the same texts for an agreement check. HaikuJudge: one Messages API call
on Claude Haiku 5.5 (config/eval.yaml judge), effort from the config,
adaptive thinking (the model default; no `thinking` parameter). Haiku 5.5 has
no server-side refusal fallback: a refusal is a Grade with an error. The key
is org-level: with judge.workspace_id_env set, every request carries the
anthropic-workspace-id header. Grades are cached on disk, so a second suite
run costs nothing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from rmprep.contracts import DecisionResult, NarrativeDraft
from rmprep.eval.config import JudgeConfig, RubricItem

CHOICES = ("yes", "partly", "no")
PROMPT_VERSION = "j1"            # bump on any change of the prompt or the schema
WORKSPACE_HEADER = "anthropic-workspace-id"

SYSTEM = (
    "You review a meeting-preparation text that a bank's relationship manager (RM) will "
    "use before meeting one client. The text was checked by code for numbers, sources, "
    "forbidden phrases and product rules; do not re-check those. Grade only the rubric "
    "questions, from the RM's point of view. For each question choose exactly one of "
    "yes, partly, no, and give a one-line reason (at most 25 words, in English) that "
    "names what in the text supports the choice."
)


@dataclass(frozen=True)
class Grade:
    run_id: str
    lang: str
    model: str
    items: Mapping[str, tuple[str, str]] = field(default_factory=dict)  # id -> (choice, reason)
    cost_usd: float = 0.0
    error: str | None = None    # set when there is no grade (refusal, API error, budget)

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "lang": self.lang, "model": self.model,
                "items": {k: list(v) for k, v in self.items.items()},
                "cost_usd": self.cost_usd, "error": self.error}

    @classmethod
    def from_dict(cls, d: Mapping) -> Grade:
        return cls(run_id=d["run_id"], lang=d["lang"], model=d["model"],
                   items={k: (v[0], v[1]) for k, v in d["items"].items()},
                   cost_usd=d["cost_usd"], error=d["error"])


class Judge(Protocol):
    model: str

    def grade(self, result: DecisionResult, draft: NarrativeDraft,
              rubric: tuple[RubricItem, ...]) -> Grade: ...


def schema(rubric: Iterable[RubricItem]) -> dict[str, Any]:
    item = {"type": "object",
            "properties": {"choice": {"type": "string", "enum": list(CHOICES)},
                           "reason": {"type": "string"}},
            "required": ["choice", "reason"], "additionalProperties": False}
    ids = [r.id for r in rubric]
    return {"type": "object", "properties": {i: item for i in ids}, "required": ids,
            "additionalProperties": False}


def user_text(result: DecisionResult, draft: NarrativeDraft,
              rubric: tuple[RubricItem, ...]) -> str:
    from rmprep.narrator.template import to_markdown

    labels = {o.option.option_id: o.option.label for o in result.options}
    client = {k: v for k, v in result.persona.to_dict().items() if k != "persona_id"}
    questions = "\n".join(f"- {r.id}: {r.question}" for r in rubric)
    return (
        "<client>\n" + json.dumps(client, ensure_ascii=False, indent=1) + "\n</client>\n\n"
        "<rm_selection>\n" + "\n".join(f"- {labels.get(i, i)}" for i in result.rm_selected)
        + "\n</rm_selection>\n\n"
        f"<meeting_text lang=\"{draft.lang}\">\n{to_markdown(draft)}\n</meeting_text>\n\n"
        f"<rubric>\n{questions}\n</rubric>"
    )


class HaikuJudge:
    def __init__(self, config: JudgeConfig, *, api_key: str | None = None,
                 workspace_id: str | None = None, sdk=None) -> None:
        if sdk is None:
            import anthropic          # optional extra [narrator]

            extra = {"default_headers": {WORKSPACE_HEADER: workspace_id}} if workspace_id else {}
            sdk = anthropic.Anthropic(api_key=api_key, **extra)
        self._sdk = sdk
        self.config = config
        self.model = config.model

    def grade(self, result: DecisionResult, draft: NarrativeDraft,
              rubric: tuple[RubricItem, ...]) -> Grade:
        import anthropic

        base = Grade(result.run_id, draft.lang, self.model)
        try:
            msg = self._sdk.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=SYSTEM,
                messages=[{"role": "user", "content": user_text(result, draft, rubric)}],
                output_config={"effort": self.config.effort,
                               "format": {"type": "json_schema", "schema": schema(rubric)}},
            )
        except anthropic.RateLimitError as e:
            return _err(base, f"rate_limit: {e.message}")
        except anthropic.APIStatusError as e:
            return _err(base, f"api {e.status_code}: {e.message}")
        except anthropic.APIConnectionError as e:   # includes APITimeoutError
            return _err(base, f"connection: {e}")

        u = msg.usage
        cost = (u.input_tokens * self.config.price_input_per_mtok
                + u.output_tokens * self.config.price_output_per_mtok) / 1e6
        g = Grade(result.run_id, draft.lang, msg.model, cost_usd=cost)
        if msg.stop_reason == "refusal":
            details = msg.stop_details
            return _err(g, f"refusal ({details.category if details else 'no category'})")
        if msg.stop_reason == "max_tokens":
            return _err(g, "cut off (max_tokens)")
        text = next((b.text for b in msg.content if b.type == "text"), None)
        try:
            data = json.loads(text or "")
            items = {r.id: (data[r.id]["choice"], data[r.id]["reason"]) for r in rubric}
        except (ValueError, KeyError, TypeError) as e:
            return _err(g, f"bad reply: {e}")
        if any(c not in CHOICES for c, _ in items.values()):
            return _err(g, "bad reply: unknown choice")
        return Grade(g.run_id, g.lang, g.model, items, cost)


def _err(g: Grade, error: str) -> Grade:
    return Grade(g.run_id, g.lang, g.model, {}, g.cost_usd, error)


def judge_from_env(config: JudgeConfig, env: Mapping[str, str]) -> HaikuJudge | None:
    """A judge if env holds the API key (config.api_key_env), else None. Key and
    workspace id are passed on, never logged."""
    key = env.get(config.api_key_env, "")
    if not key.strip():
        return None
    ws = env.get(config.workspace_id_env, "").strip() if config.workspace_id_env else ""
    return HaikuJudge(config, api_key=key, workspace_id=ws or None)


class CachedJudge:
    """A judge with a grade cache: one file per (model, prompt version, rubric,
    run, lang, text). Errors are not cached."""

    def __init__(self, inner: Judge, cache_dir: Path | str) -> None:
        self.inner = inner
        self.model = inner.model
        self.cache_dir = Path(cache_dir)

    def key(self, result: DecisionResult, draft: NarrativeDraft,
            rubric: tuple[RubricItem, ...]) -> str:
        parts = [self.model, PROMPT_VERSION, [[r.id, r.question] for r in rubric],
                 user_text(result, draft, rubric)]
        digest = hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8"),
                              usedforsecurity=False).hexdigest()[:12]
        return f"{result.run_id}-{draft.lang}-{digest}"

    def cached(self, result: DecisionResult, draft: NarrativeDraft,
               rubric: tuple[RubricItem, ...]) -> Grade | None:
        path = self.cache_dir / f"{self.key(result, draft, rubric)}.json"
        if path.exists():
            return Grade.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return None

    def grade(self, result: DecisionResult, draft: NarrativeDraft,
              rubric: tuple[RubricItem, ...]) -> Grade:
        hit = self.cached(result, draft, rubric)
        if hit is not None:
            return Grade(hit.run_id, hit.lang, hit.model, hit.items, 0.0, hit.error)
        g = self.inner.grade(result, draft, rubric)
        if g.error is None:
            path = self.cache_dir / f"{self.key(result, draft, rubric)}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(g.to_dict(), ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        return g


@dataclass(frozen=True)
class GradedText:
    scenario_id: str
    repeat: int
    grade: Grade


def grade_texts(runs, judge: Judge | None, rubric: tuple[RubricItem, ...], *,
                budget_left: Callable[[], float] | None = None,
                spend: Callable[[float], None] | None = None) -> list[GradedText]:
    """Grade each LLM meeting text once (the first run of each scenario; a
    repeat has the same text). Template texts are not graded (they are code).
    Over the budget, no new call is made (a cached grade is still used)."""
    if judge is None:
        return []
    out = []
    for sr in runs:
        if not sr.runs:
            continue
        run = sr.runs[0]
        for lang, d in sorted(run.narratives.items()):
            if d.source != "llm" or run.approved is None:
                continue
            cached = judge.cached(run.approved, d, rubric) if isinstance(judge, CachedJudge) else None
            if cached is None and budget_left is not None and budget_left() <= 0:
                g = Grade(run.result.run_id, lang, judge.model, error="budget: eval limit reached")
            else:
                g = judge.grade(run.approved, d, rubric)
                if spend is not None:
                    spend(g.cost_usd)
            out.append(GradedText(sr.scenario.id, run.repeat, g))
    return out
