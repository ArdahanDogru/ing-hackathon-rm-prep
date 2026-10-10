"""N8: the facts pack sent to the LLM is small; the validator keeps the full facts."""

import dataclasses
import json

from rmprep.contracts import (
    ConstraintResult,
    DataQualityNote,
    NarrativeSection,
    NarrativeSentence,
    ProductOption,
    ScoredOption,
)
from rmprep.narrator.facts import build_facts
from rmprep.narrator.prompt import facts_block, prompt_facts
from rmprep.narrator.template import fmt_number, quantity_name, template_sections
from rmprep.narrator.validator import validate
from tests.narrator.conftest import approved, evidence

KINDS = ("debt", "money_market", "equity", "precious_metals", "mixed")
PARTS = ("return", "low_risk", "liquidity", "income", "principal")


def big_result():
    """A real-size approved result: every fund of evidence_medium with its rows,
    5 groups, the head of each selected, and data-quality notes listing every row."""
    ev = evidence()
    rows: dict[str, list] = {}
    for dp in ev.datapoints:
        if dp.quantity.startswith("fund_") and dp.value is not None:
            rows.setdefault(dp.entity, []).append(dp)
    base = approved("decision_p02_ready", ("fund:BBF",))
    rejected = {x.option.entity for x in base.rejected}
    codes = sorted(c for c, rs in rows.items() if c not in rejected
                   and {"fund_return_1y", "fund_risk_level"} <= {d.quantity for d in rs})
    options = [base.options[0]]                                # the deposit baseline
    for i, code in enumerate(codes):
        ids = tuple(d.id for d in rows[code])
        risk = next(d.id for d in rows[code] if d.quantity == "fund_risk_level")
        name = ev.entities[code].name if code in ev.entities else f"{code} FONU"
        parts = {p: round(0.2 - 0.01 * j - 0.001 * i, 4) for j, p in enumerate(PARTS)}
        options.append(ScoredOption(
            option=ProductOption(f"fund:{code}", "fund", name, code, KINDS[i % len(KINDS)]),
            score=sum(parts.values()), score_parts=parts,
            constraints=(ConstraintResult("risk_ceiling", True, "risk tavan içinde", (risk,)),),
            confidence=0.9, stability=1.0, evidence_ids=ids,
            reasons={p: f"(örnek) {p.replace('_', ' ')} gerekçesi, fon {code}"
                     for p in parts}))
    heads = tuple(o.option.option_id for o in options[1:1 + len(KINDS)])
    all_ids = tuple(d.id for d in ev.datapoints)
    notes = (DataQualityNote(f"tefas_web: {len(all_ids)} değer \"needs_check\" işaretli.",
                             ("needs_check",), ("tefas_web",), all_ids),
             DataQualityNote("evds: 120 değer eski.", ("stale",), ("evds",), all_ids[:120]))
    return dataclasses.replace(base, options=tuple(options), rm_selected=heads,
                               rm_option_notes={}, data_quality=notes)


def test_big_result_is_real_size():
    f = build_facts(big_result(), evidence())
    assert len(f.selected) == 5 and len(f.alternatives) >= 12
    assert len(json.dumps(f.to_dict(), ensure_ascii=False)) > 30_000   # the old pack


def test_facts_block_is_small():
    f = build_facts(big_result(), evidence())
    block = facts_block(f)
    assert len(block) < 10_000, len(block)
    assert "\n" not in block                                            # compact JSON


def test_pack_has_no_data_quality_details():
    """N7: only a flag; the text points to the "Olası sorunlar" pane."""
    pack = prompt_facts(build_facts(big_result(), evidence()))
    assert pack["data_quality_notes"] is True
    assert "data_quality" not in pack and "rejected" not in pack


def test_alternatives_are_short():
    f = build_facts(big_result(), evidence())
    for a in prompt_facts(f)["alternatives"]:
        assert set(a) == {"option_id", "label", "kind", "fx", "as_of", "numbers"}
        assert 1 <= len(a["numbers"]) <= 3
        assert list(a["numbers"])[:2] == ["fund_return_1y", "fund_risk_level"]


