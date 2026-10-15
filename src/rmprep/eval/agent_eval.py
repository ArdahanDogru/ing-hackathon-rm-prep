"""E11: the eval of the agentic top-3 decision (docs/agent.md; spec section 10).

For the base scenarios and the agent scenarios (group `agent`,
scenarios/agent/*.yaml), the first ready run of each gets an agent decision:

- One AgentService per scenario run, with the eval's own cache
  (<report_dir>/agent/<scenario id>/): two scenarios on the same engine run (e.g.
  base-p01 and agent-negative-news) must not share a decision. The agent's daily
  limit is off; the eval limit of the suite run (config/eval.yaml) applies.
- The research is the real one (or a fake for tests) behind RecordingResearch:
  it adds the scenario's fake news (`agent_news`, deterministic) and records what
  the agent got, so the eval rebuilds the data pack the agent saw (also stored
  next to the decision, for a cached decision of a later suite run).
- start, then wait for the decision with a deadline (more than the agent's own
  limits); a decision still running at the deadline is a finding.
- Repeatability: a second decision of the same run in a fresh cache dir
  (<report_dir>/agent-repeat/<suite time>/<scenario id>/), report only; and a
  second service on the first cache must give the stored decision again.

The check `agent_decision` (checks.py) and the A/B judge (judge.py) read the
AgentRecord of the run."""

from __future__ import annotations

import dataclasses
import json
import statistics
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rmprep.contracts import TR_TZ, AgentDecision, DecisionState
from rmprep.eval.scenario import Scenario, engine_option

AGENT_GROUPS = ("base", "agent")
NO_DAILY_LIMIT = 1e9            # the eval's limit per suite run applies instead
DEADLINE_MARGIN_S = 30.0
AUTO = "auto"


def top3(d: AgentDecision | None) -> tuple[str, ...] | None:
    """The top 3 a decision shows: the agent's picks, the engine's for a fallback;
    None while running or off."""
    if d is None:
        return None
    if d.state == "done":
        return tuple(p.option_id for p in d.picks)
    if d.state == "fallback":
        return tuple(d.engine_top3)
    return None


@dataclass
class AgentRecord:
    """The agent part of one run (RunRecord.agent)."""

    decision: AgentDecision | None = None
    pack: dict | None = None                # the data pack the agent saw (rebuilt by the eval)
    lang: str = "TR"
    labels: Mapping[str, str] = field(default_factory=dict)    # estimate | web -> label
    words: Mapping[str, int] = field(default_factory=dict)
    phrases: tuple[str, ...] = ()
    cached: bool = False                    # from the cache of an earlier suite run (no call)
    cache_same: bool | None = None          # the stored decision comes back the same
    seconds: float = 0.0
    cost_usd: float = 0.0                   # the new model cost (0 when cached)
    research_cost_usd: float = 0.0          # growth of the research ledger
    repeat: AgentDecision | None = None     # a second decision without the cache
    repeat_seconds: float = 0.0
    repeat_cost_usd: float = 0.0
    news: list[str] = field(default_factory=list)       # options with injected news
    watch: list[dict] = field(default_factory=list)
    marks: list[dict] = field(default_factory=list)     # E12: the resolved scenario marks
    marks_hash: str = ""                    # E12: the hash the marks must give (pack.marks_hash)
    error: str | None = None                # deadline | budget | an exception

    def to_dict(self) -> dict:
        d = self.decision
        return {
            "state": None if d is None else d.state,
            "engine_top3": [] if d is None else list(d.engine_top3),
            "top3": list(top3(d) or ()),
            "picks": [] if d is None else [
                {"option_id": p.option_id, "uses_estimate": p.uses_estimate,
                 "uses_web": p.uses_web,
                 "reasons": [{"text": r.text, "cites": list(r.cites), "labels": list(r.labels)}
                             for r in p.reasons]} for p in d.picks],
            "dropped": [] if d is None else [
                {"option_id": p.option_id, "reason": p.reasons[0].text if p.reasons else ""}
                for p in d.dropped],
            "summary": "" if d is None else d.summary,
            "fallback_reason": "" if d is None else d.fallback_reason,
            "model": None if d is None else d.model,
            "prompt_version": None if d is None else d.prompt_version,
            "cached": self.cached, "cache_same": self.cache_same,
            "seconds": self.seconds, "cost_usd": self.cost_usd,
            "research_cost_usd": self.research_cost_usd,
            "repeat": None if self.repeat is None else {
                "state": self.repeat.state, "top3": list(top3(self.repeat) or ()),
                "fallback_reason": self.repeat.fallback_reason,
                "seconds": self.repeat_seconds, "cost_usd": self.repeat_cost_usd},
            "news": list(self.news), "watch": list(self.watch),
            "marks": mark_results(self) if self.marks else [],
            "marks_hash": {"want": self.marks_hash,
                           "decision": None if d is None else d.marks_hash},
            "error": self.error,
        }


