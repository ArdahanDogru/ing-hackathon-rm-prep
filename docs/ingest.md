# Ingestion layer — design

Status: steps 1–9 built (steps 5–9 in one run at the user's request on
2026-10-09); step 10 (KAP) is open. Code: `src/rmprep/ingest/`, tests:
`tests/ingest/`. The DataPoint and EvidenceSet types live in
`src/rmprep/contracts.py` (lead-owned).

## Time (ingest details)

- DuckDB stores `fetched_at` as `TIMESTAMPTZ`; connections set
  `SET TimeZone = 'Europe/Istanbul'`. Converting TIMESTAMPTZ to a Python
  datetime inside DuckDB needs `pytz`, which is not a dependency: read it as
  `epoch_us(fetched_at)` (see `store._from_epoch_us`).

## Contract: DataPoint

Frozen dataclass, validated in `__post_init__`.

| field | type | rule |
|---|---|---|
| id | str | `"E" + sha1(f"{source}\|{quantity}\|{entity}\|{as_of}".encode("utf-8")).hexdigest()[:8]`, `as_of` as ISO `YYYY-MM-DD` |
| quantity | str | must be declared in `sources.yaml` `quantities` |
| entity | str | e.g. series code, fund code, bank name |
| value | float \| None | `None` requires `missing` in flags |
| unit | str | e.g. `pct`, `TRY`, `index` |
| as_of | date | observation date (Europe/Istanbul business date) |
| source | str | source key from `sources.yaml` |
| source_url | str | non-empty |
| fetched_at | datetime | must be tz-aware; converted to `Europe/Istanbul` (`contracts.TR_TZ`) |
| snapshot_id | str | snapshot that produced this row |
| raw_ref | str | `<snapshot_id>/payloads/<file>#<locator>` (row, JSON path) |
| flags | frozenset[Flag] | stored sorted |
| note | str | free text, default `""` |

Flags (`StrEnum`-like, Python 3.11 has `enum.StrEnum`): `missing`, `stale`,
`out_of_range`, `conflict`, `fallback_snapshot`, `unverified_series`,
`manual_entry`, `needs_check`.

**Checks add flags (and may append to `note`); they never change `value`,
`as_of` or any other field.** Implement checks as `DataPoint -> DataPoint` via
`dataclasses.replace(dp, flags=..., note=...)`.

## Raw snapshots

- `snapshot_id` = `YYYYMMDD-HHMMSS-<4 hex>` (Turkey-time creation time + random
  suffix).
- Written to `data/snapshots/.tmp-<id>/`, then renamed atomically; after that the
  files are set read-only. Nothing ever writes into a finished snapshot.
- `manifest.json`: snapshot_id, created_at (ISO 8601 with `+03:00`), tool version, a **copy of the
  resolved sources.yaml**, and per source: status (`ok` | `failed` | `skipped`),
  error text, request (URL without key), fetched_at, payload list
  (`path`, `sha256`, `bytes`), rejected manual rows with reasons, and
  `fallback_from` (snapshot_id) when used.
- Payloads are stored byte-for-byte as received (API JSON, copied inbox files)
  at `payloads/<source>/<name>`; each `PayloadRef` has optional `meta` (series
  code, original file name). Every payload must belong to a source record.
- `manifest.sha256` holds the manifest hash. `open_snapshot` (verify=True)
  checks the manifest hash, every payload hash, and rejects files not listed in
  the manifest. Replay aborts on any mismatch.
- `SnapshotWriter(secrets=[api_key])` refuses to write a manifest that contains
  a secret string (e.g. a key leaked in an error message).
- Use `snapshot.find_previous_ok(root, source, before)` for fallback lookup.

## Determinism (replay must give identical output)

- Parsing and checks are pure functions of (payload bytes, manifest, exclude
  set). They never
  read the wall clock, `.env`, the network, or the current `sources.yaml`.
- Reference time for staleness = manifest `created_at`, not `now()`.
- `fetched_at` comes from the manifest.
- Output rows are sorted by `id`; flags sorted; Parquet written from that order.

## Evidence store (DuckDB)

- Table `datapoints`: all contract fields + `is_latest BOOLEAN`.
  Primary key `(snapshot_id, id)`. `flags VARCHAR[]`, `value DOUBLE`.
- Loading a snapshot is idempotent: delete its rows, then insert, in one
  transaction.
- Rows are bulk-loaded through a temporary CSV + `read_csv` (see
  `store._bulk_insert_sql`). Do not go back to `executemany` or bound
  parameters: DuckDB binding took ~110 s for one TEFAS export; the CSV path
  takes < 1 s. A full ingest takes ~2 s.
- `is_latest` = true only for rows of the snapshot with the greatest
  `created_at` among loaded snapshots; recomputed after every load. Replaying an
  old snapshot does not make it latest.
- Export: `data/export/<snapshot_id>.parquet`, rows ordered by `id`, contract
  columns only. `is_latest` is store state, not snapshot content, so it is not
  exported (replay gives a byte-identical file).
- Table `snapshots(snapshot_id, created_at)` drives `is_latest`, so a snapshot
  with zero rows can still be the latest.

## Sources (`config/sources.yaml`)

Every source needs `adapter`, `tos_note` (non-empty; loader fails without it),
and `source_url`; `enabled` defaults to true, `on_failure` to `previous`.
Quantities section declares per quantity: `unit`, `max_age_days`, `min`, `max`,
`conflict_tolerance` (relative). The unit of a DataPoint always comes from its
quantity (no per-series unit). Unknown keys are errors (catches typos), and
errors name the key path, e.g. `sources.evds.series[2].quantity`.
TEFAS header matching uses `config.normalize_header`: case, extra spaces and
Turkish letters are folded (`FİYAT` = `Fiyat` = `FIYAT`).
Series codes in the shipped config are all `verified: false` until a person
checks them on the EVDS site; a `VERIFY_` code cannot be `verified: true`.

1. **EVDS** (TCMB). API key from `.env` `EVDS_API_KEY`, sent in the `key` HTTP
   header (never in the URL, never logged, never in the manifest). Series list:
   `code`, `quantity`, `entity`, `frequency` (daily|weekly|monthly),
   `verified: bool` (required, no default).
   - `verified: false` → flag `unverified_series`.
   - code starts with `VERIFY_` → no request; emit `value=None`, flags
     `missing` + `unverified_series`, `as_of` = snapshot date, note "placeholder
     series code".
   - Missing key, HTTP error, timeout, bad JSON → source fetch failure (see
     fallback).
   - From the "EVDS Web Servis Kılavuzu" (EVDS3, read 2026-10-09): base URL
     `https://evds3.tcmb.gov.tr/igmevdsms-dis/`; missing/wrong key → 403;
     max 1000 observations per request; fetch once a day; `startDate` must be
     the first day of a period → `evds.request_start` uses the first day of
     the month. The JSON response shape (`items`, `Tarih`, code with `_`) was
     confirmed by the first real ingest on 2026-10-09.
   - Tests do not use the real series list: `tests/ingest/conftest.py`
     `TEST_EVDS_SERIES` replaces it, so changing codes in `sources.yaml`
     does not break tests.
   - `python -m rmprep evds-find TEXT` / `evds-info CODE` use the metadata
     services (`datagroups`, `serieList`) with the key from `.env` to find
     codes. They are helpers only; ingest does not use them.
   - One request and one payload per series. All-or-nothing: if any series
     fails, the source fails and no payload is stored.
   - `fetch` parses every response in memory before it stores it, so a stored
     ok payload always parses on replay.
   - `null` values (holidays) are skipped, not `missing`. A series with no
     observations in the range gives one `missing` row.
   - Monthly dates (`2026-9`) → `as_of` = last day of the month.
   - `parse(cfg, src, snap, out_snapshot_id=, out_date=)`: the `out_*`
     arguments are for fallback (new snapshot_id, old `raw_ref`/`fetched_at`).

