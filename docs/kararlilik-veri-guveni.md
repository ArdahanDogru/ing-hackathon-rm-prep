# Kararlılık and Veri güveni: how the fund card's chips are measured

The fund card ("Neden bu öneri?", docs/web-ui.md W15) shows two chips, e.g.

> Kararlılık %100 · kararlı  
> Veri güveni %90 · yüksek

Both values are computed by the decision engine (`ScoredOption.stability`,
`ScoredOption.confidence`; docs/decision.md section 5 and D25). The web app only
shows them and turns them into a word. Factors and steps are in
`config/decision.yaml` (`confidence`, `stability`, `warnings`).

## Kararlılık (stability)

*Would we still recommend this option if our assumptions were a bit different?*

The weights and penalty maxima are judgement calls, so the engine tests how
sensitive the result is to them:

1. It computes the ranking again **30 times**. Each run changes one number by
   ×0.8 or ×1.2 (`stability.step: 0.2`): one of the 7 raw criterion weights
   (then normalized again) or one of the 8 penalty maxima. 15 numbers × 2
   directions = 30 runs.
2. Each run applies the same recommendation rule as the real result
   (`recommend.py`: the class rule when it applies, else the plain order).
3. **For a recommended option:** Kararlılık = the share of the runs in which it
   is recommended again.
   **For any other option:** the share of the runs in which it is in positions
   1–20 (`stability.size`). The deposit baseline counts as always in.

Example: **%100** = recommended in all 30 runs; no single assumption changed by
20 % removes it.

| Value | Label |
|---|---|
| ≥ 80 % | kararlı |
| ≥ 50 % | kısmen kararlı |
| < 50 % | kararsız |

Below 50 % (`warnings.low_stability_below`) the engine also raises the
`low_stability` warning for the RM.

## Veri güveni (data confidence)

*How much can we trust the data behind this option?*

It starts at 1.0 and is multiplied down.

**1. The weakest data point the option uses sets the base.** A data point with
several flags takes its lowest factor.

| Flag on the data | Factor |
|---|---|
| none | 1.0 |
| `needs_check`, `manual_entry` | 0.9 |
| `unverified_series`, `fallback_snapshot` | 0.8 |
| `stale` (older than the quantity's `max_age_days`) | 0.7 |
| `conflict` (sources disagree) | 0.6 |

**2. Each estimate the engine had to make multiplies it again.**

| Estimate | Factor |
|---|---|
| risk level estimated, no SPK value (`risk_estimate`) | × 0.7 |
| return history shorter than the client's horizon (`shorter_period`) | × 0.8 |
| liquidity from the fund-type table, sell valör missing (`liquidity_proxy`, D14) | × 0.8 |
| no TÜFE row, or no stopaj row for the product type (`real_return_missing`, D24) | × 0.8 |

Examples:

- **%90**, a typical TEFAS fund: the TEFAS rows are `needs_check` (0.9), no
  estimate.
- **%63**, a fund with an estimated risk level: 0.9 × 0.7.

| Value | Label |
|---|---|
| ≥ 80 % | yüksek |
| ≥ 60 % | orta |
| < 60 % | düşük |

## Where the labels come from

The value cut-offs (80 / 50 for Kararlılık, 80 / 60 for Veri güveni) are a UI
choice for the fund card, not engine rules: `stabilityLevel` and
`confidenceLevel` at the end of `web/src/explain.ts`. Only the 50 % stability
threshold for the `low_stability` warning is engine config.
