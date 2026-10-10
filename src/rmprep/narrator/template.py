"""Template text: the meeting text built from the facts pack only (no LLM).
It is the fallback when the LLM text fails the validator or the budget is
used up, so it must always pass the validator itself (docs/narrator.md).

Engine texts (reasons, warnings, questions, assumptions) and persona values are
Turkish only; the English template quotes them as they are."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime

from rmprep.contracts import (
    NARRATIVE_LANGS,
    NARRATIVE_SECTIONS,
    NarrativeDraft,
    NarrativeSection,
    NarrativeSentence,
)
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import INTERNAL_PARTS, Facts, KeyNumber, OptionFacts

MAIN_REASONS = 3        # largest score parts quoted per selected option

KIND_NAMES = {
    "deposit": {"TR": "Mevduat", "EN": "Deposit"},
    "time_deposit": {"TR": "Vadeli mevduat", "EN": "Time deposit"},
    "money_market": {"TR": "Para Piyasası", "EN": "Money market"},
    "debt": {"TR": "Borçlanma Araçları", "EN": "Debt instruments"},
    "participation": {"TR": "Katılım", "EN": "Participation"},
    "variable": {"TR": "Değişken", "EN": "Variable"},
    "mixed": {"TR": "Karma", "EN": "Mixed"},
    "equity": {"TR": "Hisse Senedi", "EN": "Equity"},
    "precious_metals": {"TR": "Kıymetli Madenler", "EN": "Precious metals"},
    "fund_of_funds": {"TR": "Fon Sepeti", "EN": "Fund of funds"},
}

QUANTITY_NAMES = {
    "fund_return_ytd": {"TR": "yılbaşından bu yana getiri", "EN": "year-to-date return"},
    "fund_risk_level": {"TR": "risk düzeyi", "EN": "risk level"},
    "deposit_rate": {"TR": "yıllık faiz oranı", "EN": "annual interest rate"},
    "fund_price": {"TR": "pay fiyatı", "EN": "unit price"},
    "fund_total_value": {"TR": "fon büyüklüğü", "EN": "fund size"},
    "fund_investor_count": {"TR": "yatırımcı sayısı", "EN": "number of investors"},
}
_PERIOD = re.compile(r"fund_return_(\d+)([my])$")
_PERIOD_WORDS = {"m": {"TR": "aylık", "EN": "month"}, "y": {"TR": "yıllık", "EN": "year"}}

SOURCE_NAMES = {"tefas": "TEFAS", "tefas_web": "TEFAS", "tefas_detail": "TEFAS",
                "evds": "TCMB EVDS", "manual": {"TR": "manuel giriş", "EN": "manual entry"}}

# N7: the client need a score part speaks to (persona field), and the part's name
PART_NEEDS = {"return": "yatirim_amaci", "low_risk": "risk_profili",
              "liquidity": "likidite_ihtiyaci", "income": "gelir_nakit_akisi_ihtiyaci",
              "principal": "anapara_koruma_tercihi", "simplicity": "risk_profili",
              "quality": "yatirim_ufku"}
PART_NAMES = {
    "return": {"TR": "getiri", "EN": "return"},
    "low_risk": {"TR": "düşük risk", "EN": "low risk"},
    "liquidity": {"TR": "likidite", "EN": "liquidity"},
    "income": {"TR": "düzenli gelir", "EN": "regular income"},
    "principal": {"TR": "anapara koruma", "EN": "capital protection"},
    "simplicity": {"TR": "sadelik", "EN": "simplicity"},
    "quality": {"TR": "fon büyüklüğü ve yatırımcı tabanı", "EN": "fund size and investor base"},
}
NEED_NAMES = {
    "yatirim_amaci": {"TR": "yatırım amacı", "EN": "investment goal"},
    "risk_profili": {"TR": "risk profili", "EN": "risk profile"},
    "likidite_ihtiyaci": {"TR": "likidite ihtiyacı", "EN": "liquidity need"},
    "gelir_nakit_akisi_ihtiyaci": {"TR": "gelir / nakit akışı ihtiyacı",
                                   "EN": "income / cash-flow need"},
    "anapara_koruma_tercihi": {"TR": "anapara koruma tercihi",
                               "EN": "capital protection preference"},
    "yatirim_ufku": {"TR": "yatırım ufku", "EN": "investment horizon"},
}

HEADINGS = {
    "ozet": {"TR": "Özet", "EN": "Summary"},
    "oneriler": {"TR": "Öneriler", "EN": "Options to discuss"},
    "alternatifler": {"TR": "Alternatifler", "EN": "Alternatives"},
    "dikkat": {"TR": "Dikkat", "EN": "Points to watch"},
    "sorular": {"TR": "Sorular", "EN": "Questions"},
    "teklif_metni": {"TR": "Teklif metni", "EN": "Proposal script"},
    "varsayimlar": {"TR": "Varsayımlar", "EN": "Assumptions"},
}

TEXTS = {
    "TR": {
        "title": "Görüşme metni",
        "client": "{profil} ({yas} yaşında); durum: {durum}.",
        "goal": "Yatırım amacı: {amac} (ufuk: {ufuk}, risk profili: {risk}).",
        "priorities": "Öncelikler: {items}.",
        "client_note": "Müşteri notu: {note}",
        "rm_note": "RM'in görüşme notu: {note}",
        "meeting": "Görüşmede RM'in seçtiği {n} seçenek konuşulacak.",
        "meeting_baseline": "Görüşmede RM'in seçtiği {n} seçenek konuşulacak; "
                            "karşılaştırma ölçütü {baseline}.",
        "option": "{label} ({kind}{fx}): {reasons}.",
        "option_bare": "{label} ({kind}{fx}).",
        "link": "{label}, müşterinin {need} (\"{value}\") açısından {part} ile öne çıkıyor.",
        "fx": ", döviz içerir",
        "numbers": "Ana rakamlar: {items}.",
        "number": "{name} {value} ({source}, {as_of})",
        "watch": "İzlenecek nokta: {message}",
        "option_note": "RM notu: {note}",
        "group": "{kind} grubunda diğer seçenekler: {labels}.",
        "group_empty": "{kind} grubunda seçilenler dışında seçenek yok.",
        "no_groups": "Seçilen seçenekler için aynı türde başka seçenek yok.",
        "baseline": "Karşılaştırma ölçütü: {label}.",
        "baseline_numbers": "Karşılaştırma ölçütü: {label}; {items}.",
        "dq_pointer": "Veri kalitesi notları için \"Olası sorunlar\" bölümüne bakın.",
        "past": "Fon getirileri geçmiş getirilerdir; gelecekteki getiriyi göstermez ve "
                "değerleri dalgalanabilir.",
        "constraint": "Kısıtı müşteriyle teyit edin: \"{item}\".",
        "ask_priorities": "Öncelikler hâlâ bu sırada mı: {items}?",
        "pitch_goal": "Bugün \"{durum}\" durumunuzu ve \"{amac}\" hedefinizi dikkate "
                      "alarak birkaç seçeneği birlikte değerlendirmek istiyorum.",
        "pitch_baseline": "Karşılaştırma için {baseline} ile başlayalım.",
        "pitch_options": "Sizin için öne çıkan seçenekler: {labels}.",
        "pitch_past": "Konuştuğumuz getiriler geçmiş getirilerdir.",
        "pitch_close": "Kararı sizin önceliklerinize göre birlikte verelim; "
                       "sorularınızı memnuniyetle yanıtlarım.",
        "no_assumptions": "Varsayım yok.",
    },
    "EN": {
        "title": "Meeting text",
        "client": "Client: {profil}, age {yas}; situation: {durum}.",
        "goal": "Investment goal: {amac} (horizon: {ufuk}, risk profile: {risk}).",
        "priorities": "Priorities: {items}.",
        "client_note": "Client note: {note}",
        "rm_note": "The RM's meeting note: {note}",
        "meeting": "The meeting will discuss the {n} options that the RM selected.",
        "meeting_baseline": "The meeting will discuss the {n} options that the RM selected; "
                            "the baseline for comparison is {baseline}.",
        "option": "{label} ({kind}{fx}): {reasons}.",
        "option_bare": "{label} ({kind}{fx}).",
        "link": "{label} stands out on {part} for the client's {need} (\"{value}\").",
        "fx": ", FX exposure",
        "numbers": "Key numbers: {items}.",
        "number": "{name} {value} ({source}, {as_of})",
        "watch": "Point to watch: {message}",
        "option_note": "RM note: {note}",
        "group": "Other options in the {kind} group: {labels}.",
        "group_empty": "The {kind} group has no options other than the selected ones.",
        "no_groups": "The selected options have no other options of the same kind.",
        "baseline": "Baseline for comparison: {label}.",
        "baseline_numbers": "Baseline for comparison: {label}; {items}.",
        "dq_pointer": "For the data-quality notes, see the \"Possible issues\" pane.",
        "past": "Fund returns are past returns; they do not show future returns, and "
                "values can go up and down.",
        "constraint": "Confirm the constraint with the client: \"{item}\".",
        "ask_priorities": "Are the priorities still in this order: {items}?",
        "pitch_goal": "Today I would like to look at a few options with you, based on your "
                      "situation (\"{durum}\") and your goal (\"{amac}\").",
        "pitch_baseline": "For comparison, let us start with {baseline}.",
        "pitch_options": "The options that stand out for you: {labels}.",
        "pitch_past": "The returns we talk about are past returns.",
        "pitch_close": "We will decide together, based on your priorities; I am glad to "
                       "answer your questions.",
        "no_assumptions": "No assumptions.",
    },
}


# snake_case field, flag, source or quantity names, and score keys such as
# penalty:principal: internal names that the text must not show (N7)
INTERNAL_NAME = re.compile(r"(?<![\w:])(?:[a-z][a-z0-9]*(?:_[a-z0-9]+)+|penalty:[a-z_]+)(?![\w])")


def is_quotable(reason: tuple[str, float, str]) -> bool:
    """A reason text the text may quote: not an internal part, no internal name."""
    part, _, text = reason
    return part not in INTERNAL_PARTS and not INTERNAL_NAME.search(text)


def tr_lower(text: str) -> str:
    """Lower case with the Turkish dotted and dotless i (İ -> i, I -> ı)."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def fmt_number(value: float, unit: str, lang: str) -> str:
    """A number as the text writes it: TR 1.054,64 / EN 1,054.64; pct with a % sign."""
    if unit == "level" and float(value).is_integer():
        s = str(int(value))
    else:
        s = f"{value:,.2f}"
        if lang == "TR":
            s = s.translate(str.maketrans(",.", ".,"))
    if unit == "pct":
        return f"%{s}" if lang == "TR" else f"{s}%"
    return s


