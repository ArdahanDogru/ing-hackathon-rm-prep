"""Manual CSV adapter: values entered by hand (bank deposit rates, withholding tax).

Columns: quantity, entity, value, unit, as_of, source_url[, note].
A row is rejected (recorded in the manifest, not stored) if it has no
source_url or as_of, or any other field is invalid. Accepted rows are flagged
`manual_entry`. The same validation runs at fetch and at replay, so the
accepted set is identical.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from rmprep.ingest.adapters._inbox import list_inbox, payload_name
from rmprep.ingest.config import Config, ManualSource, normalize_header
from rmprep.contracts import TR_TZ, DataPoint, Flag
from rmprep.ingest.parsing import ParseError, detect_decimal, parse_date, parse_number, read_csv_rows
from rmprep.ingest.snapshot import Snapshot, SnapshotWriter, SourceRecord, raw_ref

REQUIRED_COLUMNS = ("quantity", "entity", "value", "unit", "as_of", "source_url")
OPTIONAL_COLUMNS = ("note",)


@dataclass(frozen=True)
class ManualRow:
    locator: str
    quantity: str
    entity: str
    value: float
    unit: str
    as_of: date
    source_url: str
    note: str


def parse_file(data: bytes, name: str, cfg: Config,
               src: ManualSource) -> tuple[list[ManualRow], list[dict[str, Any]]]:
    """(accepted rows, rejected rows). Raises ParseError only for file-level
    problems (empty file, missing columns)."""
    rows = read_csv_rows(data)
    if not rows:
        raise ParseError(f"{name}: empty file")
    header = [normalize_header(h).replace(" ", "_") for h in rows[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ParseError(f"{name}: missing column(s) {missing}")
    idx = {h: i for i, h in enumerate(header)}

    def get(row: list[str], col: str) -> str:
        i = idx.get(col)
        return row[i].strip() if i is not None and i < len(row) else ""

    body = list(enumerate(rows[1:], start=2))
    decimal = detect_decimal(get(r, "value") for _, r in body)

    accepted: list[ManualRow] = []
    rejected: list[dict[str, Any]] = []
    for n, row in body:
        if all(not c.strip() for c in row):
            continue
        reasons: list[str] = []

        url = get(row, "source_url")
        if not url:
            reasons.append("missing source_url")
        elif not url.lower().startswith(("http://", "https://")):
            reasons.append("source_url is not an http(s) URL")

        as_of = None
        if not get(row, "as_of"):
            reasons.append("missing as_of")
        else:
            try:
                as_of = parse_date(get(row, "as_of"))
            except ParseError:
                reasons.append(f"bad as_of {get(row, 'as_of')!r}")

        quantity = get(row, "quantity")
        expected_unit = None
        if quantity not in src.allowed_quantities:
            reasons.append(f"quantity {quantity!r} not allowed "
                           f"(allowed: {list(src.allowed_quantities)})")
        else:
            expected_unit = cfg.quantities[quantity].unit

        entity = get(row, "entity")
        if not entity or "|" in entity:
            reasons.append(f"bad entity {entity!r}")

        value = None
        try:
            value = parse_number(get(row, "value"), decimal)
            if value is None:
                reasons.append("missing value")
        except ParseError:
            reasons.append(f"bad value {get(row, 'value')!r}")

        unit = get(row, "unit")
        if expected_unit and unit and unit != expected_unit:
            reasons.append(f"unit {unit!r} does not match quantity unit {expected_unit!r}")

        if reasons:
            rejected.append({"file": name, "row": n, "reason": "; ".join(reasons)})
        else:
            accepted.append(ManualRow(
                locator=f"row={n}", quantity=quantity, entity=entity, value=value,
                unit=expected_unit, as_of=as_of, source_url=url, note=get(row, "note")))
    return accepted, rejected


def fetch(
    src: ManualSource,
    writer: SnapshotWriter,
    cfg: Config,
    *,
    inbox: Path,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
) -> SourceRecord:
    files = list_inbox(inbox, src.file_patterns)
    request = {"inbox": src.inbox, "files": [f.name for f in files],
               "method": "manual CSV files; no HTTP"}

    def failed(error: str) -> SourceRecord:
        return SourceRecord(status="failed", on_failure=src.on_failure,
                            request=request, error=error)

    if not files:
        return failed(f"no files matching {list(src.file_patterns)} in {src.inbox}")
    received, rejected = [], []
    for f in files:
        data = f.read_bytes()
        name = payload_name(f.name)
        try:
            _, bad = parse_file(data, name, cfg, src)
        except ParseError as e:
            return failed(str(e))
        received.append((f.name, name, data))
        rejected.extend(bad)

    fetched_at = now()
    refs = tuple(writer.add_payload(src.name, name, data, meta={"original_name": original})
                 for original, name, data in received)
    return SourceRecord(status="ok", on_failure=src.on_failure, fetched_at=fetched_at,
                        request=request, payloads=refs, rejected_rows=tuple(rejected))


def parse(cfg: Config, src: ManualSource, snap: Snapshot, *,
          out_snapshot_id: str | None = None, out_date: date | None = None) -> list[DataPoint]:
    rec = snap.sources.get(src.name)
    if rec is None or rec.status != "ok":
        raise ValueError(f"{snap.snapshot_id}: source {src.name!r} has no ok record")
    sid = out_snapshot_id or snap.snapshot_id
    points = []
    for p in rec.payloads:
        name = p.path.rsplit("/", 1)[-1]
        accepted, _ = parse_file(snap.read_payload(p.path), name, cfg, src)
        for row in accepted:
            points.append(DataPoint.create(
                quantity=row.quantity, entity=row.entity, value=row.value, unit=row.unit,
                as_of=row.as_of, source=src.name, source_url=row.source_url,
                fetched_at=rec.fetched_at, snapshot_id=sid,
                raw_ref=raw_ref(snap.snapshot_id, p.path, row.locator),
                flags=[Flag.MANUAL_ENTRY], note=row.note))
    return points
