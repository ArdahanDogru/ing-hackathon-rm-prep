"""E13: replay stored A/B comparisons with a second judge (docs/eval.md).

The agent eval (E11) stores, per scenario, the agent decision and the data pack the
agent saw (`data/eval/agent/<scenario>/<run>.pack.json`), and the report keeps the
client profile and both top 3. From these the replay builds the A/B question again.
A question counts only if the first judge (Haiku) has a cached answer for exactly the
same text: that proves the second judge sees what the first judge saw (a later run can
overwrite a pack). No agent call, no research call; only the second judge costs.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from rmprep.contracts import TR_TZ, Persona
from rmprep.eval.judge import (
    AbChoice, AbGrade, AbJudge, CachedAbJudge, ab_compare, ab_user_text, _ab_sets,
)


class CacheOnly:
    """The first judge in a replay: its cached answers only, never a model call."""

    def __init__(self, model: str) -> None:
        self.model = model

    def choose(self, user: str) -> AbChoice:
        return AbChoice(model=self.model, error="not cached")


@dataclass(frozen=True)
class _Stored:
    """The two fields of a DecisionResult that the A/B text reads."""
    persona: Persona
    run_id: str
    options: tuple = ()


@dataclass(frozen=True)
class _Decision:
    """The fields of an AgentDecision that ab_compare reads."""
    picks: tuple
    engine_top3: tuple


@dataclass(frozen=True)
class _Pick:
    option_id: str


@dataclass
class ReplayRow:
    report: str
    scenario_id: str
    run_id: str
    first: AbGrade | None = None        # the first judge's cached answer
    second: AbGrade | None = None
    skipped: str = ""                   # why the question was not asked

    def to_dict(self) -> dict:
        return {"report": self.report, "scenario_id": self.scenario_id, "run_id": self.run_id,
                "skipped": self.skipped,
                "first": None if self.first is None else self.first.to_dict(),
                "second": None if self.second is None else self.second.to_dict()}


@dataclass
class Replay:
    first_model: str
    second_model: str
    rows: list[ReplayRow] = field(default_factory=list)

    def asked(self) -> list[ReplayRow]:
        return [r for r in self.rows if not r.skipped]

    def tally(self, which: str) -> dict[str, int]:
        c = Counter((getattr(r, which).winner or "error") for r in self.asked())
        return {k: c.get(k, 0) for k in ("agent", "engine", "equal", "error")}

    def agreement(self) -> tuple[int, int]:
        both = [r for r in self.asked() if r.first.winner and r.second.winner]
        return sum(r.first.winner == r.second.winner for r in both), len(both)

    def cost_usd(self) -> float:
        return sum(r.second.choice.cost_usd for r in self.asked())


def _rows_of(report_dir: Path, agent_dir: Path):
    """(scenario id, run id, stored result, decision, pack or None) per scenario run
    with a done agent decision whose top 3 differs from the engine's."""
    data = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    for s in data["scenarios"]:
        run = s["runs"][0] if s.get("runs") else {}
        a = run.get("agent")
        if not a or a.get("state") != "done":
            continue
        agent, engine = tuple(a["top3"]), tuple(a["engine_top3"])
        if agent == engine:
            continue
        f = agent_dir / s["id"] / f"{run['run_id']}.pack.json"
        pack = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
        stored = _Stored(persona=Persona.from_dict(run["persona"]), run_id=run["run_id"])
        yield s["id"], run["run_id"], stored, _Decision(tuple(_Pick(o) for o in agent), engine), pack


def replay_ab(root: Path | str, reports: list[str], first: CachedAbJudge, second: AbJudge,
              *, report_dir: str = "data/eval") -> Replay:
    """Ask `second` the stored A/B questions of `reports` (report folder names under
    report_dir) that `first` answered for exactly the same text; each text once."""
    root = Path(root)
    base = root / report_dir
    out = Replay(first_model=first.model, second_model=second.model)
    seen: set[str] = set()
    for name in reports:
        for sid, rid, stored, decision, pack in _rows_of(base / name, base / "agent"):
            row = ReplayRow(name, sid, rid)
            out.rows.append(row)
            if pack is None:
                row.skipped = "no stored pack"
                continue
            _, a, b = _ab_sets(rid, tuple(p.option_id for p in decision.picks), decision.engine_top3)
            user = ab_user_text(stored, pack, a, b)
            if first.cached(user) is None:
                row.skipped = "input differs from the first judge's (pack overwritten by a later run)"
                continue
            if user in seen:
                row.skipped = "same question as an earlier row"
                continue
            seen.add(user)
            row.first = ab_compare(sid, stored, pack, decision, first)
            row.second = ab_compare(sid, stored, pack, decision, second)
    return out


def render(r: Replay, reports: list[str], created: datetime) -> str:
    agree, n = r.agreement()
    t1, t2 = r.tally("first"), r.tally("second")
    lines = [
        "# A/B judge replay (E13)", "",
        f"- Time: {created.isoformat()}",
        f"- Reports: {', '.join(f'`{x}`' for x in reports)}",
        f"- First judge: {r.first_model} (cached answers) · second judge: {r.second_model}",
        f"- Questions asked: {len(r.asked())} of {len(r.rows)} stored comparisons",
        f"- Second judge cost: ${r.cost_usd():.4f}", "",
        "| Judge | agent | engine | equal | error |", "|---|---|---|---|---|",
        f"| {r.first_model} | {t1['agent']} | {t1['engine']} | {t1['equal']} | {t1['error']} |",
        f"| {r.second_model} | {t2['agent']} | {t2['engine']} | {t2['equal']} | {t2['error']} |", "",
        f"Agreement: the two judges pick the same winner in {agree} of {n} questions.", "",
        "| Report | Scenario | Run | First | Second | Second judge's reason |",
        "|---|---|---|---|---|---|",
    ]
    for x in r.rows:
        if x.skipped:
            lines.append(f"| `{x.report}` | {x.scenario_id} | {x.run_id} | — | — | skipped: {x.skipped} |")
            continue
        reason = (x.second.choice.error or x.second.choice.reason).replace("|", "/").replace("\n", " ")
        lines.append(f"| `{x.report}` | {x.scenario_id} | {x.run_id} | {x.first.winner or 'error'} "
                     f"| {x.second.winner or 'error'} | {reason} |")
    return "\n".join(lines) + "\n"


def write_replay(root: Path | str, r: Replay, reports: list[str], *,
                 report_dir: str = "data/eval", now: datetime | None = None) -> Path:
    created = now or datetime.now(TR_TZ)
    out = Path(root) / report_dir / f"{created:%Y%m%d-%H%M%S}-ab-replay"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(render(r, reports, created), encoding="utf-8", newline="\n")
    agree, n = r.agreement()
    data = {"created_at": created.isoformat(), "reports": reports, "first_model": r.first_model,
            "second_model": r.second_model, "tally_first": r.tally("first"),
            "tally_second": r.tally("second"), "agreement": [agree, n], "cost_usd": r.cost_usd(),
            "rows": [x.to_dict() for x in r.rows]}
    (out / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8", newline="\n")
    return out
