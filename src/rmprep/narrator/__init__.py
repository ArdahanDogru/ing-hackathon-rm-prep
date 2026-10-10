"""Narrator: the meeting text of an approved DecisionResult (docs/narrator.md).

The decision layer decides; the narrator only writes. facts builds the facts
pack, template the text without an LLM, validator checks a text against the
facts, prompt and llm make the LLM call, service (Narrator.draft) runs it all
with retry, fallback, cache and the daily budget."""
