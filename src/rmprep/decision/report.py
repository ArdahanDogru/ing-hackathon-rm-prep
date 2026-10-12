"""Plain-text report of a DecisionResult for tuning (`python -m rmprep decide`).

Grouped like the UI "Kısa liste" with the shared rule `rmprep.grouping`
(docs/decision.md 4.6): the deposit baseline, then each group as its head (with
score parts) and all its alternatives.
"""

from __future__ import annotations

from rmprep import grouping
from rmprep.contracts import DecisionResult, ScoredOption

REJECTED_SHOWN = 10


def _head(prefix: str, o: ScoredOption) -> str:
    opt = o.option
    kind = grouping.group_key(opt)
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

    if r.recommended:
        lines += ["", f"recommended: {', '.join(r.recommended)}"]

    funds = [o for o in r.options if o.option.kind != "deposit"]
    position = {o.option.option_id: i for i, o in enumerate(funds, start=1)}
    groups = grouping.groups(r.options)
    for g in groups:
        lines += ["", f"{g.key} ({1 + len(g.alternatives)})",
                  _head(f"{position[g.head.option.option_id]:>4}. ", g.head), _parts(g.head)]
        lines += [_head(f"      - {position[o.option.option_id]}. ", o) for o in g.alternatives]
    shown = sum(1 + len(g.alternatives) for g in groups)
    if len(funds) > shown:
        lines.append(f"\n{len(funds) - shown} more scored options outside the groups")

    if r.allocation:
        lines.append("\nallocation:")
        lines += [f"  {n}" for n in r.allocation_notes]
        for b in r.allocation:
            band = "-" if b.low is None else f"{b.low:g}-{b.high:g} %{'*' if b.inferred else ''}"
            best = b.option_id or "-"
            note = f" ({b.note})" if b.note else ""
            source = f"  ({b.source})" if b.low is not None else ""
            lines.append(f"  {b.asset_class} {band}{source}  best {best}{note}")

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
