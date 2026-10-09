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
10. *(Later)* KAP adapter.

I1 (added 2026-10-10 for the decision layer, `docs/decision.md`): fund name
and umbrella type. The `tefas_web` parser also reads `fonUnvan` and
`fonTurAciklama` for each fund from the page it already downloads (no new
request) and returns them as `EntityInfo(name, category, source="tefas_web")`,
text verbatim. `build_evidence` fills `EvidenceSet.entities` (fund code →
`EntityInfo`) from the snapshot payload, also on replay and fallback; an
excluded or skipped `tefas_web` gives an empty mapping. No new DataPoints, no
DuckDB table (`build_evidence` already re-parses the payloads). Tests: parse
from a fixture page; replay gives identical `entities`; exclusion empties them.

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
