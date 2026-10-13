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
     scraper has a stable record.
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

## Noted for later (decided 2026-10-09, not to be done now)

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
