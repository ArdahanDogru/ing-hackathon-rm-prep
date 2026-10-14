# RM meeting-prep tool (ING hackathon prototype)

Python 3.11 (`requires-python = ">=3.11"`; do not use 3.12-only features — the
dev machine runs 3.12). Package `rmprep`, src layout, all code under `prototype/`.
The persona JSONs in the folder above (`../p0*.json`, `../persona_schema.json`)
are input and are not changed here.

Modules and their design docs: ingest = `docs/ingest.md`, decision =
`docs/decision.md`, ui (Streamlit, the fallback) = `docs/ui.md`, narrator =
`docs/narrator.md`, eval = `docs/eval.md`, web UI (the new front end, in
design) = `docs/web-ui.md`, research (web research with Exa) = `docs/research.md`. Read the doc of the module you work on; you do not
need the others.

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
  .env                      EVDS_API_KEY=..., ANTHROPIC_API_KEY=..., EXA_API_KEY=...   (gitignored, never logged)
  config/sources.yaml       sources, series, quantities, bounds
  config/decision.yaml      decision tables, weights, penalties, texts (docs/decision.md)
  config/narrator.yaml      narrator model, cost limit, forbidden phrases (docs/narrator.md)
  config/eval.yaml          eval snapshot, judge, budget, targets (docs/eval.md)
  config/glossary.yaml      plain explanations of technical terms, TR/EN (docs/ui.md U11)
  config/research.yaml      web research providers, queries, limit (docs/research.md)
  config/manual_template.csv  example for data/inbox/manual/
  config/withholding_tax_template.csv  empty stopaj rows (brief rule 7: never
                            hard-code tax rates); fill from Resmî Gazete/GİB,
                            then copy to data/inbox/manual/. Unfilled rows are
                            all rejected (test_manual).
  src/rmprep/
    contracts.py            DataPoint, Flag, make_id, EvidenceSet (lead-owned)
    cli.py                  `python -m rmprep ...` (lead-owned)
    grouping.py             short-list grouping rule, top_heads (lead-owned)
    backend.py              RealBackend (lead-owned)
    api/                    FastAPI JSON API for the web app (lead-owned, docs/web-ui.md)
    research/               web research: Exa and Claude web search, checks, service (ing-lead-2)
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
  web/                      React + TypeScript web app (worker ing-web; npm in web/)
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
Optional extras `kap = ["docling"]`, `ui = ["streamlit"]`, `narrator = ["anthropic>=1.0"]`,
`web = ["fastapi", "uvicorn"]`.

## Multi-agent workflow

This repo is built by a lead session (`ing-lead`, branch `main`) and one worker
session per module, each in its own git worktree
(`C:/Users/yardang/dev/ing-wt/<module>`, branch `<module>`). Protocol, owners
and message formats: `docs/workflow.md`.

- A worker edits only `src/rmprep/<module>/` and `tests/<module>/` (ing-web:
  only `web/`). Everything
  else (`contracts.py`, `pyproject.toml`, `config/`, `docs/`, this file, main)
  belongs to ing-lead; a hook enforces it. Ask ing-lead for changes.
- The decision/UI contracts in `contracts.py` are frozen (v1, 2026-10-10;
  v1.1 adds option kind `time_deposit`; v1.2 adds the narrator types and
  `Backend.draft_narrative` / `approve_narrative`; v1.3 adds warning audience,
  talking points, `to_confirm`, `NARRATIVE_SECTIONS_V13`, sentence title and
  need tags, docs/web-ui.md section 3; v1.4 adds `NarrativeBrief` and
  `Backend.brief`; v1.5 adds the per-block edits of the meeting text; v1.6 adds
  `ProductOption.asset_class` and `DecisionResult.recommended`; v1.7 adds the
  approval times `DecisionResult.rm_decided_at` and `NarrativeDraft.approved_at`;
  v1.8 adds `AllocationBand` and `DecisionResult.allocation`; v1.9 adds the
  option kinds `etf` and `stock`, `rm_edits[block] == ""` = a deleted
  block, and the section key `piyasa_notu`, `NARRATIVE_SECTIONS_V19`; v1.10
  adds the current split in `AllocationBand`, `HoldingsInput`,
  `DecisionResult.holdings_input` / `effective_weights` and
  `Backend.set_holdings`); their design is
  `docs/decision.md`, `docs/ui.md` and `docs/narrator.md`.
- GitHub: private repo `ArdahanDogru/ing-hackathon-rm-prep`; only the lead
  pushes `main`, and only when the user asks (`docs/workflow.md`).

## Commands

```
cd prototype
python -m venv .venv; .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q
python -m rmprep ingest
```
