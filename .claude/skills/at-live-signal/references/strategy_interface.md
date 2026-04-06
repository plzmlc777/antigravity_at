# Strategy Interface Guide

AI가 새 전략을 만들 때 참고하는 인터페이스 규약.

## 상속 구조

```
BaseStrategy (base.py)          ← 최상위 추상 클래스
  └── MartingaleBase (martingale_base.py)  ← 포지션 관리/트레일링/마틴게일
        ├── RsiMartingaleStrategy
        ├── DipMartingaleStrategy
        ├── EmaMomentumStrategy
        ├── TimeMomentumStrategy
        ├── ChartPatternStrategy
        ├── FundingRateArbStrategy
        ├── SpotFuturesHedgeStrategy
        └── UsMarketFollowStrategy
  └── NoOpStrategy               ← 스킬 전용 (빈 전략)
```

## MartingaleBase 서브클래스 작성법 (가장 일반적)

### 필수 구현 메서드

```python
class MyStrategy(MartingaleBase):

    PARAMETER_SCHEMA = {
        "fields": [
            # 전략 고유 파라미터 정의
            {"name": "my_param", "type": "number", "label": "My Param",
             "default": 10, "min": 1, "max": 100, "step": 1,
             "description": "설명", "show_in_table": True,
             "defaultOptRange": "5, 10, 15, 20"},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS  # 공통 필드 반드시 추가
    }

    def _initialize_trigger(self):
        """전략 초기화. config에서 파라미터 로드."""
        self.my_param = float(self.config.get("my_param", 10))

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """L1 진입 조건. Side.LONG / Side.SHORT / None 반환."""
        if some_condition:
            return Side.LONG
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """L2+ 추가 진입 조건. True/False 반환."""
        return False

    @property
    def _log_prefix(self) -> str:
        return "MyStrategy"

    @property
    def _strategy_id(self) -> str:
        return "my_strategy"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["my_param"] = self.my_param
        return state
```

### 선택적 오버라이드 메서드

```python
    def _on_candle(self, data: Dict[str, Any]):
        """캔들마다 호출 (트리거 체크 전). 지표 업데이트에 사용."""
        pass

    def preload_history(self, candles: list):
        """히스토리 캔들로 지표 워밍업. 라이브 시작 전 호출."""
        pass

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        """커스텀 청산 조건. True 반환 시 포지션 청산."""
        return False
```

## PARAMETER_SCHEMA 필드 타입

| type | 설명 | 추가 속성 |
|------|------|----------|
| `number` | 숫자 입력 | min, max, step |
| `select` | 드롭다운 | options: ["a", "b"] |
| `multiselect` | 복수 선택 | options: ["a", "b", "c"] |
| `time` | 시간 입력 | (HH:MM 형식) |
| `combobox` | 텍스트+선택 | options: ["a", "b"] |

### 공통 속성
- `name`: 파라미터 키 (config에서 읽을 이름)
- `label`: UI 표시명
- `default`: 기본값
- `description`: 설명
- `show_in_table`: 목록 테이블에 표시 여부
- `defaultOptRange`: 최적화 범위 (쉼표 구분)
- `group`: 파라미터 그룹명
- `visible_when`: 조건부 표시 (예: `{"position_side": {"ne": "short"}}`)

## 사용 가능한 context 메서드 (IContext)

```python
context.buy(symbol, quantity, price=0, on_filled=callback)   # 매수
context.sell(symbol, quantity, price=0, on_filled=callback)   # 매도
context.short(symbol, quantity, price=0, on_filled=callback)  # 숏 진입
context.close_position(symbol, quantity, price=0, on_filled=callback)  # 숏 청산
context.get_price(symbol)          # 현재가
context.get_balance()              # 잔고
context.get_total_equity()         # 총 자산
context.get_holdings()             # 보유 종목
context.get_futures_data(symbol)   # 선물 데이터 (funding rate 등)
context.log(message)               # 로그 출력
```

## data (캔들) 구조

```python
data = {
    "open": 100.0,
    "high": 105.0,
    "low": 98.0,
    "close": 103.0,
    "volume": 1000.0,
    "timestamp": "2026-04-04T17:00:00+09:00"
}
```

## Side 상수

```python
from app.core.constants import Side

Side.LONG   # "long"
Side.SHORT  # "short"
```

## 전략 등록 (strategy_registry.py)

새 전략 파일 생성 후 레지스트리에 등록 필요:
```python
# backend/app/core/strategy_registry.py
STRATEGY_MAP = {
    "my_strategy": ("app.strategies.my_strategy", "MyStrategy"),
    ...
}
```

## 전략 난이도별 분류

| 난이도 | 전략 | 특징 |
|--------|------|------|
| 쉬움 | dip_martingale | 단순 가격 비교, 파라미터 2개 |
| 보통 | rsi_martingale | 지표 계산 + 크로스오버 감지 |
| 보통 | ema_momentum | EMA 계산 + 골든/데드 크로스 |
| 보통 | time_momentum | 시간 기반 + 일일 리셋 |
| 보통 | us_market_follow | 외부 데이터(미국 지수) 연동 |
| 어려움 | chart_pattern | 복합 패턴 인식 알고리즘 |
| 특수 | funding_rate_arb | 선물 전용, on_data 오버라이드 |
| 특수 | spot_futures_hedge | 선물+현물 헤지, 듀얼 계정 |