Adapter shape (all adapters): `fetch(...) -> SourceRecord` adds payloads to the
writer; `parse(cfg, src, snap, ...) -> list[DataPoint]` is pure.
2. **TEFAS**. **No scraping, no HTTP to tefas.gov.tr** (`tefas.py` imports no
   HTTP client; a test checks this). Read files a user exported
   by hand into `data/inbox/tefas/` (`.xlsx`, `.csv`). Header matching via column
   aliases in config (e.g. `Tarih`/`Date` → `date`, `Fon Kodu` → `fund_code`,
   `Fiyat` → `price`). Accept Turkish numbers (`1.234,56`) and dates
   (`09.10.2026`, `09/10/2026`, ISO). Files are copied into the snapshot; the
   inbox is not modified.
   - Header row is searched in the first 20 rows (title rows are allowed).
   - Decimal separator is detected per file (`parsing.detect_decimal`): any
     value with a comma or with several dots → Turkish style. A file whose only
     values look like `1.234` is read as decimal point.
   - CSV: UTF-8 (BOM ok) or cp1254; delimiter `;`, `,` or tab. XLSX: first sheet;
     date cells, Excel serial dates and text dates all work. `.xls` is not
     supported.
   - Empty value cell → no DataPoint for that column. Bad date/number → the file
     fails, so the source fails (all-or-nothing, like EVDS).
   - Empty inbox → source `failed` (so `on_failure` applies). Hidden files and
     Excel lock files (`~$...`) are ignored.
   - `raw_ref` locator: `row=<n>;col=<canonical column>` (xlsx: `<sheet>!row=...`).
