# BTC Seasonal Strategy — Backtest-Ready Specification

**전략 ID**: `btc_seasonal_v1`
**대상 심볼**: `BTCUSDT` (Binance USDⓈ-M Perpetual, 1h 봉 기반)
**전략 분류**: 시즌성/시간대 기반 통계 차익 매매
**예상 신호 빈도**: 월 12~17건 (주 3~4건)
**예상 보유 기간**: 4시간 ~ 14일

---

## 진행 상태 (2026-04-29 업데이트)

- **시그널 1 (CME Gap Fill)**: 폐기 — 2022-2026 일봉 백테스트 결과 -28.83% (Sharpe -0.88). "갭은 메워진다" 통념이 이 기간엔 거짓. 반대 가설(Continuation) +27% 가능했지만 BTC Buy-and-Hold(+66%)에 명확히 미달 → 알파 없음 판정.
- **시그널 2 (Post-Macro Reversal)**: 미검증
- **시그널 3 (Time-of-Day Trend)**: 미검증

---

## 1. 전략 개요

3개의 독립 시그널을 OR 합성하고, 매크로 이벤트 필터로 차단:

```
EnterLong  = (CME_Gap_Fill_Long  OR  Post_Macro_Reversal_Long  OR  TOD_Trend_Long)
             AND  NOT  Macro_Blackout
             AND  Liquidity_OK

EnterShort = (CME_Gap_Fill_Short OR  Post_Macro_Reversal_Short OR  TOD_Trend_Short)
             AND  NOT  Macro_Blackout
             AND  Liquidity_OK
```

3개 시그널은 독립 PnL 추적 + 통합 리스크 한도(동시 보유 ≤ 2 포지션).

---

## 2. 시그널 1: CME Gap Fill

### 정의
- CME 비트코인 선물은 금 22:00 UTC ~ 일 23:00 UTC 휴장 (≈22h 갭)
- 휴장 동안 Spot/Perp 가격 변동분 = "Gap"
- 통계적으로 ~75%가 1~21일 내 메워짐

### 입력 데이터
| 필드 | 소스 | 설명 |
|---|---|---|
| `cme_close_friday` | 외부 (CME API or yfinance `BTC=F`) | 금요일 22:00 UTC 종가 |
| `cme_open_sunday` | 동일 | 일요일 23:00 UTC 시작가 |
| `binance_close_now` | 자체 OHLCV | 현재 BTCUSDT 종가 |

### 갭 계산
```python
gap_size = cme_open_sunday - cme_close_friday
gap_pct = gap_size / cme_close_friday

# Gap 종류
if gap_pct > 0:
    gap_type = "up_gap"      # 메우려면 가격 ↓ 필요 → SHORT 시그널
elif gap_pct < 0:
    gap_type = "down_gap"    # 메우려면 가격 ↑ 필요 → LONG 시그널
else:
    gap_type = "none"
```

### 진입 조건
**Down Gap → Long**:
```python
ENTER_LONG if (
    gap_type == "down_gap"
    AND abs(gap_pct) >= 0.005           # 0.5% 이상 갭만 거래
    AND abs(gap_pct) <= 0.05            # 5% 초과는 매크로 변동 → 제외
    AND age_hours <= 14*24              # 14일 내 미체결 갭만
    AND binance_close_now < cme_close_friday  # 현재가가 갭 위쪽 (메우는 방향 진입)
    AND distance_to_gap_pct >= 0.003    # 최소 0.3% 거리 남았을 때 진입
)
```

**Up Gap → Short**: 부호 반대로 동일.

### 청산 조건
```python
EXIT_LONG if (
    binance_close_now >= cme_close_friday        # 갭 메움 (TP)
    OR  binance_close_now <= entry_price * 0.97  # -3% 손절 (SL)
    OR  age_hours >= 14*24                       # 14일 만료 (Timeout)
)
```

### 사이즈
- 포지션 사이즈: 자본의 30%
- 레버리지: 2x (실효 노출 60%)

---

## 3. 시그널 2: Post-Macro Reversal

### 정의
FOMC/CPI 발표 직후 시장이 1차 과민 반응 → 1~3일 내 평균 회귀 패턴

### 입력 데이터
| 필드 | 소스 | 설명 |
|---|---|---|
| `macro_calendar` | 사전 정의된 CSV (직접 작성 또는 외부 API) | FOMC, CPI, NFP, PCE 발표 시각 (UTC) |
| `pre_event_close` | 자체 OHLCV | 이벤트 -1h 봉 종가 |
| `post_event_close` | 자체 OHLCV | 이벤트 +6h 봉 종가 |

### 매크로 캘린더 형식
```csv
event_time_utc,event_type
2026-05-01 18:00,FOMC
2026-05-13 12:30,CPI
2026-05-02 12:30,NFP
2026-05-30 12:30,PCE
...
```

