# Current portfolio projection and allocation gap — Implementation Plan

> **For agentic workers:** runs in the multi-agent workflow (`docs/workflow.md`):
> ing-lead does Tasks 1, 2, 4 and 7 on `main`; `ing-decision` does Task 3 (D27);
> then `ing-web` (Task 5, W18) and `ing-narrator` (Task 6, N15) work in parallel.
> At most 3 sessions run at a time (the lead included). Steps use checkbox
> (`- [ ]`) syntax. Read the spec first.

**Goal:** The tool estimates the client's current split over the five asset
classes, the RM confirms or corrects it, and a new score criterion
"Portföy açığı" moves options of under-weight classes up.

**Architecture:** Contract v1.10 adds the current split to `AllocationBand`,
`HoldingsInput` and `effective_weights` to `DecisionResult`, and
`Backend.set_holdings`. A pure decision module (`decision/holdings.py`) builds
the estimate from config (persona text rules, job rows, national default) and
the RM input; the scoring gets the criterion `allocation_gap`, active only for
classes from the RM or the persona text. The backend keeps the RM input as a
run input (new run id); the API and the web show and edit it; the narrator
mentions only active gaps.

**Tech Stack:** Python 3.11+, FastAPI, pytest; React 18 + TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-14-portfolio-projection-design.md`

## Global Constraints

- Classes: `nakit_benzeri`, `borclanma`, `hisse`, `altin_doviz`, `dengeli` (= `allocation.classes`); `dengeli` has no band and no gap.
- Source ids: `rm`, `rm_confirmed`, `persona_text`, `profile`, `national`. Active (change the ranking): `rm`, `rm_confirmed`, `persona_text` only.
- RM input: every class 0–100, total 100 ± 0.5; origin `rm` or `rm_confirmed`.
- Gap: low − x below the band (positive), high − x above it (negative), 0 inside.
- Criterion value: clamp(gap / scale, −1, 1); negative × `overweight_factor`; 0 for inactive, `dengeli`, no band.
- No active class → weight 0 → `allocation_gap` not in `score_parts` → scores identical to the run without the feature.
- Hard rules run before scoring and do not change.
- Estimate texts say "tahmini senaryo, müşteri bilgisi değildir"; the to_confirm item is "Müşterinin mevcut portföy dağılımını alın (şu an tahmini senaryo)."
- Contract v1.10 is additive (defaults); v1.9 JSON still loads.
- No test touches the network; every task ends with green pytest (web: also `npx vitest run --maxWorkers=4` and `npm run build`). Commit only on pytest exit code 0.
- Workers' tests use their own config copy; the lead adds the config keys after each merge.

## Review Focus

1. A persona with two matching text rules for the same class (or rules whose points add to more than 100): the estimate must still add to 100 — the later rule for the same class is ignored and text points are capped at 100 (Task 3 test `test_text_rules_capped`).
2. RM input with a missing class, an unknown class, a negative value or a total of 99.4: refused with a clear message, never stored (Task 1 `test_holdings_input_rejects`, Task 4 API 422 test).
3. A run loaded from an old record (v1.9 JSON without the new fields): loads, `holdings_input` None, `effective_weights` {} (Task 1 `test_v19_json_loads`).
4. An RM "reset" after an input must give back exactly the run id of the run without input (Task 4 `test_reset_gives_the_original_run`).
5. Persona text in other case or with Turkish letters ("MEVDUAT AĞIRLIKLI") must match like the priorities do (Task 3 `test_text_rule_turkish_case`).

---

### Task 1: Contract v1.10 (lead, main)

**Files:**
- Modify: `src/rmprep/contracts.py` (header note; `AllocationBand` ~line 427; new `HoldingsInput` after it; `DecisionResult` ~line 456; `Backend` protocol ~line 705)
- Modify: `src/rmprep/ui/fake.py` (`FakeBackend.set_holdings`)
- Modify: `CLAUDE.md` (v1.10 note)
- Test: `tests/contracts/test_contracts_v1_10.py`

**Interfaces:**
- Produces: `HOLDINGS_SOURCES`, `ACTIVE_HOLDINGS_SOURCES`, `HOLDINGS_ORIGINS`, `HoldingsInput(shares: Mapping[str, float], origin: str)`, `AllocationBand.current/current_low/current_high/current_source/current_ref/gap/active`, `DecisionResult.holdings_input: HoldingsInput | None`, `DecisionResult.effective_weights: Mapping[str, float]`, `Backend.set_holdings(run_id, shares, origin="rm") -> DecisionResult`.

- [ ] **Step 1: Write the failing tests**

```python
"""Contract v1.10 (2026-10-14): current split, RM holdings input, effective weights
(spec docs/superpowers/specs/2026-10-14-portfolio-projection-design.md, section 7)."""

