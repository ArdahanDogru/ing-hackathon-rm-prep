"""Ingest, replay and read-time evidence building.

ingest  = fetch every enabled source -> snapshot -> build_evidence -> DuckDB + Parquet
replay  = build_evidence from an existing snapshot -> DuckDB + Parquet (offline)
build_evidence(snapshot, exclude_sources) = parse -> drop excluded sources -> checks
                                            (+ entities from the same payloads)

Only `ingest` reads the clock, the network, .env, the inbox and the current
sources.yaml. Everything after the snapshot is written reads the snapshot only.
"""

from __future__ import annotations

import dataclasses
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values

from rmprep.contracts import TR_TZ, DataPoint, EntityInfo, EvidenceSet, Flag
from rmprep.ingest.adapters import evds, manual, tefas, tefas_detail, tefas_web
from rmprep.ingest.config import (
    Config,
    EvdsSource,
    SourceConfig,
    TefasDetailSource,
    load_raw,
    parse_config,
)
from rmprep.ingest.quality import run_checks
from rmprep.ingest.snapshot import (
    Snapshot,
    SnapshotWriter,
    SourceRecord,
    find_previous_ok,
    open_snapshot,
)
from rmprep.ingest.store import EvidenceStore

_PARSERS = {"evds": evds.parse, "tefas": tefas.parse, "tefas_web": tefas_web.parse,
            "tefas_detail": tefas_detail.parse, "manual": manual.parse}
# Adapters that also give EntityInfo (fund names and types) from their payloads.
_ENTITY_READERS = {"tefas_web": tefas_web.entities}


class ExclusionError(ValueError):
    """Exclude list names a source that the snapshot does not have."""


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config" / "sources.yaml"

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    @property
    def snapshots(self) -> Path:
        return self.root / "data" / "snapshots"

    @property
    def db(self) -> Path:
        return self.root / "data" / "evidence.duckdb"

    @property
    def export(self) -> Path:
        return self.root / "data" / "export"

    def inbox(self, rel: str) -> Path:
        return self.root / rel


# --- ingest ------------------------------------------------------------------------

def load_env(paths: Paths) -> dict[str, str]:
    """.env values, overridden by real environment variables."""
    file_values = {k: v for k, v in dotenv_values(paths.env_file).items() if v is not None}
    return {**file_values, **os.environ}