class RecordingResearch:
    """ResearchLike around the research service (or a fake, or none): adds the
    scenario's fake news to the products it names and records every product research
    and every answered product question, so the eval can rebuild the agent's pack.

    E12: `marks()` gives the scenario's marks (agent_marks), resolved to finding ids
    on the recorded research of the engine's top 3; never the RM's real marks of the
    inner research (the eval stays deterministic)."""

    def __init__(self, inner: Any, news: Mapping[str, Sequence[Any]] | None = None, *,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
                 marks: Sequence[Any] = (), recommended: Sequence[str] = ()) -> None:
        self.inner = inner
        self.news = dict(news or {})
        self.now = now
        self.mark_specs = tuple(marks)
        self.recommended = tuple(recommended)
        self.products: dict[str, Any] = {}
        self.answers: list[tuple[str, Any]] = []

    def resolved_marks(self) -> list[dict]:
        """One row per scenario mark: the option, the finding id and text, or the error
        when the research of the run has no such finding (yet)."""
        rows = []
        for m in self.mark_specs:
            oid = (self.recommended[m.place - 1] if m.place <= len(self.recommended)
                   else None)
            row = {"product": m.product, "option_id": oid, "finding": m.finding,
                   "finding_id": None, "text": None, "mark": m.mark, "error": None}
            r = self.products.get(oid) if oid is not None else None
            items = () if r is None else (r.findings if m.group == "findings" else r.news)
            if oid is None:
                row["error"] = f"the engine has no {m.product}"
            elif r is None or r.error:
                row["error"] = f"{oid} has no research" + (f" ({r.error})" if r else "")
            elif m.index >= len(items):
                row["error"] = f"{oid} has no {m.group} item {m.index}"
            else:
                row["finding_id"], row["text"] = items[m.index].id, items[m.index].text
            rows.append(row)
        return rows

    def marks(self) -> dict[str, str]:
        return {r["finding_id"]: r["mark"] for r in self.resolved_marks() if r["finding_id"]}

    def research_many(self, options, lang):
        from rmprep.research.types import ProductResearch

        out = list(self.inner.research_many(options, lang)) if self.inner is not None else []
        have = {r.option_id for r in out}
        for o in options:
            if o.option_id in self.news and o.option_id not in have:
                out.append(ProductResearch(o.option_id, o.label, "", "", (), lang, "eval",
                                           self.now()))
        out = [self._inject(r) for r in out]
        for r in out:
            self.products[r.option_id] = r
        return out

    def _inject(self, r):
        extra = tuple(self.news.get(r.option_id, ()))
        if not extra:
            return r
        return dataclasses.replace(r, error="", news=(*extra, *r.news))

    def ask_product(self, option, question, lang, persona=None):
        if self.inner is None:
            return "web research is off"
        answer = self.inner.ask_product(option, question, lang, persona=persona)
        if not isinstance(answer, str) and not answer.error:
            self.answers.append((option.option_id, answer))
        return answer

    def spent_today(self) -> float:
        spent = getattr(self.inner, "spent_today", None)
        return float(spent()) if spent else 0.0


