"""Plain-text report of a DecisionResult: the baseline and positions 1-10 with
their score parts (for tuning with `python -m rmprep decide`)."""

from __future__ import annotations

from rmprep.contracts import DecisionResult, ScoredOption

SHOWN = 10


def _option_lines(prefix: str, o: ScoredOption) -> list[str]:
    opt = o.option
    kind = opt.fund_kind or opt.kind
    fx = " FX" if opt.fx else ""
    head = (f"{prefix}{opt.label} ({opt.option_id}, {kind}{fx})  score {o.score:+.3f}  "
            f"confidence {o.confidence:.2f}  stability {o.stability:.2f}")
    parts = "  ".join(f"{k} {v:+.3f}" for k, v in o.score_parts.items())
    return [head, f"      {parts}"]


def render(result: DecisionResult) -> str:
    r = result
    lines = [f"run {r.run_id}  persona {r.persona_id}  snapshot {r.snapshot_id}  "
             f"config {r.config_hash}  state {r.state.value}"]
    if r.excluded_sources:
        lines.append(f"excluded: {', '.join(sorted(r.excluded_sources))}")

    options = list(r.options)
    if options and options[0].option.kind == "deposit":
        lines.append("")
        lines += _option_lines("baseline: ", options.pop(0))
    if options:
        lines.append("")
        for i, o in enumerate(options[:SHOWN], start=1):
            lines += _option_lines(f"{i:>3}. ", o)
        if len(options) > SHOWN:
            lines.append(f"     ... {len(options) - SHOWN} more")
    if r.rejected:
        lines.append(f"\nrejected: {len(r.rejected)} "
                     f"({', '.join(x.option.option_id for x in r.rejected)})")

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