### 진입 조건
이벤트 발표 +6h 시점에 평가:
```python
event_move_pct = (post_event_close - pre_event_close) / pre_event_close

# 과민 반응 감지
if event_move_pct <= -0.03:        # 3% 이상 급락 → Long 진입 (반전 베팅)
    ENTER_LONG
elif event_move_pct >= +0.03:      # 3% 이상 급등 → Short 진입
    ENTER_SHORT
else:
    NO_TRADE                       # 정상 반응 → 패스
```

추가 필터:
- 동일 방향 신호가 다른 시그널에서도 발생하면 사이즈 1.5x

### 청산 조건
```python
# Take Profit: 이벤트 직전 가격으로 회귀
EXIT if abs(current_close - pre_event_close) / pre_event_close < 0.005

# Stop Loss: 이벤트 후 추가 -2% 진행
EXIT if (long  AND current_close <= entry_price * 0.98)
EXIT if (short AND current_close >= entry_price * 1.02)

# Timeout: 72시간
EXIT if age_hours >= 72
```

### 사이즈
- 포지션 사이즈: 자본의 25%
- 레버리지: 2x

---

## 4. 시그널 3: Time-of-Day Trend

### 정의
13~16 UTC (유럽/미국 겹침) 변동성 최대 구간에서, 직전 4h 추세 방향 추종.

### 진입 조건
매일 13:00 UTC 봉 마감 시 평가:
```python
prior_4h_return = (close_at_13_utc - close_at_09_utc) / close_at_09_utc

# 거래량 조건 (직전 4h 거래량 > 30일 평균)
volume_4h = sum(volume from 09 UTC to 13 UTC)
avg_volume_4h_30d = mean(prior 30 days same window)

if (
    abs(prior_4h_return) >= 0.005          # 0.5% 이상 움직임
    AND volume_4h >= avg_volume_4h_30d * 1.2  # 거래량 우위
):
    if prior_4h_return > 0:
        ENTER_LONG
    else:
        ENTER_SHORT
```

### 청산 조건 (단기 매매)
```python
# Take Profit: 진입 후 +1.5%
# Stop Loss:   진입 후 -1.0%
# Timeout:     21:00 UTC 강제 청산 (당일 종료)
```

### 사이즈
- 포지션 사이즈: 자본의 20%
- 레버리지: 3x (실효 60%)

---

## 5. 전역 필터: Macro Blackout

다음 시간대엔 **모든 시그널 무시 + 기존 포지션 강제 축소**:

```python
BLACKOUT_WINDOWS = [
    # FOMC: 발표 -2h ~ +2h
    (event_time - 2h, event_time + 2h),
    # CPI: 발표 -30min ~ +30min
    (event_time - 0.5h, event_time + 0.5h),
    # NFP: 발표 -30min ~ +30min
    (event_time - 0.5h, event_time + 0.5h),
    # PCE: 발표 -30min ~ +30min
    (event_time - 0.5h, event_time + 0.5h),
]

if any(window contains current_time for window in BLACKOUT_WINDOWS):
    NEW_ENTRIES_BLOCKED = True
    EXISTING_POSITIONS = halve_size()  # 50%로 축소
```

**연간 차단 시간**: ~50시간 (전체의 0.6%) — 빈도 영향 미미하지만 Tail Risk 큰 폭 감소.

---

## 6. 전역 필터: Liquidity OK

```python
LIQUIDITY_OK = (
    binance_24h_volume_btcusdt >= 1_000_000_000  # $1B
    AND order_book_depth_2pct >= 5_000_000       # $5M
    AND bid_ask_spread <= 0.0002                  # 2bp
)
```

BTC는 거의 항상 통과. 비상시(거래소 장애, 플래시 크래시)에만 차단.

---

## 7. 리스크 관리

| 항목 | 한도 |
|---|---|
| 동시 보유 포지션 | ≤ 2개 |
| 단일 시그널 최대 손실 (per trade) | -3% (자본 대비 -1.5%~) |
| 일일 누적 손실 | -5% → 24h 거래 중단 |
| 주간 누적 손실 | -10% → 1주 거래 중단 |
| 최대 레버리지 | 3x |

**포지션 충돌 처리**:
- Long + Long → 같은 방향 누적 (한도 내)
- Long + Short → 새 시그널 무시 (먼저 들어온 포지션 우선)

---

## 8. 백테스트 명세

### 데이터
- **기간**: 2022-01-01 ~ 2026-04-29 (4년 4개월, 약 1,580일)
- **봉 단위**: 1h (BTCUSDT Binance Spot 또는 Perp)
- **추가 데이터**:
  - CME `BTC=F` 1h OHLC (yfinance)
  - 매크로 이벤트 캘린더 CSV (수동 작성)