import json
from pathlib import Path

import pytest

from rmprep.contracts import (ACTIVE_HOLDINGS_SOURCES, HOLDINGS_SOURCES, AllocationBand,
                              DecisionResult, HoldingsInput)

CLASSES = ("nakit_benzeri", "borclanma", "hisse", "altin_doviz", "dengeli")
FIXTURES = Path(__file__).parent / "fixtures"     # as FIX in tests/api/conftest.py


def _shares(**over):
    d = {"nakit_benzeri": 40.0, "borclanma": 20.0, "hisse": 20.0, "altin_doviz": 10.0, "dengeli": 10.0}
    return d | over


def test_sources():
    assert HOLDINGS_SOURCES == ("rm", "rm_confirmed", "persona_text", "profile", "national")
    assert ACTIVE_HOLDINGS_SOURCES == ("rm", "rm_confirmed", "persona_text")


def test_holdings_input_ok():
    h = HoldingsInput(_shares(), "rm")
    assert h.origin == "rm" and sum(h.shares.values()) == 100.0
    assert HoldingsInput(_shares(dengeli=10.4), "rm_confirmed")       # within ± 0.5


@pytest.mark.parametrize("shares, origin, msg", [
    (_shares(dengeli=11.0), "rm", "total"),
    ({k: v for k, v in _shares().items() if k != "dengeli"} | {"hisse": 30.0}, "rm", "classes"),
    (_shares() | {"gayrimenkul": 0.0}, "rm", "classes"),
    (_shares(hisse=-1.0, nakit_benzeri=61.0), "rm", "0-100"),
    (_shares(), "profile", "origin"),
])
def test_holdings_input_rejects(shares, origin, msg):
    with pytest.raises(ValueError, match=msg):
        HoldingsInput(shares, origin)


def test_band_current_fields():
    b = AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=10.0, current_low=5.0,
                       current_high=15.0, current_source="profile", current_ref="Teknoloji kurucusu",
                       gap=60.0, active=False)
    assert b.gap == 60.0 and not b.active
    old = AllocationBand("hisse", 70, 85, "Ata", False, None, "")      # v1.8 constructor
    assert old.current is None and old.current_source == "" and old.active is False


def test_band_rejects_bad_current():
    with pytest.raises(ValueError, match="current"):
        AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=20.0, current_low=25.0,
                       current_high=30.0, current_source="profile")
    with pytest.raises(ValueError, match="active"):
        AllocationBand("hisse", 70, 85, "Ata", False, None, "", current=20.0, current_low=20.0,
                       current_high=20.0, current_source="national", active=True)


def test_v19_json_loads():
    """A run record written before v1.10 (no new keys) still loads."""
    from rmprep.ui.fake import FakeBackend
    b = FakeBackend(FIXTURES)
    r = b.decide(b.list_personas()[0], b.list_snapshots()[0])
    d = r.to_dict()
    d.pop("holdings_input")
    d.pop("effective_weights")
    for band in d["allocation"]:
        for k in ("current", "current_low", "current_high", "current_source", "current_ref", "gap", "active"):
            band.pop(k)
    back = DecisionResult.from_dict(json.loads(json.dumps(d)))
    assert back.holdings_input is None and dict(back.effective_weights) == {}
