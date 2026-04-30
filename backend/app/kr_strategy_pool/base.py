"""
KR 전략 mini-Base.

production BaseStrategy(외부 strategies/base.py)와 호환되도록 인터페이스 일치
(initialize / on_data). KrBacktestEngine은 strategy_class를 인자로 받아
context와 config로 인스턴스화 → initialize() → 매 candle마다 on_data()를 호출.

확장 시 production 전략으로 그대로 이식 가능.
"""
from typing import Any, ClassVar, Dict, Optional


class KrStrategyBase:
    """
    KR 전략 베이스. 모든 전략은 이 클래스를 상속한다.

    필수 override:
      - on_data(candle): dict 형식의 candle을 받아 매매 의사결정.

    선택 override:
      - initialize(): 시작 시 1회 (warmup 등).
      - name: 클래스 변수, 기본 = 클래스 이름.

    파라미터:
      - DEFAULT_PARAMS: 클래스 변수 dict, 기본 파라미터.
      - PARAMETER_SCHEMA: optional dict, validation/optimization 시 활용.
      - TIMEFRAME: 클래스 변수, '1m' | '5m' | '15m' | '30m' | '1d'.
        토너먼트 러너는 이 값을 보고 적절한 resample 데이터를 공급한다.
    """

    name: ClassVar[str] = "base"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {}
    PARAMETER_SCHEMA: ClassVar[Optional[Dict[str, Any]]] = None
    TIMEFRAME: ClassVar[str] = "5m"

    def __init__(self, context, config: Dict[str, Any] = None):
        self.ctx = context
        # config = DEFAULT_PARAMS overlaid with run-time overrides
        merged = dict(self.DEFAULT_PARAMS)
        merged.update(config or {})
        self.config = merged
        # strategy-local mutable state
        self.symbol: str = self.config.get("symbol", "")
        self.position_open: bool = False
        self.entry_price: Optional[float] = None
        self.entry_time: Optional[str] = None

    def initialize(self) -> None:
        """Called once before the first on_data call."""
        pass

    def on_data(self, candle: Dict[str, Any]) -> None:
        """Called once per candle. Override required."""
        raise NotImplementedError

    # ─── helpers ───
    def _has_position(self) -> bool:
        return self.ctx.holdings.get(self.symbol, 0) > 0

    def _quantity_for_full_capital(self, price: float) -> int:
        """Return integer share count that fully uses available cash (after fee)."""
        # buy fee 0.015% included → divide cash by price * 1.00015
        cash = self.ctx.cash
        from ..core.kr_backtest_engine import KR_BUY_FEE_RATE
        max_qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
        return max(0, max_qty)
