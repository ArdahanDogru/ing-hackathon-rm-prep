"""Plain-text report of a DecisionResult for tuning (`python -m rmprep decide`).

Grouped like the UI "Kısa liste" (docs/ui.md section 1): the deposit baseline,
then at most 5 kind groups (fund_kind; the time deposit is its own kind) from
the first 20 ranked options of the display order,
ordered by the score of their best option; each group is its best option (with
score parts) and its alternatives in score order.
"""

from __future__ import annotations

from rmprep.contracts import DecisionResult, ScoredOption
from rmprep.decision.universe import group_kind

POOL = 20
MAX_GROUPS = 5
REJECTED_SHOWN = 10


def _by_score(o: ScoredOption) -> tuple[float, str]:
    return (-o.score, o.option.option_id)


def fund_groups(result: DecisionResult) -> list[tuple[str, list[ScoredOption]]]:
    """[(group_kind, options best first)], at most MAX_GROUPS, from the first POOL
    ranked options (funds and the time deposit)."""
    pool = [o for o in result.options if o.option.kind != "deposit"][:POOL]
    groups: dict[str, list[ScoredOption]] = {}
    for o in pool:
        groups.setdefault(group_kind(o.option), []).append(o)
    ordered = [(kind, sorted(members, key=_by_score)) for kind, members in groups.items()]
    ordered.sort(key=lambda g: _by_score(g[1][0]))
    return ordered[:MAX_GROUPS]


def _head(prefix: str, o: ScoredOption) -> str:
    opt = o.option
    kind = group_kind(opt)
    fx = " FX" if opt.fx else ""
    return (f"{prefix}{opt.label} ({opt.option_id}, {kind}{fx})  score {o.score:+.3f}  "
            f"confidence {o.confidence:.2f}  stability {o.stability:.2f}")


def _parts(o: ScoredOption) -> str:
    return "      " + "  ".join(f"{k} {v:+.3f}" for k, v in o.score_parts.items())


def render(result: DecisionResult) -> str:
    r = result
    lines = [f"run {r.run_id}  persona {r.persona_id}  snapshot {r.snapshot_id}  "
             f"config {r.config_hash}  state {r.state.value}"]
    if r.excluded_sources:
        lines.append(f"excluded: {', '.join(sorted(r.excluded_sources))}")

    if r.options and r.options[0].option.kind == "deposit":
        lines += ["", _head("baseline: ", r.options[0]), _parts(r.options[0])]

    funds = [o for o in r.options if o.option.kind != "deposit"]
    position = {o.option.option_id: i for i, o in enumerate(funds, start=1)}
    groups = fund_groups(r)
    for kind, members in groups:
        head, *alternatives = members
        lines += ["", f"{kind} ({len(members)})",
                  _head(f"{position[head.option.option_id]:>4}. ", head), _parts(head)]
        lines += [_head(f"      - {position[o.option.option_id]}. ", o) for o in alternatives]
    shown = sum(len(m) for _, m in groups)
    if len(funds) > shown:
        lines.append(f"\n{len(funds) - shown} more scored options outside the groups")

    if r.rejected:
        ids = [x.option.option_id for x in r.rejected]
        more = ", ..." if len(ids) > REJECTED_SHOWN else ""
        lines.append(f"\nrejected: {len(ids)} ({', '.join(ids[:REJECTED_SHOWN])}{more})")

    if r.questions:
        lines.append("\nquestions:")
        for q in r.questions:
            state = f"answer: {q.answer}" if q.answer is not None else "open"
            block = "blocking" if q.blocking else "non-blocking"
            lines.append(f"  {q.question_id} [{block}, {state}] {q.text} ({q.reason})")
    if r.warnings:
        lines.append("\nwarnings:")
        for w in r.warnings:
            on = f" [{', '.join(w.option_ids)}]" if w.option_ids else ""
            lines.append(f"  {w.code}: {w.message}{on}")
    if r.data_quality:
        lines.append("\ndata quality:")
        lines += [f"  {n.message}" for n in r.data_quality]
    if r.assumptions:
        lines.append("\nassumptions:")
        lines += [f"  {a}" for a in r.assumptions]
    return "\n".join(lines) + "\n"
