# Paradigm 225 — Graveyard

**Name**: `coin_m_vs_usdt_m_funding_spread_miner_vs_speculator_momentum`
**Paradigm number**: 225
**Phase halted**: R-1
**Verdict**: `BROAD_FALSIFIED + PATTERN_P1_ALPHA_DECAY + LESSON39_SUB_CLASS_B_MECHANISM_INVERTED_HYBRID`
**Date**: 2026-07-13

---

## Hypothesis Summary

COIN-M perpetuals (BTC/ETH/BNB/XRP/ADA-margined) are dominated by miners/arbitrageurs; USDT-M perpetuals are dominated by retail speculators. When COIN-M funding rate significantly exceeds USDT-M funding rate for a given underlying, sophisticated capital is positioned more bullish than retail → directional continuation. Test: per-sym 30d rolling z-score of spread = coinm - usdtm; bilateral |z|≥1.5 trigger × 4-quadrant SNT × hold sweep 4h/8h/12h/24h/48h, 24h primary.

Universe: 5 syms × 2.25yr × 8h cadence. Substrate confirmed via data.binance.vision `futures/cm/monthly/fundingRate/` (daily prefix does NOT exist — used monthly zips).

---

## R-0 Prescreen Outcomes

- Item 1 slug grep: PASS (zero prior-art collisions).
- Item 2 substrate audit: PASS (monthly not daily, 5 syms × 30 months).
- Item 3 sample density: PASS (per-cell 16-way = 97.6 at |z|≥1.5 across 5 syms × 12255 obs).
- Item 4 DNA distinct 4/5: PASS (new statistic_class = cross-CLASS inter-margin spread).
- Item 5 family-proxy risk: LOW.
- Item 6 alpha decay Pattern P1: FLAGGED for mandatory era stratification — confirmed to fire, see R-1 results.
- Item 7 asymmetry ratio: PASS (1.19-1.47 across syms, no structural infeasibility).
- Item 8 concentration pre-estimate: STRICT 50% required (5 syms).
- Item 9 life-changing pre-check: PASS at 24h primary (util ≈ 92% realized).

---

## R-1 Measurement Summary (24h PRIMARY hold)

| Quadrant | n | mean bp | sigex | ci_lo bp | perm_p | 3-gate | conc |
|---|---|---|---|---|---|---|---|
| A_focus (z≥+1.5 LONG) | 798 | -7.64 | -1.35 | -33.45 | 0.68 | FAIL | FAIL |
| A_mirror (z≥+1.5 SHORT) | 798 | -8.36 | 0.17 | -35.43 | 0.64 | FAIL | FAIL |
| B_focus (z≤-1.5 SHORT) | 752 | -52.05 | -3.21 | -76.98 | 0.000 | FAIL (opp sign) | FAIL |
| B_mirror (z≤-1.5 LONG) | 752 | +36.05 | 1.98 | +11.68 | 0.012 | FAIL (sigex<2.0) | FAIL (ci_pos=0.4) |

### Hold Sweep — B_mirror (z≤-1.5 → LONG) is the only cell with positive signal

| Hold | n | mean bp | sigex | ci_lo bp | perm_p | 3-gate | conc |
|---|---|---|---|---|---|---|---|
| 12h | 752 | +24.87 | 1.89 | +5.30 | 0.022 | FAIL (sigex<2.0) | FAIL |
| 24h | 752 | +36.05 | 1.98 | +11.68 | 0.012 | FAIL (sigex<2.0) | FAIL |
| **48h** | 752 | **+82.72** | **3.03** | **+43.65** | **0.000** | **PASS** | **FAIL (0.4)** |

### Era Stratification (B_mirror 48h — the strongest cell)

| Era | n | mean bp | t-stat |
|---|---|---|---|
| 2024H1 | 139 | +200.62 | **+4.99** |
| 2024H2 | 172 | +227.31 | **+4.20** |
| 2025H1 | 177 | +29.74 | +0.76 |
| 2025H2 | 136 | +8.77 | +0.22 |
| 2026H1 | 128 | **-87.76** | **-2.43** |

**Pattern P1 monotonic decay CONFIRMED at 48h**: t-stats fell 4.99 → 4.20 → 0.76 → 0.22 → **-2.43**, with 2026H1 sign-flipped to negative. Alpha has fully decayed.

### Per-Symbol Concentration (B_mirror 48h)

| Sym | n | mean bp | ci_lower bp | ci_pos |
|---|---|---|---|---|
| BTCUSDT | 171 | +27.99 | -22.10 | FALSE |
| ETHUSDT | 172 | +30.39 | -39.72 | FALSE |
| BNBUSDT | 134 | +17.75 | -52.85 | FALSE |
| XRPUSDT | 151 | +224.08 | +113.98 | TRUE |
| ADAUSDT | 124 | +128.87 | +27.42 | TRUE |