2b. **TEFAS web** (`adapters/tefas_web.py`, source `tefas_web`). Allowed by the
   organizers (rule 8: follow each source's terms). One GET per ingest of
   `https://www.tefas.gov.tr/tr/fon-getirileri`, no redirects, honest
   User-Agent. **Never call robots-disallowed paths** (`/api/`, `/_next/`,
   `/static/`, `/private/`, `/tefasbuild`): `config.py` rejects such URLs and
   `check_url_allowed` checks again. Data: Next.js `self.__next_f.push` chunks
   → joined JSON text → one object per fund (`extract_funds`).
   - Quantities `fund_return_{1m,3m,6m,ytd,1y,3y,5y}` (pct) and
     `fund_risk_level` (1–7); entity = fund code; note = name + fund type.
   - `as_of` = previous business day before the date of the snapshot that
     holds the page (user chose option A; weekends skipped, Turkish holidays
     not known). Fallback rows keep that as_of.
   - null / "-" values give no row; risk "0" gives a row flagged out_of_range.
   - Fewer than `min_funds` (1000) funds → the page changed → source fails.
   - `flag_needs_check: true` adds `needs_check` to every row until the
     scraper has a stable record. Set to `false` for `tefas_web` and
     `tefas_detail` on 2026-10-14 (the user): 12 snapshots without a format
     change. A replay parses with the config **stored in the snapshot**
     (`build_evidence` → `snap.config_raw`), so older snapshots keep their
     `needs_check` rows; only snapshots made after the change have none. The
     same holds for every config change (I5, I7, I8).
3. **Manual CSV** in `data/inbox/manual/`: columns `quantity, entity, value, unit,
   as_of, source_url, note`. Rows without `source_url` or `as_of` are rejected
   (logged in manifest with row number + reason, not stored). Accepted rows get
   `manual_entry`.
   - Also rejected: source_url not http(s), quantity not in
     `allowed_quantities`, empty entity, empty/bad value, bad date, unit that
     differs from the quantity unit (empty unit → quantity unit). All reasons of
     a row are listed.
   - `source_url` of the DataPoint is the row's URL. `note` is the row's note.
   - Missing column in the header → source `failed`. Empty inbox → `failed`.
   - The same validation runs at fetch and at replay.
4. *(Later)* **KAP** fund documents via docling, optional extra `[kap]`; every
   extracted value flagged `needs_check`.

## Quality checks (in this order, in `quality.py`)

1. **Plausibility**: value outside `[min, max]` of its quantity → `out_of_range`.
2. **Staleness**: per `(source, quantity, entity)`, only the latest `as_of`
   observation is checked; if `created_at.date() - as_of > max_age_days` →
   `stale`. Older observations are history and never flagged stale.
3. **Duplicates** (same `id` within a snapshot): identical values → keep one
   (lowest `raw_ref`), note the count. Different values → keep the first by
   `raw_ref`, flag `conflict` + `needs_check`, list the other values and their
   `raw_ref` in `note` (raw data stays in the snapshot).
4. **Cross-source conflict**: same `(quantity, entity, as_of)` from different
   sources, relative difference > `conflict_tolerance` → `conflict` on all of
   them.
Missing values (`None`) skip checks 1, 3 (value comparison) and 4.
Also: `as_of` after the snapshot date → `needs_check`; a quantity that is not in
the config (possible for fallback rows from an older config) → `needs_check`
and the bound checks are skipped. For cross-source conflict to work, both
sources must use the same `entity` name.

## Fallback on fetch failure

Per source in `sources.yaml`: `on_failure: previous | exclude` (default
`previous`). The policy used is recorded in the manifest.

- `previous`: take the rows of that source from the most recent earlier
  snapshot where it had status `ok`, re-parse them from that snapshot's
  payloads, and emit them with the new `snapshot_id`, flag `fallback_snapshot`,
  original `fetched_at` and `raw_ref`, note `fallback from <id>`. Manifest
  records `fallback_from`. If there is no earlier ok snapshot, EVDS emits
  `missing` rows for each configured series; other sources emit nothing.
  Replay uses the same `fallback_from` recorded in the manifest.
- `exclude`: the source contributes no rows to this snapshot. Manifest status
  `failed`, `excluded: true`.

## Source exclusion at read time (UI "cross out a source")

Exclusion is a read-time parameter, not stored state, and never alters a
snapshot or the stored rows.

- `pipeline.build_evidence(snapshot_id, exclude_sources=frozenset()) ->
  EvidenceSet` re-parses from the snapshot, drops rows of excluded sources
  **before** the quality checks, then runs the checks. This matters: a
  cross-source `conflict` caused only by an excluded source disappears.
- `EvidenceSet {snapshot_id, excluded_sources, source_status, datapoints}` —
  downstream (decisions/recommendations) must read `excluded_sources` so it can
  say what the result was computed without. Excluded ≠ missing.
- DuckDB holds the full, no-exclusion result per snapshot. Exclusion views are
  computed on demand (offline, fast) and are not written to DuckDB or Parquet.
- Same snapshot + same exclude set → identical output (same determinism rule).

## CLI

- `python -m rmprep ingest` — fetch all enabled sources → snapshot → parse →
  checks → DuckDB → Parquet. Prints snapshot_id and a flag summary.
- `python -m rmprep replay <snapshot_id>` — offline, from the snapshot only.
- `python -m rmprep show <snapshot_id> [--exclude SOURCE ...]` — table of rows +
  flag counts + source status; with `--exclude`, shows the exclusion view.
- `python -m rmprep list` — snapshots with per-source status.
- `--root PATH` (before the command) sets the project folder; default is the
  current folder. Also installed as the `rmprep` console script.
Exit code 2 only for hard errors (bad config, missing/tampered snapshot,
unknown `--exclude` source), not for failed sources.

## Tests (pytest, fixtures in `tests/ingest/fixtures/`, `tmp_path` for data dirs)

HTTP is mocked with `httpx.MockTransport` (no extra dependency). Required cases:
no API key, HTTP error (→ fallback and → no-previous-snapshot), stale,
out of range, conflict (duplicate and cross-source), bad manual row rejected,
Turkish number/date parsing, `VERIFY_` code, contract validation (null value
without `missing`, naive datetime), replay gives identical rows and identical
Parquet content, `on_failure: exclude`, read-time exclusion removes the excluded
source's rows and the cross-source conflict it caused.

## Steps (stop for review after each)

1. Project skeleton, `pyproject.toml`, `contracts.py` + tests.
2. `config.py` + `config/sources.yaml` + tests.
3. `snapshot.py` (write, hash, read-only, verify) + tests.
4. EVDS adapter + tests.
5. TEFAS adapter + tests.
6. Manual CSV adapter + tests.
7. `quality.py` + tests.
8. `store.py` (DuckDB, is_latest, Parquet) + tests.
9. `pipeline.py` (ingest, replay, fallback, `build_evidence` with exclusion) +
   `cli.py` + end-to-end replay test.
10. *(Dropped for now, 2026-10-10: KAP blocks automated requests; I3 gives valör and fees)* KAP adapter.

I1 (added 2026-10-10 for the decision layer, `docs/decision.md`): fund name
and umbrella type. The `tefas_web` parser also reads `fonUnvan` and
`fonTurAciklama` for each fund from the page it already downloads (no new
request) and returns them as `EntityInfo(name, category, source="tefas_web")`,
text verbatim. `build_evidence` fills `EvidenceSet.entities` (fund code →
`EntityInfo`) from the snapshot payload, also on replay and fallback; an
excluded or skipped `tefas_web` gives an empty mapping. No new DataPoints, no
DuckDB table (`build_evidence` already re-parses the payloads). Tests: parse
from a fixture page; replay gives identical `entities`; exclusion empties them.

I3 (approved by the user 2026-10-10): source `tefas_detail`, the TEFAS fund
detail page `https://www.tefas.gov.tr/tr/fon-detayli-analiz/<code>` (allowed by
robots.txt; checked 2026-10-10). It replaces the hand export for prices, sizes
and investor counts, and adds valör and fees (KAP is dropped for now: it blocks
automated requests, and this page has the data we needed from it).

- Funds: the funds of the `tefas_web` payload of the same snapshot, without the
  categories in `exclude_categories` (start: `Serbest Şemsiye Fonu`), 818 on
  2026-10-10.
  No `tefas_web` funds → the source fails (`on_failure`).
- Requests: one GET per fund, `User-Agent` from config, at least
  `min_interval_s` (1.0) between requests (about 14 minutes), no redirects,
  `check_url_allowed` before each request; `max_funds` (optional) limits the
  list for tests and trials.
- Payloads: the raw response bytes of each page, gzip-compressed
  (`payloads/tefas_detail/<code>.html.gz`, about 30 MB per snapshot); replay
  parses them like any other payload.
- Parser: the embedded page data objects `bilgiData` and `profilData` (Next.js
  flight data). Strict: a page without them, or with a non-numeric required
  value, is a rejected row with the reason; if more than `max_fail_share` (5 %)
  of the pages fail, the source fails (the page format changed).
- DataPoints (as built, I3 2026-10-10): required (`value_fields`)
  `fund_price` (`sonFiyat`), `fund_total_value` (`portBuyukluk`),
  `fund_investor_count` (`yatirimciSayi`), `fund_buy_valor_days`
  (`fonGeriAlisValor`, shown on the page as "Fon Alış Valörü") and
  `fund_sell_valor_days` (`fonSatisValor`, "Fon Satış Valörü"; the design had
  the two reversed). Optional (`optional_fields`; null, "" or "-" → no row):
  `fund_risk_level` (`riskDegeri`; 52 of 818 funds have none), `fund_entry_fee`
  and `fund_exit_fee` (`girisKomisyonu`, `cikisKomisyonu`; null on the 3 pages
  checked). No `fund_expense_ratio`: `fonTopGiderKesoran` is only a label, the
  value is not in the page. The same quantities as `tefas` and `tefas_web` give
  the cross-source conflict check for free.
- `as_of`: the page has **no date** (3 pages checked 2026-10-10), so the
  previous business day before the snapshot date, as for `tefas_web`. All rows
  `needs_check` until the source has a stable record.
- Failed pages are stored (audit) but give no rows; when the failed share passes
  `max_fail_share`, the fetch stops at once. The pipeline fetches
  `tefas_detail` after `tefas_web`; `ingest()` takes `sleep=time.sleep` (tests
  replace it).
- Not now: asset allocation (`portfolioDistribution`), price history.
- Tests: fixture pages for 3 funds (one with null fees), MockTransport, a page
  without data, the fail share, a disallowed path, replay identical, the
  interval (with a fake clock, no real sleep in tests).
- Later (decision D12, after I3): liquidity from the sell valör instead of the
  kind table; entry/exit fees in the net return.

I3b (2026-10-10, after the first live run): the trade status of each fund.
The first live run fetched 279 pages: 213 "TEFAS'ta işlem görüyor", 40
"TEFAS'ta İşlem Görmüyor" (no valör on the page) and 26 "Fon Alımına Kapalı,
Fon Bozumuna Kapalı". A fund that does not trade on TEFAS or is closed for
purchase cannot be bought by an ING client through TEFAS, so the decision layer
must see it.

- New quantity `fund_buyable` (unit `flag`, 0 or 1) from `profilData.tefasDurum`
  through a config table `status_map` (text → 0/1, matched after Turkish
  lower-casing and space collapsing). Start: "TEFAS'ta işlem görüyor" → 1;
  "TEFAS'ta işlem görmüyor" → 0; "Fon Alımına Kapalı, Fon Bozumuna Kapalı" → 0.
- Unknown status text → no `fund_buyable` row and a rejected-row entry with the
  text (it does not fail the page, so it does not count for `max_fail_share`).
- Later (decision D12): `fund_buyable = 0` → rejected (new hard rule
  `not_buyable`); a missing row → a data-quality note, not a rejection.

I5 (approved by the user 2026-10-14): annual TÜFE from EVDS, so that the
manual `cpi_annual` row is no longer the only source. Checked 2026-10-14:
`TP.TUKFIY2025.GENEL` starts in 2005; 137.23 (2026-9) / 105.78 (2025-9) − 1 =
29.73 %, the value of the manual row.

- Series option `lookback_days` (optional, positive int): overrides the
  source's `lookback_days` for this series only. The CPI series gets 400 (13
  months are needed); the other series keep 120.
- Series option `annual_change: {quantity, entity}` (optional; the quantity
  must exist in `quantities`): `parse` adds one DataPoint for the latest
  observation month M of the series when the observation of M − 12 months is
  in the payload: value = (index(M) / index(M − 12) − 1) × 100 (full float, no
  rounding), unit of the quantity, `as_of` = the `as_of` of M, `source` =
  `evds`, `source_url`/`fetched_at` of the series, `raw_ref` =
  `<code>:<M>/<M−12>` (e.g. `TP.TUKFIY2025.GENEL:2026-9/2025-9`), the series'
  flags (`unverified_series` if not verified), note `12-month change of
  <code>: <index M> (<M>) / <index M−12> (<M−12>) − 1`.
