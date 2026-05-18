# Paradigm 94 — `cross_asset_volume_concentration_alt_long_1d` (R-1 PoC)

**Status**: R-1 dispatch ad-hoc (2026-05-18). Campaign 휴면 mode 사용자 명시 예외.

## Hypothesis (single sentence)

BTC daily volume share (= BTC 24h USD-volume / sum(26-sym 24h USD-volume)) 30d rolling z-score
`<= -1.5` (BTC share 압축 = alt rotation leading indicator) → 13 alts LONG, hold +1d (entry next 00:00 UTC bar open, exit 24h later at close).

## DNA

| Dim | Value |
|---|---|
| Data dimension | cross-asset daily volume share (vol divided by panel-aggregate vol) |
| Decision mode | level-crossing boundary z-score, long-only directional |
| Time scale | daily (1d) entry, 24h hold |
| Universe | 26-sym (BTC + 13 paradigm-69 alts + 12 보강) for denominator; 13 alts for entry direction |
| Statistic class | rolling z of cross-sectional share fraction (NEW transform class) |
| Substrate | Binance perp 1m OHLCV → 1d resample (local DB) |

## Family-distinct verification

| Retired/cautioned family | Distinguishing factor |
|---|---|
| `5m_microstructure_single_domain_alpha_family` (advisory caution) | this paradigm uses **daily** aggregation, not 5m boundary detection |
| `kr_equity_post_earnings_guidance_directional_momentum_family` (Tier 4) | crypto perp, not KR equity earnings |
| `geometric_path_metrics_family` | this is a volume-share ratio, not a path-shape metric |
| `funding_oi_joint_squeeze_family` | volume only, no funding or OI axis |
| `btc_eth_5m_corr_breakdown_family` | daily volume share, not 5m correlation |

Conclusion: family-distinct, new transform class.

## Lesson grid (R-1 prescreen + in-body checks)

| Lesson | Application |
|---|---|
| #11 sample density | per-cell ≥30 floor. Fallback cutoffs `-1.0`, `-1.2`, `-1.5` measured. |
| #16 Concentration Gate | per-quarter t + per-symbol bootstrap CI mandatory output |
| #19 Symmetric Negative Test | 2-quadrant (focus z<-1.5 LONG, mirror z>+1.5 LONG) — single trigger, not joint |
| #21 axis stacking | single statistic ✓ |
| #22 stateful detector | rolling z is not stateful ✓ |
| #24 boundary-event horizon | level crossing instantaneous, density preserved ✓ |
| #27/#28 entry-side/substrate | internal market structure, not external event ✓ |
| #29 cross-proxy strict | obs proxy = volume_share_z; fund proxy = BTC_absolute_volume_change_z (raw flow magnitude). Both tracks must PASS. |

## Universe (exact)

**Denominator (26 syms)**: BTCUSDT + 13 paradigm-69 alts + 12 보강 alts
- paradigm-69 alts (13): ADAUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, DOGEUSDT, ETHUSDT, FILUSDT, LINKUSDT, LTCUSDT, NEARUSDT, SOLUSDT, WIFUSDT, XRPUSDT
- 보강 (12 actually loaded — original spec listed 11 + 1000LUNCUSDT): AXSUSDT, HBARUSDT, LDOUSDT, COMPUSDT, UNIUSDT, PYTHUSDT, TONUSDT, ETCUSDT, ICPUSDT, JUPUSDT, WLDUSDT, 1000LUNCUSDT

**Entry direction (13 alts)**: paradigm-69 alt list (LONG only on focus quadrant, SHORT not applied — mirror = inverse trigger same LONG direction per lesson #19 2-quadrant).

## Cutoffs / config

- BTC volume share z-score window: 30d trailing (rolling, min_periods=30)
- Focus trigger: share_z <= -1.5 (with fallback -1.2, -1.0 if per-cell <30)
- Mirror trigger: share_z >= +1.5 (Lesson #19 symmetric negative)
- Hold: 1d (24h, entry next 00:00 UTC bar open, exit 24h later at close)
- Fee round-trip: 0.0008 (8 bp); fee-floor stress: 0.0050 (50 bp)
- Entry execution: next-bar open
- Cross-proxy fund track: BTC absolute volume USD change z (BTC_vol - rolling_30d_mean) / rolling_30d_std

## Data window

- Local DB 1m OHLCV BTCUSDT: **2025-12-22 → 2026-05-13** (143 days)
- After 30d warmup: ~113 days usable
- Expected trigger rate (|z|>1.5 one-sided) ≈ 6.7% normal-tail → ~7-8 trigger days × 13 alts ≈ 91-104 trades focus quadrant
- **lesson #11 risk**: per-quarter cells will be sparse (~2-3 events per quarter), Concentration Gate may degenerate

## Verdict candidates

- `PASS_R1` — 3-gate ALL PASS + Concentration PASS + cross-proxy PASS_R1_CROSS_PROXY_PROMOTE_R2
- `FAIL_THREE_GATE` — sigex/ci/perm_p any FAIL
- `BROAD_FALSIFIED` — 2-quadrant 모두 FAIL
- `BROAD_FALSIFIED_FEE_FLOOR` — gross < 16bp
- `SAMPLE_INSUFFICIENT` — cutoff 완화 fallback도 per-cell <30
- `CONCENTRATED_R1_PASS` — three-gate PASS but Concentration FAIL
- `SINGLE_PROXY_TRAP_{OBS|FUND}_ONLY` — 한 트랙만 PASS (lesson #29)

## Constraints

- R-1 ONLY. Halt after completion.
- Foreground synchronous execution.
- Output: r1_metrics.json + r1_summary.md (Korean) + INDEX.md row update.
