"""Web research service (docs/research.md sections 4 and 9): researches a run's
recommended products in the background, answers RM questions, and keeps the
cache, the cost ledger and the daily limit. Providers run in the config order;
only auth, credit, server and connection errors fall back to the next one.

Research is per product, not per client: the cache key is (option id, language,
Turkish date, shape version). Every provider result is shaped (shape.py) before it
is cached, so the cache holds what the panel shows; v1 files are never read. A
failed product is not cached; `start` (a new run view) tries it again, `status` (polling) never does, so a lasting error ends the polling."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, TypeVar

from rmprep.contracts import TR_TZ, DecisionResult, DecisionState, ProductOption
from rmprep.research.checks import check_question
from rmprep.research.config import ResearchConfig, load_config
from rmprep.research.shape import shape_answer, shape_product
from rmprep.research.types import SHAPE_VERSION, ProductResearch, QuestionAnswer, ResearchError

RESEARCHED_KINDS = ("fund", "etf", "stock")      # deposit, time_deposit: ING's own products
FALLBACK_KINDS = ("auth", "credit", "server", "connection")
LIMIT_ERROR = "daily limit"

T = TypeVar("T", ProductResearch, QuestionAnswer)


class SearchProvider(Protocol):
    name: str

    def research_product(self, option: ProductOption, lang: str) -> ProductResearch: ...

    def answer_question(self, question: str, products: Sequence[ProductOption],
                        lang: str) -> QuestionAnswer: ...


class QuestionRefused(ValueError):
    """The question may not go to a provider; the message is the reason for the RM."""


def researchable(option: ProductOption) -> bool:
    return option.kind in RESEARCHED_KINDS


def research_products(result: DecisionResult) -> list[ProductOption]:
    """The recommended options that are researched, in the recommended order."""
    by_id = {s.option.option_id: s.option for s in result.options}
    return [by_id[i] for i in result.recommended if i in by_id and researchable(by_id[i])]


class ResearchService:
    def __init__(self, config: ResearchConfig, providers: Sequence[SearchProvider],
                 cache_root: Path | str, *,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
                 off_reason: str = "", max_workers: int = 3) -> None:
        self._config = config
        self._providers = tuple(providers)
        self._root = Path(cache_root)
        self._now = now
        self._off_reason = off_reason or "no provider key"
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research")
        self._jobs: dict[tuple[str, str, date], Future] = {}
        self._lock = threading.Lock()
        self._ledger_lock = threading.Lock()
        self._spent: dict[str, float] = {}      # Turkish day -> USD, also when the ledger cannot be written

    @property
    def enabled(self) -> bool:
        return bool(self._providers)

    # --- products -------------------------------------------------------------

    def start(self, result: DecisionResult, lang: str = "TR") -> None:
        """Starts the research of the run's products (idempotent; retries failed ones)."""
        self._jobs_for(result, lang, self._now().date(), retry=True)

    def status(self, result: DecisionResult, lang: str) -> dict:
        """{"state": "off", "reason"} | {"state": "running"} |
        {"state": "ready", "products": [...], "questions": [...]} (JSON-ready)."""
        if not self._providers:
            return {"state": "off", "reason": self._off_reason}
        jobs = self._jobs_for(result, lang, self._now().date(), retry=False)
        if any(not j.done() for j, _ in jobs):
            return {"state": "running"}
        return {"state": "ready", "products": [self._job_result(j, o, lang).to_dict() for j, o in jobs],
                "questions": [q.to_dict() for q in self.questions(result.run_id, lang)]}

    def wait(self) -> None:
        """Waits for every started job (tests)."""
        with self._lock:
            jobs = list(self._jobs.values())
        wait(jobs)

    def _jobs_for(self, result: DecisionResult, lang: str,
                  day: date, *, retry: bool) -> list[tuple[Future, ProductOption]]:
        if not self._providers or result.state != DecisionState.READY:
            return []
        jobs = []
        with self._lock:
            for opt in research_products(result):
                key = (opt.option_id, lang, day)
                job = self._jobs.get(key)
                failed = job is not None and job.done() and (
                    job.exception() is not None or bool(job.result().error))
                if job is None or (retry and failed):
                    job = self._jobs[key] = self._pool.submit(self._product, opt, lang, day)
                jobs.append((job, opt))
        return jobs

    def _product(self, opt: ProductOption, lang: str, day: date) -> ProductResearch:
        name = f"{opt.option_id.replace(':', '_')}-{lang}-{day:%Y%m%d}-v{SHAPE_VERSION}.json"
        path = self._root / "products" / name
        try:
            cached = _read(path, ProductResearch)
            if cached is not None:
                return cached
            out = self._call(lambda p: p.research_product(opt, lang), "product", opt.option_id)
        except Exception as e:          # a provider bug must not break the panel
            out = f"{type(e).__name__}: {e}"
        if isinstance(out, str):
            return ProductResearch(opt.option_id, opt.label, "", "", (), lang, "", self._now(),
                                   error=out, news_days=self._config.shape.news_days)
        out = shape_product(out, self._config.shape, day)
        _try_write(path, out)
        return out

    # --- questions ------------------------------------------------------------

    def ask(self, result: DecisionResult, question: str, lang: str) -> QuestionAnswer:
        """The answer (cached per run, language and question), or one with `error`.
        Raises QuestionRefused when research is off or the question check refuses it."""
        if not self._providers:
            raise QuestionRefused(self._off_reason)
        reason = check_question(question, result.persona, lang, self._config.client_words,
                                self._config.question_max_chars)
        if reason:
            raise QuestionRefused(reason)
        q = question.strip()
        digest = hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]
        path = self._root / "questions" / f"{result.run_id}-{lang}-v{SHAPE_VERSION}-{digest}.json"
        cached = _read(path, QuestionAnswer)
        if cached is not None:
            return cached
        products = research_products(result)
        try:
            out = self._call(lambda p: p.answer_question(q, products, lang), "question", path.stem)
        except Exception as e:
            out = f"{type(e).__name__}: {e}"
        if isinstance(out, str):
            return QuestionAnswer(q, "", (), lang, "", self._now(), error=out)
        out = shape_answer(out, self._config.shape)
        _try_write(path, out)
        return out

    def questions(self, run_id: str, lang: str) -> list[QuestionAnswer]:
        files = (self._root / "questions").glob(f"{run_id}-{lang}-v{SHAPE_VERSION}-*.json")
        found = (_read(p, QuestionAnswer) for p in files)
        return sorted((q for q in found if q is not None), key=lambda q: q.created_at)

    # --- providers, cost ------------------------------------------------------

    def _call(self, fn: Callable[[SearchProvider], T], kind: str, ref: str) -> T | str:
        """The first provider's result, or an error text: "daily limit" or
        "exa: credit; claude: auth" (the kinds of the failed providers)."""
        errors: list[str] = []
        for p in self._providers:
            if self.spent_today() >= self._config.max_cost_usd_per_day:
                return LIMIT_ERROR
            try:
                out = fn(p)
            except ResearchError as e:
                if e.cost_usd > 0:                  # a paid call with a bad reply still costs money
                    self._record(p.name, kind, ref, e.cost_usd)
                errors.append(f"{p.name}: {e.kind}")
                if e.kind in FALLBACK_KINDS:
                    continue
                break
            self._record(p.name, kind, ref, out.cost_usd)
            return out
        return "; ".join(errors) or "no provider"

    def spent_today(self) -> float:
        """USD spent today: the larger of the ledger file and the in-memory total. The guard
        fails closed: a ledger that cannot be read gives infinity (calls stop with the limit
        error); only a missing ledger file is zero."""
        today = self._now().date().isoformat()
        with self._ledger_lock:
            memory = self._spent.get(today, 0.0)
        try:
            lines = (self._root / "costs.jsonl").read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return memory
        except OSError:
            return math.inf
        total = 0.0
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if str(row.get("at", ""))[:10] == today:
                total += float(row.get("cost_usd") or 0.0)
        return max(total, memory)

    def _job_result(self, job: Future, opt: ProductOption, lang: str) -> ProductResearch:
        exc = job.exception()
        if exc is None:
            return job.result()
        return ProductResearch(opt.option_id, opt.label, "", "", (), lang, "", self._now(),
                               error=f"{type(exc).__name__}: {exc}",
                               news_days=self._config.shape.news_days)

    def _record(self, provider: str, kind: str, ref: str, cost: float) -> None:
        """Adds a paid call to the in-memory total, then to the ledger file. A file error
        never loses the result of the call: the in-memory total still counts."""
        now = self._now()
        row = {"at": now.isoformat(), "provider": provider, "kind": kind, "ref": ref,
               "cost_usd": round(cost, 6)}
        with self._ledger_lock:
            day = now.date().isoformat()
            self._spent[day] = self._spent.get(day, 0.0) + cost
            try:
                self._root.mkdir(parents=True, exist_ok=True)
                with (self._root / "costs.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            except OSError:
                pass


def _read(path: Path, cls):
    try:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj.to_dict(), ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8", newline="\n")


def _try_write(path: Path, obj) -> None:
    """The result is still returned when the cache cannot be written (only uncached);
    its cost is already in the ledger."""
    try:
        _write(path, obj)
    except OSError:
        pass


def research_from_root(root: Path | str, env: Mapping[str, str] | None = None) -> ResearchService:
    """The service of a prototype root: config/research.yaml, keys from the
    environment or root/.env (environment wins), cache under root. A provider
    without its key is left out; none left -> research is off."""
    root = Path(root)
    config = load_config(root / "config" / "research.yaml")
    if env is None:
        from dotenv import dotenv_values
        env = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
        env.update(os.environ)
    providers: list[SearchProvider] = []
    for name in config.providers:
        if name == "exa":
            key = env.get(config.exa.api_key_env, "").strip()
            if key:
                from rmprep.research.exa import ExaProvider
                providers.append(ExaProvider(config.exa, config.system_prompt, key,
                                             highlights_prompt=config.highlights_prompt,
                                             news_days=config.shape.news_days))
        elif name == "claude" and config.claude is not None:
            from rmprep.research.claude_search import ClaudeSearchProvider
            p = ClaudeSearchProvider.from_env(config.claude, config.system_prompt,
                                              config.exa.exclude_domains, env,
                                              highlights_prompt=config.highlights_prompt)
            if p is not None:
                providers.append(p)
    off = "" if providers else f"no key in .env: {config.exa.api_key_env}"
    return ResearchService(config, providers, root / config.cache_dir, off_reason=off)
