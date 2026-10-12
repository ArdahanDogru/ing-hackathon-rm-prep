# Section-by-section editing Implementation Plan

> **For agentic workers:** runs in the multi-agent workflow (`docs/workflow.md`):
> ing-lead does L15 on `main`, then `ing-narrator` (N11) and `ing-web` (W11) work
> in parallel. Steps use checkbox (`- [ ]`) syntax. Read `docs/web-ui.md`,
> section "Section-by-section editing of the meeting text" (the spec), first.

**Goal:** The RM edits the meeting text one block at a time; each saved block is
checked; rule findings block the approval, number findings only warn.

**Architecture:** Contract v1.5 adds `rm_edits` and `edit_checks` to
`NarrativeDraft` and `Backend.edit_narrative`. The narrator owns the block ids,
the block check and the Markdown with edits; the backend stores the edits per
run and language and refuses an approval with an open blocking finding; the API
gives one endpoint per block; the web replaces the whole-text editor.

**Tech Stack:** Python 3.11+, FastAPI, pytest; React 18 + TypeScript, Vitest.

**Spec:** `docs/web-ui.md` — "Section-by-section editing of the meeting text".

## Global Constraints

- Blocks: `ozet`, `teklif_metni`, `dikkat`, `alternatifler`, `sorular`, `varsayimlar`; `talking_points:<i>`; `oneriler:<option_id>`.
- `BLOCKING_CHECK_KINDS = ("phrase", "option", "internal", "label")`; kind `number` only warns. A finding is the string `"<kind>: <message>"`.
- Contract v1.5 is additive (defaults: empty mappings); v1.4 JSON still loads.
- Edits persist in `data/narratives/<run_id>-<lang>-edits.json` and survive a restart.
- No test touches the network; every task ends with green pytest (web: also npm test and build).

## Review Focus

1. **An edit of an approved text**: editing after "Metni onayla" is refused (422), the approved text stays. Test: L15 `test_no_edit_after_approval`.
2. **An unknown block id** (a stale page after the text was made again): 422 with the list of valid ids, nothing stored. Test: L15 `test_unknown_block_422`.
3. **An empty edit**: text "" or only spaces means "restore the original" is NOT assumed; it is refused (422, "boş metin"); restore is `{text: null}`. Test: L15 `test_empty_edit_422`.
4. **A blocking finding fixed by a second edit**: the finding goes away and approval works again. Test: L15 `test_fixing_the_block_clears_the_blocker`.
5. **Turkish case in forbidden phrases** ("GARANTİ", "Kesin Getiri") in an edit: found as in the LLM text. Test: N11 `test_check_block_turkish_case`.

---

### Task L15 (lead): contract v1.5, backends, API

**Files:** `src/rmprep/contracts.py`, `src/rmprep/backend.py`, `src/rmprep/ui/fake.py`, `src/rmprep/api/app.py`; tests `tests/contracts/test_contracts_v1_5.py`, `tests/cli/test_backend.py`, `tests/api/test_blocks.py`, `tests/ui/test_fake.py` (method count 12).

**Interfaces (produces):**

```python
BLOCKING_CHECK_KINDS = ("phrase", "option", "internal", "label")

# NarrativeDraft, new fields:
    rm_edits: Mapping[str, str] = field(default_factory=dict)              # block id -> edited text
    edit_checks: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # block id -> findings

    def blocking_findings(self) -> dict[str, tuple[str, ...]]: ...          # only BLOCKING_CHECK_KINDS

# Backend:
def edit_narrative(self, run_id: str, lang: str, block_id: str,
                   text: str | None) -> NarrativeDraft: ...
```

- RealBackend: needs the narrator functions of N11 (`block_ids(draft)`, `check_block(draft, result, evidence, block_id, text) -> tuple[str, ...]`); until N11 is merged it uses a stand-in in `backend.py` (block ids from the sections; no findings) behind `getattr(narrator_module, ...)`.
- `approve_narrative` raises `ValueError("blocking findings: …")` while `blocking_findings()` is not empty.
- API: `PUT /api/runs/{id}/narrative/{lang}/blocks/{block_id}` body `{"text": str | null}` → the narrative view (as GET narrative: `markdown` with the edits, `draft_markdown` without).

