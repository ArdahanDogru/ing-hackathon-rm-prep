"""The LLM judge (docs/eval.md): grades only what code cannot - is the meeting
text tailored to this client, clear for the RM, balanced. Fixed choices per
rubric item (yes | partly | no) and a one-line reason, through structured
output. The rule checks stay in code.

Prompt caching (the user's decision, docs/eval.md): the instructions and the
full rubric are one stable system block with cache_control (5-minute TTL; the
grades of a suite run are consecutive calls). It holds no per-call value, and
its real content is above Haiku 5.5's minimum cacheable prefix (512 tokens;
below it nothing caches, silently). Only the text to grade is in the user
message. The cost counts cache writes (1.25x) and cache reads (0.1x).

Judge is a small protocol, so another grader (Jev, later) can replace it or
grade the same texts for an agreement check. HaikuJudge: one Messages API call
on Claude Haiku 5.5 (config/eval.yaml judge), effort from the config,
adaptive thinking (the model default; no `thinking` parameter). Haiku 5.5 has
no server-side refusal fallback: a refusal is a Grade with an error. The key
is org-level: with judge.workspace_id_env set, every request carries the
anthropic-workspace-id header. Grades are cached on disk, so a second suite
run costs nothing."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from rmprep.contracts import DecisionResult, EvidenceSet, NarrativeDraft
from rmprep.eval.config import JudgeConfig, RubricItem

CHOICES = ("yes", "partly", "no")
PROMPT_VERSION = "j3"            # bump on any change of the prompt or the schema
# j3 (E10, 2026-10-12): the 8 sections in screen order, the collapsed ones, varsayimlar
# as engine text, and the per-option facts (<option_facts>) as context
WORKSPACE_HEADER = "anthropic-workspace-id"
CACHE_WRITE_FACTOR = 1.25        # 5-minute cache write, times the input price
CACHE_READ_FACTOR = 0.1

INSTRUCTIONS = """\
You review a meeting-preparation text. A relationship manager (RM) of a Turkish bank \
will read it before a meeting with one client. The text was written for this client from \
a ranked list of products (deposits, a time deposit and TEFAS investment funds) that the \
RM already approved, and from the RM's own selection of products to discuss.