def fmt_date(d: date, lang: str) -> str:
    return d.strftime("%d.%m.%Y") if lang == "TR" else d.isoformat()


def kind_name(kind: str, lang: str) -> str:
    return KIND_NAMES.get(kind, {}).get(lang, kind)


def quantity_name(quantity: str, lang: str) -> str:
    if quantity in QUANTITY_NAMES:
        return QUANTITY_NAMES[quantity][lang]
    m = _PERIOD.match(quantity)
    if m:
        n, unit = m.group(1), _PERIOD_WORDS[m.group(2)][lang]
        return f"{n} {unit} getiri" if lang == "TR" else f"{n}-{unit} return"
    return quantity


def _sentence(text: str, option_ids: Sequence[str] = (),
              evidence_ids: Sequence[str] = ()) -> NarrativeSentence:
    return NarrativeSentence(text, tuple(dict.fromkeys(option_ids)),
                             tuple(dict.fromkeys(evidence_ids)))


def _end(text: str) -> str:
    """Engine and RM texts as one sentence: add a full stop if they have no end mark."""
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _labels(options: Sequence[OptionFacts]) -> str:
    return ", ".join(o.label for o in options)


def _ozet(f: Facts, tx: dict, disclaimer: str) -> list[NarrativeSentence]:
    c = f.client
    out = [_sentence(tx["client"].format(profil=c["profil"], yas=c["yas"], durum=c["durum"])),
           _sentence(tx["goal"].format(amac=c["yatirim_amaci"], ufuk=c["yatirim_ufku"],
                                       risk=c["risk_profili"]))]
    if c["oncelikler"]:
        out.append(_sentence(tx["priorities"].format(items=", ".join(c["oncelikler"]))))
    if c["rm_notu"]:
        out.append(_sentence(tx["client_note"].format(note=_end(c["rm_notu"]))))
    if f.rm_note:
        out.append(_sentence(tx["rm_note"].format(note=_end(f.rm_note))))
    ids = [o.option_id for o in f.selected]
    if f.baseline is not None:
        out.append(_sentence(tx["meeting_baseline"].format(n=len(f.selected),
                                                           baseline=f.baseline.label),
                             [*ids, f.baseline.option_id]))
    else:
        out.append(_sentence(tx["meeting"].format(n=len(f.selected)), ids))
    out.append(_sentence(disclaimer))
    return out


