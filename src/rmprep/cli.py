"""Command line: python -m rmprep {ingest, replay, show, list, decide, eval}."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx

from rmprep import decision
from rmprep.contracts import TR_TZ, Persona
from rmprep.eval.suite import run_suite
from rmprep.ingest.adapters import evds
from rmprep.ingest.adapters.evds import EvdsParseError
from rmprep.ingest.config import ConfigError, EvdsSource, load_config
from rmprep.ingest.pipeline import (
    EvidenceSet,
    ExclusionError,
    IngestBusy,
    Paths,
    build_evidence,
    ingest,
    load_env,
    replay,
)
from rmprep.ingest.snapshot import SnapshotError, list_snapshots


def _table(rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def _fmt_value(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:,.6f}".rstrip("0").rstrip(".")


def format_evidence(ev: EvidenceSet, rows: bool = True) -> str:
    """The snapshot, the source status, the datapoints (unless `rows` is False:
    only their count, e.g. for the daily ingest log) and the flag counts."""
    lines = [f"snapshot {ev.snapshot_id}  created {ev.created_at.isoformat()}"]
    if ev.excluded_sources:
        lines.append(f"excluded at read time: {', '.join(sorted(ev.excluded_sources))}")

    lines.append("\nsources:")
    for name, rec in sorted(ev.source_status.items()):
        detail = []
        if name in ev.excluded_sources:
            detail.append("EXCLUDED (read time)")
        if rec.status == "ok":
            detail.append(f"payloads={len(rec.payloads)}")
        if rec.status == "failed":
            if rec.excluded:
                detail.append("excluded (on_failure)")
            elif rec.fallback_from:
                detail.append(f"fallback from {rec.fallback_from}")
            else:
                detail.append("no fallback available")
            detail.append(f"error: {rec.error}")
        if rec.rejected_rows:
            detail.append(f"rejected rows={len(rec.rejected_rows)}")
        lines.append(f"  {name:<8} {rec.status:<8} {'  '.join(detail)}")
        for r in rec.rejected_rows:
            where = f"{r['file']} row {r['row']}" if "file" in r else r.get("fund", "?")
            lines.append(f"           rejected {where}: {r.get('reason', '')}")

    pts = ev.datapoints
    if not rows:
        lines.append(f"\n{len(pts)} datapoints")
    else:
        lines.append(f"\ndatapoints ({len(pts)}):")
    if pts and rows:
        rows = [["id", "source", "quantity", "entity", "as_of", "value", "unit", "flags"]]
        rows += [[p.id, p.source, p.quantity, p.entity, p.as_of.isoformat(),
                  _fmt_value(p.value), p.unit, ",".join(p.sorted_flags())] for p in pts]
        lines.append(_table(rows))
    counts = Counter(f for p in pts for f in p.sorted_flags())
    lines.append("\nflags: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                                or "none"))
    return "\n".join(lines)


def _series_rows(series: list[evds.SeriesInfo]) -> str:
    rows = [["code", "frequency", "start", "end", "name"]]
    rows += [[s.code, s.frequency, s.start, s.end, s.name or s.name_eng] for s in series]
    return _table(rows)


def _evds_meta(paths: Paths, args: argparse.Namespace,
               client: httpx.Client | None = None) -> int:
    """Look up EVDS metadata with the key from .env. The key is never printed."""
    src = next((s for s in load_config(paths.config).sources.values()
                if isinstance(s, EvdsSource)), None)
    if src is None:
        print("error: no EVDS source in config", file=sys.stderr)
        return 2
    key = evds.get_api_key(src, load_env(paths))
    if not key:
        print(f"error: {src.api_key_env} is empty; add your key to {paths.env_file}",
              file=sys.stderr)
        return 2
    with client or httpx.Client() as c:
        if args.command == "evds-info":
            series = evds.list_series(src, c, key, args.code)
            print(_series_rows(series) if series else f"no series found for {args.code!r}")
            return 0
        groups, series = evds.find_series(src, c, key, args.text)
    if not groups:
        print(f"no data group name contains {args.text!r}; try a shorter word")
        return 0
    print(f"data groups ({len(groups)}):")
    for g in groups:
        print(f"  {evds._field(g, 'datagroup_code'):<20} {evds._field(g, 'datagroup_name')}"
              f"  [{evds._field(g, 'frequency_str')}]")
    if len(groups) > 15:
        print("  (series listed for the first 15 groups only; use a more exact word)")
    print(f"\nseries ({len(series)}):")
    print(_series_rows(series) if series else "  none")
    return 0


def _persona(folder: Path, persona_id: str) -> Persona:
    for f in sorted(folder.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if isinstance(d, dict) and str(d.get("persona_id", "")).upper() == persona_id.upper():
            return Persona.from_dict(d)
    raise ValueError(f"no persona {persona_id!r} in {folder}")


def _decide(paths: Paths, args: argparse.Namespace) -> int:
    answers = {}
    for a in args.answer:
        qid, sep, value = a.partition("=")
        if not sep or not qid:
            raise ValueError(f"--answer needs QID=VALUE, got {a!r}")
        answers[qid] = value
    persona = _persona(args.personas or paths.root.parent, args.persona)
    snapshot_id = args.snapshot
    if snapshot_id is None:
        snaps = list_snapshots(paths.snapshots)
        if not snaps:
            raise ValueError(f"no snapshot in {paths.snapshots}; run ingest first")
        snapshot_id = snaps[-1].snapshot_id
    ev = build_evidence(paths.snapshots, snapshot_id, frozenset(args.exclude))
    config = decision.load_config(paths.root / "config" / "decision.yaml")
    result = decision.decide(ev, persona, config, answers, created_at=datetime.now(TR_TZ))
    print(decision.render(result))
    return 0


def _eval(paths: Paths, args: argparse.Namespace) -> int:
    kw = {"suite": args.suite, "only": args.only or None, "snapshot": args.snapshot}
    if args.no_llm:                       # template texts, no grades, no cost
        kw.update(narrator=None, judge=None)
    if args.agent:                        # E11: the agentic top 3 (docs/agent.md; costs about $2)
        kw["agent"] = True
        if args.no_llm:                   # no model: the agent part is checked without calls
            kw.update(agent_client=None, ab_judge=None)
    result = run_suite(paths.root, **kw)
    if result.report_dir is not None:
        print((result.report_dir / "report.md").read_text(encoding="utf-8"))
        print(f"report: {result.report_dir}")
    return 0


def _feedback(paths: Paths, args: argparse.Namespace) -> int:
    """F1: the manual feedback report over the RM action log (no LLM, no cost)."""
    from rmprep.eval.feedback import run_feedback
    res = run_feedback(paths.root, args.since, args.until)
    print(res.markdown)
    print(f"report: {res.out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="rmprep", description="RM meeting-prep ingestion")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="project folder with config/ and data/ (default: current folder)")
    sub = parser.add_subparsers(dest="command", required=True)
    p_ingest = sub.add_parser("ingest", help="fetch all enabled sources into a new snapshot")
    p_ingest.add_argument("--summary", action="store_true",
                          help="print the source status and flag counts, not every datapoint")
    p_replay = sub.add_parser("replay", help="rebuild store + export from a snapshot (offline)")
    p_replay.add_argument("snapshot_id")
    p_show = sub.add_parser("show", help="show the evidence of a snapshot")
    p_show.add_argument("snapshot_id")
    p_show.add_argument("--exclude", action="append", default=[], metavar="SOURCE",
                        help="leave out a source (repeatable); checks run again without it")
    sub.add_parser("list", help="list snapshots")
    p_dec = sub.add_parser("decide", help="score the options of a snapshot for a persona")
    p_dec.add_argument("--persona", required=True, help="persona id, e.g. P01")
    p_dec.add_argument("--snapshot", help="snapshot id (default: the latest)")
    p_dec.add_argument("--exclude", action="append", default=[], metavar="SOURCE",
                       help="leave out a source (repeatable)")
    p_dec.add_argument("--answer", action="append", default=[], metavar="QID=VALUE",
                       help="answer to an RM question (repeatable)")
    p_dec.add_argument("--personas", type=Path,
                       help="folder with the persona JSONs (default: the folder above --root)")
    p_eval = sub.add_parser("eval", help="run the eval suite and write its report (docs/eval.md)")
    p_eval.add_argument("--suite", default="full", help="suite name in the report folder")
    p_eval.add_argument("--only", action="append", default=[], metavar="ID",
                        help="scenario id or group to run (repeatable)")
    p_eval.add_argument("--snapshot", help="snapshot id (default: the frozen eval snapshot)")
    p_eval.add_argument("--no-llm", action="store_true",
                        help="no narrator LLM and no judge: template texts, no cost")
    p_eval.add_argument("--agent", action="store_true",
                        help="also run the agentic top-3 decision (E11): about $2")
    p_fb = sub.add_parser("feedback", help="manual feedback report over the RM action log (F1)")
    p_fb.add_argument("--since", help="first day YYYY-MM-DD (default: all)")
    p_fb.add_argument("--until", help="last day YYYY-MM-DD (default: all)")
    p_serve = sub.add_parser("serve", help="start the web app and its API on 127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8600)
    p_serve.add_argument("--personas", type=Path,
                         help="folder with the persona JSONs (default: the folder above --root)")
    p_find = sub.add_parser("evds-find", help="search EVDS data groups by name; list their series")
    p_find.add_argument("text", help='e.g. "mevduat" or "politika faizi"')
    p_info = sub.add_parser("evds-info", help="show EVDS metadata for a series or data group code")
    p_info.add_argument("code")
    args = parser.parse_args(argv)
    paths = Paths(args.root.resolve())

    try:
        if args.command == "ingest":
            ev = ingest(paths)
            print(format_evidence(ev, rows=not args.summary))
        elif args.command == "replay":
            ev = replay(paths, args.snapshot_id)
            print(f"replayed {ev.snapshot_id}: {len(ev.datapoints)} datapoints")
        elif args.command == "show":
            print(format_evidence(build_evidence(paths.snapshots, args.snapshot_id,
                                                 frozenset(args.exclude))))
        elif args.command == "list":
            for s in list_snapshots(paths.snapshots):
                status = " ".join(f"{k}={v.status}" for k, v in sorted(s.sources.items()))
                print(f"{s.snapshot_id}  {s.created_at.isoformat()}  {status}")
        elif args.command == "decide":
            return _decide(paths, args)
        elif args.command == "eval":
            return _eval(paths, args)
        elif args.command == "feedback":
            return _feedback(paths, args)
        elif args.command == "serve":
            from rmprep.api import serve as web
            web.serve(paths.root, args.port, personas_dir=args.personas)
        elif args.command in ("evds-find", "evds-info"):
            return _evds_meta(paths, args)
    except IngestBusy as e:   # I6: the daily job or the web app's refresh runs
        print(str(e), file=sys.stderr)
        return 3
    except (ConfigError, SnapshotError, ExclusionError, EvdsParseError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
