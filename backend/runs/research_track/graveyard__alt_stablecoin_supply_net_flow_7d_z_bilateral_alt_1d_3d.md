# Graveyard — alt_stablecoin_supply_net_flow_7d_z_bilateral_alt_1d_3d

- **paradigm_counter**: 251
- **verdict**: G1 FAIL — alpha decay
- **phase**: R-1 (tier3_gate)
- **date**: 2026-08-09

## Hypothesis

Net 7-day USDT+USDC stablecoin market cap change (z-scored over 60d rolling
window) as crypto capital inflow signal.
- `z > +1.0` → LONG alt perps (fresh capital entering)
- `z < -1.0` → SHORT alt perps (redemptions, capital exit)

Daily signal, entry T+1 open, hold sweep 1d/2d/3d, fee 0.0008 RT.

## DNA (5-dim, all novel vs INDEX)

1. `usdt_usdc_combined_supply_7d_change_z`
2. `stablecoin_market_cap_coingecko_daily` (non-OHLCV)
3. `bilateral_z_threshold_1.0_directional`
4. `net_crypto_capital_inflow_risk_appetite`
5. `1d_2d_3d_hold_daily_1440min_cycle`

## R-0 prescreen (all PASS)

- Lesson #61 slug grep: clean (no verbatim match in INDEX/RUNBOOK)
- DNA overlap: distinct from `stablecoin_mint_event_long_alt_24h` (event trigger
  vs continuous rolling z-score)
- Lesson #77 non-OHLCV substrate: satisfied (CoinGecko market cap)
- Lesson #79 pretest: `corr(z, SOL fwd_1d) = +0.097`, `E[sign(z)·fwd_ret] = +0.475%`
  on n=85 — meaningfully non-zero, proceeded
- Sample density: 121 triggers / 299 signal days = 40.5% trigger rate. OK.

## Data window

- CoinGecko free tier: 365 days (2025-08-10 → 2026-08-09), auth required for longer
- OHLCV cache overlap: 2024-01-02 → 2026-05-12
- Effective backtest window: 2025-10-26 → 2026-05-05 (~6 months, 85 triggers per symbol)

## R-1 backtest results (raw)

Universe: SOL / AVAX / DOGE / LINK / XRP / BNB × hold {1d, 2d, 3d}, all n=85.

| cell | raw mean | t-stat | win% |
|---|---|---|---|
| DOGEUSDT h3d | +2.572% | +3.42 | 69.4% |
| SOLUSDT h3d  | +2.322% | +2.89 | 61.2% |
| BNBUSDT h3d  | +2.076% | +3.29 | 57.6% |
| LINKUSDT h3d | +1.903% | +2.53 | 58.8% |
| AVAXUSDT h3d | +1.889% | +2.47 | 56.5% |
| DOGEUSDT h2d | +1.769% | +2.52 | 64.7% |
| SOLUSDT h2d  | +1.703% | +2.40 | 60.0% |
| (all others positive, no cell < +0.88%)

DOGEUSDT h3d long/short split: long n=26 mean +2.38% win 73.1%, short n=59
mean +2.66% win 67.8% — both sides individually profitable.

Delayed T+2 variant: DOGEUSDT h3d mean +3.012% (t=+3.76). Edge persists past
T+1 (delay_retention = 1.44 — actually amplifies).

## Tier3 gate — best cell (DOGEUSDT h3d)

```
G1 time-weighted performance (halflife 90d):
  n_trades              85
  raw edge              +2.5718%
  time-weighted edge    +2.0932%
  time-weighted t       2.781    (>= 1.5 required)   PASS
  recent 1/3 edge       +0.3968% (> 0 required)      PASS
  older 1/3 edge        +2.8794%
  decay_ratio           0.138    (>= 0.30 required)  FAIL

G2 executability:
  edge_after_1bar_pct   3.012
  roundtrip_friction    0.08%
  delay_retention       1.44
  net_headroom          37.65    (>= 3.0 required)   PASS
  cycle_margin          3.0      (>= 3.0 required)   PASS
```

## Root cause — regime-scoped alpha, monotonic decay

Signal window (Oct-2025 → May-2026) straddles the tail of a stablecoin-supply-led
alt rally and its subsequent breakdown. Split by thirds (sorted by exit_ts):

| cell         | recent ⅓ | older ⅓ | decay |
|---|---|---|---|
| DOGEUSDT h3d | +0.397%  | +2.879% | 0.14  |
| BNBUSDT h3d  | -0.159%  | +3.088% | -0.05 |
| SOLUSDT h3d  | -0.877%  | +3.457% | -0.25 |
| LINKUSDT h3d | -1.459%  | +3.272% | -0.45 |

**Every cell except DOGE h3d flipped negative in the recent ⅓.** DOGE h3d remained
barely positive but decayed to 14% of its early edge. This is not statistical noise
— it is a coherent mechanism death across the whole universe.

Interpretation: during the Oct-2025→Feb-2026 phase, stablecoin supply growth
was informative because fresh USDT/USDC was actively being deployed into alts.
From Mar-2026 onward, supply continued to grow (Fed easing persisting) but the
capital rotated into equities/T-bills instead of crypto risk — the linkage broke.
The z-score signal keeps firing but the follow-through evaporates.

## Verdict

**GRAVEYARD — G1_ALPHA_DECAY**

Do not enqueue into 2군 promotion queue. G2 executability is clean (net_headroom
37×, delay_retention 1.44×, cycle 3× margin), but the alpha itself no longer
exists in the recent window. Sending this to 2군 forward would waste a slot
watching a dead signal cross zero.

## Lessons cross-reference

- Lesson #55 alpha-decay cross-family (paradigm 87 delisting, paradigm 136/202
  RV intraday): same monotonic-temporal-decay pattern. Now confirmed also in
  **macro-liquidity substrate** — the failure mode is substrate-agnostic and
  applies to any signal whose underlying mechanism has finite regime lifetime.
- Lesson #26 temporal WF mandatory: G1 recent-vs-older split caught what a
  pooled statistic hid (raw mean +2.57% t=+3.42 looks great; recent ⅓ is
  effectively zero).
- Lesson #77 (non-OHLCV substrate): substrate class is orthogonal to alpha
  persistence — a novel-substrate signal decays the same way as an OHLCV one.

## Non-follow-up

- **Do not** re-run with a shorter roll_win (e.g. 30d) — a shorter baseline just
  makes the trigger more responsive to short-term noise, not more predictive
  in-regime.
- **Do not** narrow to DOGE-only — the mechanism inversion is universe-wide,
  DOGE h3d survival is likely luck at n=85.
- **Do** consider a *regime-conditional* variant later: gate the stablecoin
  z-signal on a separate risk-on indicator (e.g. BTC 60d trend positive).
  That is a *different* paradigm (extra axis) and belongs to a future DNA slot.

## Artifacts

```
scripts/research/r1_paradigm_251_stablecoin_supply_flow_bilateral.py
runs/research_track/paradigm_251_stablecoin_supply_flow/
  stablecoin_supply_cache.json
  r1_summary.json
  r1_trades_{SYM}_h{1,2,3}d.json          (6 syms × 3 holds)
  r1_trades_delayed_{SYM}_h{1,2,3}d.json  (T+2 delayed variants)
  tier3_gate__DOGEUSDT.json
```