def source_name(source: str, lang: str) -> str:
    """A source as the RM reads it (TEFAS, TCMB EVDS), never an internal name."""
    name = SOURCE_NAMES.get(source, source.replace("_", " "))
    return name[lang] if isinstance(name, dict) else name


def _number(n: KeyNumber, tx: dict, lang: str) -> str:
    return tx["number"].format(name=quantity_name(n.quantity, lang),
                               value=fmt_number(n.value, n.unit, lang),
                               source=source_name(n.source, lang), as_of=fmt_date(n.as_of, lang))


def _link(o: OptionFacts, used: set[str], f: Facts, tx: dict, lang: str) -> str | None:
    """One sentence that ties the option to a named client need: its largest
    positive score part with a need, one not used by an earlier option if possible."""
    parts = [k for k, v, _ in o.reasons if v > 0 and k in PART_NEEDS and f.client[PART_NEEDS[k]]]
    if not parts:
        return None
    part = next((k for k in parts if k not in used), parts[0])
    used.add(part)
    need = PART_NEEDS[part]
    return tx["link"].format(label=o.label, need=NEED_NAMES[need][lang],
                             value=f.client[need], part=PART_NAMES[part][lang])


def _oneriler(f: Facts, tx: dict, lang: str) -> list[NarrativeSentence]:
    out, used = [], set()
    for o in f.selected:
        oid = [o.option_id]
        public = [x[2] for x in o.reasons if is_quotable(x)][:MAIN_REASONS]
        head = dict(label=o.label, kind=kind_name(o.kind, lang), fx=tx["fx"] if o.fx else "")
        text = (tx["option"].format(**head, reasons="; ".join(public)) if public
                else tx["option_bare"].format(**head))
        out.append(_sentence(text, oid, o.evidence_ids))
        link = _link(o, used, f, tx, lang)
        if link:
            out.append(_sentence(link, oid))
        if o.numbers:
            items = "; ".join(_number(n, tx, lang) for n in o.numbers)
            out.append(_sentence(tx["numbers"].format(items=items), oid,
                                 [n.evidence_id for n in o.numbers]))
        out += [_sentence(tx["watch"].format(message=_end(m)), oid) for m in o.warnings]
        if o.rm_note:
            out.append(_sentence(tx["option_note"].format(note=_end(o.rm_note)), oid))
    return out