def ingest(
    paths: Paths,
    *,
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> EvidenceSet:
    """`sleep` is for the wait between tefas_detail requests (tests pass a fake)."""
    now = now or (lambda: datetime.now(TR_TZ))
    raw = load_raw(paths.config)
    cfg = parse_config(raw)
    env = load_env(paths) if env is None else env
    created_at = now()
    secrets = [evds.get_api_key(s, env) for s in cfg.sources.values()
               if isinstance(s, EvdsSource)]

    own_client = client is None
    client = client or httpx.Client()
    try:
        with SnapshotWriter(paths.snapshots, raw, created_at=created_at,
                            secrets=[s for s in secrets if s]) as w:
            # tefas_detail reads the fund list from the tefas_web page: fetch it last.
            for name, src in sorted(cfg.sources.items(),
                                    key=lambda kv: (isinstance(kv[1], TefasDetailSource), kv[0])):
                if not src.enabled:
                    rec = SourceRecord(status="skipped", on_failure=src.on_failure)
                else:
                    rec = _fetch(src, w, cfg, paths, env, client, created_at, now, sleep)
                if rec.status == "failed":
                    rec = _apply_failure_policy(rec, src, paths, created_at)
                w.set_source(name, rec)
            snap = w.finalize()
    finally:
        if own_client:
            client.close()
    return _process(paths, snap.snapshot_id)


def _fetch(src: SourceConfig, w: SnapshotWriter, cfg: Config, paths: Paths,
           env: Mapping[str, str], client: httpx.Client, created_at: datetime,
           now: Callable[[], datetime], sleep: Callable[[float], None]) -> SourceRecord:
    if src.adapter == "evds":
        return evds.fetch(src, w, api_key=evds.get_api_key(src, env), client=client,
                          today=created_at.date(), now=now)
    if src.adapter == "tefas":
        return tefas.fetch(src, w, inbox=paths.inbox(src.inbox), now=now)
    if src.adapter == "tefas_web":
        return tefas_web.fetch(src, w, client=client, now=now)
    if isinstance(src, TefasDetailSource):
        return tefas_detail.fetch(src, w, listing=_ok_payload(w, src.funds_from), client=client,
                                  now=now, sleep=sleep)
    if src.adapter == "manual":
        return manual.fetch(src, w, cfg, inbox=paths.inbox(src.inbox), now=now)
    raise AssertionError(f"no fetch for adapter {src.adapter!r}")


def _ok_payload(w: SnapshotWriter, source: str) -> bytes | None:
    """The single payload of `source` in this snapshot if its fetch was ok."""
    rec = w.record(source)
    if rec is None or rec.status != "ok" or len(rec.payloads) != 1:
        return None
    return w.read_payload(rec.payloads[0].path)


def _apply_failure_policy(rec: SourceRecord, src: SourceConfig, paths: Paths,
                          created_at: datetime) -> SourceRecord:
    if src.on_failure == "exclude":
        return dataclasses.replace(rec, excluded=True)
    return dataclasses.replace(
        rec, fallback_from=find_previous_ok(paths.snapshots, src.name, created_at))


def replay(paths: Paths, snapshot_id: str) -> EvidenceSet:
    """Rebuild DuckDB rows and the Parquet export from the snapshot only."""
    return _process(paths, snapshot_id)


def _process(paths: Paths, snapshot_id: str) -> EvidenceSet:
    ev = build_evidence(paths.snapshots, snapshot_id)
    with EvidenceStore(paths.db) as store:
        store.load(snapshot_id, ev.created_at, list(ev.datapoints))
        store.export_parquet(snapshot_id, paths.export)
    return ev


# --- evidence ------------------------------------------------------------------------

def build_evidence(snapshots_root: str | Path, snapshot_id: str,
                   exclude_sources: frozenset[str] | set[str] = frozenset()) -> EvidenceSet:
    """Parse a snapshot, drop excluded sources BEFORE the checks, run the checks.
    Same snapshot + same exclude set -> identical result."""
    snap = open_snapshot(snapshots_root, snapshot_id)
    cfg = parse_config(snap.config_raw)
    exclude = frozenset(exclude_sources)
    unknown = sorted(exclude - snap.sources.keys())
    if unknown:
        raise ExclusionError(f"unknown source(s) {unknown}; "
                             f"snapshot has {sorted(snap.sources)}")

    points: list[DataPoint] = []
    entities: dict[str, EntityInfo] = {}
    for name in sorted(snap.sources):
        if name in exclude or name not in cfg.sources:
            continue
        points.extend(_source_points(snapshots_root, snap, cfg, cfg.sources[name],
                                     snap.sources[name]))
        entities.update(_source_entities(snapshots_root, snap, cfg.sources[name],
                                         snap.sources[name]))

    checked = run_checks(points, cfg, snap.created_at.date())
    return EvidenceSet(snapshot_id=snap.snapshot_id, created_at=snap.created_at,
                       excluded_sources=exclude, source_status=dict(snap.sources),
                       datapoints=tuple(checked),
                       entities=dict(sorted(entities.items())))


def _source_points(root: str | Path, snap: Snapshot, cfg: Config, src: SourceConfig,
                   rec: SourceRecord) -> list[DataPoint]:
    if rec.status == "skipped" or rec.excluded:
        return []
    if rec.status == "ok":
        return _PARSERS[src.adapter](cfg, src, snap)

    # failed, policy "previous"
    if rec.fallback_from:
        old = open_snapshot(root, rec.fallback_from)
        old_cfg = parse_config(old.config_raw)
        old_points = _PARSERS[src.adapter](
            old_cfg, old_cfg.sources[src.name], old,
            out_snapshot_id=snap.snapshot_id, out_date=snap.created_at.date())
        return [p.with_flags(Flag.FALLBACK_SNAPSHOT, note=f"fallback from {old.snapshot_id}")
                for p in old_points]
    if isinstance(src, EvdsSource):
        return evds.missing_points(
            cfg, src, snap.snapshot_id, snap.created_at,
            note=f"{src.name} failed ({rec.error}); no earlier snapshot to fall back to")
    return []


def _source_entities(root: str | Path, snap: Snapshot, src: SourceConfig,
                     rec: SourceRecord) -> dict[str, EntityInfo]:
    """Same source choice as _source_points: own payload if ok, the fallback
    snapshot's payload if failed with fallback, else nothing."""
    reader = _ENTITY_READERS.get(src.adapter)
    if reader is None or rec.status == "skipped" or rec.excluded:
        return {}
    if rec.status == "ok":
        return reader(src, snap)
    if rec.fallback_from:
        old = open_snapshot(root, rec.fallback_from)
        return reader(parse_config(old.config_raw).sources[src.name], old)
    return {}