- No M − 12 observation (e.g. the snapshots made before I5 hold only 4
  months) → **no row at all**, not a `missing` row: a `missing` row with a
  newer `as_of` would hide the manual row in `EvidenceIndex` and remove TÜFE
  from old snapshots on replay.
- Config: `cpi_index` series → `lookback_days: 400`, `annual_change:
  {quantity: cpi_annual, entity: "TÜFE yıllık değişim (TÜİK)"}` (the entity of
  the manual row, so the cross-source conflict check compares the two). The
  manual row stays as a cross-check; with the same `as_of` the manual row is
  used (source order in `EvidenceIndex`), a newer EVDS month wins.
- Tests: a payload with 13 months gives the row (value, as_of, raw_ref, note);
  12 months gives no row; replay is identical; per-series lookback in the
  request start date; config errors (unknown quantity, bad lookback).
- As built (merged 2026-10-14, `ingest@75c6223`): `annual_change` is allowed
  only on a `monthly` series (config error otherwise); `raw_ref` keeps the
  usual form `<snapshot>/<payload path>#<code>:<M>/<M−12>`; the manifest
  request of EVDS gets `series_start_dates` {code: date} only for series with
  their own `lookback_days` (`start_date` stays the source value); a zero
  index at M − 12 also gives no row; the note uses ASCII "- 1". Live check
  2026-10-14 (EVDS and manual only, temp folder): EVDS row 29.7315 (as_of
  2026-09-30), manual row 29.73, no conflict flag. The snapshots before I5
  keep only the manual row.

I6 (approved by the user 2026-10-14): one ingest at a time, for the daily
Task Scheduler job and the "Veriyi yenile" button of the web app (W14).

- Lock file `data/.ingest.lock` (in `Paths.root`), created with exclusive
  create at the start of `ingest()` and removed in `finally`. Content: JSON
  `{"pid": <int>, "started_at": "<ISO, Europe/Istanbul>"}`.
- Lock present → `IngestBusy` (new exception in `pipeline.py`, with
  `started_at`); the CLI `ingest` prints "another ingest is running since
  <time>" and exits with code 3. A lock older than 2 hours is stale: it is
  replaced, and the replacement is logged.
- `ingest_status(paths) -> dict`: `{"running": bool, "started_at": str |
  None}` from the lock (a stale lock counts as not running).
- Tests: a second ingest while the lock exists raises `IngestBusy`; the lock
  is removed after success and after an exception; a stale lock is replaced;
  `ingest_status`; the CLI exit code 3.
- As built (merged 2026-10-14, `ingest@a3d81d9`): `Paths.lock`,
  `ingest_status(paths, now=None)`, `LOCK_STALE_AFTER` = 2 h (exactly 2 h is
  still active); the stale-lock warning goes to the logger
  `rmprep.ingest.pipeline`. Known limit: two ingests that find the same stale
  lock at the same moment can both replace it (acceptable for one daily job
  and one button). The lead added the CLI exit code 3 (`tests/cli/
  test_ingest_cli.py`) and `rmprep ingest --summary` (the source status and
  flag counts only; the daily log uses it).
- Daily job: `scripts/schedule_ingest.ps1` registers the Task Scheduler task
  "rmprep daily ingest" (07:30, a missed start runs when the laptop is on);
  `scripts/run_ingest.cmd` logs to `data/logs/ingest.log`. First run
  2026-10-14 00:56 → snapshot `20261014-005625-c76a` (813 detail pages; 2
  pages "Server disconnected", 1 HTTP 404; a new status text "Fon Alımına
  Kapalı, Fon Bozumuna Açık" on 4 funds, now mapped to `fund_buyable` 0).

I7 (approved by the user 2026-10-14): an end date for manual rows. The stopaj
rates are valid until 31.12.2026 (CK 11444), and no source publishes them in a
form a program can read, so they stay manual with an automatic warning when
they expire (brief rule 7: a current source or a confirmation note to the RM).

- Manual CSV: optional column `valid_until` (same date formats as `as_of`;
  empty = no end date). A bad date → the row is rejected with the reason. A
  file without the column works as before.
- `parse`: when the snapshot date (Turkey time) is after `valid_until`, the
  row gets the flag `stale` and the note gets `valid until <DD.MM.YYYY>;
  check the current value` (after the row's own note, with the usual note
  separator). On or before the date: no flag. Pure (the snapshot date, not
  the clock), so replay gives the same result.
- The same check at fetch and replay (like the other manual checks).
- Data (lead): the `withholding_tax_rate` rows get `valid_until` 31.12.2026.
  The decision layer turns a stale stopaj row into an RM warning (D22,
  docs/decision.md section 12).
- Tests: a row after its end date is `stale` with the note; on the end date
  it is not; an empty `valid_until`; a bad date rejects the row; a file
  without the column; replay identical.

I8 (approved by the user 2026-10-14, item 2 option A): the holdings of each
fund. The fund detail page that `tefas_detail` already downloads has
`varlikData`: a list of `{fonKodu, fonUnvan, kiymetTip, portfoyOrani}` (the
asset type and its share of the portfolio, %). On 2026-10-14: 775 of 814 pages
have it, 40 different `kiymetTip` texts, kept verbatim. (Correction by
`ing-ingest`: the pages have correct Turkish letters; the `K�ymetli` seen at
design time was a Windows console display problem.)

- New optional source key `holdings_quantity` (a quantity name; start
  `fund_holding_share`, unit `pct`). Absent → no holdings rows (old configs
  and old tests work unchanged).
- `parse`: one DataPoint per `varlikData` row: quantity = `holdings_quantity`,
  entity = `<fund code>/<kiymetTip verbatim>` (e.g. `BVF/Ters-Repo`), value =
  `portfoyOrani` (may be negative: `Repo` = borrowing), `as_of` and flags as
  the other `tefas_detail` rows, `raw_ref` = the page payload with
  `#varlikData[<i>]`, note = the `kiymetTip` text. Rows of another fund code
  than the page's are skipped (rejected-row note). A non-numeric share → no
  row and a rejected-row note; it does not fail the page and does not count
  for `max_fail_share`. No `varlikData` or an empty list → no rows.
- Replay of older snapshots gives these rows too (the payloads are stored).
- Quantity (lead adds it to `config/sources.yaml` after the merge):
  `fund_holding_share` unit pct, min −100, max 200, conflict_tolerance 0.01.
- Tests: a page with `varlikData` (rows, entities, negative share), a page
  without it, a bad share, another fund's row, no `holdings_quantity` in the
  config, replay identical.
- As built (merged 2026-10-14, `ingest@c8f40e3`): an empty `kiymetTip` and a
  `kiymetTip` with `|` (the id hash separator) also give no row and a
  rejected-row note; `varlikData` that is null or not a list gives no rows.
  Read-only check of snapshot `20261014-005625-c76a`: 813 pages, no repeated
  `kiymetTip` within a fund, no `|`, no row of another fund, all shares
  numeric. Config added by the lead (`bde2708`). The holdings appear only in
  snapshots made with this config (the replay rule above): the first one is
  the next ingest after 2026-10-14 02:00.
- I7 as built (`ingest@1c4d758`): fallback rows are checked against the new
  snapshot date. Data: the stopaj CSV has `valid_until` 31.12.2026 **before**
  `note`, because the manual CSV puts extra `;` fields of an unquoted note
  into the last column.

I10 (approved by the user 2026-10-14): exchange-traded funds (BYF) from TEFAS.
The returns page has a BYF view, `https://www.tefas.gov.tr/tr/fon-getirileri?fundType=BYF`
(an HTML page under the allowed `/`; linked from the page we read today). Probe
2026-10-14: 37 ETFs, the same embedded data as `tefas_web` (returns 1m–5y,
`riskDegeri` for 36, name, `fonTurAciklama` such as "Hisse Senedi Yoğun",
"Endeks Fon"). The fund detail page works for ETF codes too (BOE: price, size,
holdings 100 % Hisse Senedi; `tefasDurum` "Platformda İşlem Görmüyor", because
ETFs trade on the exchange; `fonSatisValor` null; `yatirimciSayi` 0).

- New source `tefas_byf`, adapter `tefas_web` (the same parser), its own `url`,
  `min_funds` 20, `on_failure: previous`; `EntityInfo.source` = `tefas_byf`, so
  the decision layer knows the kind. Same quantities and entities (fund codes;
  BYF codes do not clash with fund codes).
- `tefas_detail`: `funds_from` becomes a list (`[tefas_web, tefas_byf]`); the
  BYF codes are fetched too (about 37 more pages). The status text "Platformda
  İşlem Görmüyor" maps to `fund_buyable` 1 for a BYF code (bought on the
  exchange) — the status map gets a per-source override, or the decision layer
  ignores `fund_buyable` for ETFs (decision D26 does the latter; ingest maps
  the text to 0 like "TEFAS'ta işlem görmüyor" and keeps it verbatim in the
  note).
