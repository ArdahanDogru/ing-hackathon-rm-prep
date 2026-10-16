"""F1: the manual feedback report (spec docs/superpowers/specs/2026-10-16-feedback-report-
design.md): measures of the RM action log (L1, data/logs/rm-actions/*.jsonl) and
recommendations by fixed rules (config/feedback.yaml). No LLM, no network, no cost;
the same log gives the same report (only the creation time differs).

Rules (per group; a group below min_n gives "Yeterli veri yok (n/min_n)"):
  R1 ✗ share of the research marks (the last mark of each finding)   asset class × section
  R2 deletion share of a meeting-text section: approved runs with a deletion / approved runs
  R3 edit share of a section, with examples (before → after)        section
  R4 acceptance: the RM's selected options in the engine's / the agent's top 3, on the
     approvals with an agent decision; the agent lower by more than the threshold
  R5 error of the D27 estimate: mean |RM split - estimate| per source (and profile row)
     × class

Versions (L1b): every measure is computed per value of the version parts that it
depends on (R1 research, R2/R3 narrator_prompt, R4 agent_prompt + decision_config,
R5 decision_config); a record without `versions` is the column "sürüm yok".
A record without a field that its measure needs (written before L1b) is skipped
for that measure and counted as "eksik alan" (missing field)."""

from __future__ import annotations

import json
import statistics
import string
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from rmprep.contracts import TR_TZ

LOG_DIR = Path("data") / "logs" / "rm-actions"
OUT_DIR = Path("data") / "feedback"
RULE_IDS = ("R1", "R2", "R3", "R4", "R5")
LANGS = ("TR", "EN")
NO_VERSION = "sürüm yok"
MISSING = "eksik alan"
MARKS = ("ok", "wrong")
SECTIONS = ("news", "highlight")
BASE_KEYS = {"min_n", "threshold", "text"}
RULE_KEYS = {"R1": BASE_KEYS | {"actions"}, "R2": BASE_KEYS, "R3": BASE_KEYS | {"examples"},
             "R4": BASE_KEYS, "R5": BASE_KEYS}
FIELDS = {"R1": {"asset_class", "section", "share", "wrong", "n", "action"},
          "R2": {"section", "share", "deleted", "n"},
          "R3": {"section", "share", "edited", "n"},
          "R4": {"agent_share", "engine_share", "n", "diff"},
          "R5": {"source", "asset_class", "error", "n"}}
VERSION_PARTS = {"R1": ("research",), "R2": ("narrator_prompt",), "R3": ("narrator_prompt",),
                 "R4": ("agent_prompt", "decision_config"), "R5": ("decision_config",)}
TITLES = {
    "R1": ("Araştırma işaretleri (✗ payı)",
           "✗ / (✓ + ✗), her bulgunun son işareti; varlık sınıfı × bölüm (news, highlight)"),
    "R2": ("Metin bölümü silme payı",
           "bölümü silinen onaylı çalıştırmalar / onaylı çalıştırmalar; bölüm"),
    "R3": ("Metin bölümü düzenleme payı",
           "bölümü düzenlenen onaylı çalıştırmalar / onaylı çalıştırmalar; bölüm"),
    "R4": ("Kabul (RM seçimi)",
           "RM'in seçtiği ürünlerden motorun ve ajanın ilk 3'ünde olanların payı; ajan "
           "kararı olan onaylar"),
    "R5": ("D27 tahmin hatası",
           "RM bölünmesi ile tahmin arasındaki ortalama mutlak fark (puan); kaynak (meslek "
           "satırı veya ulusal) × sınıf"),
}
EXAMPLE_CHARS = 160


