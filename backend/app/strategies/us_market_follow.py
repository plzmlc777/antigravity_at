from typing import Dict, Any, Optional
from .base import BaseStrategy, customize_fields
from .martingale_base import MartingaleBase
from app.core.us_market_data import us_market


class UsMarketFollowStrategy(MartingaleBase):
    """
    US Market Follow Strategy

    미국 증시 변동률을 기반으로 한국 주식 매매:
    - 매수 조건: 전일 미국 증시가 N% 이상 변동 시 한국 장 시작에 매수
    - 매도 조건: 목표 수익률 달성 또는 최대 보유 시간 경과 시 매도
    - trailing stop, stop loss는 MartingaleBase 기본 기능 활용
    """

    PARAMETER_SCHEMA = {
        "fields": [
            {
                "name": "us_index",
                "type": "combobox",
                "label": "US Index",
                "default": "^GSPC",
                "options": [
                    {"value": "^GSPC", "label": "S&P 500"},
                    {"value": "^IXIC", "label": "NASDAQ"},
                    {"value": "^DJI", "label": "DOW"},
                    {"value": "^SOX", "label": "Philadelphia Semi"},
                ],
                "description": "기준이 되는 미국 지수 (Yahoo Finance 심볼 직접 입력 가능)",
                "show_in_table": True,
            },
            {
                "name": "trigger_direction",
                "type": "select",
                "label": "Trigger Direction",
                "default": "above",
                "options": [
                    {"value": "above", "label": "상승 (Above)"},
                    {"value": "below", "label": "하락 (Below)"},
                ],
                "description": "above=미국 상승 시 매수, below=미국 하락 시 매수",
                "show_in_table": True,
            },
            {
                "name": "us_change_threshold",
                "type": "number",
                "label": "US Change Threshold (%)",
                "default": 1.0,
                "min": 0.1,
                "max": 10.0,
                "step": 0.1,
                "description": "미국 증시 변동률 임계값 (n1)",
                "show_in_table": True,
                "defaultOptRange": "0.5, 1.0, 1.5, 2.0",
            },
            {
                "name": "entry_start_time",
                "type": "time",
                "label": "Entry Start Time",
                "default": "09:00",
                "description": "매수 시작 시간 (한국 시간)",
                "show_in_table": True,
            },
        ] + customize_fields(BaseStrategy.COMMON_PARAMETER_FIELDS, {
            "max_buy_count": {"default": 1},
            "last_level_allin": {"default": "on"},
            "trailing_start_percent": {"default": 2.0, "defaultOptRange": "1.0, 2.0, 3.0, 5.0"},
            "trailing_stop_percent": {"default": 1.0, "defaultOptRange": "0.5, 1.0, 1.5, 2.0"},
            "max_loss_percent": {"default": 3.0, "defaultOptRange": "2.0, 3.0, 5.0"},
            "cycle_max_hours": {"default": 6, "defaultOptRange": "2, 4, 6, 8"},
        })
    }

    def _initialize_trigger(self):
        """Initialize strategy parameters from config."""
        self.us_index = self.config.get("us_index", "^GSPC")
        self.trigger_direction = self.config.get("trigger_direction", "above")
        self.us_change_threshold = float(self.config.get("us_change_threshold", 1.0))

        # Parse entry start time
        entry_start_str = self.config.get("entry_start_time", "09:00")

        from datetime import datetime
        try:
            self.entry_start_time = datetime.strptime(entry_start_str, "%H:%M").time()
        except ValueError:
            self.entry_start_time = datetime.strptime("09:00", "%H:%M").time()

        # Daily state
        self._daily_date = None
        self._checked_today = False
        self._us_change_today = None
        self._trigger_met = False

        # For backtest: preload US change map
        self._us_change_map = None

    def preload_history(self, candles: list):
        """Preload US market change map for backtest."""
        # Load 1 year of US market data for backtest lookups
        self._us_change_map = us_market.get_change_map(self.us_index, days=365)

    def _get_us_change(self) -> float:
        """Get US market change for trading decision."""
        current_time = self.context.get_time()

        if self._us_change_map:
            # Backtest mode: lookup from preloaded map
            return us_market.get_change_for_date(
                current_time.strftime("%Y-%m-%d"),
                self._us_change_map
            )
        else:
            # Live mode: get real-time data
            return us_market.get_change(self.us_index)

    def _on_candle(self, data: Dict[str, Any]):
        """Daily reset and US change capture."""
        current_time = self.context.get_time()
        current_date = current_time.date()

        # Daily reset
        if self._daily_date != current_date:
            self._daily_date = current_date
            self._checked_today = False
            self._us_change_today = None
            self._trigger_met = False

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Check if US market change meets threshold at market open.
        Entry allowed after entry_start_time (exit controlled by cycle_max_hours).
        """
        if self._checked_today:
            return None

        current_time = self.context.get_time()
        current_time_only = current_time.time()

        # Check if past entry start time
        if current_time_only < self.entry_start_time:
            return None

        # Get US market change (captures once per day)
        if self._us_change_today is None:
            self._us_change_today = self._get_us_change()
            self.context.log(f"[UsMarketFollow] US {self.us_index} change: {self._us_change_today:.2f}%")

        # Mark as checked
        self._checked_today = True

        # Check if threshold is met based on direction
        us_change = self._us_change_today
        threshold = self.us_change_threshold

        if self.trigger_direction == "above":
            self._trigger_met = us_change >= threshold
        elif self.trigger_direction == "below":
            self._trigger_met = us_change <= -threshold

        if self._trigger_met:
            self.context.log(
                f"[UsMarketFollow] Trigger met! US change {us_change:.2f}% "
                f"(threshold: {threshold}%, direction: {self.trigger_direction})"
            )

        return "long" if self._trigger_met else None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """No additional entries for this strategy (single entry per day)."""
        return False

    @property
    def _log_prefix(self) -> str:
        return "UsMarketFollow"

    @property
    def _strategy_id(self) -> str:
        return "us_market_follow"

    def get_state(self) -> Dict[str, Any]:
        """Return current strategy state for UI display."""
        state = super().get_state()

        # Add US market specific state
        state["us_index"] = self.us_index
        state["us_change_today"] = self._us_change_today
        state["us_change_threshold"] = self.us_change_threshold
        state["trigger_direction"] = self.trigger_direction
        state["trigger_met"] = self._trigger_met
        state["checked_today"] = self._checked_today
        state["entry_start_time"] = self.config.get("entry_start_time", "09:00")

        return state