```

- [ ] **Step 2: Run** `.venv/Scripts/python -m pytest tests/contracts/test_contracts_v1_10.py -q` — expected: FAIL (ImportError `HoldingsInput`).

- [ ] **Step 3: Implement** in `src/rmprep/contracts.py`:

```python
HOLDINGS_SOURCES = ("rm", "rm_confirmed", "persona_text", "profile", "national")   # v1.10
ACTIVE_HOLDINGS_SOURCES = ("rm", "rm_confirmed", "persona_text")                  # change the ranking
HOLDINGS_ORIGINS = ("rm", "rm_confirmed")
HOLDINGS_TOTAL_TOLERANCE = 0.5
```

`AllocationBand` new fields after `note` (all with defaults) and checks appended to `__post_init__`:

```python
    current: float | None = None        # v1.10: the client's current share, % (point)
    current_low: float | None = None
    current_high: float | None = None
    current_source: str = ""            # "" | HOLDINGS_SOURCES
    current_ref: str = ""               # rule id, profile label or source short text
    gap: float | None = None            # points to the band edge; + under, - over, 0 inside
    active: bool = False                # counts in the ranking (ACTIVE_HOLDINGS_SOURCES)

        # in __post_init__, after the band check:
        if self.current is not None:
            lo = self.current if self.current_low is None else self.current_low
            hi = self.current if self.current_high is None else self.current_high
            if not 0 <= lo <= self.current <= hi <= 100:
                raise ValueError(f"current must satisfy 0 <= low <= current <= high <= 100, "
                                 f"got {lo}-{self.current}-{hi}")
            if self.current_source not in HOLDINGS_SOURCES:
                raise ValueError(f"current_source must be one of {HOLDINGS_SOURCES}")
        if self.active and self.current_source not in ACTIVE_HOLDINGS_SOURCES:
            raise ValueError("active only with an active source (rm, rm_confirmed, persona_text)")
```

New dataclass after `AllocationBand`:

```python
@dataclass(frozen=True)
class HoldingsInput:
    """v1.10: the client's current split typed (rm) or accepted (rm_confirmed) by the RM."""

    shares: Mapping[str, float]     # asset class -> %, all ALLOCATION_CLASSES, total 100 ± 0.5
    origin: str                     # HOLDINGS_ORIGINS

    def __post_init__(self) -> None:
        if self.origin not in HOLDINGS_ORIGINS:
            raise ValueError(f"origin must be one of {HOLDINGS_ORIGINS}, got {self.origin!r}")
        if set(self.shares) != set(ALLOCATION_CLASSES):
            raise ValueError(f"shares must name exactly the classes {ALLOCATION_CLASSES}")
        if any(not 0 <= v <= 100 for v in self.shares.values()):
            raise ValueError("each share must be in 0-100")
        total = sum(self.shares.values())
        if abs(total - 100) > HOLDINGS_TOTAL_TOLERANCE:
            raise ValueError(f"shares must add to 100 (± {HOLDINGS_TOTAL_TOLERANCE}), got total {total}")
        object.__setattr__(self, "shares", {k: float(self.shares[k]) for k in ALLOCATION_CLASSES})
```

with `ALLOCATION_CLASSES = ("nakit_benzeri", "borclanma", "hisse", "altin_doviz", "dengeli")` defined next to the other constants (the D19/D20 classes; config `allocation.classes` must equal it — Task 4 adds that check to the API start-up test).

`DecisionResult` new fields after `allocation_notes`:

```python
    holdings_input: HoldingsInput | None = None         # v1.10: the RM's split (a run input)
    effective_weights: Mapping[str, float] = field(default_factory=dict)  # v1.10: criterion -> weight used
```

`Backend` protocol:

```python
    def set_holdings(self, run_id: str, shares: Mapping[str, float] | None,
                     origin: str = "rm") -> DecisionResult: ...   # v1.10; None removes the input