class FeedbackConfigError(ValueError):
    """Invalid config/feedback.yaml. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class RuleConfig:
    id: str
    min_n: int
    threshold: float
    text: Mapping[str, str]                              # TR, EN with named fields
    actions: Mapping[str, Mapping[str, str]] = field(default_factory=dict)   # R1
    examples: int = 0                                    # R3


@dataclass(frozen=True)
class FeedbackConfig:
    rules: Mapping[str, RuleConfig]
    evidence_max: int
    labels: Mapping[str, str] = field(default_factory=dict)

    def label(self, key: str) -> str:
        return self.labels.get(key, key)


# --- config ------------------------------------------------------------------------------

def _keys(node: Any, path: str, required: set[str], optional: set[str] = frozenset()) -> Mapping:
    if not isinstance(node, Mapping):
        raise FeedbackConfigError(f"{path or '<root>'}: must be a mapping")
    unknown = sorted(set(node) - required - optional)
    if unknown:
        raise FeedbackConfigError(f"{path or '<root>'}: unknown keys {unknown}")
    missing = sorted(required - set(node))
    if missing:
        raise FeedbackConfigError(f"{path or '<root>'}: missing keys {missing}")
    return node


def _texts(node: Any, path: str, allowed: set[str]) -> dict[str, str]:
    node = _keys(node, path, set(LANGS))
    out = {}
    for lang in LANGS:
        v = node[lang]
        if not isinstance(v, str) or not v.strip():
            raise FeedbackConfigError(f"{path}.{lang}: must be a non-empty string")
        try:
            names = {f for _, f, _, _ in string.Formatter().parse(v) if f is not None}
        except ValueError as e:
            raise FeedbackConfigError(f"{path}.{lang}: {e}") from None
        bad = sorted(names - allowed)
        if bad:
            raise FeedbackConfigError(f"{path}.{lang}: unknown field {bad}; known: "
                                      f"{sorted(allowed)}")
        out[lang] = v
    return out


def _int(v: Any, path: str, lo: int) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < lo:
        raise FeedbackConfigError(f"{path}: must be an integer >= {lo}, got {v!r}")
    return v


def parse_feedback_config(raw: Any) -> FeedbackConfig:
    raw = _keys(raw, "", {"version", "rules", "evidence_max"}, {"labels"})
    if raw["version"] != 1:
        raise FeedbackConfigError(f"version: must be 1, got {raw['version']!r}")
    rules_raw = _keys(raw["rules"], "rules", set(RULE_IDS))
    rules = {}
    for rid in RULE_IDS:
        path = f"rules.{rid}"
        r = _keys(rules_raw[rid], path, RULE_KEYS[rid])
        threshold = r["threshold"]
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold < 0:
            raise FeedbackConfigError(f"{path}.threshold: must be a number >= 0, got "
                                      f"{threshold!r}")
        actions = {}
        if rid == "R1":
            a = _keys(r["actions"], f"{path}.actions", set(SECTIONS))
            actions = {s: _texts(a[s], f"{path}.actions.{s}", set()) for s in SECTIONS}
        rules[rid] = RuleConfig(
            rid, _int(r["min_n"], f"{path}.min_n", 1), float(threshold),
            _texts(r["text"], f"{path}.text", FIELDS[rid]), actions,
            _int(r["examples"], f"{path}.examples", 0) if rid == "R3" else 0)
    labels = raw.get("labels") or {}
    if not isinstance(labels, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in labels.items()):
        raise FeedbackConfigError("labels: must map keys to non-empty strings")
    return FeedbackConfig(rules, _int(raw["evidence_max"], "evidence_max", 1), dict(labels))


def load_feedback_config(path: Path | str) -> FeedbackConfig:
    return parse_feedback_config(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


# --- the log -------------------------------------------------------------------------------

@dataclass(frozen=True)
class Record:
    file: str
    line: int
    day: date
    data: Mapping[str, Any]

    @property
    def at(self) -> str:
        return f"{self.file}:{self.line}"

    @property
    def action(self) -> str:
        return str(self.data.get("action", ""))

    @property
    def details(self) -> Mapping[str, Any]:
        d = self.data.get("details")
        return d if isinstance(d, Mapping) else {}

    def version(self, parts: Iterable[str]) -> str:
        v = self.data.get("versions")
        if not isinstance(v, Mapping):
            return NO_VERSION
        return ", ".join(f"{p}={v.get(p, '')}" for p in parts)


def _day(rec: Mapping, file_day: date | None) -> date | None:
    try:
        return datetime.fromisoformat(str(rec["ts"])).astimezone(TR_TZ).date()
    except (KeyError, TypeError, ValueError):
        return file_day


def read_log(folder: Path, since: date | None = None,
             until: date | None = None) -> tuple[list[Record], list[str], list[str]]:
    """(records in the period in file and line order, files with a record of the period,
    broken lines as file:line)."""
    records: list[Record] = []
    files: list[str] = []
    broken: list[str] = []
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else ():
        try:
            file_day: date | None = date.fromisoformat(path.stem)
        except ValueError:
            file_day = None
        used = False
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except ValueError:
                data = None
            day = _day(data, file_day) if isinstance(data, Mapping) else None
            if day is None:
                broken.append(f"{path.name}:{i}")
                continue
            if (since is not None and day < since) or (until is not None and day > until):
                continue
            records.append(Record(path.name, i, day, data))
            used = True
        if used:
            files.append(path.name)
    return records, files, broken


def section_of(block_id: str) -> str:
    """The section key of a meeting-text block: talking_points:<i> -> talking_points,
    oneriler:<id> -> oneriler, else the block id."""
    return str(block_id).split(":", 1)[0]


# --- formatting --------------------------------------------------------------------------

def pct(x: float | None, lang: str) -> str:
    if x is None:
        return "-"
    v = round(100 * x)
    return f"%{v}" if lang == "TR" else f"{v}%"


def num(x: float | None, lang: str) -> str:
    if x is None:
        return "-"
    s = f"{x:.1f}".removesuffix(".0")
    return s.replace(".", ",") if lang == "TR" else s


def _version_order(v: str) -> tuple:
    return (v == NO_VERSION, v)


# --- measures ------------------------------------------------------------------------------

@dataclass
class _Group:
    version: str
    key: dict[str, Any]
    label: str
    n: int
    value: float | None
    records: list[Record]
    extra: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)    # lang -> text fields
    above: bool = False


class _Report:
    def __init__(self, cfg: FeedbackConfig, records: list[Record]):
        self.cfg = cfg
        self.records = records
        self.missing: dict[str, list[Record]] = defaultdict(list)
        self.test_runs: dict[str, Record] = {}       # W30: approvals of an edited profile

    def of(self, *actions: str) -> list[Record]:
        return [r for r in self.records if r.action in actions]

    def approvals(self) -> dict[str, Record]:
        """The last decision_approved record of each run. W30: an approval of an edited
        profile (details.test_run) is left out and kept in self.test_runs."""
        out: dict[str, Record] = {}
        for r in self.of("decision_approved"):
            out[str(r.data.get("run_id", ""))] = r
        self.test_runs = {k: r for k, r in out.items() if r.details.get("test_run") is True}
        return {k: r for k, r in out.items() if k not in self.test_runs}

    # R1
    def r1(self) -> list[_Group]:
        last: dict[str, Record | None] = {}
        for r in self.of("research_marked"):
            d = r.details
            if any(k not in d for k in ("section", "asset_class")) or "finding_id" not in d:
                self.missing["R1"].append(r)
                continue
            last[str(d["finding_id"])] = r if d.get("mark") in MARKS else None
        by: dict[tuple, list[Record]] = defaultdict(list)
        for r in sorted((r for r in last.values() if r is not None), key=lambda r: (r.file, r.line)):
            d = r.details
            by[(r.version(VERSION_PARTS["R1"]), str(d["asset_class"]), str(d["section"]))].append(r)
        out = []
        for (version, cls, section), recs in by.items():
            wrong = sum(1 for r in recs if r.details["mark"] == "wrong")
            n = len(recs)
            value = wrong / n
            g = _Group(version, {"asset_class": cls, "section": section},
                       f"{self.cfg.label(cls)} · {self.cfg.label(section)}", n, value, recs,
                       {"wrong": wrong, "ok": n - wrong})
            action = self.cfg.rules["R1"].actions.get(section, {})
            g.fields = {lang: {"asset_class": self.cfg.label(cls),
                               "section": self.cfg.label(section), "share": pct(value, lang),
                               "wrong": wrong, "n": n, "action": action.get(lang, "")}
                        for lang in LANGS}
            g.above = value > self.cfg.rules["R1"].threshold
            out.append(g)
        return out

    # R2, R3
    def blocks(self, rid: str, action: str, count_word: str) -> list[_Group]:
        approved = self.approvals()
        runs_of: dict[str, set[str]] = defaultdict(set)
        for run_id, r in approved.items():
            runs_of[r.version(VERSION_PARTS[rid])].add(run_id)
        by: dict[tuple, list[Record]] = defaultdict(list)
        for r in self.of(action):
            if "block_id" not in r.details:
                self.missing[rid].append(r)
                continue
            run_id = str(r.data.get("run_id", ""))
            if run_id not in approved:
                continue
            version = approved[run_id].version(VERSION_PARTS[rid])
            by[(version, section_of(r.details["block_id"]))].append(r)
        out = []
        rule = self.cfg.rules[rid]
        for (version, section), recs in by.items():
            hits = len({str(r.data.get("run_id", "")) for r in recs})
            n = len(runs_of[version])
            value = hits / n
            g = _Group(version, {"section": section}, self.cfg.label(section), n, value, recs,
                       {count_word: hits})
            g.fields = {lang: {"section": self.cfg.label(section), "share": pct(value, lang),
                               count_word: hits, "n": n} for lang in LANGS}
            g.above = value > rule.threshold
            if rule.examples:
                g.extra["examples"] = [
                    {"before": _short(r.details.get("before", "")),
                     "after": _short(r.details.get("after", "")), "at": r.at}
                    for r in recs[:rule.examples]]
            out.append(g)
        return out

    # R4
    def r4(self) -> list[_Group]:
        by: dict[str, list[Record]] = defaultdict(list)
        for r in self.approvals().values():
            d = r.details
            if "selected" not in d or "engine_top3" not in d:
                self.missing["R4"].append(r)
                continue
            by[r.version(VERSION_PARTS["R4"])].append(r)
        out = []
        for version, recs in by.items():
            sel_all = eng_all = 0
            agent_recs = []
            sel = eng = ag = 0
            for r in recs:
                d = r.details
                chosen = list(d.get("selected") or ())
                engine = set(d.get("engine_top3") or ())
                agent = set(d.get("agent_top3") or ())
                sel_all += len(chosen)
                eng_all += sum(1 for o in chosen if o in engine)
                if agent and chosen:
                    agent_recs.append(r)
                    sel += len(chosen)
                    eng += sum(1 for o in chosen if o in engine)
                    ag += sum(1 for o in chosen if o in agent)
            engine_share = eng / sel if sel else None
            agent_share = ag / sel if sel else None
            diff = None if sel == 0 else engine_share - agent_share
            g = _Group(version, {}, "Motor / ajan", len(agent_recs), agent_share,
                       agent_recs or recs,
                       {"engine_share": engine_share, "agent_share": agent_share,
                        "diff": diff, "approvals": len(recs),
                        "engine_share_all": eng_all / sel_all if sel_all else None})
            g.fields = {lang: {"agent_share": pct(agent_share, lang),
                               "engine_share": pct(engine_share, lang), "n": len(agent_recs),
                               "diff": pct(diff, lang)} for lang in LANGS}
            g.above = diff is not None and diff > self.cfg.rules["R4"].threshold
            out.append(g)
        return out

    # R5
    def r5(self) -> list[_Group]:
        by: dict[tuple, list[tuple[Record, float]]] = defaultdict(list)
        for r in self.of("holdings_set"):
            d = r.details
            est, shares = d.get("estimate"), d.get("shares")
            if not isinstance(est, Mapping) or not isinstance(shares, Mapping):
                self.missing["R5"].append(r)
                continue
            for cls, e in est.items():
                if not isinstance(e, Mapping) or e.get("current") is None or cls not in shares:
                    continue
                key = (r.version(VERSION_PARTS["R5"]), str(e.get("source", "")),
                       str(e.get("ref") or ""), str(cls))
                by[key].append((r, abs(float(shares[cls]) - float(e["current"]))))
        out = []
        for (version, source, ref, cls), rows in by.items():
            recs = [r for r, _ in rows]
            value = statistics.fmean(x for _, x in rows)
            src = self.cfg.label(source) + (f" ({ref})" if ref else "")
            g = _Group(version, {"source": source, "ref": ref, "asset_class": cls},
                       f"{src} · {self.cfg.label(cls)}", len(rows), value, recs)
            g.fields = {lang: {"source": src, "asset_class": self.cfg.label(cls),
                               "error": num(value, lang), "n": len(rows)} for lang in LANGS}
            g.above = value > self.cfg.rules["R5"].threshold
            out.append(g)
        return out


def _short(text: Any) -> str:
    t = " ".join(str(text).split())
    return t if len(t) <= EXAMPLE_CHARS else t[:EXAMPLE_CHARS - 1] + "…"


def _group_json(g: _Group, rule: RuleConfig, evidence_max: int) -> dict[str, Any]:
    if g.n < rule.min_n:
        status, rec = "insufficient", None
    elif g.above:
        status = "recommendation"
        rec = {lang: rule.text[lang].format(**g.fields[lang]) for lang in LANGS}
    else:
        status, rec = "no_recommendation", None
    lines = [r.at for r in g.records]
    return {"version": g.version, "group": g.key, "label": g.label, "n": g.n,
            "value": g.value, **g.extra, "status": status, "recommendation": rec,
            "evidence": lines[:evidence_max], "evidence_more": max(0, len(lines) - evidence_max)}


def _rule_status(groups: list[dict]) -> str:
    if any(g["status"] == "recommendation" for g in groups):
        return "recommendation"
    if any(g["status"] == "no_recommendation" for g in groups):
        return "no_recommendation"
    return "insufficient"


def measure(records: list[Record], cfg: FeedbackConfig) -> tuple[dict, dict]:
    """(the rules part of the report, research questions part)."""
    rep = _Report(cfg, records)
    raw = {"R1": rep.r1(), "R2": rep.blocks("R2", "text_block_deleted", "deleted"),
           "R3": rep.blocks("R3", "text_block_edited", "edited"), "R4": rep.r4(),
           "R5": rep.r5()}
    rules = {}
    for rid in RULE_IDS:
        rule = cfg.rules[rid]
        gs = sorted(raw[rid], key=lambda g: (g.label, _version_order(g.version)))
        groups = [_group_json(g, rule, cfg.evidence_max) for g in gs]
        missing = rep.missing.get(rid, [])
        rules[rid] = {
            "title": TITLES[rid][0], "measure": TITLES[rid][1],
            "min_n": rule.min_n, "threshold": rule.threshold,
            "versions": sorted({g["version"] for g in groups}, key=_version_order),
            "status": _rule_status(groups),
            "missing_fields": len(missing),
            "missing_evidence": [r.at for r in missing][:cfg.evidence_max],
            "groups": groups,
        }
        if rid in ("R2", "R3", "R4"):              # W30: approvals of an edited profile
            rules[rid]["test_runs_skipped"] = len(rep.test_runs)
    questions: dict[str, dict[str, Any]] = {}
    for r in rep.of("research_question"):
        q = " ".join(str(r.details.get("question", "")).split())
        if not q:
            continue
        row = questions.setdefault(q.casefold(), {"question": q, "count": 0, "refused": 0})
        row["count"] += 1
        row["refused"] += 1 if r.details.get("refused") else 0
    ordered = sorted(questions.values(), key=lambda x: (-x["count"], x["question"]))
    return rules, ordered


# --- the report ----------------------------------------------------------------------------

def _rule_line(rid: str, rule: RuleConfig) -> str:
    t = rule.threshold
    return {
        "R1": f"Kural: en az {rule.min_n} işaret ve ✗ payı > {pct(t, 'TR')}",
        "R2": f"Kural: en az {rule.min_n} onaylı çalıştırma ve silme payı > {pct(t, 'TR')}",
        "R3": f"Kural: en az {rule.min_n} onaylı çalıştırma ve düzenleme payı > {pct(t, 'TR')}",
        "R4": (f"Kural: ajan kararı olan en az {rule.min_n} onay ve motor payı − ajan payı > "
               f"{num(100 * t, 'TR')} puan"),
        "R5": f"Kural: en az {rule.min_n} bölünme ve ortalama sapma > {num(t, 'TR')} puan",
    }[rid]


def _cell(rid: str, g: dict) -> str:
    if rid == "R1":
        return f"{pct(g['value'], 'TR')} ({g['wrong']}/{g['n']})"
    if rid in ("R2", "R3"):
        hits = g["deleted"] if rid == "R2" else g["edited"]
        return f"{pct(g['value'], 'TR')} ({hits}/{g['n']})"
    if rid == "R4":
        return (f"ajan {pct(g['agent_share'], 'TR')}, motor {pct(g['engine_share'], 'TR')} "
                f"({g['n']})")
    return f"{num(g['value'], 'TR')} puan ({g['n']})"


def _md_text(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def to_markdown(m: dict) -> str:
    meta = m["meta"]
    period = (f"{meta['since'] or 'başlangıç'} – {meta['until'] or 'bugün'}"
              if meta["since"] or meta["until"] else "tüm kayıtlar")
    L = ["# Geri bildirim raporu", "", f"- Oluşturma: {meta['created_at']}",
         f"- Dönem: {period}",
         f"- Dosyalar: {', '.join(meta['files']) or '-'}",
         f"- Kayıtlar: {meta['records']}"
         + (f"; bozuk satır: {', '.join(meta['broken_lines'])}" if meta["broken_lines"] else ""),
         "- Kurallar sabittir (config/feedback.yaml); hiçbir şey otomatik değişmez: öneriyi bir "
         "kişi okur ve karar verir.", ""]

    L += ["## Kayıt sayıları", ""]
    if not meta["records"]:
        L += ["Bu dönemde kayıt yok.", ""]
    else:
        L += ["| Eylem | Kayıt |", "|---|---|"]
        L += [f"| {a} | {n} |" for a, n in m["actions"].items()]
        L.append("")

    for rid in RULE_IDS:
        r = m["rules"][rid]
        L += [f"## {rid} — {r['title']}", "", f"- Ölçü: {r['measure']}",
              f"- {r['rule_line']}"]
        if r["missing_fields"]:
            L.append(f"- Eksik alan: {r['missing_fields']} kayıt (L1b öncesi; bu ölçüde "
                     f"atlandı): {', '.join(r['missing_evidence'])}")
        if r.get("test_runs_skipped"):
            L.append(f"- Düzenlenmiş profil onayları (dışarıda): {r['test_runs_skipped']}")
        L.append("")
        groups = r["groups"]
        if not groups:
            L += [f"Yeterli veri yok (0/{r['min_n']})", ""]
            continue
        versions = r["versions"]
        labels = list(dict.fromkeys(g["label"] for g in groups))
        cells = {(g["label"], g["version"]): _cell(rid, g) for g in groups}
        L += ["| Grup | " + " | ".join(versions) + " |",
              "|---|" + "---|" * len(versions)]
        for label in labels:
            L.append(f"| {_md_text(label)} | "
                     + " | ".join(cells.get((label, v), "-") for v in versions) + " |")
        L.append("")
        for g in groups:
            head = f"**{g['label']}**" + (f" ({g['version']})" if len(versions) > 1 else "")
            if g["status"] == "recommendation":
                result = f"Öneri: {g['recommendation']['TR']}"
            elif g["status"] == "no_recommendation":
                result = "Öneri yok (kural sağlanmadı)."
            else:
                result = f"Yeterli veri yok ({g['n']}/{r['min_n']})"
            more = f" + {g['evidence_more']} more" if g["evidence_more"] else ""
            L.append(f"- {head}: {result} — kanıt: {', '.join(g['evidence'])}{more}")
            for ex in g.get("examples", ()):
                L.append(f"  - {ex['at']}: {_md_text(ex['before'])} → {_md_text(ex['after'])}")
        L.append("")

    L += ["## Araştırma soruları", ""]
    if m["research_questions"]:
        L += ["| Soru | Sayı | Reddedilen |", "|---|---|---|"]
        L += [f"| {_md_text(q['question'])} | {q['count']} | {q['refused']} |"
              for q in m["research_questions"]]
    else:
        L.append("Bu dönemde araştırma sorusu yok.")
    L.append("")
    return "\n".join(L)


@dataclass(frozen=True)
class FeedbackResult:
    out_dir: Path | None
    report_md: Path | None
    report_json: Path | None
    markdown: str
    measures: dict[str, Any]


def _as_date(x: date | str | None, what: str) -> date | None:
    if x is None or isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x))
    except ValueError:
        raise ValueError(f"{what}: must be YYYY-MM-DD, got {x!r}") from None


def run_feedback(root: Path | str, since: date | str | None = None,
                 until: date | str | None = None, *,
                 now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
                 config: FeedbackConfig | None = None, write: bool = True) -> FeedbackResult:
    """The report of the log period [since, until] (Turkish days, both included; None =
    open). Writes <root>/data/feedback/<YYYYMMDD-HHMMSS>/report.md and report.json."""
    root = Path(root)
    since, until = _as_date(since, "since"), _as_date(until, "until")
    cfg = config or load_feedback_config(root / "config" / "feedback.yaml")
    created = now().astimezone(TR_TZ)
    records, files, broken = read_log(root / LOG_DIR, since, until)
    rules, questions = measure(records, cfg)
    for rid in RULE_IDS:
        rules[rid]["rule_line"] = _rule_line(rid, cfg.rules[rid])
    measures = {
        "meta": {"created_at": created.isoformat(),
                 "since": None if since is None else since.isoformat(),
                 "until": None if until is None else until.isoformat(),
                 "files": files, "records": len(records), "broken_lines": broken,
                 "evidence_max": cfg.evidence_max},
        "actions": dict(Counter(r.action for r in records)),
        "rules": rules,
        "research_questions": questions,
    }
    md = to_markdown(measures)
    if not write:
        return FeedbackResult(None, None, None, md, measures)
    out = root / OUT_DIR / f"{created:%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(md, encoding="utf-8", newline="\n")
    (out / "report.json").write_text(json.dumps(measures, ensure_ascii=False, indent=1) + "\n",
                                     encoding="utf-8", newline="\n")
    return FeedbackResult(out, out / "report.md", out / "report.json", md, measures)
