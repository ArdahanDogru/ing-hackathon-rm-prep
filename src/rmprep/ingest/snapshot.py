"""Immutable raw snapshots.

Layout of one snapshot:

    <root>/<snapshot_id>/
        manifest.json        snapshot metadata, config copy, per-source records
        manifest.sha256      SHA-256 of manifest.json
        payloads/<source>/<name>   raw bytes, exactly as received

A snapshot is written into `<root>/.tmp-<id>/`, made read-only, then renamed.
A finished snapshot is never written again. Readers verify every hash.

Cache payloads (I11): a payload path `cache/<source>/<name>` points to an
immutable file in `<root>/../cache/<source>/` (e.g. data/cache/bist_bulletin),
shared by many snapshots and not copied. The manifest keeps its SHA-256, and
readers verify it like any other payload.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets as _secrets
import shutil
import stat
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from rmprep import __version__
from rmprep.contracts import TR_TZ

MANIFEST = "manifest.json"
MANIFEST_HASH = "manifest.sha256"
PAYLOADS = "payloads"
CACHE = "cache"
TMP_PREFIX = ".tmp-"
MANIFEST_VERSION = 1

Status = Literal["ok", "failed", "skipped"]
STATUSES = ("ok", "failed", "skipped")

_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
_SOURCE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PAYLOAD_NAME_RE = re.compile(r"^\w[\w .()\-]*$")


class SnapshotError(Exception):
    """Snapshot cannot be written or read."""


class SnapshotIntegrityError(SnapshotError):
    """A finished snapshot does not match its hashes."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def new_snapshot_id(created_at: datetime, suffix: str | None = None) -> str:
    """`YYYYMMDD-HHMMSS-xxxx` in Turkey time."""
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    suffix = suffix if suffix is not None else _secrets.token_hex(2)
    sid = f"{created_at.astimezone(TR_TZ):%Y%m%d-%H%M%S}-{suffix}"
    if not _ID_RE.match(sid):
        raise ValueError(f"invalid snapshot id {sid!r}")
    return sid


def raw_ref(snapshot_id: str, payload_path: str, locator: str) -> str:
    """Pointer from a DataPoint to the raw bytes it came from."""
    return f"{snapshot_id}/{payload_path}#{locator}"