- Tests: the BYF page fixture parses; entities carry `tefas_byf`; the detail
  list joins both sources; old configs (one `funds_from` string) still work.

I11 (approved by the user 2026-10-14): Borsa İstanbul shares from the official
end-of-day bulletins. Checked 2026-10-14: `robots.txt` allows `/`; real-time
("eşanlı") data needs a signed licence; the end-of-day bulletin files are
published for download (paths in `/files/DataFilePaths.zip`: "Bülten Verileri"
= `/data/thb/YYYY/AA/thbYYYYAAGG1.zip`, one ZIP of about 260 KB a day, one CSV
`;`-separated, UTF-8 with BOM, two header lines TR and EN, decimal point). The
13.10.2026 file: 628 shares with a closing price (`ENSTRUMAN GRUBU` `EQT`,
code ending `.E`), 100 in BIST 100; 36 ETFs (`ETF`, `.F`); 10,298 warrants and
certificates (`ECW`, `EPW`), not used (complex products, see decision D26).

- New source `bist_bulletin`, adapter `bist_bulletin`; `url` template with
  `{yyyy}`, `{mm}`, `{yyyymmdd}`; `history_days` 400; `min_interval_s` 1.0;
  `user_agent` as for TEFAS; `on_failure: previous`.
- Cache: the bulletin of a past day never changes, so each file is fetched
  once into `data/cache/bist_bulletin/thb<date>1.zip` (immutable, read-only
  after write) with its SHA-256. Weekends are skipped; a weekday that returns
  404 is a holiday or not yet published, stored as a small marker so it is not
  asked again (except for the last 3 days, which are asked again). The first
  run fetches about 280 files (5 minutes), a daily run one.
- Snapshot: the manifest lists every cache file used (date, path, SHA-256,
  bytes) as payload references that live in the cache; `open_snapshot` and
  replay verify them like snapshot payloads (a changed or missing cache file =
  replay error). The snapshot does not copy the 70 MB of history.
- Parse (pure, from the files of the manifest): shares only (`EQT`, `.E`,
  closing price > 0). Adjusted closes: walking forward by day, when a day's
  `ONCEKI KAPANIS FIYATI` differs from the previous day's `KAPANIS FIYATI` by
  more than 0.1 %, all earlier closes of that share are multiplied by
  their ratio (splits, bonus shares, dividends); the number of adjustments goes
  into the note.
- DataPoints per share (entity = the code without `.E`, e.g. `THYAO`; `as_of` =
  the bulletin date of the newest file; `raw_ref` = the files used):
  `stock_close` (TRY), `stock_return_1m|3m|6m|1y` (pct, adjusted close on the
  newest day vs. the last trading day on or before the date 1/3/6/12 months
  earlier; no row when the history is shorter), `stock_volatility_1y` (pct,
  the SPK method on adjusted closes: weekly return = close of the week's last
  trading day / close of its first trading day − 1 (SPK guide 9.3.2.1,
  footnote 22), σ = √(52/(T−1) · Σ(r − r̄)²) over the T weeks of the last
  year; no row with fewer than 26 weeks), `stock_turnover_3m` (TRY, mean daily
  `TOPLAM ISLEM HACMI` over the last 63 trading days), `stock_bist100` (flag
  1/0, `BIST 100 ENDEKS`). `EntityInfo(name = BULTEN ADI, category =
  "BIST pay · " + PAZAR, source = "bist_bulletin")`.
- Quantities (lead adds them to `config/sources.yaml` after the merge), bounds:
  close 0.01–1e6, returns −100–10,000, volatility 0–500, turnover ≥ 0.
- Tests: small fixture bulletins (3 shares, 60 days, one split, one holiday
  404), cache reuse (no second request), the adjustment, returns, volatility
  on a known series, fewer than 26 weeks, replay identical, a changed cache
  file fails replay, no request to a disallowed path, the interval.

I11 as built (merged 2026-10-14, ingest@48ea5cd; config added by the lead):

- Config: `url` must be https on `www.borsaistanbul.com` under `/data/` and
  contain `{yyyymmdd}`; optional `timeout_seconds` (30); `recheck_days` 3;
  `min_shares` 100 (a new file with fewer shares with a close is invalid). The
  loader needs the 8 quantities above (`stock_bist100` unit `flag`).
- Snapshot: a payload path `cache/<source>/<name>` is a file in
  `<snapshots>/../cache/<source>/` (`data/cache/bist_bulletin`), with SHA-256 in
  the manifest; `open_snapshot` and `read_payload` verify it. The manifest
  request has `files {fetched, from_cache, not_published}`.
- Not published = HTTP 404, or HTTP 200 with an HTML page ("Sayfa
  Bulunamadı"). Other statuses, redirects, a bad ZIP, `TARIH` not equal to the
  day of the URL, or fewer than `min_shares` fail the source; that file is not
  cached, and the good files fetched before the failure stay in the cache.
- Header names are matched with single spaces (`ISLEM  KODU` has two in the
  file).
- Volatility: weeks with one trading day have no return; the window is the
  days after the date 12 months before the newest day. Return base = the last
  close on or before the same day 1/3/6/12 months earlier (the day is clamped
  to the month). The adjustment uses the close of the share's previous row (a
  suspended day is skipped). Turnover = the mean over the days with a row for
  the share in the last 63 bulletins.
- `raw_ref` = `<snapshot>/cache/bist_bulletin/<newest>.zip#<CODE>` (close, BIST
  100) and `#<CODE>;files=<first>..<newest>` (returns, volatility).
- Speed: the 13.10.2026 file parses in 22 ms; 280 files take about 6 s on the
  first `build_evidence` in a process. Parsed files are kept in memory per
  SHA-256, so later builds only verify the hashes.

I11b (2026-10-14, ingest@c1b7164): in the real bulletins `ONCEKI KAPANIS
FIYATI` is the previous close NOT adjusted, and `REFERANS FIYAT` is 0, so the
I11 rule never fired (KORDS 14.09: 1-month return −96 %).

