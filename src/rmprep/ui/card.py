"""Summary card ("Görüşme kartı") of an approved run (docs/ui.md section 3), as
Markdown and as stand-alone HTML (print to PDF in the browser). Both are built
from one list of sections, so they always hold the same content. The RM-approved
meeting text (NarrativeDraft.rm_text, contract v1.2) of the card language is
added at the end."""

from __future__ import annotations

import dataclasses
import html
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from rmprep.contracts import (
    AgentDecision,
    DecisionResult,
    EvidenceSet,
    NarrativeDraft,
    NarrativeStatus,
    RmStatus,
)
from rmprep.api.names import with_code
from rmprep.ui import glossary, views
from rmprep.ui.i18n import t


@dataclass(frozen=True)
class _Item:
    text: str
    sub: tuple[str, ...] = ()
    strong: bool = False


@dataclass(frozen=True)
class _Section:
    heading: str
    items: list[_Item] = field(default_factory=list)


def _sections(r: DecisionResult, ev: EvidenceSet, lang: str,
              persona_changes: Sequence[Mapping] = (),
              resolutions: Mapping | None = None) -> list[_Section]:
    if r.rm_status != RmStatus.APPROVED:
        raise ValueError("only an approved run has a card")
    p = r.persona
    client = _Section(t("card_client", lang))
    if persona_changes:              # W30: an approved edited profile says so first
        client.items.append(_Item(f"{t('card_edited', lang)}: " + "; ".join(
            f"{t('f_' + c['field'], lang)}: {_value(c['original'])} → {_value(c['edited'])}"
            for c in persona_changes), strong=True))
    res = resolutions or {}
    done = [f"{x['text']} → {t('card_confirmed', lang)}: {x['note']}" for x in res.get("resolutions", ())]
    if res.get("ai_check") not in (None, "done", "off"):
        done.append(t("card_ai_not_done", lang).format(state=res["ai_check"]))
    if done:                         # W44: the RM's confirmations of the profile conflicts
        client.items.append(_Item(t("card_resolved", lang), tuple(done), strong=True))
    for f in dataclasses.fields(p):
        v = getattr(p, f.name)
        if f.name in views.LIST_FIELDS:
            v = ", ".join(v) if v else "—"
        if v != "":
            client.items.append(_Item(f"{t('f_' + f.name, lang)}: {v}"))

    warned = views.warned(r)
    options = _Section(t("card_options", lang))
    for pos, o in enumerate(r.options):
        oid = o.option.option_id
        if oid not in r.rm_selected:
            continue
        head = [with_code(oid, o.option.label), views.kind_label(o, lang)] + (["FX"] if o.option.fx else [])
        sub = [f"{t('score', lang)} {points(o.score)} · {t('confidence', lang)} %{round(o.confidence * 100)} · "
               f"{t('stability', lang)} %{round(o.stability * 100)}"]
        sub += [f"{b['part']} ({points(b['value'], signed=True)}): {b['reason']}" for b in views.main_parts(o, lang)]
        sub += [f"⚠ {w.code}: {w.message}" for w in warned.get(oid, [])]
        if r.rm_option_notes.get(oid):
            sub.append(f"{t('card_rm_note', lang)}: {r.rm_option_notes[oid]}")
        options.items.append(_Item(" · ".join(head), tuple(sub), strong=True))

    out = [client, options]
    general = [w for w in r.warnings if not w.option_ids]
    if general:
        out.append(_Section(t("card_general_warnings", lang),
                            [_Item(f"⚠ {w.code}: {w.message}") for w in general]))
    if r.data_quality:
        out.append(_Section(t("data_quality", lang), [_Item(n.message) for n in r.data_quality]))
    if r.assumptions:
        out.append(_Section(t("assumptions", lang), [_Item(a) for a in r.assumptions]))
    out.append(_Section(t("card_sources", lang), [_Item(c) for c in views.citations(r, ev, lang)]))
    if r.rm_note:
        out.append(_Section(t("card_rm_note", lang), [_Item(r.rm_note)]))
    return out


def _value(v) -> str:
    """W30: a persona value in the changes line (a list joined)."""
    return ", ".join(v) if isinstance(v, (list, tuple)) else str(v)


def _title(r: DecisionResult, lang: str) -> str:
    return f"{t('card_title', lang)}: {r.persona_id} · {r.persona.profil}"


