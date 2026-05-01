"""
Crypto 전략 mini-Base (Binance USDT-M Futures).

KrStrategyBase의 mirror — 24/7 시장이라 EOD 개념 없음, futures 수수료 사용.
"""
from typing import Any, ClassVar, Dict, Optional


class CryptoStrategyBase:
    """
    Crypto 전략 베이스. 모든 multi-TF crypto 전략은 이 클래스를 상속한다.

    필수 override:
      - on_data(candle): dict 형식 candle을 받아 매매 의사결정.

    선택 override:
      - initialize(): 시작 시 1회 (warmup, signal precompute).
      - name: 클래스 변수, 기본 = 클래스 이름.

    파라미터:
      - DEFAULT_PARAMS: 클래스 변수 dict, 기본 파라미터.
      - PARAMETER_SCHEMA: optional dict.
      - TIMEFRAME: '1m' | '5m' | '15m' | '30m' | '60m' | '1d'.
    """

    name: ClassVar[str] = "base"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {}
    PARAMETER_SCHEMA: ClassVar[Optional[Dict[str, Any]]] = None
    TIMEFRAME: ClassVar[str] = "5m"

    def __init__(self, context, config: Dict[str, Any] = None):
        self.ctx = context
        merged = dict(self.DEFAULT_PARAMS)
        merged.update(config or {})
        self.config = merged
        self.symbol: str = self.config.get("symbol", "")
        self.position_open: bool = False
        self.entry_price: Optional[float] = None
        self.entry_time: Optional[str] = None

    def initialize(self) -> None:
        pass

    def on_data(self, candle: Dict[str, Any]) -> None:
        raise NotImplementedError

    # ─── helpers ───
    def _has_position(self) -> bool:
        # crypto context: holdings stores (qty in base asset). qty>0 = long.
        return float(self.ctx.holdings.get(self.symbol, 0)) > 0

    def _quantity_for_capital_pct(self, price: float, pct: float) -> float:
        """Return float quantity in base asset (e.g. BTC) using `pct` of cash.

        Crypto allows fractional position sizes; integer rounding (KR) NOT applied.
        Fee is already taken into account in CryptoBacktestContext.buy.
        """
        from ..core.crypto_backtest_engine import CRYPTO_TAKER_FEE
        cash = self.ctx.cash * float(pct)
        if price <= 0:
            return 0.0
        return cash / (price * (1 + CRYPTO_TAKER_FEE))
