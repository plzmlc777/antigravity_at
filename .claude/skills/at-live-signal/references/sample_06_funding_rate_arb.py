"""
[샘플] Funding Rate Arbitrage Strategy — 선물 펀딩비 차익거래.

난이도: 특수 (선물 전용)
진입: |funding_rate| > entry_threshold 시 반대 포지션
  - 양수 펀딩비 → SHORT (숏이 수수료 수취)
  - 음수 펀딩비 → LONG (롱이 수수료 수취)
청산: 펀딩비 정상화, 방향 반전, 최대보유시간, 최대손실
LONG/SHORT: Both (펀딩비 방향에 따라)

핵심 포인트:
- REQUIRES_FUTURES = True (선물 거래소 전용)
- on_data() 완전 오버라이드 — MartingaleBase 트리거 시스템 미사용
- context.get_futures_data(symbol)로 펀딩비 조회
- context.short(), context.close_position() 직접 호출
- _check_entry_trigger, _check_additional_trigger는 빈 구현 (on_data 직접 관리)
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base import BaseStrategy, IContext
from .martingale_base import MartingaleBase


class FundingRateArbStrategy(MartingaleBase):
    """
    Funding Rate Arbitrage — 펀딩비 수취를 위한 단방향 선물 포지션.
    on_data()를 완전 오버라이드하여 자체 진입/청산 로직 사용.
    """

    REQUIRES_FUTURES = True  # ★ 선물 거래소 필수 플래그

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "entry_rate_threshold", "type": "number", "label": "Entry Rate (%)",
             "default": 0.03, "min": 0.001, "max": 1.0, "step": 0.001,
             "description": "Enter when |funding_rate| exceeds this %",
             "group": "trigger", "show_in_table": True},
            {"name": "exit_rate_threshold", "type": "number", "label": "Exit Rate (%)",
             "default": 0.005, "min": 0.0, "max": 0.5, "step": 0.001,
             "description": "Exit when |funding_rate| drops below this %",
             "group": "trigger", "show_in_table": True},
            {"name": "position_size_pct", "type": "number", "label": "Position Size (%)",
             "default": 50.0, "min": 5, "max": 100, "step": 5,
             "description": "% of capital to use",
             "group": "common", "show_in_table": True},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        self.entry_rate = self.config.get("entry_rate_threshold", 0.03) / 100
        self.exit_rate = self.config.get("exit_rate_threshold", 0.005) / 100
        self.position_size_pct = self.config.get("position_size_pct", 50.0) / 100
        self._position_side: Optional[str] = None
        self._entry_price: float = 0
        self._entry_time: Optional[datetime] = None
        self._position_qty: float = 0

    def on_data(self, data: Dict[str, Any]):
        """★ on_data 완전 오버라이드 — MartingaleBase.on_data() 호출하지 않음."""
        symbol = data.get("symbol", self.symbol)
        current_price = data.get("close", 0)
        if current_price <= 0:
            return
        # ★ 선물 데이터에서 펀딩비 조회
        futures_data = self.context.get_futures_data(symbol)
        funding_rate = futures_data.get("funding_rate", 0)

        if self._position_side:
            self._check_exit(symbol, current_price, funding_rate, futures_data)
        else:
            self._check_entry(symbol, current_price, funding_rate)

    def _check_entry(self, symbol: str, price: float, funding_rate: float):
        if abs(funding_rate) < self.entry_rate:
            return
        initial_capital = getattr(self.context, 'initial_capital', 10000)
        qty = (initial_capital * self.position_size_pct) / price
        if qty <= 0:
            return
        if funding_rate > 0:
            # 양수 펀딩비 → SHORT (숏이 수취)
            result = self.context.short(symbol, qty, metadata={"reason": "funding_arb"})
            if result.get("status") != "failed":
                self._position_side = "SHORT"
                self._entry_price = price
                self._entry_time = self.context.get_time()
                self._position_qty = qty
        else:
            # 음수 펀딩비 → LONG (롱이 수취)
            result = self.context.buy(symbol, int(qty) if qty >= 1 else qty,
                                      metadata={"reason": "funding_arb"})
            if result.get("status") != "failed":
                self._position_side = "LONG"
                self._entry_price = price
                self._entry_time = self.context.get_time()
                self._position_qty = qty

    def _check_exit(self, symbol: str, price: float, funding_rate: float, futures_data: Dict):
        should_exit = False
        reason = ""
        # 1. 펀딩비 정상화
        if abs(funding_rate) < self.exit_rate:
            should_exit, reason = True, f"rate_normalized ({funding_rate*100:.4f}%)"
        # 2. 방향 반전
        if not should_exit:
            if self._position_side == "SHORT" and funding_rate < -self.entry_rate:
                should_exit, reason = True, f"rate_reversed ({funding_rate*100:.4f}%)"
            elif self._position_side == "LONG" and funding_rate > self.entry_rate:
                should_exit, reason = True, f"rate_reversed ({funding_rate*100:.4f}%)"
        # 3. 최대 보유 시간
        if not should_exit and self.max_hold_hours > 0 and self._entry_time:
            elapsed = (self.context.get_time() - self._entry_time).total_seconds() / 3600
            if elapsed >= self.max_hold_hours:
                should_exit, reason = True, f"max_hold ({elapsed:.1f}h)"
        # 4. 최대 손실
        if not should_exit and self._entry_price > 0:
            if self._position_side == "LONG":
                pnl_pct = (price - self._entry_price) / self._entry_price
            else:
                pnl_pct = (self._entry_price - price) / self._entry_price
            if pnl_pct <= -self.max_loss_pct:
                should_exit, reason = True, f"max_loss ({pnl_pct*100:.2f}%)"

        if should_exit:
            self.context.close_position(symbol, metadata={"reason": reason})
            self._position_side = None
            self._entry_price = 0
            self._entry_time = None
            self._position_qty = 0

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        return None  # on_data 직접 관리

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return False  # on_data 직접 관리

    @property
    def _log_prefix(self) -> str:
        return "FundingArb"

    @property
    def _strategy_id(self) -> str:
        return "funding_rate_arb"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["position_side"] = self._position_side or "NONE"
        state["arb_entry_price"] = self._entry_price
        state["arb_position_qty"] = self._position_qty
        return state