def news_findings(s: Scenario, result) -> dict[str, tuple]:
    """The scenario's agent_news as research findings per option id ("@engineN"
    resolved on the run; "{name}" replaced with the option's label)."""
    from rmprep.research.types import Finding, Source

    labels = {o.option.option_id: o.option.label for o in result.options}
    out: dict[str, list] = {}
    for n in s.agent_news:
        oid = engine_option(n.option, tuple(result.recommended))
        if oid is None or oid not in labels:
            continue
        text = n.text.replace("{name}", labels[oid])
        out.setdefault(oid, []).append(
            Finding(text, "haber", (Source(n.url, "", n.date),), "medium", n.date))
    return {k: tuple(v) for k, v in out.items()}


class AgentEval:
    def __init__(self, make_service: Callable[[Any, Path], Any], research: Any,
                 cache_root: Path, repeat_root: Path | None, decision_config, *,
                 labels: Mapping[str, Mapping[str, str]], words: Mapping[str, int],
                 phrases: Sequence[str], candidates: int, deadline_s: float,
                 lang: str = "TR", poll_s: float = 0.05, client_on: bool = True,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ)) -> None:
        self.make_service = make_service
        self.research = research
        self.cache_root = Path(cache_root)
        self.repeat_root = None if repeat_root is None else Path(repeat_root)
        self.decision_config = decision_config
        self.labels = {k: v.get(lang, v.get("TR", "")) for k, v in labels.items()}
        self.words = dict(words)
        self.phrases = tuple(phrases)
        self.candidates = candidates
        self.deadline_s = deadline_s
        self.lang = lang
        self.poll_s = poll_s
        self.clock = clock
        self.sleep = sleep
        self.now = now
        self.client_on = client_on          # False: no API key, every decision is "off"

    def run(self, runs, *, budget_left: Callable[[], float] | None = None,
            spend: Callable[[float], None] | None = None) -> None:
        """Sets RunRecord.agent on the first run of each base and agent scenario."""
        for sr in runs:
            if sr.scenario.group not in AGENT_GROUPS or not sr.runs:
                continue
            rec = sr.runs[0]
            try:
                rec.agent = self.run_one(sr.scenario, rec, budget_left, spend)
            except Exception as e:      # noqa: BLE001 - one bad run must not stop the suite
                rec.agent = self._record(error=f"{type(e).__name__}: {e}")

    # --- one run -----------------------------------------------------------------------

    def _record(self, **kw) -> AgentRecord:
        return AgentRecord(lang=self.lang, labels=self.labels, words=self.words,
                           phrases=self.phrases, **kw)

    def _research(self, s: Scenario, result,
                  news: Mapping[str, tuple]) -> RecordingResearch | None:
        if self.research is None and not news and not s.agent_marks:
            return None
        return RecordingResearch(self.research, news, now=self.now, marks=s.agent_marks,
                                 recommended=result.recommended)

    def run_one(self, s: Scenario, rec, budget_left=None, spend=None) -> AgentRecord:
        result = rec.result
        rid = result.run_id
        news = news_findings(s, result) if result.state == DecisionState.READY else {}
        out = self._record(news=sorted(news))
        cache = self.cache_root / s.id
        research = self._research(s, result, news)
        svc = self.make_service(research, cache)
        before = svc.status(rid)
        out.cached = before is not None and before.state in ("done", "fallback")
        if not out.cached and budget_left is not None and budget_left() <= 0:
            out.error = "budget: eval limit reached; no agent decision"
            return out

        r0 = research.spent_today() if research is not None else 0.0
        t = time.perf_counter()
        svc.start(result, rec.evidence, self.lang)
        d = self._await(svc, rid)
        out.seconds = time.perf_counter() - t
        out.decision = d
        # A2: a stored decision of the same key comes back without a model call
        out.cached = (out.cached and d is not None and before is not None
                      and d.to_dict() == before.to_dict())
        if research is not None:
            out.research_cost_usd = max(0.0, research.spent_today() - r0)
        if d is not None and d.state == "running":
            out.error = f"deadline: no decision in {self.deadline_s:.0f} s"
        out.cost_usd = 0.0 if out.cached or d is None else d.cost_usd
        if spend is not None:
            spend(out.cost_usd + out.research_cost_usd)

        out.pack = self._pack(result, rec.evidence, research, cache, rid, cached=out.cached)
        if research is not None and s.agent_marks:
            out.marks = research.resolved_marks()
            out.marks_hash = self._marks_hash(out.pack, research)
        if d is not None and d.state in ("done", "fallback"):
            again = self.make_service(None, cache).status(rid)
            out.cache_same = again is not None and again.to_dict() == d.to_dict()
            self._repeat(s, rec, news, out, budget_left, spend)
        out.watch = self._watch(s, result, out)
        return out

    def _await(self, svc, rid: str) -> AgentDecision | None:
        end = self.clock() + self.deadline_s
        while True:
            d = svc.status(rid)
            if d is None or d.state != "running" or self.clock() >= end:
                return d
            self.sleep(self.poll_s)

    def _pack(self, result, evidence, research: RecordingResearch | None, cache: Path,
              rid: str, *, cached: bool) -> dict | None:
        """The data pack the agent saw: build_pack with the recorded research, plus the
        findings of its arastir answers. Stored next to the decision; a cached decision
        reads it back (its research was not recorded in this suite run)."""
        from rmprep.agent.pack import build_pack, finding_items

        path = cache / f"{rid}.pack.json"
        if cached:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if result.state != DecisionState.READY:
            return None
        products = research.products if research is not None else {}
        marks = research.marks() if research is not None else {}
        pack = build_pack(result, evidence, self.decision_config, products, self.lang,
                          n=self.candidates, marks=marks)
        for oid, answer in (research.answers if research is not None else ()):
            if oid not in pack["arastirma"]:
                continue
            block = pack["arastirma"][oid]
            block["bulgular"] = [*block["bulgular"],
                                 *finding_items(oid, answer.findings, marks)]
        if not cached:
            try:
                cache.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n",
                                encoding="utf-8", newline="\n")
            except OSError:
                pass
        return pack

    @staticmethod
    def _marks_hash(pack: dict | None, research: RecordingResearch) -> str:
        """The marks_hash the decision must carry: the agent's rule on the candidates'
        recorded research and the resolved marks."""
        from rmprep.agent.pack import marks_hash

        ids = {c["option_id"] for c in (pack or {}).get("adaylar", ())}
        found = {k: v for k, v in research.products.items() if k in ids}
        return marks_hash(found, research.marks())

    def _repeat(self, s: Scenario, rec, news, out: AgentRecord, budget_left, spend) -> None:
        if self.repeat_root is None:
            return
        if budget_left is not None and budget_left() <= 0:
            return
        svc = self.make_service(self._research(s, rec.result, news), self.repeat_root / s.id)
        t = time.perf_counter()
        svc.start(rec.result, rec.evidence, self.lang)
        d = self._await(svc, rec.result.run_id)
        out.repeat_seconds = time.perf_counter() - t
        out.repeat = d
        out.repeat_cost_usd = 0.0 if d is None else d.cost_usd
        if spend is not None:
            spend(out.repeat_cost_usd)

    @staticmethod
    def _watch(s: Scenario, result, out: AgentRecord) -> list[dict]:
        cands = {c["option_id"]: c for c in (out.pack or {}).get("adaylar", ())}
        shown = top3(out.decision) or ()
        rows = []
        for oid in s.agent_watch:
            c = cands.get(oid)
            rows.append({"option_id": oid, "candidate": c is not None,
                         "engine_place": None if c is None else c["motor_sirasi"],
                         "warnings": [] if c is None else [w["kod"] for w in c["uyarilar"]],
                         "engine_top3": oid in result.recommended,
                         "agent_top3": oid in shown})
        return rows