def _alternatifler(f: Facts, tx: dict, lang: str) -> list[NarrativeSentence]:
    by_id = f.named_options()
    out = []
    for g in f.groups:
        kind = kind_name(g.key, lang)
        if g.alternatives:
            alts = [by_id[i] for i in g.alternatives]
            out.append(_sentence(tx["group"].format(kind=kind, labels=_labels(alts)),
                                 g.alternatives))
        else:
            out.append(_sentence(tx["group_empty"].format(kind=kind), g.selected))
    if not out:
        out.append(_sentence(tx["no_groups"], [o.option_id for o in f.selected]))
    b = f.baseline
    if b is not None and b.option_id not in {o.option_id for o in f.selected}:
        if b.numbers:
            items = "; ".join(_number(n, tx, lang) for n in b.numbers)
            out.append(_sentence(tx["baseline_numbers"].format(label=b.label, items=items),
                                 [b.option_id], [n.evidence_id for n in b.numbers]))
        else:
            out.append(_sentence(tx["baseline"].format(label=b.label), [b.option_id]))
    return out


def _dikkat(f: Facts, tx: dict, lang: str) -> list[NarrativeSentence]:
    whole = [o.option_id for o in f.selected]      # citation of a note about the whole result
    out = []
    for w in f.warnings:
        out.append(_sentence(_end(w.message), w.option_ids or ([] if w.evidence_ids else whole),
                             w.evidence_ids))
    if f.data_quality:
        out.append(_sentence(tx["dq_pointer"], whole))
    out.append(_sentence(tx["past"], whole))
    return out