```

`FakeBackend.set_holdings` (src/rmprep/ui/fake.py): returns the stored run with `holdings_input` replaced (`dataclasses.replace(r, holdings_input=None if shares is None else HoldingsInput(shares, origin))`); no scoring change in the fake.

- [ ] **Step 4: Run** the new tests, then the full suite: `.venv/Scripts/python -m pytest -q -p no:cacheprovider` — expected exit code 0.
- [ ] **Step 5: Commit** `contract v1.10: current split in AllocationBand, HoldingsInput, effective_weights, Backend.set_holdings`; tell the user "contract changed (v1.10)".

### Task 2: Design docs (lead, main)

**Files:** `docs/decision.md` (new section 17 "Current split and allocation gap (D27)" = spec sections 3–6 and 11 with the config shape of Task 4), `docs/web-ui.md` (W18 = spec section 9 + the API of spec section 8), `docs/narrator.md` (N15 = spec section 10), `CLAUDE.md` (contract v1.10 line).

- [ ] **Step 1:** Copy the spec sections into the module docs (the workers read only their module doc), with the exact config keys of Task 4 Step 2.
- [ ] **Step 2:** Commit `docs: D27, W18, N15 design (portfolio projection)`.

### Task 3: D27 — estimate, gap and criterion (ing-decision, branch decision)

**Files:**
- Create: `src/rmprep/decision/holdings.py`
- Modify: `src/rmprep/decision/config.py` (optional sections `holdings`, `allocation_gap`, `weights.allocation_gap`, texts), `scoring.py` (criterion), `allocation.py` (current fields), `engine.py` (`decide(..., holdings=)`, `run_id`, `effective_weights`, to_confirm), `confidence.py` (D25 varies the new weight)
- Test: `tests/decision/test_holdings.py`, `tests/decision/test_allocation_gap.py`

**Interfaces:**
- Consumes: Task 1 contract names.
- Produces:

```python
@dataclass(frozen=True)
class ClassEstimate:
    asset_class: str
    point: float
    low: float
    high: float
    source: str          # HOLDINGS_SOURCES
    ref: str             # rule id / profile label / national source short text

def estimate(persona: Persona, config: DecisionConfig,
             holdings: HoldingsInput | None) -> tuple[ClassEstimate, ...]   # order = ALLOCATION_CLASSES
def class_gap(point: float, band: tuple[float, float] | None) -> float | None
def gap_value(gap: float | None, active: bool, config: DecisionConfig) -> float      # in [-1, 1]
def gap_weight_factor(persona: Persona, estimates: Sequence[ClassEstimate],
                      config: DecisionConfig) -> float                                 # 0 when nothing active
def holdings_status(estimates: Sequence[ClassEstimate]) -> str   # "rm" | "rm_confirmed" | "persona_text" | "estimate"

# engine
def decide(evidence, persona, config, answers={}, *, created_at,
           holdings: HoldingsInput | None = None) -> DecisionResult
def run_id(cfg_hash, persona, snapshot_id, excluded_sources, answers,
           holdings: HoldingsInput | None = None) -> str     # key unchanged when holdings is None
```

Config shape (the worker's test copy; the lead adds the same to `config/decision.yaml` in Task 4):

```yaml
holdings:
  national: {label: "Türkiye hanehalkı ortalaması", source: "TCMB Finansal İstikrar Raporu 2026-I, Tablo III.1.2 (Mart 2026)",
             url: "https://www.tcmb.gov.tr/...", shares: {nakit_benzeri: 39, borclanma: 10, hisse: 10, altin_doviz: 30, dengeli: 11}}
  profiles:
    - {match: ["emekli"], label: "Emekli", rule: "...", source: "varsayım",
       shares: {nakit_benzeri: 32, borclanma: 22, hisse: 10, altin_doviz: 26, dengeli: 10}}
    # ihracatçı/şirket sahibi 22/22/13/33/10; teknoloji kurucusu/kurucu 45/12/20/15/8;
    # aile ofisi 15/28/27/15/15; hekim/doktor 28/12/13/25/22
  text_rules:
    - {id: mevduat_agirlikli, fields: [durum], match: "mevduat ağırlıklı", class: nakit_benzeri, range: [60, 90]}
    - {id: sirket_satisi_nakit, fields: [durum], match: "şirket satışından gelen nakdi", class: nakit_benzeri, range: [50, 100]}
  spread: 5
allocation_gap:
  scale: 30
  overweight_factor: 0.5
  per_signal: 0.5
  max_signals: 2
  source_factor: {rm: 1.0, rm_confirmed: 0.75, persona_text: 0.75}
  signals: ["çeşitlendirme", "mevduat yoğunluğunu azalt", "tek ürün veya tek varlık sınıfında yoğunlaşmama", "fırsat maliyetini azaltma"]
weights:
  allocation_gap: {base: 1.0}
texts:
  reasons:
    allocation_gap: "{class_label} payı {source_label} %{current:.0f}; {profile} model bandı %{low:.0f}–{high:.0f}."
  holdings:
    source_labels: {rm: "RM'e göre", rm_confirmed: "RM onaylı tahmine göre", persona_text: "persona metnine göre"}
    to_confirm: "Müşterinin mevcut portföy dağılımını alın (şu an tahmini senaryo)."