What the user message holds:
- <client>: the client profile as the RM entered it (profession, age, risk profile, \
situation, goal, horizon, liquidity need, FX preference, income need, principal \
protection, priorities, explicit constraints, the RM's note). The values are Turkish.
- <rm_selection>: the products the RM selected for the meeting.
- <option_facts>: for each selected product, the facts the text could use: short name, \
real 1-year return after tax and inflation, SPK risk level (1-7), access to the money \
(settlement days or the term), entry/exit fees above 0, and the risk note of its asset \
class. A fact marked "not available" is not in the data: the text cannot state it, so \
its absence is not a gap. A fact that is available and matters for this client but is \
left out of the text is a gap.
- <meeting_text>: the text to grade, in Markdown, in Turkish or English. Its 8 sections, \
in the order of the RM's screen: summary (ozet), talking points for the client \
(talking_points), a short offer text (teklif_metni), recommendations with one heading per \
selected product (oneriler), points of attention (dikkat); then, under the heading \
"Ek bilgiler" / "Additional information": alternatives (alternatifler), questions for the \
client (sorular) and assumptions (varsayimlar). The RM sees the first five sections at \
once; the last three are collapsed and opened only on demand, so judge clarity and length \
mainly on the first five. The assumptions (varsayimlar) are the engine's text, copied \
word for word by rule; they may hold field names or mixed language. Read them as context, \
but do not grade its wording, its language or its length.

What code already checked (do not grade these, do not mention them): every number and \
date comes from the evidence; every named product was selected or is a listed \
alternative; no product breaks the client's risk ceiling or explicit constraints; \
sentences cite evidence ids; no forbidden phrase (for example a guarantee) is present; \
the disclaimer and the assumptions are present. Ids such as E1234abcd or fund:ABC are \
citations for the RM's tool; they are not a style problem.

Your task: answer only the rubric questions below, from the RM's point of view, for \
this client. For each question choose exactly one of yes, partly or no, using the \
definitions of that question. Give a one-line reason in English (at most 25 words) that \
names the part of the text that decides the choice. Judge the text as it is; do not \
suggest a better text and do not grade the products themselves. When in doubt between \
two choices, choose the lower one.

Rubric:
"""

# The yes / partly / no definitions of the known rubric items (config/eval.yaml ids).
DEFINITIONS = {
    "tailored": (
        "yes = the text uses this client's own facts in the recommendations and the offer "
        "(at least the goal or situation, the horizon, the priorities or constraints, and the "
        "RM's note where it matters), and it explains why each selected product fits them. "
        "partly = some client facts appear, but parts read as a generic offer that could be "
        "given to any client, or a central fact (for example the horizon or the liquidity "
        "need) is ignored. no = a generic product description; the client's situation is not "
        "used."),
    "clear_for_rm": (
        "yes = the RM can use it in the meeting as it is: a clear structure, short sentences, "
        "plain language, the main message first, concrete questions for the client, and a "
        "length that fits a meeting preparation. partly = usable, but the RM must reorder, "
        "shorten or decode parts (long or repeated sentences, unexplained terms, a weak "
        "order). no = confusing, contradictory or much too long to use."),
    "balanced": (
        "yes = risks, costs and uncertainty (past returns, risk level, liquidity or valör, "
        "data limits) stand next to the benefits with fair weight, and the tone gives the "
        "client a choice without pressure. partly = risks are mentioned but brief or hidden "
        "behind the benefits, or the tone pushes a little. no = benefits only, or sales "
        "pressure."),
}
GENERIC_DEFINITION = ("yes = fully true for this text and this client. partly = true for "
                      "some parts only, or with a clear gap. no = not true.")


def system_text(rubric: Iterable[RubricItem]) -> str:
    """The stable system block: instructions and the full rubric. No per-call value."""
    items = "\n".join(f"- {r.id}: {r.question}\n  {DEFINITIONS.get(r.id, GENERIC_DEFINITION)}"
                      for r in rubric)
    return INSTRUCTIONS + items + "\n"


@dataclass(frozen=True)
class Grade:
    run_id: str
    lang: str
    model: str
    items: Mapping[str, tuple[str, str]] = field(default_factory=dict)  # id -> (choice, reason)
    cost_usd: float = 0.0
    error: str | None = None    # set when there is no grade (refusal, API error, budget)
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "lang": self.lang, "model": self.model,
                "items": {k: list(v) for k, v in self.items.items()},
                "cost_usd": self.cost_usd, "error": self.error,
                "cache_write_tokens": self.cache_write_tokens,
                "cache_read_tokens": self.cache_read_tokens}

    @classmethod
    def from_dict(cls, d: Mapping) -> Grade:
        return cls(run_id=d["run_id"], lang=d["lang"], model=d["model"],
                   items={k: (v[0], v[1]) for k, v in d["items"].items()},
                   cost_usd=d["cost_usd"], error=d["error"],
                   cache_write_tokens=d.get("cache_write_tokens", 0),
                   cache_read_tokens=d.get("cache_read_tokens", 0))


class Judge(Protocol):
    model: str

    def grade(self, result: DecisionResult, draft: NarrativeDraft,
              rubric: tuple[RubricItem, ...], *, evidence: EvidenceSet | None = None,
              repeat: int = 0) -> Grade: ...


def schema(rubric: Iterable[RubricItem]) -> dict[str, Any]:
    item = {"type": "object",
            "properties": {"choice": {"type": "string", "enum": list(CHOICES)},
                           "reason": {"type": "string"}},
            "required": ["choice", "reason"], "additionalProperties": False}
    ids = [r.id for r in rubric]
    return {"type": "object", "properties": {i: item for i in ids}, "required": ids,
            "additionalProperties": False}


NOT_AVAILABLE = "not available"


def option_facts(result: DecisionResult, evidence: EvidenceSet, lang: str) -> str:
    """One line per selected option with the facts the text could use (narrator
    facts pack N13 and decision display facts): short name, real 1-year return,
    risk level, access, fees above 0, the risk note; a missing fact says so."""
    from rmprep.decision.config import DEFAULT_PATH
    from rmprep.decision.config import load_config as load_decision
    from rmprep.decision.display import display_facts
    from rmprep.narrator.facts import build_facts

    facts = build_facts(result, evidence)
    shown = display_facts(result, evidence, load_decision(DEFAULT_PATH))
    lines = []
    for o in facts.selected:
        d = shown.get(o.option_id)
        risk = facts.risks.get(o.option_id)
        real = (f"real 1-year return {d.real_1y.value:+.1f} %"
                if d is not None and d.real_1y is not None
                else f"real 1-year return: {NOT_AVAILABLE}")
        level = (f"risk level {d.risk.value:.0f}" if d is not None and d.risk is not None
                 else f"risk level: {NOT_AVAILABLE}")
        access = (f"access: {risk.access}" if risk is not None and risk.access
                  else f"access: {NOT_AVAILABLE}")
        fees = ("fees: " + ", ".join(f"{n.quantity} {n.value:g} %" for n in risk.fees)
                if risk is not None and risk.fees else "fees: none above 0")
        note = (risk.note.get(lang) or "") if risk is not None else ""
        lines.append(f"- {o.name or o.label} ({o.option_id}): {real}; {level}; {access}; "
                     f"{fees}; risk note: {note or NOT_AVAILABLE}")
    return "\n".join(lines)


def user_text(result: DecisionResult, draft: NarrativeDraft,
              evidence: EvidenceSet | None = None) -> str:
    """The per-call part: the client, the RM selection, the option facts (with
    evidence) and the text to grade."""
    from rmprep.api.names import short_name
    from rmprep.narrator.template import to_markdown

    labels = {o.option.option_id: o.option.label for o in result.options}
    # the screen names as headings, as the RM sees the text (lead fix 2026-10-12)
    names = {i: " ".join(short_name(lbl)).strip() for i, lbl in labels.items()}
    client = {k: v for k, v in result.persona.to_dict().items() if k != "persona_id"}
    facts = ("" if evidence is None else
             "<option_facts>\n" + option_facts(result, evidence, draft.lang)
             + "\n</option_facts>\n\n")
    return (
        "<client>\n" + json.dumps(client, ensure_ascii=False, indent=1) + "\n</client>\n\n"
        "<rm_selection>\n" + "\n".join(f"- {labels.get(i, i)}" for i in result.rm_selected)
        + "\n</rm_selection>\n\n" + facts
        + f"<meeting_text lang=\"{draft.lang}\">\n{to_markdown(draft, names=names)}\n</meeting_text>"
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
              rubric: tuple[RubricItem, ...], *, evidence: EvidenceSet | None = None,
              repeat: int = 0) -> Grade:
        """repeat: the index of a repeated grade (E10). The request is the same;
        the variation of the model gives the spread."""
        import anthropic

        base = Grade(result.run_id, draft.lang, self.model)
        try:
            msg = self._sdk.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=[{"type": "text", "text": system_text(rubric),
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_text(result, draft, evidence)}],
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
        cache_write = u.cache_creation_input_tokens or 0
        cache_read = u.cache_read_input_tokens or 0
        tokens_in = (u.input_tokens + CACHE_WRITE_FACTOR * cache_write
                     + CACHE_READ_FACTOR * cache_read)
        cost = (tokens_in * self.config.price_input_per_mtok
                + u.output_tokens * self.config.price_output_per_mtok) / 1e6
        g = Grade(result.run_id, draft.lang, msg.model, cost_usd=cost,
                  cache_write_tokens=cache_write, cache_read_tokens=cache_read)
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
        return dataclasses.replace(g, items=items)


def _err(g: Grade, error: str) -> Grade:
    return dataclasses.replace(g, items={}, error=error)


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
    run, lang, text with its option facts, repeat index). Errors are not cached."""

    def __init__(self, inner: Judge, cache_dir: Path | str) -> None:
        self.inner = inner
        self.model = inner.model
        self.cache_dir = Path(cache_dir)

    def key(self, result: DecisionResult, draft: NarrativeDraft,
            rubric: tuple[RubricItem, ...], *, evidence: EvidenceSet | None = None,
            repeat: int = 0) -> str:
        parts = [self.model, PROMPT_VERSION, system_text(rubric),
                 user_text(result, draft, evidence), repeat]
        digest = hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8"),
                              usedforsecurity=False).hexdigest()[:12]
        return f"{result.run_id}-{draft.lang}-{digest}"

    def cached(self, result: DecisionResult, draft: NarrativeDraft,
               rubric: tuple[RubricItem, ...], *, evidence: EvidenceSet | None = None,
               repeat: int = 0) -> Grade | None:
        key = self.key(result, draft, rubric, evidence=evidence, repeat=repeat)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            return Grade.from_dict(json.loads(path.read_text(encoding="utf-8")))
        return None

    def grade(self, result: DecisionResult, draft: NarrativeDraft,
              rubric: tuple[RubricItem, ...], *, evidence: EvidenceSet | None = None,
              repeat: int = 0) -> Grade:
        kw = {"evidence": evidence, "repeat": repeat}
        hit = self.cached(result, draft, rubric, **kw)
        if hit is not None:
            return dataclasses.replace(hit, cost_usd=0.0, cache_write_tokens=0,
                                       cache_read_tokens=0)
        g = self.inner.grade(result, draft, rubric, **kw)
        if g.error is None:
            path = self.cache_dir / f"{self.key(result, draft, rubric, **kw)}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(g.to_dict(), ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8", newline="\n")
        return g


