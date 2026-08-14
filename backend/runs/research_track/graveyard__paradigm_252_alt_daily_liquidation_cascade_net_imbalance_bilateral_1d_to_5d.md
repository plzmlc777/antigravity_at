# paradigm 252 GRAVEYARD

## 최종 판정

- **Verdict**: `R0_HALT_BY_SUBSTRATE_DISPATCH_IMPOSSIBLE_LESSON_28_LESSON_61_DUPLICATE_OF_PARADIGM_224`
- **Phase**: G0 SUBSTRATE AUDIT HALT (R-1 not dispatched)
- **Timestamp**: 2026-08-10 KST
- **Compute avoided**: ~40 min R-1 batch + ~30 min download not attempted

## 가설 요약

Per-symbol Binance USDT-M daily forced liquidation notional value (long+short) → 7d volume normalize → 90d z-score. z ≥ +T (T ∈ {1.0, 1.5, 2.0}) 발생일에 `sign(short_liq - long_liq)` 방향 축으로 4-quadrant bilateral SNT. hold 1d/3d/5d, BTCUSDT PoC, 14 alt 유니버스.

메커니즘: forced liquidation cascade → 유동성 이탈 및 오버슈트 → 1~5d 내 MM 재진입으로 평균회귀.

## G0 프리스크린 결과

### 1. Lesson #61 slug uniqueness — FAIL (강)

INDEX.json 및 그레이브야드 디렉토리에 이미 3개 liquidation 계열 파러다임이 존재:

| Slug | 상태 | Verdict |
|---|---|---|
| `paradigm_224_alt_binance_liq_asymmetry_forced_deleveraging_reversal_4h` | GRAVEYARD | R0 substrate 부재 |
| `liquidation_cascade_post_capitulation_alt_directional_30m_x_45m` | GRAVEYARD | 사전 결정 |
| `binance_perp_liquidation_cascade_event_alt_intraday` | GRAVEYARD | 사전 결정 |

paradigm 252 는 224 와 DNA 5/6 차원 중복:
- substrate 클래스: forced liquidation notional (동일)
- data source: Binance UM forced liquidation (동일 — historical 부재도 동일)
- 유니버스: 14 alt USDT perp (동일 계열)
- decision mode: 4-quadrant bilateral SNT (동일 원리)
- hold scale: 1440min cycle (224 는 4h, 252 는 1d — 단 하나의 차이)

→ 5/6 중복이므로 Lesson #61 halt 기준 충족.

### 2. Lesson #28 substrate dispatch feasibility — FAIL (확정)

**Binance Vision S3 실측 (2026-08-10 KST)**:

`data/futures/um/daily/` 하위 CommonPrefixes 전량:
```
aggTrades, bookDepth, bookTicker, indexPriceKlines, klines,
markPriceKlines, metrics, premiumIndexKlines, trades
```

→ `liquidationSnapshot/` **prefix 부재** (사용자 프롬프트가 가정한 경로는 존재하지 않음).

`data/futures/um/monthly/` 하위 전량:
```
aggTrades, bookTicker, fundingRate, indexPriceKlines, klines,
markPriceKlines, premiumIndexKlines, trades
```

→ monthly 계층에도 부재.

**직접 URL 프로브 (모두 HTTP 404)**:

| Date | Symbol | HTTP |
|---|---|---|
| 2026-01-01 | BTCUSDT | 404 |
| 2025-06-01 | BTCUSDT | 404 |
| 2025-01-01 | BTCUSDT | 404 |
| 2024-06-01 | BTCUSDT | 404 |
| 2024-01-01 | BTCUSDT | 404 |
| 2023-01-01 | BTCUSDT | 404 |
| 2022-06-01 | BTCUSDT | 404 |
| 2020-01-01 | BTCUSDT | 404 |
| 2026-01-01 | SOLUSDT | 404 |