```

- [ ] **Step 1: Write the failing tests** (`tests/decision/test_holdings.py`), at least:

```python
def test_national_default_when_nothing_matches(cfg, persona_p05_like):   # profil "Mimar"
    est = estimate(persona_p05_like, cfg, None)
    assert [e.source for e in est] == ["national"] * 5
    assert sum(e.point for e in est) == 100.0

def test_profile_row(cfg, p03):            # "Teknoloji kurucusu" -> 45/12/20/15/8 before text rules
    est = {e.asset_class: e for e in estimate(p03_without_durum(p03), cfg, None)}
    assert est["nakit_benzeri"].point == 45.0 and est["hisse"].source == "profile"

def test_text_rule_and_rest_in_base_proportions(cfg, p01):
    est = {e.asset_class: e for e in estimate(p01, cfg, None)}
    assert est["nakit_benzeri"].point == 75.0 and est["nakit_benzeri"].source == "persona_text"
    assert (est["nakit_benzeri"].low, est["nakit_benzeri"].high) == (60.0, 90.0)
    rest = {k: e.point for k, e in est.items() if k != "nakit_benzeri"}
    assert round(sum(rest.values()), 1) == 25.0          # emekli base 22/10/26/10 scaled to 25

def test_text_rule_turkish_case(cfg, p01):
    loud = p01_with(durum="VARLIĞI TL MEVDUAT AĞIRLIKLI")
    assert estimate(loud, cfg, None)[0].source == "persona_text"

def test_text_rules_capped(cfg, p01):       # two rules on one class: the first wins; points never > 100
    raw = copy.deepcopy(cfg.raw)
    raw["holdings"]["text_rules"] += [
        {"id": "again", "fields": ["durum"], "match": "mevduat", "class": "nakit_benzeri", "range": [95, 100]},
        {"id": "fx", "fields": ["durum"], "match": "tl", "class": "altin_doviz", "range": [60, 100]}]
    est = {e.asset_class: e for e in estimate(p01, parse_config(raw), None)}
    assert est["nakit_benzeri"].point == 75.0 and est["nakit_benzeri"].ref == "mevduat_agirlikli"
    assert est["altin_doviz"].point == 25.0                  # capped: 75 + 80 > 100 -> 100 - 75
    assert round(sum(e.point for e in est.values()), 1) == 100.0

def test_rm_input_replaces_all(cfg, p01):
    h = HoldingsInput({"nakit_benzeri": 20, "borclanma": 60, "hisse": 10, "altin_doviz": 10, "dengeli": 0}, "rm")
    est = estimate(p01, cfg, h)
    assert {e.source for e in est} == {"rm"} and est[1].point == 60.0 and est[1].low == est[1].high == 60.0
```

and in `tests/decision/test_allocation_gap.py`:

```python
@pytest.mark.parametrize("point, band, gap", [(10, (70, 85), 60), (90, (70, 85), -5), (75, (70, 85), 0),
                                              (70, (70, 85), 0), (85, (70, 85), 0), (50, None, None)])
def test_class_gap(point, band, gap):
    assert class_gap(point, band) == gap

def test_gap_value_scale_and_overweight(cfg):     # scale 30, overweight 0.5
    assert gap_value(60, True, cfg) == 1.0
    assert gap_value(15, True, cfg) == 0.5
    assert gap_value(-30, True, cfg) == -0.5
    assert gap_value(60, False, cfg) == 0.0

def test_no_active_class_no_criterion(cfg, evidence, p05):   # national/profile only
    r = decide(evidence, p05, cfg, created_at=T0)
    assert all("allocation_gap" not in o.score_parts for o in r.options)
    assert r == decide_without_feature(evidence, p05)           # same options, scores and order

