import shutil
from datetime import date

import pytest

from conftest import FIXTURES, T0
from rmprep.adapters import manual
from rmprep.contracts import Flag
from rmprep.snapshot import SnapshotWriter

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
        6: "quantity 'gold_price' not allowed (allowed: ['deposit_rate', 'withholding_tax_rate'])",
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
    from conftest import PROJECT
    data = (PROJECT / "config" / "withholding_tax_template.csv").read_bytes()
    accepted, rejected = manual.parse_file(data, "template.csv", cfg, cfg.sources["manual"])
    assert accepted == [] and len(rejected) == 8
    assert all("missing source_url" in r["reason"] and "missing value" in r["reason"]
               for r in rejected)


def test_replay_parse_gives_same_accepted_rows(tmp_path, cfg, inbox):
    shutil.copy(RATES, inbox / "rates.csv")
    _, snap = _fetch(tmp_path, cfg, inbox)
    src = cfg.sources["manual"]
    assert manual.parse(cfg, src, snap) == manual.parse(cfg, src, snap)
