# Paradigm 96 — R-1 Spec

**Name**: `funding_rate_sign_flip_event_alt_long_4h`
**Phase**: R-1 PoC
**Run timestamp**: 2026-05-19 11:03 KST (Mint host)
**Wall clock**: 15.3s
**Verdict**: **BROAD_FALSIFIED**

## Hypothesis

Funding rate categorical SIGN FLIP event at 8h cycle boundary on per-symbol basis triggers price reaction over the next half-cycle (+4h hold). Two sub-triggers:
- **A** (pos→neg): long-side over-positioning unwind expected to reverse
- **B** (neg→pos): short squeeze ignition expected to extend

Direction: 13 alts LONG (paradigm 69 verified pool).
Hold sweep: 4h / 8h / 12h.

## Family-distinct DNA

- Paradigm 22 `funding_carry` — z-score MR (continuous transform)
- Paradigm 73 `funding_oi_bipolar` — joint funding × OI event detection
- Paradigm 79 `funding_extreme` — extreme z-score level filter
- **Paradigm 96 (THIS)** — categorical SIGN FLIP boundary event (NEW transform class)

5/6 DNA dimensions distinct from any active or graveyard paradigm. Statistic class = categorical boundary (not continuous z, not level threshold, not joint event).

## Lesson grid prescreen

| # | Status | Note |
|---|---|---|
| #4 universe size | OK | 13 alts (BNBUSDT effectively absent — only 2 flips total) → 12 measurable |
| #11 sample density | OK | 3470 A + 3464 B events / 10 quarters / 12 syms = ~29 per cell minimum |
| #16 Concentration Gate | dispatched | per-quarter + per-symbol bootstrap |
| #19 Symmetric Negative Test | dispatched | 4-quadrant joint-trigger paradigm 의무 |
| #20 narrow-scope 4-cond | N/A | focus three-gate FAIL → no Concentration FAIL fallback path |
| #21 axis stacking | OK | single statistic (sign flip categorical) |
| #22 stateful detector | OK | sign flip is stateless boundary |
| #23 event-anchored low-freq × strict z | OK | 8h cycle + boundary detection, not strict z |
| #24 boundary-event horizon-bound | OK | 8h cycle x ~10% flip rate x 13 syms x 2.5yr -> 6934 events |
| #27/#28 entry/substrate | OK | internal mechanism, substrate available |
| #29 cross-proxy strict | dispatched | obs (sign category) + fund (|mag_z| >= 1.0) |
| #30 short-data verdict | OK | Mint full-window (data_window_ratio = 1.0) |

## Substrate

- Mint `binance_funding_rate` DB — 14 syms, 2.5yr coverage (2023-11-15 -> 2026-05-15+)
- Mint OHLCV joblib cache `runs/ohlcv_cache/` — 14 syms x 1m x ~860d (avg)

## Three-gate definition

PASS requires ALL:
- `signal_t_excess >= 2.0`
- `bootstrap_ci.ci_lower > 0`
- `perm_p <= 0.10`

## Concentration Gate (lesson #16)

PASS requires ALL:
- `quarter_pos_t_ratio >= 0.5`
- `symbol_ci_pos_ratio >= 0.30`
- `n_symbols_ci_pos >= 3`

## Verdict tree (paradigm 95 dogfood)

```
3-gate ALL FAIL -> BROAD_FALSIFIED  [TAKEN]
3-gate PASS + Conc PASS -> PASS_R1
3-gate PASS + Conc FAIL -> lesson #20 4-cond -> NARROW_SCOPE_CANDIDATE / LIFE_CHANGING_FAIL / CONCENTRATED_R1_PASS
```