def mark_results(a: AgentRecord) -> list[dict]:
    """E12: per resolved mark of the scenario, what the run did with it: a ✗ ("wrong")
    finding must not be in the pack; a ✓ ("ok") finding is in the pack as "RM
    doğruladı", and every reason that cites it has the label web_confirmed.
    `ok` is True when all of that holds; `problems` say what does not."""
    from rmprep.agent.pack import CONFIRMED

    items = {f["id"]: f for block in (a.pack or {}).get("arastirma", {}).values()
             for f in (*block.get("bulgular", ()), *block.get("haberler", ()))}
    d = a.decision
    reasons = [] if d is None else [(p.option_id, r) for p in (*d.picks, *d.dropped)
                                    for r in p.reasons]
    label = a.labels.get("web_confirmed", "")
    out = []
    for m in a.marks:
        problems = [m["error"]] if m["error"] else []
        fid = m["finding_id"]
        cited = None
        if fid and m["mark"] == "wrong" and fid in items:
            problems.append(f"the ✗ finding {fid} of {m['option_id']} is still in the pack")
        if fid and m["mark"] == "ok":
            got = items.get(fid, {}).get("dogrulama")
            if got != CONFIRMED:
                problems.append(f"the ✓ finding {fid} of {m['option_id']} is "
                                f"{'not in the pack' if got is None else repr(got)}, not "
                                f"\"{CONFIRMED}\"")
            citing = [(oid, r) for oid, r in reasons if fid in r.cites]
            cited = bool(citing)
            problems += [f"{oid}: a reason cites the ✓ finding {fid} without the label "
                         f"{label}: \"{r.text[:60]}\"" for oid, r in citing
                         if label not in r.labels]
        out.append({**m, "cited": cited, "ok": not problems, "problems": problems})
    return out


