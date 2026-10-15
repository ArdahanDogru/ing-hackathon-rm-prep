"""Shared helpers of the agent tests (A1, docs/agent.md): a scripted fake model,
a fake research service, real engine runs on the shared test evidence, and the
test copy of config/agent.yaml. No test touches the network."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from rmprep.agent.client import AgentTurn, ToolCall
from rmprep.agent.config import AgentConfig, load_agent_config
from rmprep.contracts import TR_TZ, DecisionResult, EvidenceSet, Persona
from rmprep.decision.config import DecisionConfig
from rmprep.decision.config import load_config as load_decision_config
from rmprep.research.types import Finding, ProductResearch, QuestionAnswer, Source

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONTRACT_FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures"
CREATED = datetime(2026, 10, 15, 10, 0, tzinfo=TR_TZ)
MODEL = "claude-sonnet-5-5"


def _read(name: str) -> dict:
    return json.loads((CONTRACT_FIX / name).read_text(encoding="utf-8"))


def evidence() -> EvidenceSet:
    return EvidenceSet.from_dict(_read("evidence_medium.json"))


def persona(pid: str) -> Persona:
    return Persona.from_dict(_read(f"personas/{pid}.json"))


_RUNS: dict[str, DecisionResult] = {}


def ready(pid: str) -> DecisionResult:
    """A real engine run on evidence_medium (ready, not approved)."""
    from rmprep.decision.engine import decide

    if pid not in _RUNS:
        _RUNS[pid] = decide(evidence(), persona(pid), load_decision_config(), created_at=CREATED)
    return _RUNS[pid]


@pytest.fixture(scope="session")
def cfg() -> AgentConfig:
    return load_agent_config(FIXTURES / "agent.yaml")


@pytest.fixture(scope="session")
def dcfg() -> DecisionConfig:
    return load_decision_config()


@pytest.fixture(scope="session")
def phrases() -> tuple[str, ...]:
    from rmprep.narrator.config import load_config

    return tuple(dict.fromkeys(p for ps in load_config().forbidden_phrases.values() for p in ps))


@pytest.fixture(scope="session")
def ev() -> EvidenceSet:
    return evidence()


@pytest.fixture(scope="session")
def ready_p01() -> DecisionResult:
    return ready("p01")


@pytest.fixture(scope="session")
def ready_p03() -> DecisionResult:
    return ready("p03")


# --- fake research -------------------------------------------------------------

def finding(text: str, url: str = "https://www.kap.org.tr/x", topic: str = "urun",
            date: str = "") -> Finding:
    return Finding(text, topic, (Source(url, "Başlık", date),), "medium", date)


class FakeResearch:
    """research_many: one highlight and one news item per product; `texts`
    overrides the highlight text of an option, `errors` makes a product fail."""

    def __init__(self, texts: dict[str, str] | None = None, errors: set[str] = frozenset(),
                 answer: QuestionAnswer | str | None = None, raise_many: bool = False,
                 block=None, marks: dict[str, str] | None = None):
        self.texts = texts or {}
        self.errors = set(errors)
        self.answer = answer
        self.raise_many = raise_many
        self.block = block                      # a threading.Event: research_many waits for it
        self.personas: list = []
        self.marks_map = marks if marks is not None else {}     # finding id -> ok | wrong (R4)
        self.many_calls: list[list[str]] = []
        self.questions: list[tuple[str, str]] = []

    def research_many(self, options, lang):
        self.many_calls.append([o.option_id for o in options])
        if self.block is not None:
            self.block.wait(5)
        if self.raise_many:
            raise RuntimeError("research down")
        out = []
        for o in options:
            if o.option_id in self.errors:
                out.append(ProductResearch(o.option_id, o.label, "", "", (), lang, "", CREATED,
                                           error="connection: timeout"))
                continue
            text = self.texts.get(o.option_id, f"{o.label} para piyasası araçlarına yatırım yapar.")
            out.append(ProductResearch(
                o.option_id, o.label, "Örnek Portföy", "Özet metni (gösterilmez).",
                (finding(text, "https://www.tefas.gov.tr/fon"),), lang, "exa", CREATED,
                cost_usd=0.01,
                news=(finding("Fon büyüklüğü 2025'te %12 arttı.", "https://www.bloomberght.com/a",
                              "haber", "2026-09-30"),), news_days=90))
        return out

    def marks(self):
        return dict(self.marks_map)

    def ask_product(self, option, question, lang, persona=None):
        self.questions.append((option.option_id, question))
        self.personas.append(persona)
        if self.answer is not None:
            return self.answer
        return QuestionAnswer(question, "Yanıt özeti.",
                              (finding(f"{option.label} için yönetim ücreti yıllık %1,5.",
                                       "https://www.kap.org.tr/y"),),
                              lang, "exa", CREATED, cost_usd=0.02)


# --- scripted model --------------------------------------------------------------

class ScriptedClient:
    """Plays fixed turns; records what it was sent. `tick` advances a fake clock
    on each step (a slow model)."""

    def __init__(self, *turns, clock=None, tick: float = 0.0):
        self.turns = list(turns)
        self.sent: list[tuple[str, list[dict], list[dict]]] = []
        self.clock = clock
        self.tick = tick

    def step(self, system, messages, tools):
        self.sent.append((system, json.loads(json.dumps(messages)), tools))
        if self.clock is not None:
            self.clock.t += self.tick
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


_N = [0]


def call(name: str, **inp) -> ToolCall:
    _N[0] += 1
    return ToolCall(f"toolu_{_N[0]:04d}", name, inp)


def turn(*calls: ToolCall, inp: int = 1000, out: int = 200) -> AgentTurn:
    return AgentTurn(tuple(calls), inp, out, "tool_use" if calls else "end_turn", MODEL)


def pack_of(messages: list[dict]) -> dict:
    """The data pack of the first user message: block 1 <veri> (stable), block 2
    <arastirma> (research with the marks) and the task text."""
    blocks = messages[0]["content"]
    pack = json.loads(blocks[0]["text"].removeprefix("<veri>\n").removesuffix("\n</veri>"))
    text = blocks[1]["text"]
    start = text.index("<arastirma>\n") + len("<arastirma>\n")
    pack["arastirma"] = json.loads(text[start:text.index("\n</arastirma>")])
    return pack


def cand_ids(result: DecisionResult) -> list[str]:
    return [o.option.option_id for o in result.options if o.option.kind != "deposit"][:10]


def valid_picks(result: DecisionResult) -> list[str]:
    """P01: BBF, AAL, EIL (the engine's AIS is dropped)."""
    ids = cand_ids(result)
    return [ids[1], ids[3], ids[0]]


def reason(text: str, *cites: str) -> dict:
    return {"metin": text, "kaynaklar": list(cites)}


def karar(result: DecisionResult, picks: list[str], **over) -> dict:
    """A karar_ver input that passes the checks for P01: every pick cites its
    return score part; the first also the estimated debt class."""
    secimler = []
    for i, oid in enumerate(picks):
        rs = [reason("Getiri puanı adaylar arasında güçlü.", "puan:return")]
        if i == 0:
            rs.append(reason("Borçlanma payı düşük, model bandına göre eksik.", "portfoy:borclanma"))
        secimler.append({"option_id": oid, "gerekceler": rs})
    dropped = [o for o in result.recommended if o not in picks]
    cikanlar = [{"option_id": o, "gerekce": reason("Likidite cezası daha yüksek.",
                                                   "puan:penalty_liquidity")} for o in dropped]
    d = {"secimler": secimler, "cikanlar": cikanlar,
         "ozet": "Borçlanma eksikliği ve getiri dengesi öne alındı.", "amac": "Son karar."}
    d.update(over)
    return d


@pytest.fixture
def svc_factory(cfg, dcfg, phrases, tmp_path):
    from rmprep.agent.service import AgentService

    def make(client, research=None, *, clock=None, now=None, root=None, **kw):
        research = FakeResearch() if research is None else research
        return AgentService(cfg, client, research, dcfg, phrases, root or tmp_path / "agent",
                            now=now or (lambda: CREATED + timedelta(minutes=1)),
                            clock=clock or FakeClock(), **kw)
    return make