**로컬 recorder 부재 확인**:
- `backend/runs/` 하위 liquidation/force 디렉토리: 0개
- Postgres `information_schema.tables` 에 liq/force 매칭 테이블: 0개
- `backend/scripts/research/` 에 liquidation recorder: 0개
- paradigm 224 에서 파일된 infrastructure task 224.1 (WS `!forceOrder@arr` recorder daemon) **아직 미시딩** → 60~90일 누적 창 부재.

**REST API 경로 (paradigm 224 이미 검증)**:
- `/fapi/v1/forceOrders` — user-scoped, 401
- `/fapi/v1/allForceOrders` — deprecated, 404
- WS `!forceOrder@arr` — 실시간 전용, 회복 불가
- 3rd-party paid — `[[feedback-no-freemium-trial]]` 차단

→ 자유계층 free-tier 로 도달 가능한 ≥2년 market-wide forced liquidation per-side USD volume 스트림 **여전히 zero**.

### 3. paradigm 224 대비 신규 반증 없음

가설 형태(hold 4h → 1d, threshold sweep 세부) 만 다르고 substrate 병목은 동일. 224 이후 recorder 가 시딩되지 않은 상태에서 재발의는 정보 없는 반복.

## Lesson dogfoods

- **Lesson #28** — 7번째 operational CONFIRMED (R-0 halt by substrate; 224 후 첫 재발의)
- **Lesson #61** — slug/DNA 중복 5/6 halt 트리거 CONFIRMED (222 이후 첫 사례)
- **Lesson #77** — non-OHLCV substrate 이지만 datasource 자체 부재 → ESCAPE 조건 무효화 사례로 기록
- **Lesson #62** — DNA 5-dim 감사 5중복 → halt 확정
- **Lesson #30** — ADA exclusion 준수 (유니버스 미도달로 자동 준수)

## 후속 권장

**절대 재발의 금지 조건**:
- Binance Vision 이 `liquidationSnapshot/` prefix 를 신설하기 전까지, 또는
- Infrastructure task 224.1 (WS `!forceOrder@arr` recorder daemon) 이 시딩되어 최소 90일 누적을 완료하기 전까지

**재발의 가능 시점 판단 게이트 (모두 만족 필수)**:
1. `curl -sI https://data.binance.vision/data/futures/um/daily/liquidationSnapshot/BTCUSDT/BTCUSDT-liquidationSnapshot-YYYY-MM-DD.zip` → 200 OK (최소 2년 range 필요)
2. 또는 postgres `forced_liquidations` 테이블 존재 + row count ≥ 90d × ~500 events/day
3. Lesson #61 재검: 224 및 252 그레이브야드 명시 참조 후, 새 가설이 **decision mode 또는 time scale 차원 이상**에서 실질적으로 다른가 검증

**대체 가설 후보 (같은 forced-flow 아이디어를 다른 substrate 로 대체)**:
1. **premiumIndex 급락** — 만기 없는 perp 에서 premium index 순간 음전환은 forced 매도 압력의 대리지표. substrate CONFIRMED (Binance Vision `premiumIndexKlines/`).
2. **markPrice-lastPrice 스프레드 절대값 스파이크** — mark 는 index 로 앵커되므로 last 이탈은 forced order 캐스케이드의 인프린트. substrate CONFIRMED (Binance Vision `markPriceKlines/` + `klines/`).
3. **funding 실현치와 예측치 괴리 8h** — 급격한 forced deleveraging 은 funding accrual 을 왜곡. substrate CONFIRMED (`fundingRate/` monthly).

세 대체안 모두 non-OHLCV Lesson #77 escape 조건 준수, substrate 즉시 도달 가능, 그리고 paradigm 224/252 와 DNA ≥3 차원 이상 상이.

---

**Timestamp**: 2026-08-10 KST  
**Recorded by**: paradigm-architect (self-recommend cron dispatch)  
**Canonical audit JSON**: `backend/runs/research_track/paradigm_252_alt_daily_liquidation_cascade_net_imbalance_bilateral_1d_to_5d/g0_substrate_audit.json`
