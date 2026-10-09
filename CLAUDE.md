# RM meeting-prep tool (ING hackathon prototype)

Python 3.11 (`requires-python = ">=3.11"`; do not use 3.12-only features — the
dev machine runs 3.12). Package `rmprep`, src layout, all code under `prototype/`.
The persona JSONs in the folder above (`../p0*.json`, `../persona_schema.json`)
are input and are not changed here.

Modules and their design docs: ingest = `docs/ingest.md`, decision =
`docs/decision.md`, ui = `docs/ui.md` (later narrator, eval). Read the doc of
the module you work on; you do not need the others.

## Working agreement

- Implement in the steps or milestones of the module's design doc. Stop after
  each one for review unless the user or the lead says otherwise.
- Every step ends with green `pytest`. No test may touch the network.
- Record any change to a decision in the module's design doc in the same step.

## Time

- All timestamps are timezone-aware and in Turkey time, `Europe/Istanbul`
  (UTC+3, no DST), via `zoneinfo`. Windows has no system tz database, so
  `tzdata` is a dependency.
- `as_of` is a plain `date` (the Turkish business date of the observation):
  sources publish daily or lower-frequency values, and the date is part of the
  id hash, so a time-of-day would split one observation into several ids.

## Layout

```
prototype/
  pyproject.toml            deps + optional extras [kap], [ui]
  .env                      EVDS_API_KEY=...   (gitignored, never logged)
  config/sources.yaml       sources, series, quantities, bounds
  config/decision.yaml      decision tables, weights, penalties, texts (docs/decision.md)
  config/manual_template.csv  example for data/inbox/manual/
  config/withholding_tax_template.csv  empty stopaj rows (brief rule 7: never
                            hard-code tax rates); fill from Resmî Gazete/GİB,
                            then copy to data/inbox/manual/. Unfilled rows are
                            all rejected (test_manual).
  src/rmprep/
    contracts.py            DataPoint, Flag, make_id, EvidenceSet (lead-owned)
    cli.py                  `python -m rmprep ...` (lead-owned)
    ingest/                 ingestion layer (ingest worker)
      config.py             load + validate sources.yaml
      snapshot.py           raw snapshot write/verify/read
      parsing.py            Turkish number/date parsing, CSV decoding
      adapters/evds.py | tefas.py | tefas_web.py | manual.py | _inbox.py   (| kap.py later)
      quality.py            checks (pure functions)
      store.py              DuckDB evidence store + Parquet export
      pipeline.py           ingest / replay orchestration, fallback
  data/
    inbox/tefas/            manually exported TEFAS .xlsx/.csv
    inbox/manual/           manual CSVs (deposit rates, withholding tax)
    snapshots/<snapshot_id>/manifest.json, payloads/...
    evidence.duckdb
    export/<snapshot_id>.parquet
  tests/<module>/           one test package per module (tests/ingest/, tests/contracts/);
                            fixtures in tests/<module>/fixtures/; import shared test
                            helpers as `from tests.ingest.conftest import ...`
  docs/ingest.md | decision.md | ui.md   design of each module (owned by ing-lead)
  docs/workflow.md          multi-agent workflow (lead + workers)
  docs/architecture.md      annotated data-flow diagram of ingest (update it when the flow changes)
  docs/architecture.html|.pdf|.png  rendered copies; keep the Mermaid code in .md and
                            .html identical, then re-render (command in architecture.md)
```

Dependencies: `httpx`, `pyyaml`, `python-dotenv`, `openpyxl`, `duckdb`; dev:
`pytest`. Parquet is written by DuckDB (`COPY ... TO`), so no pyarrow/pandas.
Optional extras `kap = ["docling"]`, `ui = ["streamlit"]`.

## Multi-agent workflow

This repo is built by a lead session (`ing-lead`, branch `main`) and one worker
session per module, each in its own git worktree
(`C:/Users/yardang/dev/ing-wt/<module>`, branch `<module>`). Protocol, owners
and message formats: `docs/workflow.md`.

- A worker edits only `src/rmprep/<module>/` and `tests/<module>/`. Everything
  else (`contracts.py`, `pyproject.toml`, `config/`, `docs/`, this file, main)
  belongs to ing-lead; a hook enforces it. Ask ing-lead for changes.
- The decision/UI contracts in `contracts.py` are frozen (v1, 2026-10-10);
  their design is `docs/decision.md` and `docs/ui.md`.

## Commands

```
cd prototype
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
python -m rmprep ingest
```
