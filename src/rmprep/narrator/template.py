"""Template text: the meeting text built from the facts pack only (no LLM).
It is the fallback when the LLM text fails the validator or the budget is
used up, so it must always pass the validator itself (docs/narrator.md).

Engine texts (reasons, warnings, questions, assumptions) and persona values are
Turkish only; the English template quotes them as they are."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime

from rmprep.contracts import (
    NARRATIVE_LANGS,
    NARRATIVE_SECTIONS_V13,
    NarrativeDraft,
    NarrativeSection,
    NarrativeSentence,
)
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import (
    INTERNAL_PARTS,
    MARKET_NAMES,
    Facts,
    KeyNumber,
    OptionFacts,
    number_rank,
)

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
    "deposit_rate": {"TR": "mevduat faizi", "EN": "deposit rate"},
    "piyasa_mevduat_faizi": {"TR": "piyasa mevduat faizi (yeni mevduat, 3 aya kadar, ağırlıklı "
                                   "ortalama)",
                             "EN": "market deposit rate (new deposits up to 3 months, weighted "
                                   "average)"},
    "ing_mevduat_faizi": {"TR": "ING mevduat faizi", "EN": "ING deposit rate"},
    "ing_vadeli_mevduat_faizi": {"TR": "ING vadeli mevduat faizi", "EN": "ING time deposit rate"},
    "real_return_1y": {"TR": "stopaj ve enflasyon sonrası reel getiri (1 yıl)",
                       "EN": "real return after stopaj and inflation (1 year)"},
    "tufe_yillik": {"TR": "yıllık TÜFE", "EN": "annual CPI"},
    "fund_entry_fee": {"TR": "giriş komisyonu", "EN": "entry fee"},
    "fund_exit_fee": {"TR": "çıkış komisyonu", "EN": "exit fee"},
    "fund_price": {"TR": "pay fiyatı", "EN": "unit price"},
    "fund_total_value": {"TR": "fon büyüklüğü", "EN": "fund size"},
    "fund_investor_count": {"TR": "yatırımcı sayısı", "EN": "number of investors"},
}
_PERIOD = re.compile(r"fund_return_(\d+)([my])$")
_PERIOD_WORDS = {"m": {"TR": "aylık", "EN": "month"}, "y": {"TR": "yıllık", "EN": "year"}}

SOURCE_NAMES = {"tefas": "TEFAS", "tefas_web": "TEFAS", "tefas_detail": "TEFAS",
                "evds": "TCMB EVDS", "manual": {"TR": "manuel giriş", "EN": "manual entry"}}

# N7: the client need a score part speaks to (persona field), and the part's name
PART_NEEDS = {"return": "yatirim_amaci", "low_risk": "risk_profili", "risk_fit": "risk_profili",
              "liquidity": "likidite_ihtiyaci", "income": "gelir_nakit_akisi_ihtiyaci",
              "principal": "anapara_koruma_tercihi", "simplicity": "risk_profili",
              "quality": "yatirim_ufku"}
PART_NAMES = {
    "return": {"TR": "getiri", "EN": "return"},
    "low_risk": {"TR": "düşük risk", "EN": "low risk"},
    "risk_fit": {"TR": "risk uyumu", "EN": "risk fit"},       # D19 (lead, 2026-10-12)
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
    "ek": {"TR": "Ek bilgiler", "EN": "Additional information"},     # N13: screen order
    "talking_points": {"TR": "Müşteriyle konuşulacaklar", "EN": "Talking points"},
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
        "client": "{profil} ({yas} yaşında); durum: {durum}; amaç: {amac} (ufuk: {ufuk}, "
                  "risk profili: {risk}).",
        "notes_file": "Dosyadaki not: {note}",
        "notes_rm": "RM onay notu: {note}",
        "o_facts": "{name} ({kind}{fx}): {items}.",
        "o_bare": "{name} ({kind}{fx}).",
        "o_fit": "{name}: müşterinin {need} (\"{value}\") açısından {part} ile öne çıktığını "
                 "anlatın.",
        "o_fit_none": "{name}: müşterinin önceliklerine nasıl uyduğunu birlikte değerlendirin.",
        "o_risk": "{name}: {note}",
        "o_risk_none": "{name}: başlıca riskini müşteriyle konuşun.",
        "watch_access": "{name}: paraya erişim {access}{fees}.",
        "watch_none": "{name}: değerini ve riskini düzenli izleyin.",
        "unmatched": "\"{p}\" önceliği seçeneklerin hiçbir ölçütüyle karşılanmıyor.",
        "ask_unmatched": "\"{p}\" önceliğinin müşteri için ne anlama geldiğini sorun.",
        "tp_unmatched": ("Kapsanmayan öncelik", "Seçeneklerin karşılamadığı önceliği konuşun: "
                                                "\"{p}\"."),
        "tp_constraint": ("Açık kısıt", "Kısıtı müşteriyle teyit edin: \"{k}\"."),
        "goal": "Yatırım amacı: {amac} (ufuk: {ufuk}, risk profili: {risk}).",
        "priorities": "Öncelikler: {items}.",
        "client_note": "Müşteri notu: {note}",
        "rm_note": "RM'in görüşme notu: {note}",
        "meeting": "Görüşmede seçtiğiniz {n} seçeneği konuşun.",
        "meeting_baseline": "Görüşmede seçtiğiniz {n} seçeneği konuşun; "
                            "karşılaştırma ölçütü {baseline}.",
        "option": "{label} ({kind}{fx}): {reasons}.",
        "option_bare": "{label} ({kind}{fx}).",
        "link": "Müşteriye {label} seçeneğinin {need} (\"{value}\") açısından {part} ile "
                "öne çıktığını anlatın.",
        "tp_goal": ("Müşterinin hedefi", "Müşterinin hedefini konuşun: \"{amac}\" "
                                         "(yatırım ufku: {ufuk})."),
        "tp_situation": ("Müşterinin durumu", "Müşterinin durumunu dikkate alın: \"{durum}\"."),
        "tp_priorities": ("Müşterinin öncelikleri", "Öncelikleri teyit edin: {items}."),
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
        "client": "Client: {profil}, age {yas}; situation: {durum}; goal: {amac} (horizon: "
                  "{ufuk}, risk profile: {risk}).",
        "notes_file": "Note in the file: {note}",
        "notes_rm": "RM approval note: {note}",
        "o_facts": "{name} ({kind}{fx}): {items}.",
        "o_bare": "{name} ({kind}{fx}).",
        "o_fit": "{name}: explain that it stands out on {part} for the client's {need} "
                 "(\"{value}\").",
        "o_fit_none": "{name}: discuss with the client how it fits their priorities.",
        "o_risk": "{name}: {note}",
        "o_risk_none": "{name}: discuss its main risk with the client.",
        "watch_access": "{name}: access to the money {access}{fees}.",
        "watch_none": "{name}: watch its value and risk regularly.",
        "unmatched": "No criterion of the options covers the priority \"{p}\".",
        "ask_unmatched": "Ask what the priority \"{p}\" means for the client.",
        "tp_unmatched": ("Uncovered priority", "Talk about the priority that the options do "
                                               "not cover: \"{p}\"."),
        "tp_constraint": ("Explicit constraint", "Confirm the constraint with the client: "
                                                 "\"{k}\"."),
        "goal": "Investment goal: {amac} (horizon: {ufuk}, risk profile: {risk}).",
        "priorities": "Priorities: {items}.",
        "client_note": "Client note: {note}",
        "rm_note": "The RM's meeting note: {note}",
        "meeting": "Discuss the {n} options that you selected.",
        "meeting_baseline": "Discuss the {n} options that you selected; the baseline for "
                            "comparison is {baseline}.",
        "option": "{label} ({kind}{fx}): {reasons}.",
        "option_bare": "{label} ({kind}{fx}).",
        "link": "Explain to the client that {label} stands out on {part} for their {need} "
                "(\"{value}\").",
        "tp_goal": ("Client's goal", "Talk about the client's goal: \"{amac}\" "
                                     "(horizon: {ufuk})."),
        "tp_situation": ("Client's situation", "Keep the client's situation in mind: "
                                               "\"{durum}\"."),
        "tp_priorities": ("Client's priorities", "Confirm the priorities: {items}."),
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
    if unit in ("level", "count") and float(value).is_integer():
        s = f"{int(value):,}"
        if lang == "TR":
            s = s.replace(",", ".")
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
    """N13: at most 3 sentences (client, notes, meeting), then the disclaimer."""
    c = f.client
    out = [_sentence(tx["client"].format(profil=c["profil"], yas=c["yas"], durum=c["durum"],
                                         amac=c["yatirim_amaci"], ufuk=c["yatirim_ufku"],
                                         risk=c["risk_profili"]))]
    notes = []
    if c["rm_notu"]:
        notes.append(tx["notes_file"].format(note=_end(c["rm_notu"])))
    if f.rm_note:
        notes.append(tx["notes_rm"].format(note=_end(f.rm_note)))
    if notes:
        out.append(_sentence(" ".join(notes)))
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
    return tx["number"].format(name=quantity_name(n.key, lang),
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
    return tx["o_fit"].format(name=_name(o), need=NEED_NAMES[need][lang],
                              value=f.client[need], part=PART_NAMES[part][lang])


OPTION_NUMBERS = 4      # numbers in the facts sentence of an option
_NOT_OPTION_NUMBERS = {"fund_buyable", "fund_sell_valor_days", "fund_entry_fee", "fund_exit_fee"}


def _name(o: OptionFacts) -> str:
    return o.name or o.label


def _own_numbers(o: OptionFacts) -> list[KeyNumber]:
    """The option's numbers for the text: real return first; no market facts and
    no risk-line rows (N13)."""
    own = [n for n in o.numbers if n.name not in MARKET_NAMES
           and n.quantity not in _NOT_OPTION_NUMBERS]
    return sorted(own, key=number_rank)[:OPTION_NUMBERS]


def _oneriler(f: Facts, tx: dict, lang: str) -> list[NarrativeSentence]:
    """N13: per selected option 3 sentences that start with its name: (a) facts,
    real return first; (b) the fit with a client need (+ the RM's option note);
    (c) the risk of its asset class (+ its warnings)."""
    out, used = [], set()
    for o in f.selected:
        oid, name = [o.option_id], _name(o)
        head = dict(name=name, kind=kind_name(o.kind, lang), fx=tx["fx"] if o.fx else "")
        nums = _own_numbers(o)
        if nums:
            items = "; ".join(_number(n, tx, lang) for n in nums)
            out.append(_sentence(tx["o_facts"].format(**head, items=items), oid,
                                 [n.evidence_id for n in nums]))
        else:
            out.append(_sentence(tx["o_bare"].format(**head), oid, o.evidence_ids))
        fit = _link(o, used, f, tx, lang) or tx["o_fit_none"].format(name=name)
        if o.rm_note:
            fit += " " + tx["option_note"].format(note=_end(o.rm_note))
        out.append(_sentence(fit, oid))
        risk = f.risks.get(o.option_id)
        note = risk.note.get(lang, "") if risk else ""
        text = tx["o_risk"].format(name=name, note=_end(note)) if note else \
            tx["o_risk_none"].format(name=name)
        text = " ".join([text, *(_end(m) for m in o.warnings)])
        out.append(_sentence(text, oid, risk.evidence_ids if risk else ()))
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
    """N13: the warnings, one watch item per selected option (access, fees), the
    unmatched priorities, the past-return caveat once."""
    whole = [o.option_id for o in f.selected]      # citation of a note about the whole result
    out = []
    for w in f.warnings:
        out.append(_sentence(_end(w.message), w.option_ids or ([] if w.evidence_ids else whole),
                             w.evidence_ids))
    for o in f.selected:
        risk = f.risks.get(o.option_id)
        if risk and risk.access:
            fees = "".join(f"; {quantity_name(n.quantity, lang)} {fmt_number(n.value, n.unit, lang)}"
                           for n in risk.fees)
            out.append(_sentence(tx["watch_access"].format(name=_name(o),
                                                           access=_lower_first(risk.access),
                                                           fees=fees),
                                 [o.option_id], risk.evidence_ids))
        else:
            out.append(_sentence(tx["watch_none"].format(name=_name(o)), [o.option_id]))
    out += [_sentence(tx["unmatched"].format(p=p), whole) for p in f.unmatched_priorities]
    out.append(_sentence(tx["past"], whole))       # N9c: no data-quality pointer (client-facing)
    return out


def _lower_first(text: str) -> str:
    return tr_lower(text[:1]) + text[1:] if text else text


def _sorular(f: Facts, tx: dict) -> list[NarrativeSentence]:
    out = [_sentence(_end(q)) for q in f.open_questions]
    out += [_sentence(tx["constraint"].format(item=k)) for k in f.client["acik_kisitlar"]]
    out += [_sentence(tx["ask_unmatched"].format(p=p)) for p in f.unmatched_priorities]
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


MAX_TALKING_POINTS = 3
MAX_TAGS = 3


def _talking_points(f: Facts, tx: dict) -> list[NarrativeSentence]:
    """The engine's talking points (title = label), then points from the
    unmatched priorities, the priorities and the constraints (N13: no profile
    facts; the goal only as the last resort), up to MAX_TALKING_POINTS."""
    whole = [o.option_id for o in f.selected]
    named = f.named_options()
    out = []
    for t in f.talking_points[:MAX_TALKING_POINTS]:
        ids = [i for i in t.option_ids if i in named]
        out.append(NarrativeSentence(t.text, tuple(ids or ([] if t.evidence_ids else whole)),
                                     tuple(t.evidence_ids), t.title))
    c = f.client
    extra = [("tp_unmatched", dict(p=p)) for p in f.unmatched_priorities]
    if c["oncelikler"]:
        extra.append(("tp_priorities", dict(items=", ".join(c["oncelikler"]))))
    extra += [("tp_constraint", dict(k=k)) for k in c["acik_kisitlar"]]
    extra.append(("tp_goal", dict(amac=c["yatirim_amaci"], ufuk=c["yatirim_ufku"])))
    for key, fields in extra:
        if len(out) >= MAX_TALKING_POINTS:
            break
        title, text = tx[key]
        out.append(NarrativeSentence(text.format(**fields), tuple(whole), (), title))
    return out


def template_need_tags(f: Facts) -> dict[str, tuple[str, ...]]:
    """Need tags per selected option: the persona priorities of its why lines
    (decision D17), as the persona writes them, at most MAX_TAGS."""
    return {o.option_id: tuple(dict.fromkeys(p for p, _ in f.why.get(o.option_id, ())))[:MAX_TAGS]
            for o in f.selected}


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
        "talking_points": _talking_points(f, tx),
    }
    return tuple(NarrativeSection(k, tuple(sections[k])) for k in NARRATIVE_SECTIONS_V13)


def template_draft(f: Facts, lang: str, config: NarratorConfig, *, created_at: datetime,
                   checks: tuple[str, ...] = ()) -> NarrativeDraft:
    """The template text as a draft (source "template", no model, no cost).
    checks: the findings of a failed LLM text this template replaces."""
    if lang not in NARRATIVE_LANGS:
        raise ValueError(f"lang must be one of {NARRATIVE_LANGS}, got {lang!r}")
    return NarrativeDraft(
        run_id=f.run_id, lang=lang, sections=template_sections(f, lang, config.disclaimer[lang]),
        source="template", model="", prompt_version=config.prompt_version, checks=checks,
        created_at=created_at, need_tags=template_need_tags(f))


# shown over a template text that replaces an LLM text (validator, budget, API error)
BANNER = {
    "TR": "Otomatik metin doğrulanamadı; şablon metin gösteriliyor.",
    "EN": "The automatic text could not be verified; the template text is shown.",
}


def banner(d: NarrativeDraft) -> str | None:
    return BANNER[d.lang] if d.source == "template" and d.checks else None


_PARAGRAPHS = ("ozet", "teklif_metni")    # prose; the other sections are lists
# N13: the screen order; the last three under "Ek bilgiler"
_MD_MAIN = ("ozet", "talking_points", "teklif_metni", "oneriler", "dikkat")
_MD_EXTRA = ("alternatifler", "sorular", "varsayimlar")


# --- blocks of the meeting text (contract v1.5; N11; ids also in rmprep.edits) ----------

WHOLE_SECTIONS = ("ozet", "teklif_metni", "dikkat", "alternatifler", "sorular", "varsayimlar")


def block_of(key: str, i: int, s: NarrativeSentence) -> str | None:
    """The block id of sentence i of section key: a whole section, one talking
    point, or the sentences of one selected option (its first option id)."""
    if key in WHOLE_SECTIONS:
        return key
    if key == "talking_points":
        return f"talking_points:{i}"
    if key == "oneriler" and s.option_ids:
        return f"oneriler:{s.option_ids[0]}"
    return None


def apply_edits(d: NarrativeDraft) -> NarrativeDraft:
    """The draft with each edited block (d.rm_edits) as one sentence in place of
    the block's sentences (title and citations of its first sentence kept);
    rm_edits then empty."""
    if not d.rm_edits:
        return d
    sections = []
    for sec in d.sections:
        out, done = [], set()
        for i, s in enumerate(sec.sentences):
            block = block_of(sec.key, i, s)
            if block in d.rm_edits:
                if block not in done:
                    done.add(block)
                    out.append(NarrativeSentence(d.rm_edits[block], s.option_ids,
                                                 s.evidence_ids, s.title))
                continue
            out.append(s)
        sections.append(NarrativeSection(sec.key, tuple(out)))
    return dataclasses.replace(d, sections=tuple(sections), rm_edits={})


def to_markdown(d: NarrativeDraft, names: Mapping[str, str] | None = None) -> str:
    """The draft as Markdown: the text the RM approves (rm_text); an edited block
    (rm_edits, v1.5) stands in place of its sentences. N13: the screen order
    (ozet, talking_points, teklif_metni, oneriler with a ### heading per option,
    dikkat, then alternatifler, sorular, varsayimlar under "Ek bilgiler"). names:
    option id -> heading (default: the fund code)."""
    d = apply_edits(d)
    by_key = {sec.key: sec for sec in d.sections}
    lines = [f"# {TEXTS[d.lang]['title']} · {d.run_id}"]
    if banner(d):
        lines += ["", f"> ⚠ {banner(d)}"]

    def body(sec) -> list[str]:
        if sec.key in _PARAGRAPHS:
            return [" ".join(s.text for s in sec.sentences)]
        return [f"- **{s.title}:** {s.text}" if s.title else f"- {s.text}" for s in sec.sentences]

    for key in _MD_MAIN:
        sec = by_key.get(key)
        if sec is None:
            continue
        lines += ["", f"## {HEADINGS[key][d.lang]}", ""]
        if key != "oneriler":
            lines += body(sec)
            continue
        loose = [s for s in sec.sentences if not s.option_ids]
        lines += [f"- {s.text}" for s in loose]
        order = list(dict.fromkeys(s.option_ids[0] for s in sec.sentences if s.option_ids))
        for oid in order:
            heading = (names or {}).get(oid) or oid.split(":", 1)[-1]
            lines += ([] if lines[-1] == "" else [""]) + [f"### {heading}", ""]
            lines += [f"- {s.text}" for s in sec.sentences if s.option_ids[:1] == (oid,)]
    extra = [by_key[k] for k in _MD_EXTRA if k in by_key]
    if extra:
        lines += ["", f"## {HEADINGS['ek'][d.lang]}"]
        for sec in extra:
            lines += ["", f"### {HEADINGS[sec.key][d.lang]}", ""] + body(sec)
    return "\n".join(lines) + "\n"