- [ ] **Step 1: failing tests**

```python
# tests/api/test_blocks.py (FakeBackend)
def _text(client, persona):
    view = client.post("/api/runs", json={"persona": persona}).json()
    rid = view["result"]["run_id"]
    client.post(f"/api/runs/{rid}/approval", json={"status": "approved", "selected": [view["result"]["options"][1]["option"]["option_id"]]})
    return rid, client.get(f"/api/runs/{rid}/narrative").json()


def test_edit_and_restore_a_block(client, persona):
    rid, d = _text(client, persona)
    r = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Yeni amaç cümlesi."}).json()
    assert r["rm_edits"] == {"ozet": "Yeni amaç cümlesi."} and "Yeni amaç cümlesi." in r["markdown"]
    back = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": None}).json()
    assert back["rm_edits"] == {} and back["markdown"] == d["markdown"]


def test_unknown_block_422(client, persona):
    rid, _ = _text(client, persona)
    r = client.put(f"/api/runs/{rid}/narrative/TR/blocks/nope", json={"text": "x"})
    assert r.status_code == 422 and "ozet" in r.json()["detail"]


def test_empty_edit_422(client, persona):
    rid, _ = _text(client, persona)
    assert client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "  "}).status_code == 422


def test_blocking_finding_stops_approval_and_fixing_clears_it(client, persona):
    rid, d = _text(client, persona)
    r = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Bu fon kesin getiri sağlar."}).json()
    assert any(f.startswith("phrase:") for f in r["edit_checks"]["ozet"])
    assert client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": r["markdown"]}).status_code == 422
    ok = client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "Bu fon düşük risklidir."}).json()
    assert "ozet" not in ok["edit_checks"]
    assert client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": ok["markdown"]}).status_code == 200


def test_no_edit_after_approval(client, persona):
    rid, d = _text(client, persona)
    client.post(f"/api/runs/{rid}/narrative/TR/approval", json={"text": d["markdown"]})
    assert client.put(f"/api/runs/{rid}/narrative/TR/blocks/ozet", json={"text": "x"}).status_code == 422
```

(The FakeBackend uses a small built-in phrase check for "kesin getiri" until N11; RealBackend tests use a fake narrator.)

```python
# tests/cli/test_backend.py
def test_edits_survive_a_restart(backend, tmp_path):
    backend._narrator_obj = FakeNarrator()
    r = _approved(backend)
    backend.draft_narrative(r.run_id, "TR")
    backend.edit_narrative(r.run_id, "TR", "ozet", "Yeni metin.")
    again = be.RealBackend(tmp_path, personas_dir=FIX / "personas", now=lambda: T0)
    again._narrator_obj = FakeNarrator()
    again.decide(r.persona, r.snapshot_id)
    assert again.draft_narrative(r.run_id, "TR").rm_edits == {"ozet": "Yeni metin."}
```

- [ ] **Step 2: FAIL. Step 3: implement. Step 4: full suite green (exit code 0), samples again (`narrative_p01_tr` with `rm_edits: {}`), commit; tell the user "contract v1.5".**

### Task N11 (`ing-narrator`): blocks, block check, Markdown with edits

**Files:** Create `src/rmprep/narrator/blocks.py`; Modify `validator.py`, `template.py` (`to_markdown` applies `rm_edits`); tests `tests/narrator/test_blocks.py`.

**Interfaces (produces):** `block_ids(d: NarrativeDraft) -> tuple[str, ...]`; `block_text(d, block_id) -> str` (the original plain text); `check_block(d, r: DecisionResult, ev: EvidenceSet, block_id: str, text: str) -> tuple[str, ...]` (findings `"<kind>: <message>"` with kinds phrase, option, internal, label, number); `to_markdown(d)` renders an edited block from `d.rm_edits` in place of its sentences.

- [ ] **Step 1: failing tests**