def _meta(r: DecisionResult, lang: str) -> str:
    return t("card_meta", lang, run_id=r.run_id, snapshot=r.snapshot_id,
             created=r.created_at.strftime("%Y-%m-%d %H:%M"))


def _approvals(r: DecisionResult, narrative: NarrativeDraft | None, lang: str) -> list[str]:
    """v1.7: the decision record of the card: when the RM approved the run and the text."""
    out = []
    if r.rm_decided_at is not None:
        out.append(t("card_rm_decided", lang, at=r.rm_decided_at.strftime("%Y-%m-%d %H:%M")))
    if (narrative is not None and narrative.approved_at is not None
            and _narrative_text(r, narrative, lang) is not None):   # the text of this card
        out.append(t("card_text_approved", lang, at=narrative.approved_at.strftime("%Y-%m-%d %H:%M"),
                     model=narrative.model or "şablon", checks=len(narrative.checks)))
    return ["", *out] if out else []


def _narrative_text(r: DecisionResult, narrative: NarrativeDraft | None, lang: str) -> str | None:
    """The RM-approved meeting text of this run and language, else None."""
    if (narrative is None or narrative.status != NarrativeStatus.APPROVED
            or narrative.lang != lang or narrative.run_id != r.run_id):
        return None
    return narrative.rm_text


def _demoted(markdown: str) -> str:
    """Headings two levels down, so the text sits under the card's "##" heading."""
    return "\n".join("##" + x if x.startswith("#") else x for x in markdown.splitlines())


def _terms(body: str, glossary_terms: tuple[glossary.Term, ...],
           lang: str) -> list[glossary.Found]:
    """The glossary terms of the card text (docs/ui.md U11), first appearance first."""
    return glossary.find_terms(body, glossary_terms, lang)


def points(x: float, signed: bool = False) -> str:
    """A score or a score part x100 without decimals (the user, 2026-10-15): 0.854 -> "85",
    +0.2449 -> "+24", -0.105 -> "−11" (Turkish minus); half away from zero; 0 has no sign."""
    n = int(math.floor(abs(x) * 100 + 0.5))
    if n == 0:
        return "0"
    if x < 0:
        return f"−{n}"
    return f"+{n}" if signed else str(n)


def _agent_lines(r: DecisionResult, agent: AgentDecision | None, lang: str) -> list[str]:
    """v1.11: the section "Ajan kararı" (Markdown lines; empty without a done or fallback decision)."""
    if agent is None or agent.state not in ("done", "fallback") or agent.run_id != r.run_id:
        return []
    names = {o.option.option_id: with_code(o.option.option_id, o.option.label) for o in r.options}
    label = lambda oid: names.get(oid, oid)                       # noqa: E731
    reason = lambda x: " ".join([x.text, *x.labels])              # noqa: E731
    out = ["", f"## {t('ag_title', lang)}", "",
           f"- {t('ag_engine', lang, labels=', '.join(label(i) for i in agent.engine_top3))}"]
    if agent.state == "fallback":
        out.append(f"- {t('ag_fallback', lang, reason=agent.fallback_reason)}")
    else:
        out.append(f"- {t('ag_agent', lang)}")
        for n, p in enumerate(agent.picks, start=1):
            out.append(f"  - {n}. **{label(p.option_id)}**")
            out += [f"    - {reason(x)}" for x in p.reasons]
        out += [f"- {t('ag_dropped', lang, label=label(p.option_id), why=' '.join(reason(x) for x in p.reasons))}"
                for p in agent.dropped]
        if agent.summary:
            out.append(f"- {agent.summary}")
    if r.rm_selected:
        out.append(f"- {t('ag_rm', lang, labels=', '.join(label(i) for i in r.rm_selected))}")
    out.append(f"- {t('ag_meta', lang, model=agent.model, prompt=agent.prompt_version, cost=agent.cost_usd)}")
    return out


