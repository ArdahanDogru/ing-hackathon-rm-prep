"""Shared helpers of the eval tests: a RealBackend root in tmp_path on the
fixture evidence (no snapshot, no network) and a fake narrator."""

from __future__ import annotations

import dataclasses
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from rmprep import backend as be
from rmprep.contracts import (
    TR_TZ, EvidenceSet, NarrativeDraft, NarrativeSection, NarrativeSentence, SourceStatus,
)

PROJECT = Path(__file__).resolve().parents[2]
CONTRACT_FIX = PROJECT / "tests" / "contracts" / "fixtures"
FIX = Path(__file__).resolve().parent / "fixtures"
T0 = datetime(2026, 10, 10, 9, 0, tzinfo=TR_TZ)
SNAP = "20261010-001233-6b20"


def eval_yaml(snapshot: str | None = None) -> str:
    """The project config/eval.yaml with the snapshot line set to `snapshot`
    (null by default), so tests do not depend on the real frozen snapshot."""
    text = (PROJECT / "config" / "eval.yaml").read_text(encoding="utf-8")
    value = "null" if snapshot is None else f'"{snapshot}"'
    new, n = re.subn(r"(?m)^snapshot:[^\n#]*", f"snapshot: {value} ", text)
    assert n == 1, "config/eval.yaml has no top-level snapshot line"
    return new


def fixture_evidence() -> EvidenceSet:
    d = json.loads((CONTRACT_FIX / "evidence_medium.json").read_text(encoding="utf-8"))
    return EvidenceSet.from_dict(d)


@pytest.fixture
def builds() -> list:
    return []


@pytest.fixture
def extra_rows() -> list:
    """DataPoints a test adds to the fixture evidence (before the backend builds it)."""
    return []


@pytest.fixture
def dropped_rows() -> list:
    """Predicates on DataPoints: matching fixture rows are removed."""
    return []


@pytest.fixture
def renamed() -> dict:
    """entity -> new fund name in EvidenceSet.entities."""
    return {}


@pytest.fixture
def root(monkeypatch, tmp_path, builds, extra_rows, dropped_rows, renamed):
    """A project root with config/ copied; build_evidence serves the fixture
    evidence (minus `dropped_rows`, plus `extra_rows` - a new source gets status
    ok -, entities renamed by `renamed`) and records its calls in `builds`."""
    base = fixture_evidence()

    def fake_build(snapshots, snapshot_id, exclude=frozenset()):
        status = dict(base.source_status)
        for d in extra_rows:
            status.setdefault(d.source, SourceStatus("ok"))
        rows = tuple(d for d in base.datapoints if not any(f(d) for f in dropped_rows))
        entities = {k: dataclasses.replace(v, name=renamed.get(k, v.name))
                    for k, v in base.entities.items()}
        ev = dataclasses.replace(base, source_status=status, entities=entities,
                                 datapoints=rows + tuple(extra_rows))
        if snapshot_id != ev.snapshot_id:
            raise ValueError(f"no snapshot {snapshot_id}")
        unknown = set(exclude) - set(ev.source_status)
        if unknown:
            raise ValueError(f"unknown sources {sorted(unknown)}")
        builds.append((snapshot_id, frozenset(exclude)))
        return dataclasses.replace(ev, excluded_sources=frozenset(exclude))

    class Snap:
        snapshot_id = base.snapshot_id

    monkeypatch.setattr(be, "build_evidence", fake_build)
    monkeypatch.setattr(be, "list_snapshots", lambda snapshots: [Snap()])
    (tmp_path / "config").mkdir()
    for name in ("decision.yaml", "narrator.yaml"):
        (tmp_path / "config" / name).write_bytes((PROJECT / "config" / name).read_bytes())
    (tmp_path / "config" / "eval.yaml").write_text(eval_yaml(), encoding="utf-8")
    return tmp_path