- A corporate action of a share on day t: close_t / close_prev outside
  [1 − L, 1 + L]. close_prev = the close of the share's previous row (a
  suspended day is skipped). L = optional source key `adjust_jump_pct`
  (default 10.5 %; the BIST daily price limit is ±10 %).
- Ratio = `ACILIS FIYATI`_t / close_prev (close_t / close_prev when the open is
  0). All earlier closes of the share × ratio; several jumps multiply.
  **[VARSAYIM]** The open stands for the theoretical base price, so the move
  from the base to the open on that day is lost (I11c narrows this).
- The `ONCEKI KAPANIS` rule is removed. `ACILIS FIYATI` is now a required
  column; `ONCEKI KAPANIS FIYATI` is not.
- Cash dividends stay below the limit and are not adjusted: returns and
  volatility are price returns. Note of the return and volatility rows:
  "<name>; adjusted closes (N jumps beyond ±10.5 %); dividends not adjusted"
  (the volatility adds "; SPK weekly method"). `stock_close` is the real
  close, not adjusted.
- Check on the 276 cache files of snapshot 20261014-164524-42c2: 116 jumps in
  111 shares. 1-month returns: KORDS −27.8 % (was −96 %), BIMAS −5.4 %, GENIL
  −56.5 %. Some shares still show about −90 % in 1 month with 0 jumps (ANELE,
  GUNDG, TEHOL): about 20 limit-down days in a row, real, not corporate
  actions. The market fell from 14.09 to 30.09 (BIST 100 members, equal
  weight, about −24 %).

I11c (2026-10-14, ingest@0ac8aba): the base price of a jump day must agree
with the daily price limit (HRKET 21.09: open 5.72, low 5.70, high 6.91; with
the open as the base, the day counted +21 %).

- Base b: high ≤ b × (1 + P) and low ≥ b × (1 − P), so b is in
  [high / (1 + P), low / (1 − P)]. The base is the open clamped to that
  interval (HRKET: [6.28, 6.33] → 6.28). If the interval is empty, or the low
  or the high is 0, the base is the open (the close when the open is 0).
  Ratio = base / close_prev. P = optional source key `price_limit_pct`
  (default 10 %), separate from `adjust_jump_pct` (the detection, 10.5 %).
  `EN DUSUK FIYAT` and `EN YUKSEK FIYAT` are required columns.
- Check on the 276 cache files: the open is inside the interval on 99 of the
  116 jump days and is clamped on 17. HRKET 1 month +75.9 % (was +93.2 %);
  KORDS, BIMAS and GENIL are unchanged.

I11d (approved by the user 2026-10-14; ingest@81f94fc): 5 years of share history.

- `history_days` 1900 (about 1,300 files; the first run fetches about 1,000
  new files, 1 GET/s, about 17 minutes once).
- New quantities (optional in the code: rows only when they are in
  `quantities`): `stock_return_3y`, `stock_return_5y` (pct; adjusted closes;
  base = the last close on or before the same day 3/5 years earlier; no row
  when the history is shorter; max 1,000,000 %); `stock_volatility_5y` (pct;
  SPK weekly method over the weeks after the date 5 years before the newest
  day; at least 26 weeks). The notes of both volatility rows end with "SPK
  weekly method, N weeks".
- Format probe 2026-10-14 (one file a year, 2021–2025): the same column names
  every year; 2023 added "BIST KATILIM TUM ENDEKS" at the end; no BOM before
  2026; 434–588 shares a day.
- Guard: a file older than `recheck_days` that cannot be read (another
  format, a bad ZIP, too few shares) does not fail the source. It gets a
  `.bad` marker (not asked again), and the history starts after the newest
  such file, so there is no gap. The manifest request has `history_from` and
  `unreadable_newest {file, reason}`; the notes of the return and volatility
  rows add "history from <date> (<file> unreadable: <reason>)". A bad file of
  the last `recheck_days` days still fails the source.
- Memory and speed: a compact per-SHA memo (interned texts, float arrays) and
  a parse-result memo. Benchmark with 1,250 files of 2026 size: the first
  build about 33 s (estimate for the real files 15–20 s), later builds about
  2 s, peak working set 142 MB. For later, if too slow: a derived disk cache
  of the parsed shares per SHA-256 (pure, so replay stays exact; a new
  process then needs about 2–3 s).

I11e (2026-10-14; ingest@b965cec): a day without trading. The first 5-year
ingest (snapshot 20261014-182901-ce5e) marked 8–14.02.2023 as unreadable
("only 0 shares with a closing price"): Borsa İstanbul was closed after the 6
February 2023 earthquake. The I11d guard then cut the history to 2023-02-15.

- A valid bulletin (a ZIP with one CSV, the columns, `TARIH` = the day of the
  URL) with 0 shares with a closing price is a day without trading. It gets a
  `.closed` marker and is counted as `files.closed`. It is never `.bad` and
  never a failure, also in the last `recheck_days` days; there it is asked
  again, like a missing day. `min_shares` still applies when 0 < shares <
  `min_shares`. A 0-share file with another `TARIH` still fails.
- An I11d `.bad` marker whose reason starts with "only 0 shares with a closing
  price" is reclassified to `.closed` (no request). Other `.bad` markers stay.

I12 (2026-10-14, lead): long EVDS windows in parts. EVDS gives at most 1000
observations per request, so a daily or weekly series whose window is longer
than `MAX_DAYS_PER_REQUEST` (900 calendar days) is asked in contiguous parts,
oldest first (`request_windows`). Payload names: `<code>.json` for the first
part (the old name, so a short series is unchanged), `<code>.p<k>.json` for
the later ones (meta `part`); the manifest request has `series_parts {code:
n}`. Parse joins the parts in order; a later part wins on a shared date; each
row's `raw_ref` names its own part. Monthly series are never split. Used for
the BIST 100 price and total-return indices (`lookback_days` 1900, 5 years,
the later benchmark for share and ETF returns); the price index is verified
(12,250.68 on 13.10.2026 = the close in the news).

I13 (2026-10-14, lead): the parsed bulletin rows on disk. A fresh process
(CLI, API start) had to read all 1,305 ZIPs again (about 40–60 s). Now
`_day` keeps the parsed rows of each bulletin in
`data/cache/bist_bulletin/parsed/<SHA-256 of the ZIP>.json` (texts as JSON lists,
number columns as base64 of little-endian doubles, `PARSE_VERSION` 2). The file is
derived and pure: the ZIP hash is still verified on every read; a file of
another parser version, day or shape is made again; a write failure only costs
speed; snapshot payloads (not cache files) are never written. Measured on
snapshot 20261014-191003-eedf: first process about 50–60 s (writes the files),
every later new process about 12 s for the whole `build_evidence` (bulletin
rows about 4 s, the share calculation about 3 s, the other sources the rest).
Bump `PARSE_VERSION` when `read_bulletin` or `_Day` changes.

I14 (approved by the user 2026-10-16): source `ing_web`, ING's own public rate
page `https://www.ing.com.tr/tr/bilgi-destek/mevduat/mevduat-faiz-oranlari`.
It replaces the hand-copied `ing_turuncu_hesap.csv` and `ing_e_vadeli.csv`;
those files stay in `data/inbox/manual` as the fallback.

- Checked by the lead on 2026-10-16. robots.txt allows the page; it disallows
  `/documents/*`, `/objects/*`, most of `/assets/*`, the search pages and some
  form paths (config rejects disallowed paths, as for tefas_web). The terms
  (`/tr/ing/kullanim-sartlari`) say all rights reserved, for information only,
  not binding; no rule on automated access (as the `manual` tos_note).
