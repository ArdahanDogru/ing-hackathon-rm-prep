import shutil
from datetime import date

import pytest

from tests.ingest.conftest import FIXTURES, T0
from rmprep.ingest.adapters import manual
from rmprep.contracts import Flag
from rmprep.ingest.snapshot import SnapshotWriter

RATES = FIXTURES / "manual" / "rates.csv"


@pytest.fixture
def inbox(tmp_path):
    d = tmp_path / "inbox"
    d.mkdir()
    return d


def _fetch(tmp_path, cfg, inbox):
    src = cfg.sources["manual"]
    w = SnapshotWriter(tmp_path / "snaps", {}, created_at=T0, snapshot_id="20261009-150000-0001")
    rec = manual.fetch(src, w, cfg, inbox=inbox, now=lambda: T0)
    w.set_source("manual", rec)
    return rec, w.finalize()


def test_bad_rows_rejected_with_reasons(tmp_path, cfg, inbox):
    shutil.copy(RATES, inbox / "rates.csv")
    rec, _ = _fetch(tmp_path, cfg, inbox)
    assert rec.status == "ok"
    reasons = {r["row"]: r["reason"] for r in rec.rejected_rows}
    assert reasons == {
        4: "missing source_url",
        5: "missing as_of",
        6: f"quantity 'gold_price' not allowed "
           f"(allowed: {list(cfg.sources['manual'].allowed_quantities)})",
        7: "bad value 'abc'",
        8: "unit 'TRY' does not match quantity unit 'pct'",
    }
    assert all(r["file"] == "rates.csv" for r in rec.rejected_rows)


def test_accepted_rows_flagged_manual_entry(tmp_path, cfg, inbox):
    shutil.copy(RATES, inbox / "rates.csv")
    _, snap = _fetch(tmp_path, cfg, inbox)
    pts = manual.parse(cfg, cfg.sources["manual"], snap)
    assert [(p.quantity, p.entity, p.value, p.as_of) for p in pts] == [
        ("deposit_rate", "Bank A 3M TRY", 45.5, date(2026, 10, 1)),
        ("withholding_tax_rate", "TRY deposit up to 6M", 17.5, date(2026, 7, 1)),
    ]
    assert all(p.flags == {Flag.MANUAL_ENTRY} for p in pts)
    assert pts[0].source == "manual"
    assert pts[0].source_url == "https://bank-a.example/rates"      # per-row URL
    assert pts[0].note == "3-month TRY deposit"
    assert pts[0].raw_ref == "20261009-150000-0001/payloads/manual/rates.csv#row=2"


def test_row_with_several_problems_lists_all(tmp_path, cfg, inbox):
    (inbox / "x.csv").write_text(
        "quantity;entity;value;unit;as_of;source_url\n"
        "deposit_rate;;;pct;;ftp://x\n", encoding="utf-8")
    rec, _ = _fetch(tmp_path, cfg, inbox)
    [r] = rec.rejected_rows
    assert r["reason"] == ("source_url is not an http(s) URL; missing as_of; "
                           "bad entity ''; missing value")


def test_empty_unit_takes_quantity_unit(tmp_path, cfg, inbox):
    (inbox / "x.csv").write_text(
        "quantity,entity,value,unit,as_of,source_url\n"
        "deposit_rate,Bank A,45.5,,2026-10-01,https://a.example/\n", encoding="utf-8")
    _, snap = _fetch(tmp_path, cfg, inbox)
    [p] = manual.parse(cfg, cfg.sources["manual"], snap)
    assert p.unit == "pct" and p.value == 45.5 and p.note == ""


def test_missing_column_fails_source(tmp_path, cfg, inbox):
    (inbox / "x.csv").write_text("quantity;entity;value;unit;as_of\n", encoding="utf-8")
    rec, _ = _fetch(tmp_path, cfg, inbox)
    assert rec.status == "failed" and "missing column(s) ['source_url']" in rec.error


def test_empty_inbox_fails(tmp_path, cfg, inbox):
    rec, _ = _fetch(tmp_path, cfg, inbox)
    assert rec.status == "failed"


def test_unfilled_withholding_template_is_fully_rejected(cfg):
    # Brief rule 7: tax rates are never invented. The empty template must not
    # produce a single row if someone copies it to the inbox unfilled.
    from tests.ingest.conftest import PROJECT
    data = (PROJECT / "config" / "withholding_tax_template.csv").read_bytes()
    accepted, rejected = manual.parse_file(data, "template.csv", cfg, cfg.sources["manual"])
    assert accepted == [] and len(rejected) == 8
    assert all("missing source_url" in r["reason"] and "missing value" in r["reason"]
               for r in rejected)