def _dt_to_json(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(TR_TZ).isoformat()


def _dt_from_json(s: str | None) -> datetime | None:
    return None if s is None else datetime.fromisoformat(s).astimezone(TR_TZ)


def _dump(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# --- records ----------------------------------------------------------------------

@dataclass(frozen=True)
class PayloadRef:
    path: str            # relative to the snapshot folder, e.g. "payloads/evds/TP.FG.J0.json",
                         # or a cache file "cache/<source>/<name>" (I11)
    sha256: str
    bytes: int
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "bytes": self.bytes, "meta": self.meta}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> PayloadRef:
        return cls(path=d["path"], sha256=d["sha256"], bytes=d["bytes"], meta=d.get("meta", {}))


@dataclass(frozen=True)
class SourceRecord:
    status: Status
    on_failure: str
    fetched_at: datetime | None = None
    request: dict[str, Any] | None = None      # never contains secrets
    error: str | None = None
    payloads: tuple[PayloadRef, ...] = ()
    rejected_rows: tuple[dict[str, Any], ...] = ()
    fallback_from: str | None = None
    excluded: bool = False

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if self.fetched_at is not None and self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        if self.status == "ok" and self.fetched_at is None:
            raise ValueError("status ok requires fetched_at")
        if self.status == "failed" and not self.error:
            raise ValueError("status failed requires error")
        if self.status != "failed" and (self.fallback_from or self.excluded):
            raise ValueError("fallback_from/excluded are only valid for status failed")
        if self.fallback_from and self.excluded:
            raise ValueError("a failed source is either excluded or uses a fallback, not both")

    def to_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "on_failure": self.on_failure,
            "fetched_at": _dt_to_json(self.fetched_at),
            "request": self.request,
            "error": self.error,
            "payloads": [p.to_json() for p in self.payloads],
            "rejected_rows": list(self.rejected_rows),
            "fallback_from": self.fallback_from,
            "excluded": self.excluded,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> SourceRecord:
        return cls(
            status=d["status"],
            on_failure=d["on_failure"],
            fetched_at=_dt_from_json(d["fetched_at"]),
            request=d["request"],
            error=d["error"],
            payloads=tuple(PayloadRef.from_json(p) for p in d["payloads"]),
            rejected_rows=tuple(d["rejected_rows"]),
            fallback_from=d["fallback_from"],
            excluded=d["excluded"],
        )


# --- writer -------------------------------------------------------------------------

class SnapshotWriter:
    """Builds one snapshot. Use as a context manager; an exception discards it.

        with SnapshotWriter(root, config_raw, secrets=[api_key]) as w:
            ref = w.add_payload("evds", "TP.FG.J0.json", body, meta={...})
            w.set_source("evds", SourceRecord(status="ok", ..., payloads=(ref,)))
            snap = w.finalize()
    """

    def __init__(
        self,
        root: str | Path,
        config_raw: dict[str, Any],
        *,
        created_at: datetime | None = None,
        snapshot_id: str | None = None,
        secrets: Iterable[str] = (),
    ) -> None:
        self.root = Path(root)
        self.created_at = (created_at or datetime.now(TR_TZ)).astimezone(TR_TZ)
        self.snapshot_id = snapshot_id or new_snapshot_id(self.created_at)
        if not _ID_RE.match(self.snapshot_id):
            raise SnapshotError(f"invalid snapshot id {self.snapshot_id!r}")
        self._config_raw = config_raw
        self._secrets = [s for s in secrets if s]
        self._sources: dict[str, SourceRecord] = {}
        self._payloads: dict[str, PayloadRef] = {}
        self._tmp = self.root / f"{TMP_PREFIX}{self.snapshot_id}"
        self._final = self.root / self.snapshot_id
        self._done = False

        if self._final.exists():
            raise SnapshotError(f"snapshot {self.snapshot_id} already exists")
        self.root.mkdir(parents=True, exist_ok=True)
        self._tmp.mkdir()
        (self._tmp / PAYLOADS).mkdir()

    def __enter__(self) -> SnapshotWriter:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._done:
            self.abort()

    def cache_dir(self, source: str) -> Path:
        """Folder of the immutable cache files of `source` (I11)."""
        return _cache_root(self.root) / source

    def add_cache_payload(self, source: str, name: str,
                          meta: dict[str, Any] | None = None) -> PayloadRef:
        """Reference an existing cache file of `source` (not copied)."""
        rel = self._new_rel(CACHE, source, name)
        f = _cache_root(self.root) / source / name
        if not f.is_file():
            raise SnapshotError(f"no cache file {rel}")
        data = f.read_bytes()
        ref = PayloadRef(path=rel, sha256=sha256_bytes(data), bytes=len(data), meta=meta or {})
        self._payloads[rel] = ref
        return ref

    def _new_rel(self, top: str, source: str, name: str) -> str:
        self._check_open()
        if not _SOURCE_RE.match(source):
            raise SnapshotError(f"invalid source name {source!r}")
        if not _PAYLOAD_NAME_RE.match(name) or ".." in name:
            raise SnapshotError(f"invalid payload name {name!r}")
        rel = f"{top}/{source}/{name}"
        if rel in self._payloads:
            raise SnapshotError(f"payload {rel} already added")
        return rel

    def add_payload(self, source: str, name: str, data: bytes,
                    meta: dict[str, Any] | None = None) -> PayloadRef:
        rel = self._new_rel(PAYLOADS, source, name)
        target = self._tmp / rel
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
        ref = PayloadRef(path=rel, sha256=sha256_bytes(data), bytes=len(data), meta=meta or {})
        self._payloads[rel] = ref
        return ref

    def set_source(self, source: str, record: SourceRecord) -> None:
        self._check_open()
        if source in self._sources:
            raise SnapshotError(f"source {source!r} already recorded")
        for p in record.payloads:
            if self._payloads.get(p.path) != p:
                raise SnapshotError(f"payload {p.path} was not added to this snapshot")
        self._sources[source] = record

    def record(self, source: str) -> SourceRecord | None:
        """The record set for `source` so far (a later source may depend on it)."""
        return self._sources.get(source)

    def read_payload(self, rel_path: str) -> bytes:
        """Bytes of a payload added to this (not yet final) snapshot."""
        self._check_open()
        if rel_path not in self._payloads:
            raise SnapshotError(f"payload {rel_path} was not added to this snapshot")
        return _payload_file(self._tmp, self.root, rel_path).read_bytes()

    def finalize(self) -> Snapshot:
        self._check_open()
        used = {p.path for r in self._sources.values() for p in r.payloads}
        orphans = sorted(self._payloads.keys() - used)
        if orphans:
            raise SnapshotError(f"payloads not referenced by any source: {orphans}")

        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "snapshot_id": self.snapshot_id,
            "created_at": _dt_to_json(self.created_at),
            "tool_version": __version__,
            "config": self._config_raw,
            "sources": {name: r.to_json() for name, r in sorted(self._sources.items())},
        }
        body = _dump(manifest)
        text = body.decode("utf-8")
        for s in self._secrets:
            if s in text:
                raise SnapshotError("manifest contains a secret value; refusing to write it")

        (self._tmp / MANIFEST).write_bytes(body)
        (self._tmp / MANIFEST_HASH).write_text(sha256_bytes(body) + "\n", encoding="ascii")
        for path in self._tmp.rglob("*"):
            if path.is_file():
                os.chmod(path, stat.S_IREAD)
        os.rename(self._tmp, self._final)
        self._done = True
        return open_snapshot(self.root, self.snapshot_id)

    def abort(self) -> None:
        if self._tmp.exists():
            _rmtree(self._tmp)
        self._done = True

    def _check_open(self) -> None:
        if self._done:
            raise SnapshotError("snapshot writer is closed")


