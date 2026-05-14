# R-5 Seed Proposal — btc_rv_spike_highvol_filter_alt_long_240m

**작성일**: 2026-05-14
**상태**: 사용자 명시 승인 대기 (DRAFT). 본 문서 승인 시 paper 풀 시드 진행.

---

## 가설 요약

BTC 30-min realized vol z-score(30d) ≥ +2.5 (rising edge + 60-min cooldown) AND BTC 30-min return > 0 AND BTC 30d rolling vol ≥ p90 of past 90d (HIGH vol regime) → 13 alts LONG, 270-min hold, TP +5%.

**Mechanism**: 이미 elevated vol regime + 추가 RV z-spike + 가격 up direction = vol cascade momentum. 고변동성 환경 leverage stress + 추가 충격 트리거 → liquidation cascade up-side + 추격 매매 → 4.5h 모멘텀 tail.

---

## R-1 ~ R-4 핵심 metrics

| Phase | 핵심 metric | 값 |
|---|---|---|
| R-1 (p75 filter) | n / mean / sig_t_excess / CI | 689 / +42.78bp / +4.73 / [+16.10, +70.25]bp |
| R-1 H5 vol cutoff monotone | p75 → p80 → p85 → p90 | +42.78 → +87.05 → +81.43 → +133.58bp ✓ |
| R-2 best (p90 + h=270m + TP=+5%) | n_trades | 455 |
| R-2 net_mean / t / sig_t_excess | 13개 alt 풀 | +126.28bp / +11.11 / +12.24 |
| R-2 CI [lower, upper] / prob_pos | bootstrap n=2000 | [+116.11, +128.29]bp / 1.000 |
| R-2 plateau (strict 4-gate) | 96-cell grid | **96/96** PASS |
| R-2 per-sym | 13/13 net positive | min +4bp / max +27bp (BCH) |
| R-3 inter-paradigm cosine | vs 68번 parent | 0.4163 (≤0.5 distinct sub-paradigm) |
| R-3 inter-paradigm cosine | vs 5 다른 시드 | ≤ 0.02 |
| R-3 within-HIGH stratification | 0 killer subregime | trend/r7d/month 모두 양수 |
| R-3 WF 5-fold | positive / t>1 | 4/5 / 4/5 |
| R-3 Q4-2025 / Q1-2026 독립 검증 | sig_t_excess | +11.94 / +5.30 둘 다 PASS |
| R-3 funding-adj net mean | 66% trades span 1bp/8h | +125.62bp t=+11.05 |
| R-3 look-ahead bias | clean | ✓ |
| R-4 자동 게이트 (patched evaluator) | E_NEW schema | **✅ PASS (9/9)** |

---

## 추천 Paper Session 설정

### Source 정의

```python
# backend/app/composer_framework/sources/binance_btc_rv_highvol_long_source.py
class BinanceBTCRVHighvolLongSource(BaseSource):
    name = "bn_btc_rv_spike_highvol_long_240m"
    universe = [
        "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
        "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
        "SOLUSDT", "WIFUSDT", "XRPUSDT",
    ]
    bar_interval = "1m"

    # Trigger: 4-AND condition
    rv_window_min = 30      # BTC 30m realized vol
    rv_z_window_days = 30   # 30d rolling z-score
    rv_z_threshold = 2.5    # |z| ≥ 2.5 rising edge
    cooldown_min = 60       # 60m between triggers
    btc_ret_sign_filter = "positive"  # BTC 30m return > 0
    vol_regime_window_days = 30        # current 30d vol
    vol_dist_window_days = 90          # vs 90d distribution
    vol_percentile_cutoff = 90         # p90 (HIGH vol)
```

### Policy 정의

```python
# backend/app/composer_framework/policy.py
class BTCRVHighvolLongPolicy:
    direction = "long"
    hold_minutes = 270
    tp_pct = 0.05           # +5%
    sl_pct = None           # no stop-loss (or optional -5%)
    position_size = "equal_weight_per_alt"   # 1/13 notional per trigger per alt
    max_concurrent_triggers = 1               # avg 0.96 expected
```

### Risk parameters

| 항목 | 값 |
|---|---|
| Position size | 1/13 per trigger per alt (equal weight) |
| Max concurrent triggers | 1 (avg 0.96 per R-3 measurement) |
| Capacity | ~35 triggers/yr × 13 alts ≈ 455 trades/yr |
| Fee | 8 bp round-trip |
| Slippage realism | unmodeled (실거래 실측 후 보정) |

### Expected performance (R-3 measured, funding-adjusted)

- Net mean: **+125.62 bp/trade**
- Annual alpha pool: 455 × 125.62 bp = **+57.16%/yr aggregate**
- Per-sym annual alpha: ~35 × 125.62 bp ≈ +4.40%/sym/yr (sym-weighted)
- signal_t_excess: +12.26, perm_p_above: 0.000
- Sharpe per trade: 0.0574 (≈ 0.86 annualized)

---

## Caveats (R-5 시드 후 모니터링 필수)

1. **Trigger sparsity**: 평균 11일/trigger. 2026-01-05~02-03 dry period (n=0 in WF Fold 4). 운영 시 trigger latency 변동 가능성.
2. **Funding cost realism**: 1bp/8h는 보수적 추정. 실제 Binance funding 0.5~1.5bp/8h alt별 변동. paper baseline에서 실측 funding 적용해 alpha 재계산 필요.
3. **Parent 68th paradigm graveyard reminder**: 부모 paradigm은 R-3.5 vol regime stratify에서 가설 반증. 본 child paradigm은 within-HIGH stratification 0 killer로 통과했으나 **data window 1.04yr short** — long-horizon regime shift 검증 부족.
4. **Cosine 0.42 vs 68 parent**: trigger 부분집합 (455/2626=17%). 68번 graveyard 이후 본 paradigm 출범한 lineage이므로 일관성 모니터 필요.
5. **Day 30 paper baseline validation 필수**: 시드 후 30일 baseline 측정. 만약 alpha < 50% of measured (예측 +57.16%/yr → measured < +28%/yr) 시 demote.

---

## 추천 ecosystem.config.cjs 항목 (template only, deploy 안 함)

```javascript
{
  name: 'paper-btc-rv-highvol-long-cycle',
  script: 'backend/venv/bin/python3',
  args: '-m scripts.paper_session_cli run --session bn_btc_rv_spike_highvol_long_240m',
  cron_restart: '30 11 * * *',  // daily 11:30 KST (02:30 UTC)
  autorestart: false,
  watch: false,
  max_memory_restart: '500M',
  env: { TRADING_MODE: 'PAPER', PYTHONPATH: '/home/mint/auto_trading/backend' },
}
```

---

## HALT 안내

본 R-5 seed proposal은 **DRAFT**입니다. 실제 paper 풀 시드 (`paper_session_cli seed`) 진행은 **사용자 명시 승인** 후에만 가능합니다.

승인 시:
1. Source class + Policy class 코드 작성 (위 template 기반)
2. backend/configs/paper_sessions/btc_rv_spike_highvol_long.json 생성
3. paper_session_cli seed 실행 (Mint)
4. ecosystem.config.cjs 항목 추가 + PM2 reload
5. Day 7 / Day 30 paper baseline 검증 스케줄 등록

---

**End** — 사용자 결정 대기.