@dataclass(frozen=True)
class GradedText:
    scenario_id: str
    repeat: int                 # the run repetition of the scenario (the first run: 0)
    grade: Grade
    judge_repeat: int = 0       # E10: the index of the repeated grade of the same text


def grade_texts(runs, judge: Judge | None, rubric: tuple[RubricItem, ...], *,
                budget_left: Callable[[], float] | None = None,
                spend: Callable[[float], None] | None = None,
                repeats: int = 1) -> list[GradedText]:
    """Grade each LLM meeting text `repeats` times (config judge_repeats), with
    the run's evidence for the option facts; the first run of each scenario (a
    run repetition has the same text). Template texts are not graded (they are
    code). Over the budget, no new call is made (a cached grade is still used)."""
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
            for k in range(repeats):
                kw = {"evidence": run.evidence, "repeat": k}
                cached = (judge.cached(run.approved, d, rubric, **kw)
                          if isinstance(judge, CachedJudge) else None)
                if cached is None and budget_left is not None and budget_left() <= 0:
                    g = Grade(run.result.run_id, lang, judge.model,
                              error="budget: eval limit reached")
                else:
                    g = judge.grade(run.approved, d, rubric, **kw)
                    if spend is not None:
                        spend(g.cost_usd)
                out.append(GradedText(sr.scenario.id, run.repeat, g, k))
    return out