def eval_agent(root: Path | str, config, env: Mapping[str, str], *, client: Any = AUTO,
               research: Any = AUTO, created: datetime | None = None, repeat: bool = True,
               deadline_s: float | None = None) -> AgentEval:
    """The AgentEval of a prototype root: config/agent.yaml (without the daily limit),
    config/decision.yaml, the forbidden phrases of config/narrator.yaml; the model
    client and the research from env (AUTO) or given (tests: fakes; None: off); the
    caches under <root>/<report_dir>/."""
    from rmprep.agent.client import agent_client_from_env
    from rmprep.agent.config import load_agent_config
    from rmprep.agent.service import AgentService
    from rmprep.decision.config import load_config as load_decision_config
    from rmprep.narrator.config import load_config as load_narrator_config

    root = Path(root)
    acfg = dataclasses.replace(load_agent_config(root / "config" / "agent.yaml"),
                               max_cost_usd_per_day=NO_DAILY_LIMIT)
    dcfg = load_decision_config(root / "config" / "decision.yaml")
    phrases = tuple(dict.fromkeys(
        p for ps in load_narrator_config(root / "config" / "narrator.yaml")
        .forbidden_phrases.values() for p in ps))
    if client == AUTO:
        client = agent_client_from_env(acfg, env)
    if research == AUTO:
        from rmprep.research.service import research_from_root
        research = research_from_root(root, env)
    off = "" if client is not None else f"no {acfg.api_key_env}"

    def make(research_: Any, cache_root: Path) -> AgentService:
        return AgentService(acfg, client, research_, dcfg, phrases, cache_root, off_reason=off)

    created = created or datetime.now(TR_TZ)
    base = root / config.report_dir
    return AgentEval(make, research, base / "agent",
                     base / "agent-repeat" / f"{created:%Y%m%d-%H%M%S}" if repeat else None,
                     dcfg, labels=acfg.labels, words=acfg.words, phrases=phrases,
                     candidates=acfg.candidates, client_on=client is not None,
                     deadline_s=(deadline_s if deadline_s is not None
                                 else 2 * acfg.timeout_s + DEADLINE_MARGIN_S))


