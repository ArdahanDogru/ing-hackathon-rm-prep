"""The LLM request of the narrator: system prompt, facts block, task, output
schema, and the parser of the reply (docs/narrator.md, "Output").

Bump prompt_version in config/narrator.yaml on any change of the texts here:
it is part of the cache key."""

from __future__ import annotations

import json
from collections.abc import Sequence

from rmprep.contracts import NARRATIVE_SECTIONS, NarrativeSection, NarrativeSentence
from rmprep.narrator.config import NarratorConfig
from rmprep.narrator.facts import Facts
from rmprep.narrator.llm import LlmRequest

_SENTENCE = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "option_ids": {"type": "array", "items": {"type": "string"}},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "option_ids", "evidence_ids"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "array", "items": _SENTENCE} for k in NARRATIVE_SECTIONS},
    "required": list(NARRATIVE_SECTIONS),
    "additionalProperties": False,
}

_LANGUAGE = {
    "TR": ("Turkish", "formal \"siz\" form", "%52,51 and 1.054,64", "09.10.2026"),
    "EN": ("English", "polite, plain form", "52.51% and 1,054.64", "2026-10-09"),
}

_SYSTEM = """\
You write the meeting preparation text for a relationship manager (RM) of ING \
Turkey. The decision engine has already chosen and ranked the options and the RM \
has approved a selection; you only write. You do not decide, rank, or recommend \
anything that is not in the facts.

Language: write in {language}, {form}. Persona fields, option labels and engine \
texts in the facts are Turkish; quote them as they are.

Input: the facts pack (JSON) in the first user block. It is the only source. \
"baseline" is the comparison deposit, "selected" are the options the RM chose, \
"alternatives" are the other options of the same groups, "groups" says which is \
which. Rejected options appear only as a count per rule.

Output: JSON with exactly these sections, each a list of sentences; each sentence \
has its text and its citations (option_ids: option_id values from the facts; \
evidence_ids: evidence_id / evidence_ids values from the facts).
- ozet: 3-5 sentences: the client situation and the aim of the meeting. The last \
sentence is exactly: "{disclaimer}"
- oneriler: for each selected option: what it is, why it fits this client (from \
its reasons and the client context), its key numbers, what to watch.
- alternatifler: 1-2 sentences per group: the other options of the same kind; \
and the baseline for comparison.
- dikkat: the warnings, risks, data-quality notes and the rejected count, in \
plain words.
- sorular: questions for the RM to ask the client: the open questions and the \
explicit constraints (acik_kisitlar) to confirm.
- teklif_metni: a short script the RM may say or adapt in the meeting, spoken \
to the client. It is not a letter.
- varsayimlar: each assumption of the facts as its own sentence, verbatim.

Rules (a validator checks each one; a text that fails is replaced):
1. Every number and date you write is a number or date of the facts, rounded \
at most. Write numbers as {numbers} and dates as {date}. Do not compute new \
numbers (no differences, sums, or averages) and do not write ids in the text.
2. Name only the baseline, the selected options and the alternatives, by their \
label or fund code. Never name or hint at a rejected option or any other product.
3. Never promise a result. Do not use these phrases or their forms: {forbidden}. \
Past returns do not show future returns; say so where you talk about returns.
4. Every sentence of oneriler, alternatifler and dikkat cites at least one \
option_id or evidence_id of the facts; cite only ids that exist in the facts.
5. Include the sentence "{disclaimer}" verbatim.
This is decision support for the RM, not investment advice.
"""

_TASK = "Write the meeting text in {lang} for run {run_id} from the facts above."

_RETRY = """\
Your previous answer failed the validator. Previous answer:
{previous}

Findings:
{findings}

Return the full corrected JSON. Change only what the findings need."""


def system_prompt(lang: str, config: NarratorConfig) -> str:
    language, form, numbers, day = _LANGUAGE[lang]
    forbidden = ", ".join(f'"{p}"' for p in config.forbidden_phrases[lang])
    return _SYSTEM.format(language=language, form=form, numbers=numbers, date=day,
                          forbidden=forbidden, disclaimer=config.disclaimer[lang])


def facts_block(f: Facts) -> str:
    """The facts as stable JSON bytes (same facts -> same prompt cache prefix)."""
    return json.dumps(f.to_dict(), ensure_ascii=False, sort_keys=True, indent=1)


def build_request(f: Facts, lang: str, config: NarratorConfig, *, previous: str | None = None,
                  findings: Sequence[str] = ()) -> LlmRequest:
    blocks = [facts_block(f), _TASK.format(lang=lang, run_id=f.run_id)]
    if previous is not None:
        blocks.append(_RETRY.format(previous=previous,
                                    findings="\n".join(f"- {x}" for x in findings)))
    return LlmRequest(system=system_prompt(lang, config), user_blocks=tuple(blocks),
                      schema=SCHEMA)


def sections_json(sections: Sequence[NarrativeSection]) -> str:
    """Sections in the shape of SCHEMA (the reply format; used for tests and retries)."""
    return json.dumps({s.key: [{"text": x.text, "option_ids": list(x.option_ids),
                                "evidence_ids": list(x.evidence_ids)} for x in s.sentences]
                       for s in sections}, ensure_ascii=False)


def _ids(v, where: str) -> tuple[str, ...]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{where}: must be a list of strings")
    return tuple(v)


def parse_sections(text: str) -> tuple[NarrativeSection, ...]:
    """The reply JSON as sections, in the contract order; a missing section is
    empty (the validator reports it). ValueError on any other shape."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("the reply must be a JSON object")
    out = []
    for key in NARRATIVE_SECTIONS:
        items = data.get(key, [])
        if not isinstance(items, list):
            raise ValueError(f"{key}: must be a list of sentences")
        sentences = []
        for i, s in enumerate(items):
            where = f"{key}[{i}]"
            if not isinstance(s, dict) or not isinstance(s.get("text"), str):
                raise ValueError(f"{where}: needs a text string")
            sentences.append(NarrativeSentence(s["text"], _ids(s.get("option_ids", []), where),
                                               _ids(s.get("evidence_ids", []), where)))
        out.append(NarrativeSection(key, tuple(sentences)))
    return tuple(out)
