"""Command line: python -m rmprep {ingest, replay, show, list}."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import httpx

from rmprep.adapters import evds
from rmprep.adapters.evds import EvdsParseError
from rmprep.config import ConfigError, EvdsSource, load_config
from rmprep.pipeline import (
    EvidenceSet,
    ExclusionError,
    Paths,
    build_evidence,
    ingest,
    load_env,
    replay,
)
from rmprep.snapshot import SnapshotError, list_snapshots


def _table(rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows)


def _fmt_value(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:,.6f}".rstrip("0").rstrip(".")


def format_evidence(ev: EvidenceSet) -> str:
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
            lines.append(f"           rejected {r['file']} row {r['row']}: {r['reason']}")

    pts = ev.datapoints
    lines.append(f"\ndatapoints ({len(pts)}):")
    if pts:
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


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="rmprep", description="RM meeting-prep ingestion")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="project folder with config/ and data/ (default: current folder)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="fetch all enabled sources into a new snapshot")
    p_replay = sub.add_parser("replay", help="rebuild store + export from a snapshot (offline)")
    p_replay.add_argument("snapshot_id")
    p_show = sub.add_parser("show", help="show the evidence of a snapshot")
    p_show.add_argument("snapshot_id")
    p_show.add_argument("--exclude", action="append", default=[], metavar="SOURCE",
                        help="leave out a source (repeatable); checks run again without it")
    sub.add_parser("list", help="list snapshots")
    p_find = sub.add_parser("evds-find", help="search EVDS data groups by name; list their series")
    p_find.add_argument("text", help='e.g. "mevduat" or "politika faizi"')
    p_info = sub.add_parser("evds-info", help="show EVDS metadata for a series or data group code")
    p_info.add_argument("code")
    args = parser.parse_args(argv)
    paths = Paths(args.root.resolve())

    try:
        if args.command == "ingest":
            ev = ingest(paths)
            print(format_evidence(ev))
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
        elif args.command in ("evds-find", "evds-info"):
            return _evds_meta(paths, args)
    except (ConfigError, SnapshotError, ExclusionError, EvdsParseError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0