### 비용 가정
| 항목 | 값 |
|---|---|
| 진입/청산 수수료 | 0.04% (Taker) × 2 = 0.08% per round trip |
| 슬리피지 | 0.02% (BTC는 충분히 깊음) |
| 펀딩비 | 평균 ±0.01%/8h 가정, 보유 기간만큼 누적 |

### 초기 자본
- $10,000 USDT

### 검증 메트릭
| 메트릭 | 목표 | 합격선 |
|---|---|---|
| Total Return (4년) | +50%+ | +20% |
| CAGR | +10%+ | +5% |
| Sharpe Ratio | 1.5+ | 1.0 |
| Max Drawdown | -20% 이하 | -30% |
| Win Rate | 55%+ | 50% |
| Profit Factor | 1.5+ | 1.2 |
| Avg Trade | +0.5%+ | +0.2% |
| 거래 빈도 | 월 12~17건 | 월 8~25건 |

### 시그널별 분리 평가
백테스트 결과를 **시그널별 PnL 곡선 분리**로 시각화:
- CME Gap 단독 PnL
- Macro Reversal 단독 PnL
- TOD Trend 단독 PnL
- 통합 PnL

→ 어느 시그널이 alpha 기여 최대인지 식별, 약한 시그널은 제거 또는 개선.

---

## 9. 구현 위치

### 파일 구조
```
backend/app/strategies/
├── base.py                          # 기존
├── btc_seasonal_v1.py               # 신규 ← 본 명세 구현
└── btc_seasonal_v1_helpers.py       # 신규 ← CME 데이터 로더, 매크로 캘린더

docs/
└── btc_seasonal_strategy_spec.md    # 본 문서

scripts/
└── fetch_cme_btc_data.py            # 신규 ← yfinance에서 BTC=F 1h 데이터 수집
└── macro_calendar_2022_2026.csv     # 신규 ← 4년치 매크로 이벤트 (수기 수집)
```

### Strategy 클래스 스켈레톤
```python
from .base import BaseStrategy
from typing import Dict, Any
from datetime import datetime, timedelta

class BtcSeasonalV1Strategy(BaseStrategy):

    PARAMETER_SCHEMA = {
        "cme_gap_min_pct":          {"type": "float", "default": 0.005},
        "cme_gap_max_pct":          {"type": "float", "default": 0.05},
        "cme_gap_timeout_days":     {"type": "int",   "default": 14},
        "cme_gap_stop_loss_pct":    {"type": "float", "default": 0.03},
        "macro_reversal_threshold": {"type": "float", "default": 0.03},
        "macro_blackout_fomc_h":    {"type": "float", "default": 2.0},
        "tod_entry_threshold":      {"type": "float", "default": 0.005},
        "tod_volume_multiplier":    {"type": "float", "default": 1.2},
        "leverage_cme":             {"type": "float", "default": 2.0},
        "leverage_macro":           {"type": "float", "default": 2.0},
        "leverage_tod":             {"type": "float", "default": 3.0},
        "size_cme_pct":             {"type": "float", "default": 0.30},
        "size_macro_pct":           {"type": "float", "default": 0.25},
        "size_tod_pct":             {"type": "float", "default": 0.20},
        "max_concurrent_positions": {"type": "int",   "default": 2},
        "daily_loss_limit_pct":     {"type": "float", "default": 0.05},
    }

    def initialize(self):
        # Load config params
        for k, spec in self.PARAMETER_SCHEMA.items():
            setattr(self, k, self.config.get(k, spec["default"]))

        # State
        self.positions = {}              # {signal_name: PositionInfo}
        self.cme_gaps_active = []        # [{open_time, gap_pct, target_price, ...}]
        self.daily_pnl = 0.0
        self.last_reset_date = None

        # Load external data
        self.cme_data = self._load_cme_data()         # DataFrame indexed by hour
        self.macro_events = self._load_macro_events() # DataFrame of events

    def on_data(self, data: Dict[str, Any]):
        ts = data['timestamp']
        close = data['close']

        # Reset daily counters at 00:00 UTC
        if self._is_new_day(ts):
            self.daily_pnl = 0.0

        # Daily loss limit check
        if self.daily_pnl <= -self.daily_loss_limit_pct:
            return  # No new entries today

        # Macro blackout check
        if self._in_macro_blackout(ts):
            self._reduce_positions(0.5)
            return

        # Liquidity check
        if not self._liquidity_ok(data):
            return

        # Manage existing positions (TP/SL/Timeout)
        self._manage_positions(close, ts)

        # New entry signals
        if len(self.positions) < self.max_concurrent_positions:
            self._check_cme_gap_signal(close, ts)
            self._check_macro_reversal_signal(close, ts)
            self._check_tod_trend_signal(close, ts, data)

    # --- Signal evaluators ---
    def _check_cme_gap_signal(self, close, ts):
        # See Section 2 logic
        ...

    def _check_macro_reversal_signal(self, close, ts):
        # See Section 3 logic
        ...

    def _check_tod_trend_signal(self, close, ts, data):
        # See Section 4 logic
        ...

    # --- Position management ---
    def _manage_positions(self, close, ts):
        for sig_name, pos in list(self.positions.items()):
            exit_reason = self._check_exit(pos, close, ts)
            if exit_reason:
                self._close_position(sig_name, close, exit_reason)

    # --- Helpers ---
    def _load_cme_data(self): ...
    def _load_macro_events(self): ...
    def _in_macro_blackout(self, ts): ...
    def _liquidity_ok(self, data): ...
    def _is_new_day(self, ts): ...
    def _reduce_positions(self, factor): ...
```