def test_p01_cash_down_debt_up(cfg, evidence, p01): ...         # rank of the best borclanma option improves
def test_rm_input_hisse_gap_lifts_equity(cfg, evidence, p03): ... # RM hisse 10 % -> best hisse option moves up
def test_hard_rules_unchanged(cfg, evidence, p01): ...           # same rejected set with and without input
def test_signals_raise_the_weight(cfg, p04): ...                 # gap_weight_factor with 2 signals = 1.0 * 0.75 * 2.0 for persona_text
def test_run_id_unchanged_without_holdings(cfg, p01): ...        # run_id(..., None) == old formula
def test_effective_weights_sum_to_one_and_name_criteria(cfg, evidence, p01): ...
def test_to_confirm_first_item_while_estimate(cfg, evidence, p05): ...
def test_allocation_rows_carry_current_and_gap(cfg, evidence, p01): ...  # nakit active, others not
```

- [ ] **Step 2:** Run `pytest tests/decision -q` — expected: FAIL (ImportError).
- [ ] **Step 3: Implement**:
  - `holdings.py`: `normalize` from `decision/text.py` for matching; base = first matching profile row else national; text rules in config order, skip a rule whose class is already fixed, cap the sum of text points at 100; spread the rest over the other classes in base proportions; range = point ± `spread` clipped to 0–100; RM input → every class `low == high == point`, source = origin; round to one decimal, the rounding rest to the largest class.
  - `scoring.py`: `Features.values["allocation_gap"]` = `gap_value(gap of the option's asset_class, active, config)`; `raw_weights` gets `allocation_gap = weights.allocation_gap.base * gap_weight_factor(...)`; when the factor is 0 the criterion is left out of the weights (so `normalize_weights` and every score stay as before); reasons with `texts.reasons.allocation_gap`.
  - `allocation.py`: fill the v1.10 fields of each band from the estimates.
  - `engine.py`: `decide(..., holdings=None)`; `run_id` adds `holdings.shares` and `origin` to the key only when holdings is not None; `effective_weights` = the normalised weights used; to_confirm: `texts.holdings.to_confirm` first while `holdings_status == "estimate"` (it replaces the D20 `holding_confirm` when `holdings` is configured).
  - `confidence.py`: D25 varies `allocation_gap` like the other weights.
  - All new config sections optional: without `holdings`, D27 does nothing and every old test passes.
- [ ] **Step 4:** `pytest -q` full suite green; run P01–P05 read-only on snapshot `20261014-191003-eedf` with the test config and report the top 3 and the allocation rows.
- [ ] **Step 5:** Commit on branch `decision`; report to ing-lead with the sha, the test count, the config keys and the docs text.

### Task 4: Merge D27, config, backend and API (lead, main)

**Files:**
- Modify: `config/decision.yaml` (the sections of Task 3, values from the spec 4.2 and 5, URL of TCMB FİR 2026-I)
- Modify: `src/rmprep/backend.py` (`_Inputs.holdings`, `set_holdings`, pass `holdings=` to `decision.decide`)
- Modify: `src/rmprep/api/app.py` (`POST /api/runs/{run_id}/holdings`), `src/rmprep/api/views.py` (allocation rows, `holdings`, `effective_weights`)
- Modify: API fixtures via a one-off script (never run `python -m rmprep.api.samples`: it approves P01 again)
- Test: `tests/api/test_holdings.py`, `tests/test_backend_holdings.py`

**Interfaces:**
- Consumes: Task 1 and Task 3.
- Produces for the web: `RunView.allocation[i]` + `current, current_low, current_high, current_source, current_ref, gap, active`; `RunView.holdings = {status, sources: [{id, label, url, date}]}`; `RunView.effective_weights`; `POST /api/runs/{id}/holdings` body `{"shares": {...} | null, "origin": "rm" | "rm_confirmed"}` → RunView; 422 with `detail` on a bad input.

- [ ] **Step 1: Write the failing tests**:

```python
def test_set_holdings_makes_a_new_run(backend, p05):
    r0 = backend.decide(p05, SNAP)
    shares = {"nakit_benzeri": 80, "borclanma": 10, "hisse": 5, "altin_doviz": 5, "dengeli": 0}
    r1 = backend.set_holdings(r0.run_id, shares, "rm")
    assert r1.run_id != r0.run_id and r1.holdings_input.shares["nakit_benzeri"] == 80.0
    assert any("allocation_gap" in o.score_parts for o in r1.options)

def test_reset_gives_the_original_run(backend, p05):
    r0 = backend.decide(p05, SNAP)
    r1 = backend.set_holdings(r0.run_id, SHARES, "rm")
    assert backend.set_holdings(r1.run_id, None).run_id == r0.run_id

def test_api_holdings_422(client, run_id):
    r = client.post(f"/api/runs/{run_id}/holdings", json={"shares": {"hisse": 50}, "origin": "rm"})
    assert r.status_code == 422 and "classes" in r.json()["detail"]

def test_api_holdings_view(client, run_id):
    r = client.post(f"/api/runs/{run_id}/holdings", json={"shares": SHARES, "origin": "rm_confirmed"})
    v = r.json()
    assert v["holdings"]["status"] == "rm_confirmed"
    assert {row["current_source"] for row in v["allocation"]} == {"rm_confirmed"}
    assert abs(sum(v["effective_weights"].values()) - 1) < 1e-9
```

- [ ] **Step 2:** Run — FAIL. **Step 3:** merge D27 (`git merge --no-ff <sha>`), add the config, implement backend and API. `set_holdings`: `_, inputs = self._runs[run_id]`; `holdings = None if shares is None else HoldingsInput(shares, origin)`; `return self._run(dataclasses.replace(inputs, holdings=holdings))`. The API maps `ValueError` to 422.
- [ ] **Step 4:** Patch the 5 run fixtures with a script that adds the new keys from the real views of the same runs (or empty defaults where the fixture run has no config), check with the contract tests; full pytest green.
- [ ] **Step 5:** Commit; tell the user "merged D27; contract v1.10 in use".

### Task 5: W18 — "Mevcut ve hedef dağılım" (ing-web, branch web)

**Files:** `web/src/api/types.ts`, `web/src/api/client.ts` (`setHoldings(runId, shares|null, origin)`), `web/src/components/AllocationCard.tsx` (rename/extend the D20 card), `web/src/i18n.ts`, tests `web/src/components/AllocationCard.test.tsx`.

**Interfaces:** Consumes the Task 4 API exactly as listed there.

- [ ] **Step 1: Write the failing tests** (Vitest + Testing Library), at least:
  - the banner "Portföy dağılımı bilinmiyor; aşağıdaki değerler tahmini senaryodur ve sıralamayı etkilemez." shows when `holdings.status == "estimate"`;
  - each row shows the band, the marker value, the badge ("tahmini senaryo" / "persona metni" / "RM" / "RM onaylı") and the gap text ("−25 puan" / "bandın içinde");
  - "Tahmini onayla" calls `setHoldings(runId, <current points>, "rm_confirmed")`;
  - "Düzenle": five number inputs, the running total, "Kaydet" disabled at 99 and enabled at 100;
  - "Sıfırla" calls `setHoldings(runId, null)`;
  - a 422 shows the server `detail` under the inputs.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `npx vitest run --maxWorkers=4` and `npm run build` green. **Step 5:** commit on `web`; report the sha and a screenshot path.

### Task 6: N15 — narrator mentions only active gaps (ing-narrator, branch narrator)

**Files:** `src/rmprep/narrator/facts.py` (allocation rows in the facts pack), `src/rmprep/narrator/validator.py` (a gap figure of an inactive row fails), prompt text (bump `prompt_version`), tests `tests/narrator/test_n15.py`.

- [ ] **Step 1: Write the failing tests**:
  - the facts pack has `allocation: [{class, band_low, band_high, current, source, gap, active}]`;
  - a draft sentence with the gap number of an inactive row → validator finding `number`;
  - a sentence "Mevcut portföy dağılımı bilinmiyor; müşteriden alınmalı." is valid while the status is an estimate;
  - the template draft mentions an active gap with the config sentence.
- [ ] **Step 2–4:** FAIL, implement, full pytest green. **Step 5:** commit on `narrator`; report the sha and the config keys (`prompt_version`, template sentence).

### Task 7: Eval and deliverables (lead, main)

- [ ] **Step 1:** Add eval checks in `src/rmprep/eval/` (via ing-eval or the lead): estimate total = 100 for P01–P05; P02/P04/P05 rankings equal to the run without the feature (no RM input); P01 best borçlanma rank improves; a P03 copy with RM input hisse 10 % lifts the best hisse option; top-3 stability ≥ the D25 target.
- [ ] **Step 2:** A new frozen snapshot (`config/eval.yaml`), no config change while the eval runs; run the full eval (about $1.20).
- [ ] **Step 3:** Update the deliverables 1/3/4/5, the README (TR) and the deck (screenshots of the W18 card), rebuild the PDFs.
- [ ] **Step 4:** Commit; push only when the user asks (check: no `.env`, no secrets, no `data/` files tracked).