def _sorular(f: Facts, tx: dict) -> list[NarrativeSentence]:
    out = [_sentence(_end(q)) for q in f.open_questions]
    out += [_sentence(tx["constraint"].format(item=k)) for k in f.client["acik_kisitlar"]]
    if f.client["oncelikler"]:
        out.append(_sentence(tx["ask_priorities"].format(items=", ".join(f.client["oncelikler"]))))
    return out


def _teklif(f: Facts, tx: dict) -> list[NarrativeSentence]:
    out = [_sentence(tx["pitch_goal"].format(durum=f.client["durum"],
                                             amac=f.client["yatirim_amaci"]))]
    if f.baseline is not None:
        out.append(_sentence(tx["pitch_baseline"].format(baseline=f.baseline.label),
                             [f.baseline.option_id]))
    out.append(_sentence(tx["pitch_options"].format(labels=_labels(f.selected)),
                         [o.option_id for o in f.selected]))
    out += [_sentence(tx["pitch_past"]), _sentence(tx["pitch_close"])]
    return out


def template_sections(f: Facts, lang: str, disclaimer: str) -> tuple[NarrativeSection, ...]:
    if lang not in NARRATIVE_LANGS:
        raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
    tx = TEXTS[lang]
    sections = {
        "ozet": _ozet(f, tx, disclaimer),
        "oneriler": _oneriler(f, tx, lang),
        "alternatifler": _alternatifler(f, tx, lang),
        "dikkat": _dikkat(f, tx, lang),
        "sorular": _sorular(f, tx),
        "teklif_metni": _teklif(f, tx),
        "varsayimlar": ([_sentence(a) for a in f.assumptions]
                        or [_sentence(tx["no_assumptions"])]),
    }
    return tuple(NarrativeSection(k, tuple(sections[k])) for k in NARRATIVE_SECTIONS)


def template_draft(f: Facts, lang: str, config: NarratorConfig, *, created_at: datetime,
                   checks: tuple[str, ...] = ()) -> NarrativeDraft:
    """The template text as a draft (source "template", no model, no cost).
    checks: the findings of a failed LLM text this template replaces."""
    if lang not in NARRATIVE_LANGS:
        raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
    return NarrativeDraft(
        run_id=f.run_id, lang=lang, sections=template_sections(f, lang, config.disclaimer[lang]),
        source="template", model="", prompt_version=config.prompt_version, checks=checks,
        created_at=created_at)


# shown over a template text that replaces an LLM text (validator, budget, API error)
BANNER = {
    "TR": "Otomatik metin doğrulanamadı; şablon metin gösteriliyor.",
    "EN": "The automatic text could not be verified; the template text is shown.",
}


def banner(d: NarrativeDraft) -> str | None:
    return BANNER[d.lang] if d.source == "template" and d.checks else None


_PARAGRAPHS = ("ozet", "teklif_metni")    # prose; the other sections are lists


def to_markdown(d: NarrativeDraft) -> str:
    """The draft as Markdown: the text the RM edits and approves (rm_text)."""
    lines = [f"# {TEXTS[d.lang]['title']} · {d.run_id}"]
    if banner(d):
        lines += ["", f"> ⚠ {banner(d)}"]
    for sec in d.sections:
        lines += ["", f"## {HEADINGS[sec.key][d.lang]}", ""]
        if sec.key in _PARAGRAPHS:
            lines.append(" ".join(s.text for s in sec.sentences))
        else:
            lines += [f"- {s.text}" for s in sec.sentences]
    return "\n".join(lines) + "\n"
