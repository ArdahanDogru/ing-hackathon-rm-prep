# UI

Status: **to be designed (step D, the user with ing-lead).** The worker starts
after decision is done or when the user asks.

Streamlit (`pip install -e ".[ui]"`) on a `FakeBackend` that implements the
`Backend` protocol in `src/rmprep/contracts.py` and serves
`tests/contracts/fixtures/` (personas, `evidence_small.json`, one
`needs_rm_input` and one `ready` DecisionResult). The lead later connects the
real backend on main.

## To decide

1. Screens: persona pick, snapshot pick and "cross out a source"
   (exclusion), ranked options with score parts and evidence, rejected options
   with reasons, warnings and data-quality notes.
2. The RM loop: answering clarification questions (`answer_question`) and
   approve / reject (`approve`), and what each does to the shown result.
3. Language (Turkish / English) and the evidence view (DataPoint id → source,
   URL, flags).
4. Worker milestones, each ending with green tests.