Only XRPUSDT and ADAUSDT drive the aggregate signal; BTC/ETH/BNB have zero individual edge. Concentration Gate FAIL (2/5 = 40%, need ≥ 50% for narrow universe).

---

## Failure Modes

1. **Focus mechanism empirically inverted**: The hypothesized "z≤-1.5 → SHORT continuation because miners hedging leads price down" produces the OPPOSITE — a strong negative return (mean=-52 bp @24h, -99 bp @48h). Price goes UP after miner bearish positioning, not DOWN. This is a Lesson #39 sub-class B mechanism-inverted failure on the B-side.

2. **A-side is Lesson #39 sub-class A broad-uniform-negative**: Both A_focus and A_mirror lose money at all holds, meaning z≥+1.5 has zero directional information. The trigger's "sophisticated capital more bullish than retail" hypothesis produces no signal.

3. **Even the mirror-inverted B-side (B_mirror z≤-1.5 → LONG) is Concentrated + Alpha-Decayed**:
   - Concentration Gate FAIL: only XRP/ADA (2/5 syms) drive the signal at all holds; BTC/ETH/BNB have zero individual edge.
   - Pattern P1 MONOTONIC DECAY: 2026H1 t-stat = **-2.43** (sign flipped). By 2026H1 the mirror signal has also died.

4. **At primary 24h hold, life-changing 4-dim FAIL**: edge=36 bp (need ≥200 bp), sharpe_ann=1.85 PASS. But edge failure alone kills life-changing.

---

## Lesson Dogfoods

| Lesson | Applied | Verdict |
|---|---|---|
| #11 sample density | expected_n_per_cell=97.6 >> 30 | PASS |
| #16 Concentration Gate | strict 50% for narrow universe (5 syms) — FAIL (0.4) | ENFORCED |
| #19 Symmetric Negative Test | 4-quadrant joint-trigger executed | ENFORCED (revealed inverted mechanism) |
| #28 substrate audit | daily prefix absent → monthly path used | ENFORCED |
| #39 sub-class A broad-uniform-negative | A-side both focus+mirror losing → confirmed sub-class A on A-side | CONFIRMED (73rd dogfood: A-side pattern) |
| #39 sub-class B mechanism-inverted | B-side focus FAIL + B-side mirror real edge → sub-class B | CONFIRMED (74th dogfood: B-side inverted) |
| #40 structural threshold feasibility | spread symmetric; no non-negative aggregate | N/A |
| Pattern P1 alpha decay | 2024H1 → 2026H1 monotonic decay with 2026H1 sign flip | CONFIRMED (Nth consecutive P1) |
| #56 family-proxy outcome | novel cross-CLASS dimension — no direct proxy | LOW RISK confirmed novel |
| #62 DNA 4/5 distinctness | new class/universe/trigger/mechanism | ENFORCED |

**NEW Lesson candidate observation** (proposed for #78 or next slot):
> *Miner/COIN-M funding spread carries NO stable alpha through 2026 across the 5-sym universe. The apparent edge in 2024 (both directions of B-side conditioning) was dominated by XRP/ADA idiosyncratic behavior and has fully decayed by 2026H1. Cross-margin-class spread signal is family-proxy-adjacent to per-sym USDT-M funding z (paradigm 22 R-5 family) and inherits the same maturity-driven decay path.*

---

## Next Paradigm Recommendation

Skip all cross-margin-class funding spread variants (BTC-only spread, ETH-only spread, threshold sweep spread, momentum-of-spread, etc.) — the mechanism is decayed. Redirect the queue to genuinely orthogonal substrates:

1. **Cross-exchange COIN-M vs USDT-M ETF flow inflows** (spot vs derivative demand asymmetry) — different dimension entirely, though ETF data availability requires archive audit.
2. **Volatility surface skew from Deribit options** vs perp funding — non-OHLCV, non-funding substrate.
3. **Non-CEX substrate paradigms** already listed in queue (on-chain / MEV / bridge flow variants).

Avoid: any per-sym funding z-score variant, any cross-margin-class spread variant, any pre-2024 backfill of same substrate hoping for older regime persistence (won't restore 2026 signal).

---

## Artifacts

- `backend/scripts/research/coin_m_vs_usdt_m_funding_spread_item3_density.py`
- `backend/scripts/research/coin_m_vs_usdt_m_funding_spread_r1.py`
- `backend/runs/research_track/coin_m_vs_usdt_m_funding_spread/artifacts/item3_density.json`
- `backend/runs/research_track/coin_m_vs_usdt_m_funding_spread/r1__metrics.json`
- `backend/runs/research_track/coin_m_vs_usdt_m_funding_spread/coinm_raw/{BTC,ETH,BNB,XRP,ADA}USD_PERP/*.zip` (30 months each; retained for future cross-class research)