def agent_meta(root: Path | str, client_on: bool) -> dict:
    from rmprep.agent.config import load_agent_config

    acfg = load_agent_config(Path(root) / "config" / "agent.yaml")
    return {"model": acfg.model, "prompt_version": acfg.prompt_version,
            "candidates": acfg.candidates, "llm": client_on}


def _stats(xs: list[float]) -> dict[str, float] | None:
    if not xs:
        return None
    return {"n": len(xs), "mean": statistics.fmean(xs), "max": max(xs)}


def agent_metrics(runs, ab: Sequence[Any]) -> dict[str, Any]:
    """The agent part of the metrics: states, fallbacks with their reasons, changed
    picks, repeatability, the A/B judge, cost and time."""
    records = [(sr.scenario.id, sr.runs[0]) for sr in runs
               if sr.runs and sr.runs[0].agent is not None]
    decided = [(sid, r) for sid, r in records if r.agent.decision is not None]
    states = Counter(r.agent.decision.state for _, r in decided)
    fallbacks = Counter(r.agent.decision.fallback_reason for _, r in decided
                        if r.agent.decision.state == "fallback")
    changed = {}
    for sid, r in decided:
        d = r.agent.decision
        if d.state == "done":
            changed[sid] = sum(1 for p in d.picks if p.option_id not in d.engine_top3)

    pairs = [(top3(r.agent.decision), top3(r.agent.repeat)) for _, r in decided
             if top3(r.agent.decision) is not None and top3(r.agent.repeat) is not None]
    identical = sum(1 for a, b in pairs if a == b)
    repeat = {"runs": len(pairs), "identical": identical,
              "same_set": sum(1 for a, b in pairs if set(a) == set(b)),
              "share_identical": identical / len(pairs) if pairs else None}

    winners = Counter(g.winner for g in ab)
    graded = winners["agent"] + winners["engine"] + winners["equal"]
    ab_cost = sum(g.choice.cost_usd for g in ab)
    a_vs_e = winners["agent"] + winners["engine"]
    model = sum(r.agent.cost_usd + r.agent.repeat_cost_usd for _, r in records)
    research = sum(r.agent.research_cost_usd for _, r in records)
    return {
        "decisions": len(decided),
        "errors": {sid: r.agent.error for sid, r in records if r.agent.error},
        "states": dict(states),
        "fallbacks": dict(fallbacks),
        "changed": changed,
        "cached": sum(1 for _, r in records if r.agent.cached),
        "cache_same": {"runs": sum(1 for _, r in records if r.agent.cache_same is not None),
                       "same": sum(1 for _, r in records if r.agent.cache_same)},
        "repeat": repeat,
        "ab": {"graded": graded, "agent": winners["agent"], "engine": winners["engine"],
               "equal": winners["equal"], "same": winners["same"],
               "errors": sum(1 for g in ab if g.choice.error),
               "share_agent": winners["agent"] / a_vs_e if a_vs_e else None,
               "per_scenario": {g.scenario_id: g.winner or f"error: {g.choice.error}"
                                for g in ab},
               "cost_usd": ab_cost},
        "cost": {"model_usd": model, "research_usd": research, "ab_judge_usd": ab_cost,
                 "total_usd": model + research + ab_cost},
        "time": {"decision_s": _stats([r.agent.seconds for _, r in decided
                                       if not r.agent.cached]),
                 "repeat_s": _stats([r.agent.repeat_seconds for _, r in decided
                                     if r.agent.repeat is not None])},
    }
