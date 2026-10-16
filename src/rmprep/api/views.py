"""View models of the API (docs/web-ui.md section 6; lead-owned).

Display arithmetic only: rank, stars, category average, match ring. Every
business value (returns, real return, risk, valör, access text, "why" lines)
comes from rmprep.decision.display."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from rmprep.api.names import short_name
from rmprep.contracts import Backend, DecisionResult, Flag, ScoredOption, _to_json
from rmprep.decision.config import DecisionConfig
from rmprep.decision.display import DisplayFacts, access_text, display_facts
from rmprep.decision.persona import read_persona
from rmprep.decision.text import normalize
from rmprep.grouping import group_key, groups, recommended
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


def priority_criteria(priorities: Sequence[str], config: DecisionConfig) -> dict[str, list[str]]:
    """Scoring criterion -> the client's priorities (as written) that boost it
    (config priorities, "boost:<criterion>"); the fund card tags its score rows
    with them (docs/web-ui.md W15)."""
    table = {normalize(k): str(v) for k, v in config.raw["priorities"].items()}
    out: dict[str, list[str]] = {}
    for written in priorities:
        kind, _, crit = table.get(normalize(written), "").partition(":")
        if kind == "boost":
            out.setdefault(crit, []).append(written)
    return out


def allocation_signal_tags(persona, config: DecisionConfig) -> list[str]:
    """The change signals of D27 that raise the "Portföy açığı" weight, for the tags
    of "Neden bu öneri?" (2026-10-15): a priority as written when the signal is in it,
    else the config phrase with "…" (found in the RM note, the goal or a constraint)."""
    from rmprep.decision.holdings import change_signals
    out = []
    for s in change_signals(persona, config):
        written = next((p for p in persona.oncelikler if normalize(s) in normalize(p)), None)
        out.append(written if written is not None else f"{s}…")
    return out


def _fact(f) -> dict | None:
    return None if f is None else {"value": f.value, "evidence_id": f.evidence_id}


# labels that the Streamlit dictionary (rmprep.ui.i18n) does not have
_MORE_LABELS = {"rule.short_history": {"TR": "Yeterli geçmiş yok", "EN": "Not enough history"},
                # D19 asset classes (D20 allocation rows)
                "class.nakit_benzeri": {"TR": "Nakit benzeri", "EN": "Cash-like"},
                "class.borclanma": {"TR": "Borçlanma", "EN": "Bonds / debt"},
                "class.hisse": {"TR": "Hisse", "EN": "Equity"},
                "class.altin_doviz": {"TR": "Altın / döviz", "EN": "Gold / FX"},
                "class.dengeli": {"TR": "Dengeli (çoklu varlık)", "EN": "Multi-asset"}}


def _label(key: str, lang: str) -> str:
    if key in LABELS:
        return t(key, lang)
    return _MORE_LABELS.get(key, {}).get(lang, key.split(".", 1)[-1])


def check_bank_context(raw: Mapping) -> dict:
    """W25: config/bank_context.yaml with strict keys; returns the options mapping
    (option id -> {own, banks, note})."""
    def keys(m, path, need):
        if not isinstance(m, Mapping) or set(m) != set(need):
            raise ValueError(f"bank_context {path}: keys must be {sorted(need)}")

    def cell(m, path):
        keys(m, path, ("label", "quantity", "entity"))
        keys(m["label"], f"{path}.label", ("TR", "EN"))
        if ", " not in m["entity"]:
            raise ValueError(f"bank_context {path}.entity: needs '<name>, <cell>'")

    keys(raw, "", ("version", "options"))
    for oid, o in raw["options"].items():
        keys(o, oid, ("own", "banks", "note"))
        cell(o["own"], f"{oid}.own")
        if not o["banks"]:
            raise ValueError(f"bank_context {oid}.banks: at least one bank")
        for i, b in enumerate(o["banks"]):
            cell(b, f"{oid}.banks[{i}]")
        keys(o["note"], f"{oid}.note", ("TR", "EN"))
    return dict(raw["options"])


def bank_context(spec: Mapping | None, idx, lang: str) -> dict | None:
    """W25: the own rate and the other banks' rates of one option, for the RM only
    (not in the score). A row without a usable value has value None (missing);
    diff_pp = the bank's rate - the own rate, in percentage points."""
    if spec is None:
        return None

    def row(c, own: bool) -> dict:
        d = idx.get(c["quantity"], c["entity"])
        return {"label": c["label"][lang], "cell": c["entity"].split(", ", 1)[1].replace(", ", " / "),
                "own": own, "value": None if d is None else d.value,
                "as_of": "" if d is None else d.as_of.isoformat(),
                "evidence_id": "" if d is None else d.id,
                "stale": d is not None and Flag.STALE in d.flags, "diff_pp": None}

    rows = [row(spec["own"], True), *(row(b, False) for b in spec["banks"])]
    base = rows[0]["value"]
    for r in rows[1:]:
        if base is not None and r["value"] is not None:
            r["diff_pp"] = round(r["value"] - base, 2)
    return {"rows": rows, "note": spec["note"][lang]}