```python
def test_block_ids_cover_every_sentence(draft_p01):
    ids = block_ids(draft_p01)
    assert "ozet" in ids and any(i.startswith("oneriler:") for i in ids) and any(i.startswith("talking_points:") for i in ids)

def test_check_block_kinds(draft_p01, approved_p01, evidence):
    f = check_block(draft_p01, approved_p01, evidence, "ozet", "Kesin getiri; ayrıca %99,9 faiz.")
    kinds = {x.split(":")[0] for x in f}
    assert {"phrase", "number"} <= kinds

def test_check_block_turkish_case(draft_p01, approved_p01, evidence):
    assert any(x.startswith("phrase:") for x in check_block(draft_p01, approved_p01, evidence, "ozet", "GARANTİ ediyoruz."))

def test_check_block_rejected_fund_by_short_name(draft_p01, approved_p01, evidence, rejected_short_name):
    assert any(x.startswith("option:") for x in check_block(draft_p01, approved_p01, evidence, "dikkat", f"{rejected_short_name} de düşünülebilir."))

def test_clean_edit_has_no_findings(draft_p01, approved_p01, evidence):
    assert check_block(draft_p01, approved_p01, evidence, "ozet", "Görüşmede düşük riskli seçenekleri konuşun.") == ()

def test_markdown_uses_the_edit(draft_p01):
    d = dataclasses.replace(draft_p01, rm_edits={"ozet": "YENİ ÖZET."})
    md = to_markdown(d)
    assert "YENİ ÖZET." in md and block_text(draft_p01, "ozet") not in md
```

- [ ] **Step 2: FAIL. Step 3: implement. Step 4: full suite green, commit, report "milestone N11 done, tests green, narrator@<sha>".**

### Task W11 (`ing-web`): block editing in the meeting text

**Files:** `web/src/screens/MeetingText.tsx`, `web/src/components/{BlockEditor,FindingList}.tsx`, `web/src/api/client.ts` (`api.editBlock(runId, lang, blockId, text | null)`), `web/src/api/types.ts` (`rm_edits`, `edit_checks`); tests.

- [ ] **Step 1: failing tests**

```tsx
test("pencil edits one block; others keep their layout", async () => {
  mockNarrative(sample("narrative_p01_tr"));
  const edit = vi.spyOn(api, "editBlock").mockResolvedValue(withEdit(sample("narrative_p01_tr"), "ozet", "Yeni amaç."));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: /Görüşmenin amacı.*düzenle/i }));
  await userEvent.clear(screen.getByRole("textbox", { name: /Görüşmenin amacı/ }));
  await userEvent.type(screen.getByRole("textbox", { name: /Görüşmenin amacı/ }), "Yeni amaç.");
  await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", "Yeni amaç.");
  expect(await screen.findByText("düzenlendi")).toBeInTheDocument();
  expect(screen.getAllByTestId("rec-card").length).toBeGreaterThan(0);
});

test("a blocking finding disables Metni onayla with the reason", async () => {
  mockNarrative(withChecks(sample("narrative_p01_tr"), "ozet", ["phrase: 'kesin getiri' kullanılmamalı"]));
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByRole("button", { name: "Metni onayla" })).toBeDisabled();
  expect(screen.getByText(/kesin getiri/)).toBeInTheDocument();
});

test("a number finding only warns", async () => {
  mockNarrative(withChecks(sample("narrative_p01_tr"), "ozet", ["number: 99,9 olgularda yok"]));
  renderMeeting(sample("run_p01_approved"));
  expect(await screen.findByRole("button", { name: "Metni onayla" })).toBeEnabled();
  expect(screen.getByText(/99,9/)).toBeInTheDocument();
});

test("Orijinale dön sends null", async () => {
  const edit = vi.spyOn(api, "editBlock").mockResolvedValue(sample("narrative_p01_tr"));
  mockNarrative(withEdit(sample("narrative_p01_tr"), "ozet", "Yeni amaç."));
  renderMeeting(sample("run_p01_approved"));
  await userEvent.click(await screen.findByRole("button", { name: "Orijinale dön" }));
  expect(edit).toHaveBeenCalledWith(expect.any(String), "TR", "ozet", null);
});
```

(`withEdit` / `withChecks`: test helpers that copy the sample and set `rm_edits` / `edit_checks`.)

- [ ] **Step 2: FAIL. Step 3: implement (the whole-text "Düzenle" goes away; the approved view shows the composed text). Step 4: npm test, build, pytest green; commit; report "milestone W11 done, tests green, web@<sha>".**