def _cache_root(snapshots_root: Path) -> Path:
    return snapshots_root.parent / CACHE


def _payload_file(snap_dir: Path, snapshots_root: Path, rel: str) -> Path:
    """File of a payload path: in the snapshot folder, or in the cache."""
    if rel.startswith(CACHE + "/"):
        return _cache_root(snapshots_root) / rel[len(CACHE) + 1:]
    return snap_dir / rel


def _make_writable_and_retry(func, path, _exc) -> None:
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: Path) -> None:
    # `onexc` exists from 3.12; 3.11 only has `onerror` (same use here).
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    else:
        shutil.rmtree(path, onerror=_make_writable_and_retry)


# --- reader ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    path: Path
    snapshot_id: str
    created_at: datetime
    tool_version: str
    config_raw: dict[str, Any]
    sources: dict[str, SourceRecord]

    def read_payload(self, rel_path: str) -> bytes:
        """Read one payload and check its hash again."""
        ref = self._ref(rel_path)
        data = _payload_file(self.path, self.path.parent, ref.path).read_bytes()
        if sha256_bytes(data) != ref.sha256:
            raise SnapshotIntegrityError(f"{self.snapshot_id}: hash mismatch for {ref.path}")
        return data

    def _ref(self, rel_path: str) -> PayloadRef:
        for r in self.sources.values():
            for p in r.payloads:
                if p.path == rel_path:
                    return p
        raise SnapshotError(f"{self.snapshot_id}: no payload {rel_path!r} in manifest")


def open_snapshot(root: str | Path, snapshot_id: str, *, verify: bool = True) -> Snapshot:
    """Open a finished snapshot. With verify=True (default), check every hash and
    reject files that are not in the manifest."""
    if not _ID_RE.match(snapshot_id):
        raise SnapshotError(f"invalid snapshot id {snapshot_id!r}")
    path = Path(root) / snapshot_id
    if not (path / MANIFEST).is_file():
        raise SnapshotError(f"snapshot {snapshot_id} not found in {root}")

    body = (path / MANIFEST).read_bytes()
    if verify:
        expected = (path / MANIFEST_HASH).read_text(encoding="ascii").strip()
        if sha256_bytes(body) != expected:
            raise SnapshotIntegrityError(f"{snapshot_id}: manifest hash mismatch")

    m = json.loads(body)
    if m.get("manifest_version") != MANIFEST_VERSION or m.get("snapshot_id") != snapshot_id:
        raise SnapshotError(f"{snapshot_id}: unsupported or inconsistent manifest")
    snap = Snapshot(
        path=path,
        snapshot_id=snapshot_id,
        created_at=_dt_from_json(m["created_at"]),
        tool_version=m["tool_version"],
        config_raw=m["config"],
        sources={k: SourceRecord.from_json(v) for k, v in m["sources"].items()},
    )
    if verify:
        _verify_files(snap)
    return snap


def _verify_files(snap: Snapshot) -> None:
    listed = {}
    for r in snap.sources.values():
        for p in r.payloads:
            listed[p.path] = p
    for rel, ref in listed.items():
        f = _payload_file(snap.path, snap.path.parent, rel)
        if not f.is_file():
            raise SnapshotIntegrityError(f"{snap.snapshot_id}: missing payload {rel}")
        if sha256_bytes(f.read_bytes()) != ref.sha256:
            raise SnapshotIntegrityError(f"{snap.snapshot_id}: hash mismatch for {rel}")
    on_disk = {
        p.relative_to(snap.path).as_posix()
        for p in (snap.path / PAYLOADS).rglob("*") if p.is_file()
    }
    extra = sorted(on_disk - listed.keys())
    if extra:
        raise SnapshotIntegrityError(f"{snap.snapshot_id}: files not in manifest: {extra}")


def list_snapshots(root: str | Path) -> list[Snapshot]:
    """All finished snapshots, oldest first (by created_at). Manifests only, no
    payload hash check."""
    root = Path(root)
    if not root.is_dir():
        return []
    snaps = [
        open_snapshot(root, d.name, verify=False)
        for d in root.iterdir()
        if d.is_dir() and _ID_RE.match(d.name) and (d / MANIFEST).is_file()
    ]
    return sorted(snaps, key=lambda s: (s.created_at, s.snapshot_id))


def find_previous_ok(root: str | Path, source: str, before: datetime) -> str | None:
    """Most recent snapshot created before `before` where `source` had status ok."""
    candidates = [
        s for s in list_snapshots(root)
        if s.created_at < before and s.sources.get(source, None) is not None
        and s.sources[source].status == "ok"
    ]
    return candidates[-1].snapshot_id if candidates else None