- The rates are not in the page HTML. The page is one ASP.NET WebForms form
  (`method=post`, action = the same URL, hidden `__VIEWSTATE` (encrypted),
  `__VIEWSTATEGENERATOR`, `__VIEWSTATEENCRYPTED`; no `__EVENTVALIDATION`).
  Three requests per product, one cookie client, at least `delay_seconds` (2)
  between requests:
  1. GET the page; read the hidden `__*` inputs.
  2. POST them + `__EVENTTARGET=5575$DdlCurrencyType`, `__EVENTARGUMENT=`,
     `5575$DdlCurrencyType=0` (TL), `5575$DdlProductList=-1`. The response lists
     the products (`E_ORANGE_ACCOUNT_GROUP` Turuncu Hesap,
     `E_TIME_DEPOSIT_ACCOUNT` e-Vadeli Mevduat, `ORANGE_ACCOUNT_KID_GROUP`,
     `E_ORANGE_ACCOUNT_ACCUMULATING_GROUP`) and has new hidden inputs.
  3. POST the new hidden inputs + `__EVENTTARGET=5575$BtnSend`, currency 0,
     `5575$DdlProductList=<product>`. The response has one `<table>`.
  A POST of step 3 straight after step 1 returns no table (checked). The form
  field names, the currency value and the product values are config, not code.
- Products in config: `E_TIME_DEPOSIT_ACCOUNT` and `E_ORANGE_ACCOUNT_GROUP`
  (6 requests per ingest). The payload is the step-3 HTML of each product
  (`<product>.html`, SHA-256 in the manifest); steps 1–2 are not stored. Replay
  parses only the payloads.
- Parse (pure, from the payload):
  - e-Vadeli: header row = the amount columns (`4.999,99-99.999` …
    `30.000.000 üzeri`); each body row = a term (`1-6 gün` … `366-370 gün`);
    a cell repeats the column label, then `%15,00`. Row entity
    `ING e-Vadeli Mevduat, <term>, <column> TL`, e.g.
    `ING e-Vadeli Mevduat, 32-45 gün, 99.999,99-250.000 TL` (the manual names).
  - Turuncu: columns balance, Faiz İşletilmeyecek Tutar (TL), Hoş Geldin Faizi,
    Standart Faiz; 14 rows. Two rows per balance:
    `ING Turuncu Hesap standart, <balance> TL` and
    `ING Turuncu Hesap hoş geldin, <balance> TL`; the balance label of the first
    row `9.999,99 'e kadar` becomes `0-9.999,99` (the manual name). The amount
    without interest goes into the note ("Faiz işletilmeyecek tutar 15.000 TL").
  - quantity `deposit_rate`, unit pct, value from `%34,50` (Turkish number);
    `as_of` from the text "<d> <Turkish month> <yyyy> itibariyle geçerli" after
    the table; `source_url` = the page URL; note says gross/net not stated.
  - The page or the table changed → the source fails (`on_failure: previous`):
    no table, no as_of text, a header that does not match the config, fewer
    rows or columns than `min_rows` / `min_columns` of the product, a cell that
    is not a percent. Never partial rows.
- Which row the engine uses: the decision index takes the latest `as_of` per
  (quantity, entity), so the web rows win over the older manual rows. On the
  same `as_of`, different values give the cross-source `conflict` flag (check 4),
  since both sources use the same entity names. If the web source fails, the
  previous web snapshot rows come with `fallback_snapshot`; if none exists, the
  manual rows are used. Staleness: the existing `deposit_rate` `max_age_days`
  (14).
- First fetch (2026-10-16, "16 Ekim 2026 itibariyle geçerli"): e-Vadeli 11
  terms × 8 columns; Turuncu 14 balances. The e-Vadeli rates changed after the
  manual file of 10.10 (the engine's cell 32-45 gün / 99.999,99-250.000 TL:
  35,00 → 34,50 %; 7-15 gün: 33,00 → 32,00 %). Turuncu is unchanged.
- Tests (offline): the saved step-3 pages of 2026-10-16 as fixtures; the parse
  of both products (count, names, values, as_of, notes); the form flow with a
  mocked transport (the 3 requests, their fields, the delay, the cookie); each
  failure case above; replay identical; the precedence over the manual rows.
- Built (ingest@9927ad4, merged 2026-10-16; 53 + 4 tests). Changes to the
  design above:
  1. Config shape: per product `layout: grid | balance` and an `entity`
     template (`{row}`, `{column}` for grid; `{rate}`, `{balance}` for
     balance; any other field is a config error). Balance products also have
     `balance_header`, `no_interest_column`, `rates` (column → word in the
     name, also the row order) and `balance_labels` (page label → name text
     with "TL"; default label + " TL"). The map holds `9.999,99 'e kadar` →
     `0-9.999,99 TL` and `35.000.000 üzeri` → `35.000.000 TL üzeri` (the
     manual name). `min_columns` counts the value columns without the label
     column. `quantity` is config. Unknown keys, a duplicate product and a
     disallowed URL are config errors.
  2. Notes: grid "<d Ekim yyyy> itibariyle geçerli; ing.com.tr rate form,
     product <value>; gross/net not stated"; balance "<rate column>; Faiz
     işletilmeyecek tutar <n> TL; <same text>". `raw_ref` =
     `<snapshot>/payloads/ing_web/<product>.html#<product>;row=<row>;column=<column>`.
  3. More failure cases (the source fails, nothing is stored): the product is
     not in the step-2 product list; a body cell whose label is not its
     column; a row with another number of cells; more than one table; an HTTP
     status other than 200. Redirects are not followed (as TEFAS).
  4. The robots rules of 2026-10-16 are in code (`config.ing_robots_disallows`),
     checked at config load and before each request.
  5. A tie on the same `as_of`: both rows get `conflict`, and `EvidenceIndex`
     then takes the source that sorts last by name ("manual" > "ing_web"), so
     the manual row is used. Accepted: the manual ING files are older, and the
     conflict flag shows the tie.
  6. The manifest request has no form state; steps 1–2 are not stored.
     Fixtures: the 4 saved pages (gzip) and the list of the 116 manual names
     (the web parse gives the same 116 names).
- I14b (the user, 2026-10-16; ingest@badfdc9): all four products of the form.
  `ORANGE_ACCOUNT_KID_GROUP` (Turuncu Çocuk Hesabı: the Turuncu table, 14
  balances) and `E_ORANGE_ACCOUNT_ACCUMULATING_GROUP` (e-Turuncu Biriktiren: 2
  balances, only "Standart Faiz") are rows only; the engine does not use them
  now. `no_interest_column` is optional for `layout: balance` (absent = the
  table has no such column, and the note has no amount part; a page that has
  the column then fails the header check). 12 requests per ingest; 146 rows
  (e-Vadeli 88, Turuncu Hesap 28, Turuncu Çocuk 28, Biriktiren 2). The
  pipeline tests' `config_raw` drops `ing_web` (as `tefas_byf`), so they keep
  their source list; `ing_web` has its own tests.

I15 (the user, 2026-10-16: "add them to the ingest pipeline for now"): the TL
deposit rates of other banks, from their own public pages. Rows only: the
engine, the narrator and the web app do not use them now (a later comparison
next to the e-Vadeli option is possible).

