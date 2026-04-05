"""
US Market Follow Strategy — Skill-local version.

미국 증시 변동률을 기반으로 매매:
- backend의 us_market_data 모듈 대신 경량 HTTP 호출로 대체
- yfinance 미설치 환경에서도 동작하도록 Yahoo Finance JSON API 직접 호출
"""

from typing import Dict, Any, Optional
from datetime import datetime
import json
import urllib.request
import urllib.error
import logging

from .base import BaseStrategy, Side, customize_fields
from .martingale_base import MartingaleBase

logger = logging.getLogger(__name__)


# ── Lightweight US Market Data (replaces app.core.us_market_data) ──

def _fetch_us_change(index_symbol: str = "^GSPC") -> float:
    """Fetch previous day's change % from Yahoo Finance.

    Returns change as percentage (e.g., 1.5 for +1.5%).
    Returns 0.0 on any error.
    """
    try:
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{index_symbol}"
            f"?range=2d&interval=1d"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        # Filter None values
        valid = [c for c in closes if c is not None]
        if len(valid) >= 2:
            prev_close = valid[-2]
            last_close = valid[-1]
            change_pct = (last_close - prev_close) / prev_close * 100
            return round(change_pct, 2)
        return 0.0
    except Exception as e:
        logger.warning(f"Failed to fetch US market data for {index_symbol}: {e}")
        return 0.0


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
                "default": 1.0, "min": 0.1, "max": 10.0, "step": 0.1,
                "description": "미국 증시 변동률 임계값",
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
        self.us_index = self.config.get("us_index", "^GSPC")
        self.trigger_direction = self.config.get("trigger_direction", "above")
        self.us_change_threshold = float(self.config.get("us_change_threshold", 1.0))

        entry_start_str = self.config.get("entry_start_time", "09:00")
        try:
            self.entry_start_time = datetime.strptime(entry_start_str, "%H:%M").time()
        except ValueError:
            self.entry_start_time = datetime.strptime("09:00", "%H:%M").time()

        self._daily_date = None
        self._checked_today = False
        self._us_change_today = None
        self._trigger_met = False

    def _on_candle(self, data: Dict[str, Any]):
        current_time = self.context.get_time()
        current_date = current_time.date()

        if self._daily_date != current_date:
            self._daily_date = current_date
            self._checked_today = False
            self._us_change_today = None
            self._trigger_met = False

    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        if self._checked_today:
            return None

        current_time = self.context.get_time()
        current_time_only = current_time.time()

        if current_time_only < self.entry_start_time:
            return None

        if self._us_change_today is None:
            self._us_change_today = _fetch_us_change(self.us_index)
            self.context.log(f"[UsMarketFollow] US {self.us_index} change: {self._us_change_today:.2f}%")

        self._checked_today = True

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

        return Side.LONG if self._trigger_met else None

    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        return False

    @property
    def _log_prefix(self) -> str:
        return "UsMarketFollow"

    @property
    def _strategy_id(self) -> str:
        return "us_market_follow"

    def get_state(self) -> Dict[str, Any]:
        state = super().get_state()
        state["us_index"] = self.us_index
        state["us_change_today"] = self._us_change_today
        state["us_change_threshold"] = self.us_change_threshold
        state["trigger_direction"] = self.trigger_direction
        state["trigger_met"] = self._trigger_met
        state["checked_today"] = self._checked_today
        state["entry_start_time"] = self.config.get("entry_start_time", "09:00")
        return state