---

## 10. 실행 순서 (Roadmap)

### Phase 1: 데이터 준비 (1~2일)
1. `scripts/fetch_cme_btc_data.py` 작성 → yfinance로 BTC=F 1h 데이터 4년치 수집
2. `scripts/macro_calendar_2022_2026.csv` 수기 작성 (FOMC ~32회, CPI ~52회, NFP ~52회)
3. 자체 BTCUSDT 1h OHLCV 데이터 검증 (DB에 이미 있음 가정)

### Phase 2: 시그널 단일 백테스트 (3~5일)
1. CME Gap 시그널만 단독 구현 → 백테스트 → 결과 분석
2. Macro Reversal 시그널만 단독 → 백테스트 → 결과 분석
3. TOD Trend 시그널만 단독 → 백테스트 → 결과 분석
4. 각 시그널의 Sharpe, Max DD, Win Rate 측정

### Phase 3: 통합 + 리스크 관리 (2~3일)
1. 3개 시그널 통합한 `btc_seasonal_v1.py` 완성
2. Macro Blackout, Liquidity Filter 추가
3. 리스크 한도 (일일/주간 손실 제한) 추가
4. 통합 백테스트 → 검증 메트릭 비교

### Phase 4: Walk-Forward + Robustness (2~3일)
1. 2022-2024 In-Sample / 2025-2026 Out-of-Sample 분리 백테스트
2. 파라미터 민감도 분석 (각 임계값 ±20% 흔들기)
3. 시즌성 분석 (강세장/약세장/횡보장 구간별 PnL)

### Phase 5: SISDS 파이프라인 통합 (1~2일)
1. Sandbox stage 등록 → 자동 평가
2. 합격 시 Audition → Paper → Live 트랙 진입

---

## 11. 결정 포인트 (백테스트 후)

백테스트 완료 후 이 4가지 결정:

1. **시그널 채택/탈락**: 시그널별 단독 Sharpe < 0.5 면 제거
2. **파라미터 튜닝**: Walk-forward에서 OOS 성능이 IS 대비 50% 미만이면 과적합 의심
3. **사이즈 재배분**: 시그널별 Kelly Criterion으로 재계산
4. **Live 승격 여부**: Paper 30일 ROI > 0 + Sharpe > 1.0 시 Live 진입

---

## 12. 알려진 한계 / 리스크

| 리스크 | 대응 |
|---|---|
| CME Gap 통계는 BTC 강세장 (2020~2021) 데이터 편향 가능 | 약세장 구간 별도 평가 |
| 매크로 이벤트 캘린더 수동 작성 → 누락/오타 리스크 | 외부 API (Trading Economics 등) 연계 검토 |
| TOD 패턴은 시장 구조 변화 시 무력화 | 분기마다 통계 재검증 |
| BTC 외 알트 적용 시 Gap 패턴 약함 | 본 전략은 BTC 전용으로 제한 |
| 펀딩비 가정 (±0.01%) 평균치 → 강세장 +0.05% 시 과소평가 | 실제 펀딩비 historical 데이터로 정확 반영 |

---

## 13. 다음 작업 제안

이 명세 그대로 진행하려면:

**(A) 즉시 시작 가능한 작업**:
- `scripts/fetch_cme_btc_data.py` 구현
- `macro_calendar_2022_2026.csv` 수집 (FOMC + CPI는 fed.gov / bls.gov에서 공개)

**(B) 검토 필요 사항**:
- 매크로 이벤트 캘린더 데이터 소스 (수동 vs API)
- 펀딩비 historical 데이터 가용성
- Antigravity 백테스트 엔진이 외부 데이터(CME 가격) 주입 지원하는지 확인

**(C) 우선순위 결정**:
- Phase 2를 시그널 1개부터 시작하면 1주일 내 첫 결과 확인 가능
- 가장 공정성 높고 단순한 **CME Gap 단독**부터 시작 권장