class FakeNarrator:
    """Narrator.draft without an LLM: one sentence per selected option, cached
    per (run_id, lang) like the real one; each new text costs `cost`."""

    def __init__(self, cost: float = 0.0, text: str = "Seçilen ürün: {label}."):
        self.cost = cost
        self.text = text
        self.calls: list[tuple[str, str]] = []
        self.cache: dict[tuple[str, str], NarrativeDraft] = {}
        self.spent = 0.0

    def spent_today(self) -> float:
        return self.spent

    def draft(self, r, ev, lang):
        key = (r.run_id, lang)
        if key in self.cache:
            return self.cache[key]
        self.calls.append(key)
        self.spent += self.cost
        labels = {o.option.option_id: o.option.label for o in r.options}
        sentences = tuple(NarrativeSentence(self.text.format(label=labels[i]), (i,))
                          for i in r.rm_selected)
        d = NarrativeDraft(r.run_id, lang, (NarrativeSection("oneriler", sentences),),
                           "llm", "fake-model", "fake", (), T0, cost_usd=self.cost)
        self.cache[key] = d
        return d


# --- E11: the agent (fake model, fake research) -------------------------------------

AGENT_MODEL = "claude-sonnet-5-5"


def agent_root(root: Path) -> Path:
    """The tmp root with config/agent.yaml copied (the agent's prices and texts)."""
    (root / "config" / "agent.yaml").write_bytes((PROJECT / "config" / "agent.yaml").read_bytes())
    return root


def pack_of(messages: list[dict]) -> dict:
    text = messages[0]["content"][0]["text"]
    return json.loads(text.removeprefix("<veri>\n").removesuffix("\n</veri>"))


class PackClient:
    """A fake agent model: reads the data pack and calls karar_ver at once.
    mode "keep": the engine's top 3; mode "swap": the engine's #1 is replaced by the
    best other candidate of the same kind and asset class (so the caps still hold).
    `web`: the first pick also cites its first research finding. Each step costs
    1000 input and 200 output tokens."""

    def __init__(self, mode: str = "keep", *, web: bool = False, block=None):
        self.mode = mode
        self.web = web
        self.block = block              # a threading.Event: step waits for it
        self.calls = 0
        self.packs: list[dict] = []

    @staticmethod
    def _reason(cand: dict) -> dict:
        return {"metin": "Puanı adaylar arasında güçlü.",
                "kaynaklar": [cand["puan_parcalari"][0]["id"]]}

    def step(self, system, messages, tools):
        from rmprep.agent.client import AgentTurn, ToolCall

        if self.block is not None:
            self.block.wait(10)
        self.calls += 1
        pack = pack_of(messages)
        self.packs.append(pack)
        cands = {c["option_id"]: c for c in pack["adaylar"]}
        top = list(pack["motor_ilk3"])
        picks, dropped = list(top), []
        if self.mode == "swap":
            first = cands[top[0]]
            alt = next((c for c in pack["adaylar"] if c["option_id"] not in top
                        and c["tur"] == first["tur"]
                        and c["varlik_sinifi"] == first["varlik_sinifi"]), None)
            if alt is not None:
                picks = [alt["option_id"], *top[1:]]
                dropped = [top[0]]
        secimler = []
        for i, oid in enumerate(picks):
            reasons = [self._reason(cands[oid])]
            found = pack["arastirma"].get(oid, {}).get("bulgular", [])
            if self.web and i == 0 and found:
                reasons.append({"metin": "Web bulgusu ürünü destekliyor.",
                                "kaynaklar": [found[0]["id"]]})
            secimler.append({"option_id": oid, "gerekceler": reasons})
        inp = {"secimler": secimler,
               "cikanlar": [{"option_id": o, "gerekce": self._reason(cands[o])} for o in dropped],
               "ozet": "Müşterinin profiline en uygun üç ürün seçildi.", "amac": "Son karar."}
        call = ToolCall(f"toolu_{self.calls:04d}", "karar_ver", inp)
        return AgentTurn((call,), 1000, 200, "tool_use", AGENT_MODEL)


class AgentFakeResearch:
    """research_many: one highlight per product (no number, no date); ask_product: one
    finding. Records the calls."""

    def __init__(self):
        self.many_calls: list[list[str]] = []

    def research_many(self, options, lang):
        from rmprep.research.types import Finding, ProductResearch, Source

        self.many_calls.append([o.option_id for o in options])
        return [ProductResearch(
            o.option_id, o.label, "Örnek Portföy", "", (Finding(
                f"{o.label} kısa vadeli araçlara yatırım yapar.", "urun",
                (Source("https://www.tefas.gov.tr/fon", "Fon"),)),), lang, "exa", T0)
            for o in options]

    def ask_product(self, option, question, lang, persona=None):
        return "not used"
