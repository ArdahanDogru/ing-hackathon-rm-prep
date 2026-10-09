"""DuckDB evidence store and Parquet export.

Table `datapoints`: all contract fields + is_latest, key (snapshot_id, id).
Table `snapshots`: one row per loaded snapshot, used to compute is_latest.
Loading a snapshot is idempotent (delete + insert in one transaction).
"""

from __future__ import annotations

import csv
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from rmprep.contracts import TR_TZ, DataPoint

_UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id VARCHAR PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS datapoints (
    snapshot_id VARCHAR NOT NULL,
    id          VARCHAR NOT NULL,
    quantity    VARCHAR NOT NULL,
    entity      VARCHAR NOT NULL,
    value       DOUBLE,
    unit        VARCHAR NOT NULL,
    as_of       DATE NOT NULL,
    source      VARCHAR NOT NULL,
    source_url  VARCHAR NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL,
    raw_ref     VARCHAR NOT NULL,
    flags       VARCHAR[] NOT NULL,
    note        VARCHAR NOT NULL,
    is_latest   BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (snapshot_id, id)
);
"""

# Contract columns in contract order. is_latest is store state, not snapshot
# content, so it is not exported (keeps replay exports identical).
_COLUMNS = ("id", "quantity", "entity", "value", "unit", "as_of", "source", "source_url",
            "fetched_at", "snapshot_id", "raw_ref", "flags", "note")


_CSV_TYPES = {"id": "VARCHAR", "quantity": "VARCHAR", "entity": "VARCHAR", "value": "DOUBLE",
              "unit": "VARCHAR", "as_of": "DATE", "source": "VARCHAR", "source_url": "VARCHAR",
              "fetched_at": "TIMESTAMPTZ", "snapshot_id": "VARCHAR", "raw_ref": "VARCHAR",
              "flags": "VARCHAR", "note": "VARCHAR"}
_FLAG_SEP = "|"


def _write_staging_csv(f, points: list[DataPoint]) -> None:
    """One CSV row per point, columns in _COLUMNS order. value None -> empty
    field (NULL); floats use repr, which round-trips exactly."""
    # "\n" row ends: with the csv default "\r\n", DuckDB rejects quoted fields
    # that contain a bare "\n".
    w = csv.writer(f, lineterminator="\n")
    for p in points:
        w.writerow([p.id, p.quantity, p.entity, "" if p.value is None else repr(p.value),
                    p.unit, p.as_of.isoformat(), p.source, p.source_url,
                    p.fetched_at.isoformat(), p.snapshot_id, p.raw_ref,
                    _FLAG_SEP.join(p.sorted_flags()), p.note])


def _bulk_insert_sql(staging: str) -> str:
    path = staging.replace("'", "''")
    types = ", ".join(f"'{c}': '{t}'" for c, t in _CSV_TYPES.items())
    not_null = ", ".join(f"'{c}'" for c, t in _CSV_TYPES.items() if c != "value")
    return f"""
        INSERT INTO datapoints ({', '.join(_COLUMNS)})
        SELECT id, quantity, entity, value, unit, as_of, source, source_url, fetched_at,
               snapshot_id, raw_ref,
               CASE WHEN flags = '' THEN []::VARCHAR[]
                    ELSE string_split(flags, '{_FLAG_SEP}') END,
               note
        FROM read_csv('{path}', header = false, auto_detect = false, delim = ',',
                      quote = '"', escape = '"', columns = {{{types}}},
                      force_not_null = [{not_null}])
    """


class EvidenceStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(str(path))
        self.con.execute("SET TimeZone = 'Europe/Istanbul'")
        self.con.execute(_SCHEMA)

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> EvidenceStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- write -------------------------------------------------------------------

    def load(self, snapshot_id: str, created_at: datetime, points: list[DataPoint]) -> None:
        """Replace all rows of one snapshot, then recompute is_latest."""
        if any(p.snapshot_id != snapshot_id for p in points):
            raise ValueError("all points must belong to the snapshot being loaded")
        con = self.con
        # Parameter binding in DuckDB is slow (~7 s per 500 rows, ~110 s for a
        # TEFAS export). Stage the rows in a temporary CSV and bulk-load it.
        fd, staging = tempfile.mkstemp(suffix=".csv", prefix="rmprep-load-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                _write_staging_csv(f, sorted(points, key=lambda p: p.id))
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute("DELETE FROM datapoints WHERE snapshot_id = ?", [snapshot_id])
                con.execute("DELETE FROM snapshots WHERE snapshot_id = ?", [snapshot_id])
                con.execute("INSERT INTO snapshots VALUES (?, CAST(? AS TIMESTAMPTZ))",
                            [snapshot_id, created_at.isoformat()])
                con.execute(_bulk_insert_sql(staging))
                con.execute("""
                    UPDATE datapoints SET is_latest = (snapshot_id = (
                        SELECT snapshot_id FROM snapshots
                        ORDER BY created_at DESC, snapshot_id DESC LIMIT 1))
                """)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        finally:
            os.remove(staging)

    # --- read ----------------------------------------------------------------------

    def latest_snapshot_id(self) -> str | None:
        row = self.con.execute(
            "SELECT snapshot_id FROM snapshots ORDER BY created_at DESC, snapshot_id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def snapshot_ids(self) -> list[str]:
        return [r[0] for r in self.con.execute(
            "SELECT snapshot_id FROM snapshots ORDER BY created_at, snapshot_id").fetchall()]

    def points(self, snapshot_id: str) -> list[DataPoint]:
        cols = [c if c != "fetched_at" else "epoch_us(fetched_at)" for c in _COLUMNS]
        rows = self.con.execute(
            f"SELECT {', '.join(cols)} FROM datapoints WHERE snapshot_id = ? ORDER BY id",
            [snapshot_id]).fetchall()
        out = []
        for r in rows:
            d = dict(zip(_COLUMNS, r))
            d["fetched_at"] = _from_epoch_us(d["fetched_at"])
            d["flags"] = frozenset(d["flags"])
            out.append(DataPoint(**d))
        return out

    def is_latest(self, snapshot_id: str) -> dict[str, bool]:
        """id -> is_latest for the rows of one snapshot."""
        return dict(self.con.execute(
            "SELECT id, is_latest FROM datapoints WHERE snapshot_id = ? ORDER BY id",
            [snapshot_id]).fetchall())

    # --- export ----------------------------------------------------------------------

    def export_parquet(self, snapshot_id: str, out_dir: str | Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{snapshot_id}.parquet"
        path_sql = str(target).replace("'", "''")
        self.con.execute(
            f"COPY (SELECT {', '.join(_COLUMNS)} FROM datapoints "
            f"WHERE snapshot_id = $sid ORDER BY id) TO '{path_sql}' (FORMAT PARQUET)",
            {"sid": snapshot_id})
        return target


def _from_epoch_us(us: int) -> datetime:
    # Read TIMESTAMPTZ as epoch microseconds: exact, and no pytz dependency.
    return (_UTC_EPOCH + timedelta(microseconds=us)).astimezone(TR_TZ)