- Lead check of 2026-10-16 (robots.txt of 10 banks, one GET per rate page, the
  legal notice pages):

  | Bank | Rate page | Rates in the static HTML | Legal notice | Now |
  |---|---|---|---|---|
  | İş Bankası | `/kampanyali-mevduat-oranlari` | one table, 9 terms × 6 amounts | `/yasal-uyari`: information only, not binding; no rule on reuse or automated access | **in** |
  | Ziraat | `/tr/fiyatlar-ve-oranlar` | TL tables for branch and internet branch (+ FX, gold, bonds, repo) | `/tr/yasal-uyari`: information only; rates in use can differ the same day | **in** |
  | Enpara (QNB) | `/hesaplar/mevduat-faiz-oranlari` | yes (4 terms × 4 amounts, in divs) | no Enpara page found; QNB `/destek/kullanim-kosullari`: content "kopyalanamaz, çoğaltılamaz, kamuya açık bir şekilde gösterilemez … ticari amaçla kullanılamaz" | **out** (terms) |
  | QNB | `/vadeli-mevduat-urunleri` | only the stopaj table | as Enpara | out |
  | Akbank, DenizBank | product pages | only one "up to" rate (38,75 %, 43,5 %) | no reuse rule found | out (no table) |
  | Garanti BBVA, Yapı Kredi, Halkbank | rate pages | no: a script loads the rates | Halkbank: no rule; others not found | out (later: check for an allowed data URL) |

  robots.txt allows both pages for `*` (İş disallows `/fiyatoran/FiyatTabloGoster.asp*`
  and search paths; Ziraat disallows `/_layouts/` and some news paths).
- One source per bank (`isbank_web`, `ziraat_web`), one shared adapter
  `bank_table` (as `tefas_web` / `tefas_byf`), so one changed page fails only its
  own bank. One GET per source and ingest (2 requests per day), no redirects,
  the robots rules in code as for `ing_web`, honest `user_agent`. Payload = the
  page HTML (SHA-256 in the manifest); replay parses the payload.
- Config per table: `header` = the exact header row (the first cell, then the
  amount columns; this selects the table on the page and detects a change),
  `entity` template `"<bank> <product>, {row}, {column}"`, `decimal` ("," for
  İş, "." for Ziraat: `%28.00`), `min_rows`, and `skip_rows` (row labels that
  are not terms, e.g. Ziraat `Vadesiz`, `Birikimli Mevduat Hesabı`). Tables:
  - İş: header `VADE | 5.000 - 100.000 TL | … | 10.000.001 TL Üzeri`;
    entity `İş Bankası kampanyalı vadeli TL, {row}, {column}`; note "campaign
    rates (İşCep, İnternet Şube, Bankamatik); conditions apply".
  - Ziraat branch: header `Vade Grupları | 0,00 - 999,99 TL | 1.000 TL ve Üzeri`;
    entity `Ziraat Bankası vadeli TL (şube), {row}, {column}`.
  - Ziraat internet branch: header `Vade Grupları | 1.000,00 - 4.999,99 TL |
    5.000 - 99.999,99 TL | 100.000 - 499.999,99 TL | 500.000,00 TL ve üzeri`;
    entity `Ziraat Bankası vadeli TL (internet), {row}, {column}`.
  Row and column labels are kept as on the page (whitespace normalised).
- Values: quantity `deposit_rate`, unit pct. A cell is a percent after all
  whitespace is removed (`% 3 7,95` on the İş page = 37,95), with the decimal
  of the config; `%31` = 31. A cell that is not a percent fails the source.
- `as_of`: neither page shows a date for the deposit tables, so `as_of` = the
  Turkish date of the fetch, and the note says "the page shows no date; as_of
  = the fetch date". (If a date is added to the page later, a config field can
  read it.)
- Fails the source (`on_failure: previous`): HTTP status not 200, no table
  with the configured header, two such tables, fewer than `min_rows` rows, a
  row with another number of cells, a bad cell.
- Tests (offline): the saved pages of 2026-10-16 (gzip, in
  `C:/Users/yardang/dev/ing-wt/ingest-fixtures/`) as fixtures; the count, names
  and values of each table (İş 9 × 6 = 54; Ziraat branch and internet with
  their skipped rows); the whitespace and decimal cases; each failure case;
  replay identical; the pipeline tests keep their source list (as `ing_web`).

## Noted for later (decided 2026-10-09, not to be done now)

- **To do, I9 (the user, 2026-10-14): zeros from TEFAS.** TEFAS sometimes
  publishes 0 for a fund's price, size and returns (43–62 funds per snapshot;
  e.g. IRF on 2026-10-14: price 0, size 0, all returns 0 %, investors 1,405;
  on 2026-10-10 price 7.70, size 354 million TL). Today 0 is a valid value, so
  the engine scores 2–13 such funds per client as real data (all at place 115
  or lower, never in a top 3). Proposal: a price or size of 0 marks all TEFAS
  rows of that fund and day as invalid (`out_of_range`), so the fund has no
  usable return and gets the short-history rule; the "Olası sorunlar" panel
  gets a note. Needs a free eval pass and a small update of the deliverables.
- **Known validator false alarm (2026-10-14):** the short fund name "Garanti
  Portföy Blockchain" contains "garanti"; N5 removes only full fund names
  before the forbidden-phrase scan. One first attempt failed in the eval
  `20261014-105720-full`; the retry passed.
- **Scheduled ingest** — done on 2026-10-14 (I6, W14), see above.

- **Scheduled ingest**: Windows Task Scheduler job running `python -m rmprep
  ingest` each morning. Only calls the official EVDS API and reads the inbox
  folders; it does not touch TEFAS or ing.com.tr.
- **Ingest trigger**: alternative to a schedule — run ingest on demand when
  meeting prep starts, only if the latest snapshot is older than N hours
  (EVDS guide: fetch at most once a day).
- **TEFAS automation**: TEFAS has no official public API. The user lifts the
  no-scraping rule **only if the organizers allow it**; until then it stays.
  Update 2026-10-09: organizers allow collecting public data if each source's
  terms are respected (rule 8). TEFAS has no terms page, but robots.txt
  disallows `/api/` for all agents → **never call `/api/`** (this also rules
  out headless-browser scraping of pages that load data from `/api/`).
  The allowed HTML page `/tr/fon-getirileri` (~0.9 MB, 1 GET) embeds, per fund
  (~2,137): fonKodu, fonUnvan, fonTurAciklama, getiri1a/3a/6a/1y/yb/3y/5y (%),
  riskDegeri (1–7). No prices, no explicit as-of date. Prices stay on the
  manual Excel export. **Built 2026-10-09 as source `tefas_web`** (see
  Sources, item 2b).
- **Fund prices** (checked 2026-10-09): `/tr/fon-verileri` HTML has no price
  rows; the table loads from `/api/` (disallowed) → no automatic prices from
  TEFAS. kap.org.tr answers automated requests with HTTP 666 (bot block) →
  not usable automatically; this also means step 10 (KAP documents) needs
  documents downloaded by hand. Prices stay on the manual export (weekly,
  date range) unless the organizers provide a feed.
  Production answer: an internal ING fund price feed or a licensed data
  vendor. EVDS has only aggregate fund statistics, not prices per fund.
  If a scraper adapter is built, rules:
  - store the raw response bytes in the snapshot like every other adapter;
  - strict validation in `fetch` (expected columns, row count, date) → on any
    mismatch the source fails and `on_failure` applies; never partial data;
  - rows flagged `needs_check` until the scraper has a stable record;
  - a repair agent (user idea) may only **propose a code change** to the
    adapter for human review and run it against stored snapshots; it must
    never change data, flags or the parser at run time (keeps replay and
    audit intact).