def test_number_shape():
    f = build_facts(big_result(), evidence())
    o = next(x for x in f.selected)
    packed = prompt_facts(f)["selected"][0]
    n = next(x for x in o.numbers if x.quantity == "fund_return_1y")
    assert packed["numbers"]["fund_return_1y"] == [n.value, n.unit, n.evidence_id]
    assert packed["as_of"] == n.as_of.isoformat()
    assert packed["reasons"] == [o.reasons[i][2] for i in range(len(o.reasons))
                                 if o.reasons[i][0] in ("return", "low_risk")]
    assert packed["fits"] == ["liquidity", "income", "principal"]


def _cited(x, ids: set, options: set) -> None:
    """Every evidence id and option id anywhere in the pack."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "numbers" and isinstance(v, dict):
                ids.update(x[2] for x in v.values())
            elif k == "evidence_id":
                ids.add(v)
            elif k == "evidence_ids":
                ids.update(v)
            elif k in ("option_id",):
                options.add(v)
            elif k in ("option_ids", "selected", "alternatives") and v and isinstance(v[0], str):
                options.update(v)
            else:
                _cited(v, ids, options)
    elif isinstance(x, list):
        for v in x:
            _cited(v, ids, options)


def test_pack_ids_come_from_the_full_facts():
    f = build_facts(big_result(), evidence())
    ids, options = set(), set()
    _cited(prompt_facts(f), ids, options)
    assert ids and ids <= f.evidence_ids()
    assert options and options <= set(f.named_options())


def _text_from_pack(pack: dict, disclaimer: str) -> tuple[NarrativeSection, ...]:
    """A good text written only from the small pack, as the LLM would."""
    def nums(o):
        return "; ".join(f"{quantity_name(q, 'TR')} {fmt_number(n[0], n[1], 'TR')}"
                         for q, n in o["numbers"].items())

    def ids(o):
        return tuple(n[2] for n in o["numbers"].values())

    selected = [o["option_id"] for o in pack["selected"]]
    s = {
        "ozet": [NarrativeSentence(f"{pack['client']['profil']} ({pack['client']['yas']} yaşında)."),
                 NarrativeSentence(disclaimer)],
        "oneriler": [NarrativeSentence(f"{o['label']}: {nums(o)}.", (o["option_id"],), ids(o))
                     for o in pack["selected"]],
        "alternatifler": [NarrativeSentence(f"{a['label']}: {nums(a)}.", (a["option_id"],), ids(a))
                          for a in pack["alternatives"]],
        "dikkat": [NarrativeSentence("Veri notları için \"Olası sorunlar\" bölümüne bakın.",
                                     selected)]
                  + [NarrativeSentence(w["message"], tuple(w["option_ids"]) or selected)
                     for w in pack["warnings"]],
        "sorular": [NarrativeSentence(q) for q in pack["open_questions"]]
                   or [NarrativeSentence("Öncelikleriniz değişti mi?")],
        "teklif_metni": [NarrativeSentence("Seçenekleri birlikte değerlendirelim.")],
        "varsayimlar": [NarrativeSentence(a) for a in pack["assumptions"]],
    }
    return tuple(NarrativeSection(k, tuple(v)) for k, v in s.items())


def test_a_text_from_the_small_pack_passes_the_full_validator(config):
    r = big_result()
    f = build_facts(r, evidence())
    sections = _text_from_pack(prompt_facts(f), config.disclaimer["TR"])
    assert validate(sections, f, r, config, "TR") == ()


def test_template_still_passes_for_the_big_result(config):
    r = big_result()
    f = build_facts(r, evidence())
    for lang in ("TR", "EN"):
        assert validate(template_sections(f, lang, config.disclaimer[lang]), f, r, config,
                        lang) == ()