def render_markdown(r: DecisionResult, evidence: EvidenceSet, lang: str = "TR",
                    narrative: NarrativeDraft | None = None,
                    glossary_terms: tuple[glossary.Term, ...] = (),
                    current_text: str | None = None,
                    agent: AgentDecision | None = None,
                    persona_changes: Sequence[Mapping] = (),
                    resolutions: Mapping | None = None) -> str:
    """current_text (W19, 2026-10-15): the meeting text as it is now, with the RM's
    edits, used when there is no approved text. agent (v1.11): the agent decision.
    persona_changes (W30): the fields of an edited profile ({field, original, edited})."""
    body = _markdown_body(r, evidence, lang, narrative, current_text, agent, persona_changes, resolutions)
    found = _terms(body, glossary_terms, lang)
    if not found:
        return body
    lines = ["", f"## {t('terms', lang)}", ""]
    lines += [f"- **{f.form}**: {f.explanation}" for f in found]
    return body + "\n".join(lines) + "\n"


def _markdown_body(r: DecisionResult, evidence: EvidenceSet, lang: str,
                   narrative: NarrativeDraft | None, current_text: str | None = None,
                   agent: AgentDecision | None = None,
                   persona_changes: Sequence[Mapping] = (),
                   resolutions: Mapping | None = None) -> str:
    lines = [f"# {_title(r, lang)}", "", _meta(r, lang)]
    lines += _approvals(r, narrative, lang)
    for s in _sections(r, evidence, lang, persona_changes, resolutions):
        lines += ["", f"## {s.heading}", ""]
        for it in s.items:
            lines.append(f"- **{it.text}**" if it.strong else f"- {it.text}")
            lines += [f"  - {x}" for x in it.sub]
    lines += _agent_lines(r, agent, lang)
    text = _narrative_text(r, narrative, lang) or current_text
    if text is not None:
        lines += ["", f"## {t('nar_title', lang)}", "", _demoted(text.strip())]
    return "\n".join(lines) + "\n"


_CSS = """body{font-family:system-ui,sans-serif;max-width:48rem;margin:2rem auto;color:#1a1a19;
line-height:1.45}h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:1.5rem;
border-bottom:1px solid #d6d5d0}.meta{color:#5c5b56}li{margin:.15rem 0}
.narrative{white-space:pre-wrap;font-family:inherit;margin:0}
@media print{body{margin:0}}"""


def render_html(r: DecisionResult, evidence: EvidenceSet, lang: str = "TR",
                narrative: NarrativeDraft | None = None,
                glossary_terms: tuple[glossary.Term, ...] = (),
                current_text: str | None = None,
                agent: AgentDecision | None = None,
                persona_changes: Sequence[Mapping] = (),
                resolutions: Mapping | None = None) -> str:
    e = html.escape
    parts = ["<!DOCTYPE html>", f'<html lang="{lang.lower()}"><head><meta charset="utf-8">',
             f"<title>{e(_title(r, lang))}</title><style>{_CSS}</style></head><body>",
             f"<h1>{e(_title(r, lang))}</h1>", f'<p class="meta">{e(_meta(r, lang))}</p>']
    for s in _sections(r, evidence, lang, persona_changes, resolutions):
        parts.append(f"<h2>{e(s.heading)}</h2><ul>")
        for it in s.items:
            text = f"<strong>{e(it.text)}</strong>" if it.strong else e(it.text)
            sub = "".join(f"<li>{e(x)}</li>" for x in it.sub)
            parts.append(f"<li>{text}{f'<ul>{sub}</ul>' if sub else ''}</li>")
        parts.append("</ul>")
    ag = _agent_lines(r, agent, lang)
    if ag:          # the same lines as the Markdown card, as a plain list
        parts.append(f"<h2>{e(t('ag_title', lang))}</h2><ul>")
        parts += [f"<li>{e(x.strip().lstrip('- ').replace('**', ''))}</li>" for x in ag[3:]]
        parts.append("</ul>")
    text = _narrative_text(r, narrative, lang) or current_text
    if text is not None:   # the RM's Markdown as written (no converter: no new dependency)
        parts.append(f'<h2>{e(t("nar_title", lang))}</h2><pre class="narrative">{e(text)}</pre>')
    found = _terms(_markdown_body(r, evidence, lang, narrative, current_text, agent), glossary_terms, lang)
    if found:      # the same terms as the Markdown card
        items = "".join(f"<li><strong>{e(f.form)}</strong>: {e(f.explanation)}</li>"
                        for f in found)
        parts.append(f"<h2>{e(t('terms', lang))}</h2><ul>{items}</ul>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"
