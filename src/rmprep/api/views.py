"""View models of the API (docs/web-ui.md section 6; lead-owned).

Display arithmetic only: rank, stars, category average, match ring. Every
business value (returns, real return, risk, valör, access text, "why" lines)
comes from rmprep.decision.display."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rmprep.api.names import short_name
from rmprep.contracts import Backend, DecisionResult, ScoredOption, _to_json
from rmprep.decision.config import DecisionConfig
from rmprep.decision.display import DisplayFacts, access_text, display_facts
from rmprep.grouping import group_key, groups, top_heads
from rmprep.ui.i18n import LABELS, t

PERIODS = ("3m", "6m", "1y")
SHOWN_PER_CATEGORY = 3


def stars(position: int, n: int) -> int:
    """Morningstar-style split: top 10 % = 5, next 22.5 % = 4, middle 35 % = 3,
    next 22.5 % = 2, bottom 10 % = 1; share = (position - 1) / n."""
    share = (position - 1) / n
    for limit, s in ((0.10, 5), (0.325, 4), (0.675, 3), (0.90, 2)):
        if share < limit:
            return s
    return 1


def match(position: int, n: int) -> float:
    """Match ring 0-10: the place of the option among the ranked options of this client."""
    return 10.0 if n <= 1 else round(10 * (n - position) / (n - 1), 1)


def category_ranks(facts: Mapping[str, DisplayFacts], members: Sequence[str]) -> dict[str, dict]:
    """Rank by the 1-year return among the members that have one (ties: option id)."""
    with_1y = [(facts[m].returns["1y"].value, m) for m in members if "1y" in facts[m].returns]
    ordered = sorted(with_1y, key=lambda x: (-x[0], x[1]))
    n = len(ordered)
    out = {}
    for i, (value, oid) in enumerate(ordered, start=1):
        lower = sum(1 for v, _ in ordered if v < value)
        out[oid] = {"position": i, "of": n, "stars": stars(i, n),
                    "better_than_pct": round(100 * lower / n)}
    return out


def category_average(facts: Mapping[str, DisplayFacts], members: Sequence[str]) -> dict:
    """Mean per period over the members that have the value; None if none has it."""
    def mean(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    out = {p: mean(facts[m].returns[p].value if p in facts[m].returns else None for m in members)
           for p in PERIODS}
    out["real_1y"] = mean(facts[m].real_1y.value if facts[m].real_1y else None for m in members)
    return out


def _fact(f) -> dict | None:
    return None if f is None else {"value": f.value, "evidence_id": f.evidence_id}


# labels that the Streamlit dictionary (rmprep.ui.i18n) does not have
_MORE_LABELS = {"rule.short_history": {"TR": "Yeterli geçmiş yok", "EN": "Not enough history"}}


def _label(key: str, lang: str) -> str:
    if key in LABELS:
        return t(key, lang)
    return _MORE_LABELS.get(key, {}).get(lang, key.split(".", 1)[-1])


class ViewBuilder:
    """views(result) -> the RunView keys after result / test_run / persona_changes."""

    def __init__(self, backend: Backend, config: DecisionConfig, lang: str = "TR") -> None:
        self._backend, self._config, self._lang = backend, config, lang

    def __call__(self, r: DecisionResult) -> dict:
        ev = self._backend.evidence(r.snapshot_id, r.excluded_sources)
        facts = display_facts(r, ev, self._config)
        members: dict[str, list[str]] = {}
        for o in (*r.options, *r.rejected):          # the category: ranked and eliminated funds
            if o.option.kind == "fund":
                members.setdefault(group_key(o), []).append(o.option.option_id)
        ranks = {oid: rk for ids in members.values() for oid, rk in category_ranks(facts, ids).items()}
        averages = {key: category_average(facts, ids) for key, ids in members.items()}
        ranked = [o.option.option_id for o in r.options if o.option.kind != "deposit"]
        position = {oid: i for i, oid in enumerate(ranked, start=1)}

        def option_view(o: ScoredOption) -> dict:
            oid, opt = o.option.option_id, o.option
            f, key = facts[oid], group_key(o)
            rk = ranks.get(oid) if opt.kind == "fund" else None
            ev_ids = set(o.evidence_ids)
            valor = f.sell_valor_days
            issuer, short_label = short_name(opt.label)
            return {
                "option_id": oid, "label": opt.label, "kind": opt.kind,
                "issuer": issuer, "short_label": short_label,
                "category_key": key, "category_label": _label(f"kind.{key}", self._lang),
                "fx": opt.fx,
                "returns": {**{p: _fact(f.returns.get(p)) for p in PERIODS},
                            "real_1y": _fact(f.real_1y)},
                "category_avg": averages.get(key) if opt.kind == "fund" else None,
                "rank": {"position": rk["position"], "of": rk["of"]} if rk else None,
                "stars": rk["stars"] if rk else None,
                "better_than_pct": rk["better_than_pct"] if rk else None,
                "risk": None if f.risk is None else {"level": int(round(f.risk.value)),
                                                     "evidence_id": f.risk.evidence_id},
                "access": {"days": None if valor is None else int(round(valor.value)),
                           "lock_days": f.lock_days, "label": access_text(f, self._config),
                           "evidence_id": valor.evidence_id if valor else ""},
                "match": match(position[oid], len(ranked)) if oid in position else None,
                "why": [list(w) for w in f.why],
                "warnings": [_to_json(w) for w in r.warnings if oid in w.option_ids],
                # only notes about this option alone; source-wide notes stay in the panel
                "data_notes": [_to_json(n) for n in r.data_quality
                               if n.evidence_ids and set(n.evidence_ids) <= ev_ids],
                "selected": oid in r.rm_selected,
                "rm_note": r.rm_option_notes.get(oid, ""),
            }

        baseline = r.options[0] if r.options and r.options[0].option.kind == "deposit" else None
        top = top_heads(r.options, 3)
        cats = []
        for g in groups(r.options):
            shown = (g.head, *g.alternatives)[:SHOWN_PER_CATEGORY]
            one_year = facts[g.head.option.option_id].returns.get("1y")
            cats.append({"key": g.key, "label": _label(f"kind.{g.key}", self._lang),
                         "count": 1 + len(g.alternatives),
                         "best_return_1y": one_year.value if one_year else None,
                         "option_ids": [o.option.option_id for o in shown]})
        shown_ids = {o.option.option_id for o in top} | {i for c in cats for i in c["option_ids"]}
        if baseline is not None:
            shown_ids.add(baseline.option.option_id)
        by_id = {o.option.option_id: o for o in r.options}

        rules: dict[str, dict] = {}
        for x in r.rejected:
            reasons = [c.reason for c in x.failed]
            for rule_id in dict.fromkeys(c.rule_id for c in x.failed):   # a fund can fail several
                row = rules.setdefault(rule_id, {"rule_id": rule_id,
                                                 "label": _label(f"rule.{rule_id}", self._lang),
                                                 "count": 0, "options": []})
                row["count"] += 1
                row["options"].append({"label": x.option.label, "reasons": reasons})

        to_confirm = [{"text": c, "question_id": None, "choices": []} for c in r.to_confirm]
        to_confirm += [{"text": q.text, "question_id": q.question_id, "choices": list(q.choices)}
                       for q in r.questions if not q.blocking and q.answer is None]
        return {
            "baseline": option_view(baseline) if baseline is not None else None,
            "top": [o.option.option_id for o in top],
            "categories": cats,
            "options": {oid: option_view(by_id[oid]) for oid in sorted(shown_ids)},
            "talking_points": [_to_json(tp) for tp in r.talking_points],
            "to_confirm": to_confirm,
            "assumptions": list(r.assumptions),
            "data_notes": [_to_json(n) for n in r.data_quality],
            "client_warnings": [_to_json(w) for w in r.warnings if w.audience == "client"],
            "rm_warnings": [_to_json(w) for w in r.warnings if w.audience == "rm"],
            "rejected_by_rule": sorted(rules.values(), key=lambda x: (-x["count"], x["rule_id"])),
        }
