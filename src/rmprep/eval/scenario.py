"""Eval scenarios (docs/eval.md "Scenarios"): YAML files with a list of
scenarios; each names a persona and what to change before the run.

```yaml
scenarios:
  - id: edit-p04-muhafazakar          # unique in the suite; [A-Za-z0-9_.-]
    group: persona_edit               # base | persona_edit | constraint | data_access | bad_data | regression
    persona: P04
    description: "..."                # optional, for the report
    edit: {risk_profili: Muhafazakâr} # persona fields to replace (not persona_id)
    add_constraints: ["..."]          # appended to acik_kisitlar
    exclude_sources: [manual]         # excluded at read time (RealBackend.decide)
    answers: {"q:acik_kisitlar[1]": "Döviz maruziyetini sınırla"}   # answered in this order
    snapshot: <id>                    # default: the suite snapshot
    evidence_edits:                   # bad data on top of the snapshot (own snapshot id)
      - {quantity: fund_risk_level, entity: AFT, value: 9, add_flags: [out_of_range]}
      - {quantity: fund_price, entity: "@top1", drop: true}   # @topN: the Nth fund of the clean run
    repeat: 2                         # runs; each repetition on a fresh RealBackend
    select: ["fund:AFT"]              # the RM selection; default: heads of the first select_top
                                      # groups (only the baseline left: the baseline)
    select_top: 3
    langs: [TR]                       # meeting text languages
    narrate: true
    rm_note: ""
    needs: [D12]                      # decision milestones the checks need (n/a before)
    compare_to: base-p04              # the scenario a sensitivity check compares with
    expect: {...}                     # per-scenario checks (docs/eval.md "Checks")
```
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from rmprep.contracts import NARRATIVE_LANGS, EvidenceSet, Flag, Persona

SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
KNOWN_NEEDS = ("D9", "D12", "D13", "D14", "D15", "I3b", "N5")
_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_TOP = re.compile(r"^@top([1-9][0-9]*)$")


class ScenarioError(ValueError):
    """Invalid scenario. The message names the file and scenario id."""


@dataclass(frozen=True)
class EvidenceEdit:
    """Change the evidence rows of one quantity (optionally one entity, one
    source): set the value, add flags, or drop the rows."""

    quantity: str
    entity: str | None = None       # "@topN": the Nth fund of the clean run
    source: str | None = None
    value: float | None = None
    add_flags: tuple[str, ...] = ()
    drop: bool = False


@dataclass(frozen=True)
class Scenario:
    id: str
    group: str
    persona: str
    description: str = ""
    edit: Mapping[str, Any] = field(default_factory=dict)
    add_constraints: tuple[str, ...] = ()
    exclude_sources: frozenset[str] = frozenset()
    answers: tuple[tuple[str, str], ...] = ()
    snapshot: str | None = None
    evidence_edits: tuple[EvidenceEdit, ...] = ()
    repeat: int = 1
    select: tuple[str, ...] = ()
    select_top: int = 3
    langs: tuple[str, ...] = ("TR",)
    narrate: bool = True
    rm_note: str = ""
    needs: tuple[str, ...] = ()
    compare_to: str | None = None
    expect: Mapping[str, Any] = field(default_factory=dict)


_FIELDS = {f.name for f in dataclasses.fields(Scenario)}
_EDIT_FIELDS = {f.name for f in dataclasses.fields(EvidenceEdit)}
_PERSONA_FIELDS = {f.name for f in dataclasses.fields(Persona)} - {"persona_id"}


def _strs(v, what: str) -> tuple[str, ...]:
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise ValueError(f"{what}: must be a list of non-empty strings, got {v!r}")
    return tuple(v)


def _edit(raw, i: int) -> EvidenceEdit:
    what = f"evidence_edits[{i}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{what}: must be a mapping")
    unknown = sorted(set(raw) - _EDIT_FIELDS)
    if unknown:
        raise ValueError(f"{what}: unknown keys {unknown}")
    if not isinstance(raw.get("quantity"), str):
        raise ValueError(f"{what}: quantity is required")
    for k in ("entity", "source"):
        if k in raw and not isinstance(raw[k], str):
            raise ValueError(f"{what}.{k}: must be a string")
    if str(raw.get("entity", "")).startswith("@") and not _TOP.match(raw["entity"]):
        raise ValueError(f"{what}.entity: a placeholder must be @top<N>, got {raw['entity']!r}")
    value = raw.get("value")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ValueError(f"{what}.value: must be a number")
    flags = _strs(raw.get("add_flags", []), f"{what}.add_flags")
    bad = [f for f in flags if f not in {x.value for x in Flag} or f == Flag.MISSING]
    if bad:
        raise ValueError(f"{what}.add_flags: unknown flag {bad} (use drop for a missing row)")
    drop = raw.get("drop", False)
    if not isinstance(drop, bool):
        raise ValueError(f"{what}.drop: must be true or false")
    if not drop and value is None and not flags:
        raise ValueError(f"{what}: no change (set value, add_flags or drop)")
    if drop and (value is not None or flags):
        raise ValueError(f"{what}: drop cannot be combined with value or add_flags")
    return EvidenceEdit(quantity=raw["quantity"], entity=raw.get("entity"),
                        source=raw.get("source"),
                        value=None if value is None else float(value),
                        add_flags=flags, drop=drop)


def parse_scenario(raw) -> Scenario:
    if not isinstance(raw, Mapping):
        raise ValueError("a scenario must be a mapping")
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ValueError(f"unknown keys {unknown}")
    for k in ("id", "group", "persona"):
        if not isinstance(raw.get(k), str) or not raw[k].strip():
            raise ValueError(f"{k} is required (a non-empty string)")
    if not _ID.match(raw["id"]):
        raise ValueError(f"id {raw['id']!r}: use only letters, digits, '_', '.', '-'")

    kw: dict[str, Any] = {k: raw[k] for k in ("id", "group", "persona")}
    for k in ("description", "rm_note"):
        if k in raw:
            if not isinstance(raw[k], str):
                raise ValueError(f"{k}: must be a string")
            kw[k] = raw[k]
    for k in ("snapshot", "compare_to"):
        if raw.get(k) is not None:
            if not isinstance(raw[k], str) or not raw[k].strip():
                raise ValueError(f"{k}: must be a non-empty string")
            kw[k] = raw[k]
    if "edit" in raw:
        e = raw["edit"]
        if not isinstance(e, Mapping):
            raise ValueError("edit: must be a mapping of persona fields")
        bad = sorted(set(e) - _PERSONA_FIELDS)
        if bad:
            raise ValueError(f"edit: not an editable persona field {bad} "
                             f"(persona_id cannot change)")
        kw["edit"] = {k: tuple(v) if isinstance(v, list) else v for k, v in e.items()}
    if "add_constraints" in raw:
        kw["add_constraints"] = _strs(raw["add_constraints"], "add_constraints")
    if "exclude_sources" in raw:
        kw["exclude_sources"] = frozenset(_strs(raw["exclude_sources"], "exclude_sources"))
    if "answers" in raw:
        a = raw["answers"]
        if not isinstance(a, Mapping) or not all(isinstance(k, str) and isinstance(v, str)
                                                 for k, v in a.items()):
            raise ValueError("answers: must map question ids to answer strings")
        kw["answers"] = tuple(a.items())
    if "evidence_edits" in raw:
        if not isinstance(raw["evidence_edits"], list):
            raise ValueError("evidence_edits: must be a list")
        kw["evidence_edits"] = tuple(_edit(x, i) for i, x in enumerate(raw["evidence_edits"]))
    for k in ("repeat", "select_top"):
        if k in raw:
            v = raw[k]
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(f"{k}: must be an integer >= 1, got {v!r}")
            kw[k] = v
    if "select" in raw:
        kw["select"] = _strs(raw["select"], "select")
    if "langs" in raw:
        langs = _strs(raw["langs"], "langs")
        bad = [x for x in langs if x not in NARRATIVE_LANGS]
        if bad or not langs:
            raise ValueError(f"langs: unknown lang {bad}; known: {NARRATIVE_LANGS}")
        kw["langs"] = langs
    if "narrate" in raw:
        if not isinstance(raw["narrate"], bool):
            raise ValueError("narrate: must be true or false")
        kw["narrate"] = raw["narrate"]
    if "needs" in raw:
        needs = _strs(raw["needs"], "needs")
        bad = [x for x in needs if x not in KNOWN_NEEDS]
        if bad:
            raise ValueError(f"needs: unknown milestone {bad}; known: {KNOWN_NEEDS}")
        kw["needs"] = needs
    if "expect" in raw:
        if not isinstance(raw["expect"], Mapping):
            raise ValueError("expect: must be a mapping")
        kw["expect"] = dict(raw["expect"])
    return Scenario(**kw)


def load_scenario_file(path: Path | str) -> list[Scenario]:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or set(raw) != {"scenarios"} or not isinstance(raw["scenarios"], list):
        raise ScenarioError(f"{path.name}: must have exactly one key 'scenarios' with a list")
    out: list[Scenario] = []
    for i, item in enumerate(raw["scenarios"]):
        sid = item.get("id", f"#{i}") if isinstance(item, Mapping) else f"#{i}"
        try:
            out.append(parse_scenario(item))
        except ValueError as e:
            raise ScenarioError(f"{path.name}: scenario {sid}: {e}") from None
    _unique(out, path.name)
    return out


def _unique(scenarios: Iterable[Scenario], where: str) -> None:
    seen: set[str] = set()
    for s in scenarios:
        if s.id in seen:
            raise ScenarioError(f"{where}: duplicate scenario id {s.id!r}")
        seen.add(s.id)


def load_scenarios(paths: Iterable[Path | str]) -> list[Scenario]:
    """All scenarios of the files, in file order; ids unique across files;
    every compare_to names a scenario of the suite."""
    out = [s for p in paths for s in load_scenario_file(p)]
    _unique(out, "suite")
    ids = {s.id for s in out}
    for s in out:
        if s.compare_to is not None and s.compare_to not in ids:
            raise ScenarioError(f"scenario {s.id}: compare_to {s.compare_to!r} is not in the suite")
    return out


def packaged_scenario_files() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("*.yaml"))


def edit_persona(persona: Persona, s: Scenario) -> Persona:
    """The persona of the scenario: fields replaced, constraints appended
    (checked by Persona itself)."""
    if not s.edit and not s.add_constraints:
        return persona
    d = persona.to_dict() | {k: list(v) if isinstance(v, tuple) else v for k, v in s.edit.items()}
    d["acik_kisitlar"] = list(d["acik_kisitlar"]) + list(s.add_constraints)
    try:
        return Persona.from_dict(d)
    except (ValueError, TypeError) as e:
        raise ScenarioError(f"scenario {s.id}: persona edit: {e}") from None


def top_placeholders(edits: Iterable[EvidenceEdit]) -> bool:
    return any(e.entity is not None and _TOP.match(e.entity) for e in edits)


def resolve_top(edits: Iterable[EvidenceEdit], fund_entities: list[str]) -> tuple[EvidenceEdit, ...]:
    """Replace each entity "@topN" with the Nth entry of fund_entities (the funds
    of the clean run in display order)."""
    out = []
    for e in edits:
        m = _TOP.match(e.entity or "")
        if m:
            n = int(m.group(1))
            if n > len(fund_entities):
                raise ScenarioError(f"evidence edit {e.entity}: the clean run has only "
                                    f"{len(fund_entities)} funds")
            e = dataclasses.replace(e, entity=fund_entities[n - 1])
        out.append(e)
    return tuple(out)


def apply_evidence_edits(ev: EvidenceSet, edits: Iterable[EvidenceEdit],
                         snapshot_id: str) -> EvidenceSet:
    """A copy of ev with the edits applied, under its own snapshot_id (so the
    run_id differs from a run on the clean snapshot)."""
    rows = list(ev.datapoints)
    for e in edits:
        hits = [i for i, d in enumerate(rows)
                if d.quantity == e.quantity and e.entity in (None, d.entity)
                and e.source in (None, d.source)]
        if not hits:
            raise ScenarioError(f"evidence edit {e}: matches no row")
        if e.drop:
            drop = set(hits)
            rows = [d for i, d in enumerate(rows) if i not in drop]
            continue
        for i in hits:
            d = rows[i]
            flags = set(d.flags) | {Flag(f) for f in e.add_flags}
            value = d.value
            if e.value is not None:
                value = e.value
                flags.discard(Flag.MISSING)
            note = "; ".join(x for x in (d.note, "eval: edited") if x)
            rows[i] = dataclasses.replace(d, value=value, flags=frozenset(flags), note=note)
    return dataclasses.replace(ev, snapshot_id=snapshot_id, datapoints=tuple(rows))