# --- I7: valid_until ---------------------------------------------------------------------

VALID_UNTIL_CSV = (
    "quantity;entity;value;unit;as_of;source_url;note;valid_until\n"
    "withholding_tax_rate;TRY deposit up to 6M;17,5;pct;01.07.2026;https://www.gib.gov.tr/;"
    "CK 11444;08.10.2026\n"                                       # row 2: one day before T0
    "withholding_tax_rate;TRY deposit 6M-1Y;15;pct;01.07.2026;https://www.gib.gov.tr/;"
    ";09.10.2026\n"                                               # row 3: on the end date
    "deposit_rate;Bank A 3M TRY;45,5;pct;01.10.2026;https://bank-a.example/;;\n"   # row 4: empty
    "withholding_tax_rate;TRY deposit 1Y+;10;pct;01.07.2026;https://www.gib.gov.tr/;"
    ";2026-09-30\n"                                               # row 5: ISO date, no own note
)


def _valid_until_points(tmp_path, cfg, inbox, **kw):
    (inbox / "tax.csv").write_text(VALID_UNTIL_CSV, encoding="utf-8")
    _, snap = _fetch(tmp_path, cfg, inbox)
    return {p.entity: p for p in manual.parse(cfg, cfg.sources["manual"], snap, **kw)}


def test_row_after_valid_until_is_stale_with_note(tmp_path, cfg, inbox):
    p = _valid_until_points(tmp_path, cfg, inbox)["TRY deposit up to 6M"]
    assert p.flags == {Flag.MANUAL_ENTRY, Flag.STALE}
    assert p.note == "CK 11444; valid until 08.10.2026; check the current value"
    assert p.value == 17.5 and p.as_of == date(2026, 7, 1)


def test_row_without_own_note_gets_only_the_end_date_note(tmp_path, cfg, inbox):
    p = _valid_until_points(tmp_path, cfg, inbox)["TRY deposit 1Y+"]
    assert p.flags == {Flag.MANUAL_ENTRY, Flag.STALE}
    assert p.note == "valid until 30.09.2026; check the current value"


def test_row_on_valid_until_date_is_not_stale(tmp_path, cfg, inbox):
    p = _valid_until_points(tmp_path, cfg, inbox)["TRY deposit 6M-1Y"]
    assert p.flags == {Flag.MANUAL_ENTRY} and p.note == ""


def test_empty_valid_until_means_no_end_date(tmp_path, cfg, inbox):
    p = _valid_until_points(tmp_path, cfg, inbox)["Bank A 3M TRY"]
    assert p.flags == {Flag.MANUAL_ENTRY}


def test_valid_until_uses_out_date_for_fallback(tmp_path, cfg, inbox):
    # Rows re-emitted for a newer snapshot are checked against that snapshot's date.
    pts = _valid_until_points(tmp_path, cfg, inbox, out_snapshot_id="20261010-090000-0002",
                              out_date=date(2026, 10, 10))
    assert Flag.STALE in pts["TRY deposit 6M-1Y"].flags


def test_bad_valid_until_rejects_row(tmp_path, cfg, inbox):
    (inbox / "x.csv").write_text(
        "quantity;entity;value;unit;as_of;source_url;valid_until\n"
        "deposit_rate;Bank A;45;pct;01.10.2026;https://a.example/;31.13.2026\n",
        encoding="utf-8")
    rec, snap = _fetch(tmp_path, cfg, inbox)
    assert rec.rejected_rows == ({"file": "x.csv", "row": 2,
                                  "reason": "bad valid_until '31.13.2026'"},)
    assert manual.parse(cfg, cfg.sources["manual"], snap) == []


def test_file_without_valid_until_column_has_no_stale_rows(tmp_path, cfg, inbox):
    shutil.copy(RATES, inbox / "rates.csv")
    _, snap = _fetch(tmp_path, cfg, inbox)
    assert all(Flag.STALE not in p.flags for p in manual.parse(cfg, cfg.sources["manual"], snap))


def test_replay_parse_gives_same_accepted_rows(tmp_path, cfg, inbox):
    shutil.copy(RATES, inbox / "rates.csv")
    _, snap = _fetch(tmp_path, cfg, inbox)
    src = cfg.sources["manual"]
    assert manual.parse(cfg, src, snap) == manual.parse(cfg, src, snap)
