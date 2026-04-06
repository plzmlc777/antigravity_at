"""
[샘플] Spot-Futures Hedge Strategy — 현선물 헤지 (Cash-and-Carry Arbitrage).

난이도: 특수 (선물+현물 듀얼 계정)
진입: 양수 펀딩비 > entry_threshold 시 현물 LONG + 선물 SHORT 동시 진입
청산: 펀딩비 정상화, 음수 전환, 최대 보유시간
포지션: 델타 뉴트럴 (시장 방향 무관, 펀딩비만 수취)

핵심 포인트:
- REQUIRES_FUTURES = True + REQUIRES_HEDGE = True (듀얼 계정 플래그)
- on_data() 완전 오버라이드
- set_hedge_coordinator()로 LiveManager가 HedgeCoordinator 주입
- HedgeCoordinator가 현물/선물 동시 주문 실행 관리
- spot_account_id / futures_account_id 파라미터로 계정 지정
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base import BaseStrategy, IContext
from .martingale_base import MartingaleBase


class SpotFuturesHedgeStrategy(MartingaleBase):
    """
    Cash-and-Carry Arbitrage: Spot Long + Futures Short.
    델타 뉴트럴로 펀딩비만 수취.
    """

    REQUIRES_FUTURES = True
    REQUIRES_HEDGE = True  # ★ 듀얼 계정 필수 (현물 + 선물)

    PARAMETER_SCHEMA = {
        "fields": [
            {"name": "entry_rate_threshold", "type": "number", "label": "Entry Rate (%)",
             "default": 0.05, "min": 0.001, "max": 1.0, "step": 0.001,
             "description": "Open hedge when funding rate exceeds this %",
             "group": "trigger", "show_in_table": True},
            {"name": "exit_rate_threshold", "type": "number", "label": "Exit Rate (%)",
             "default": 0.01, "min": 0.0, "max": 0.5, "step": 0.001,
             "description": "Close hedge when funding rate drops below this %",
             "group": "trigger", "show_in_table": True},
            {"name": "hedge_size_pct", "type": "number", "label": "Hedge Size (%)",
             "default": 50.0, "min": 10, "max": 100, "step": 5,
             "description": "% of capital for each leg",
             "group": "common", "show_in_table": True},
            {"name": "spot_account_id", "type": "number", "label": "Spot Account ID",
             "default": 0, "min": 0, "max": 9999, "step": 1,
             "description": "Exchange account ID for spot leg",
             "group": "hedge", "show_in_table": False},
            {"name": "futures_account_id", "type": "number", "label": "Futures Account ID",
             "default": 0, "min": 0, "max": 9999, "step": 1,
             "description": "Exchange account ID for futures leg",
             "group": "hedge", "show_in_table": False},
        ] + BaseStrategy.COMMON_PARAMETER_FIELDS
    }

    def _initialize_trigger(self):
        self.entry_rate = self.config.get("entry_rate_threshold", 0.05) / 100
        self.exit_rate = self.config.get("exit_rate_threshold", 0.01) / 100
        self.hedge_size_pct = self.config.get("hedge_size_pct", 50.0) / 100
        self._is_hedged = False
        self._entry_time: Optional[datetime] = None
        self._entry_funding_rate: float = 0
        self._total_funding_collected: float = 0
        self._hedge_coordinator = None  # LiveManager가 주입

    def set_hedge_coordinator(self, coordinator):
        """★ LiveManager가 호출하여 HedgeCoordinator 주입."""
        self._hedge_coordinator = coordinator

    def on_data(self, data: Dict[str, Any]):
        """on_data 완전 오버라이드."""
        symbol = data.get("symbol", self.symbol)
        current_price = data.get("close", 0)
        if current_price <= 0:
            return
        futures_data = self.context.get_futures_data(symbol)
        funding_rate = futures_data.get("funding_rate", 0)
        if self._is_hedged:
            self._check_exit(symbol, current_price, funding_rate)
        else:
            self._check_entry(symbol, current_price, funding_rate)

    def _check_entry(self, symbol: str, price: float, funding_rate: float):
        """양수 펀딩비 > threshold 시 헤지 오픈."""
        if funding_rate < self.entry_rate:
            return
        if not self._hedge_coordinator:
            self.context.log("[Hedge] ERROR: No HedgeCoordinator configured")
            return
        self._is_hedged = True
        self._entry_time = self.context.get_time()
        self._entry_funding_rate = funding_rate

    def _check_exit(self, symbol: str, price: float, funding_rate: float):
        should_exit = False
        reason = ""
        if funding_rate < self.exit_rate:
            should_exit, reason = True, f"rate_normalized ({funding_rate*100:.4f}%)"
        if not should_exit and funding_rate < 0:
            should_exit, reason = True, f"rate_negative ({funding_rate*100:.4f}%)"
        if not should_exit and self.max_hold_hours > 0 and self._entry_time:
            elapsed = (self.context.get_time() - self._entry_time).total_seconds() / 3600
            if elapsed >= self.max_hold_hours:
                should_exit, reason = True, f"max_hold ({elapsed:.1f}h)"
        if should_exit:
            self._is_hedged = False
            self._entry_time = None

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        return None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return False

    @property
    def _log_prefix(self) -> str:
        return "SpotFuturesHedge"

    @property
    def _strategy_id(self) -> str:
        return "spot_futures_hedge"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["is_hedged"] = self._is_hedged
        state["entry_funding_rate"] = self._entry_funding_rate
        state["total_funding_collected"] = self._total_funding_collected
        return state