class ViewBuilder:
    """views(result) -> the RunView keys after result / test_run / persona_changes."""

    def __init__(self, backend: Backend, config: DecisionConfig, lang: str = "TR",
                 market_series: Sequence[Mapping] | None = None,
                 bank_context: Mapping | None = None) -> None:
        """market_series: config/narrator.yaml market_note.series (W15); None = no note.
        bank_context: the checked options of config/bank_context.yaml (W25); None = none."""
        self._backend, self._config, self._lang = backend, config, lang
        self._market_series = list(market_series or ())
        self._bank_context = dict(bank_context or {})

    def _market_note(self, ev) -> list[dict]:
        """W15: the EVDS values of the market note (latest usable row of each
        series; a missing series is left out)."""
        from rmprep.decision.universe import EvidenceIndex
        idx, out = EvidenceIndex(ev), []
        for s in self._market_series:
            d = idx.get(s["quantity"], s["entity"])
            if d is None or d.value is None:
                continue
            label = s["label"][self._lang]
            change = s.get("last_change")       # the policy rate: date of the last TCMB change
            if change and abs(d.value - float(change["value"])) < 1e-9:
                when = date.fromisoformat(change["date"]).strftime("%d.%m.%Y")
                label = f"{label} ({change['label'][self._lang].format(date=when)})"
            out.append({"key": s["key"], "label": label, "value": d.value,
                        "unit": s["unit"], "as_of": d.as_of.isoformat(), "evidence_id": d.id})
        return out

    def _band(self, b, facts) -> dict:
        """D20 band with the note text of config allocation.note_texts."""
        from rmprep.decision.display import tr_percent
        texts = self._config.raw.get("allocation", {}).get("note_texts", {})
        note_text = texts.get(b.note, "") if b.note else ""
        if b.note == "negative_real" and b.option_id and facts[b.option_id].real_1y:
            note_text = note_text.format(figure=tr_percent(facts[b.option_id].real_1y.value))
        return {**_to_json(b), "note_text": note_text,
                "label": _label(f"class.{b.asset_class}", self._lang)}

    def _priority_criteria(self, r: DecisionResult) -> dict[str, list[str]]:
        """PR #1 boosts, plus the D27 change signals on "allocation_gap" when that
        criterion has a weight for this run."""
        out = priority_criteria(r.persona.oncelikler, self._config)
        if r.effective_weights.get("allocation_gap"):
            tags = allocation_signal_tags(r.persona, self._config)
            if tags:
                out["allocation_gap"] = tags
        return out

    def _holdings(self, r: DecisionResult) -> dict | None:
        """W18: the status of the current split and its sources (id = current_source);
        None when the run has no current split (config without D27)."""
        rows = [b for b in r.allocation if b.current is not None]
        if not rows:
            return None
        if r.holdings_input is not None:
            status = r.holdings_input.origin
        elif any(b.active for b in rows):
            status = "persona_text"
        else:
            status = "estimate"
        cfg = self._config.raw.get("holdings", {})
        nat = cfg.get("national", {})
        profiles = {p["label"]: p for p in cfg.get("profiles", [])}
        rules = {x["id"]: x for x in cfg.get("text_rules", [])}
        labels = self._config.raw.get("texts", {}).get("holdings", {}).get("source_labels", {})
        sources, seen = [], set()
        for b in rows:
            key = (b.current_source, b.current_ref)
            if key in seen:
                continue
            seen.add(key)
            if b.current_source == "national":
                sources.append({"id": "national", "ref": b.current_ref,
                                "label": f"{nat.get('label', '')}: {nat.get('source', '')}".strip(": "),
                                "url": nat.get("url", ""), "date": ""})
            elif b.current_source == "profile":
                p = profiles.get(b.current_ref, {})
                sources.append({"id": "profile", "ref": b.current_ref,
                                "label": f"{b.current_ref} ({p.get('source', '')}): {p.get('rule', '')}",
                                "url": "", "date": ""})
            elif b.current_source == "persona_text":
                rule = rules.get(b.current_ref, {})
                sources.append({"id": "persona_text", "ref": b.current_ref,
                                "label": f"{labels.get('persona_text', '')}: \"{rule.get('match', '')}\"",
                                "url": "", "date": ""})
            else:
                sources.append({"id": b.current_source, "ref": "",
                                "label": labels.get(b.current_source, b.current_source),
                                "url": "", "date": ""})
        return {"status": status, "sources": sources}

    def __call__(self, r: DecisionResult) -> dict:
        from rmprep.decision.universe import EvidenceIndex
        ev = self._backend.evidence(r.snapshot_id, r.excluded_sources)
        idx = EvidenceIndex(ev) if self._bank_context else None
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
                           "lock_days": f.lock_days, "label": access_text(f, self._config, self._lang),
                           "evidence_id": valor.evidence_id if valor else ""},
                "match": match(position[oid], len(ranked)) if oid in position else None,
                "why": [list(w) for w in f.why],
                "warnings": [_to_json(w) for w in r.warnings if oid in w.option_ids],
                # only notes about this option alone; source-wide notes stay in the panel
                "data_notes": [_to_json(n) for n in r.data_quality
                               if n.evidence_ids and set(n.evidence_ids) <= ev_ids],
                "selected": oid in r.rm_selected,
                "rm_note": r.rm_option_notes.get(oid, ""),
                # W25: other banks' rates, context for the RM only (not in the score)
                "bank_context": bank_context(self._bank_context.get(oid), idx, self._lang),
            }

        baseline = r.options[0] if r.options and r.options[0].option.kind == "deposit" else None
        top = recommended(r, 3)            # the engine's choice (v1.6), else the group heads
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
        # D20: the best option of each allocation class is shown in the "Dağılım" view
        shown_ids.update(b.option_id for b in r.allocation if b.option_id)
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
        answers = {q.question_id: q.answer for q in r.questions if q.answer is not None}
        try:
            levels = read_persona(r.persona, self._config, answers).levels
        except ValueError:
            levels = None
        ceiling = levels.ceiling if levels is not None else None   # None: a blocking question is open
        return {
            "risk_ceiling": ceiling,            # the SPK fund risk ceiling of the client (1..7)
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
            "allocation": [self._band(b, facts) for b in r.allocation],      # D20 (+ D27 current split)
            "holdings": self._holdings(r),                                   # W18
            "effective_weights": dict(r.effective_weights),                  # v1.10
            "allocation_notes": list(r.allocation_notes),
            "market_note": self._market_note(ev),                          # W15
            "priority_criteria": self._priority_criteria(r),                 # W16 (PR #1)
        }
