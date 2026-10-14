"""Facts for the deliverables (docs/teslim) from one snapshot: eliminations, the
recommended top 3, the P02 worked example, class risk estimates, confidence,
stability, allocation rows, warnings. Read only; deterministic (the same values
as the eval's decisions). Run in prototype/:

    python scripts/analysis/deliverable_facts.py <snapshot_id> > facts.md
"""
from __future__ import annotations

import collections
import statistics
import sys

from rmprep.backend import RealBackend
from rmprep.decision import load_config
from rmprep.decision.persona import read_persona
from rmprep.decision.scoring import class_risk_estimates, normalize_weights, option_features, raw_weights
from rmprep.decision.universe import build_universe

SNAP = sys.argv[1]
b = RealBackend(".")
cfg = load_config("config/decision.yaml")
ev = b.evidence(SNAP)
uni = build_universe(ev, cfg)


def pct(x):
    return "—" if x is None else f"{x * 100:+.1f}"


print(f"# Facts for snapshot `{SNAP}` (config `{b.decide(b.list_personas()[0], SNAP).config_hash}`)\n")
print("## Data quality notes (P01)\n")
r01 = b.decide(next(p for p in b.list_personas() if p.persona_id == "P01"), SNAP)
for n in r01.data_quality:
    print("-", n.message)
print("\n## Class risk estimates (D21)\n")
print(class_risk_estimates(uni, cfg))

for p in b.list_personas():
    r = b.decide(p, SNAP)
    lv = read_persona(p, cfg).levels
    feats, _ = option_features(uni, lv, cfg)
    F = {f.option.option_id: f for f in feats}
    print(f"\n## {p.persona_id} {p.profil} · {p.risk_profili} · state {r.state.value} · run {r.run_id}\n")
    rules = collections.Counter(c.rule_id for x in r.rejected for c in x.failed)
    multi = sum(1 for x in r.rejected if len(x.failed) > 1)
    print(f"- scored {len(r.options)}, rejected {len(r.rejected)}, by rule {dict(rules)}, more than one rule {multi}")
    print(f"- universe options {len(r.options) + len(r.rejected)}")
    order = [o.option.option_id for o in r.options]
    print("- recommended:")
    for oid in r.recommended:
        o = next(o for o in r.options if o.option.option_id == oid)
        f = F.get(oid)
        print(f"  - {oid} {o.option.label[:50]} | class {o.option.asset_class} | risk {f.risk if f else '?'}"
              f"{' (est.)' if f and f.risk_estimated else ''} | real1y {pct(f.real_return if f else None)} %"
              f" | score {o.score:.3f} | place {order.index(oid) + 1} | conf {o.confidence:.2f} | stab {o.stability:.2f}")
        if "asset_class" in o.reasons or any("Varlık sınıfı" in t for t in o.reasons.values()):
            print("    reason:", [t for t in o.reasons.values() if "Varlık sınıfı" in t])
    print("- top 6 by score:", [(o.option.option_id.split(":")[-1], round(o.score, 3), o.option.asset_class)
                                for o in sorted(r.options, key=lambda o: -o.score)[:6]])
    dep = next((o for o in r.options if o.option.kind == "deposit"), None)
    if dep:
        print(f"- Turuncu: real1y {pct(F[dep.option.option_id].real_return)} %, score {dep.score:.3f}, "
              f"parts { {k: round(v, 3) for k, v in dep.score_parts.items()} }")
    td = next((o for o in r.options if o.option.kind == "time_deposit"), None)
    if td:
        print(f"- e-Vadeli: real {pct(F[td.option.option_id].real_return)} %, score {td.score:.3f}, place {order.index(td.option.option_id) + 1}")
    mm = [F[o.option.option_id].real_return for o in r.options
          if o.option.fund_kind == "money_market" and F.get(o.option.option_id) and F[o.option.option_id].real_return is not None]
    if mm:
        print(f"- money market funds: real1y median {statistics.median(mm) * 100:+.1f} %, max {max(mm) * 100:+.1f} %")
    confs = collections.Counter(round(o.confidence, 2) for o in r.options)
    print("- confidence counts:", dict(sorted(confs.items(), reverse=True)))
    top20 = r.options[:20]
    print(f"- stability: min in first 20 {min(o.stability for o in top20):.2f}; recommended "
          f"{[(o.split(':')[-1], round(next(x for x in r.options if x.option.option_id == o).stability, 2)) for o in r.recommended]}")
    print("- warnings:", [(w.code, w.message[:90]) for w in r.warnings])
    print("- to_confirm:", list(r.to_confirm))
    print("- allocation:")
    for a in r.allocation:
        print(f"  - {a.asset_class}: {a.low}-{a.high} {'*' if a.inferred else ''} option {a.option_id} note {a.note!r}")
    if p.persona_id == "P02":
        w = normalize_weights(raw_weights(lv, cfg))
        print("- P02 weights:", {k: round(v, 3) for k, v in w.items() if v})
        for o in sorted(r.options, key=lambda o: -o.score)[:6]:
            print(f"  - {o.option.option_id} {o.option.asset_class} risk {F[o.option.option_id].risk} "
                  f"real {pct(F[o.option.option_id].real_return)} parts "
                  f"{ {k: round(v, 3) for k, v in o.score_parts.items()} } score {o.score:.3f}")
    if p.persona_id == "P01":
        print("- assumptions:")
        for a in r.assumptions:
            print("  -", a)

print("\n## Median real 1-year return by asset class (all scored funds of P03, no risk filter)\n")
r03 = b.decide(next(p for p in b.list_personas() if p.persona_id == "P03"), SNAP)
lv3 = read_persona(next(p for p in b.list_personas() if p.persona_id == "P03"), cfg).levels
F3 = {f.option.option_id: f for f in option_features(uni, lv3, cfg)[0]}
by = collections.defaultdict(list)
for o in r03.options:
    f = F3.get(o.option.option_id)
    if f and f.real_return is not None and o.option.kind == "fund":
        by[o.option.asset_class].append(f.real_return)
for c, v in sorted(by.items()):
    print(f"- {c}: n {len(v)}, median {statistics.median(v) * 100:+.1f} %")
