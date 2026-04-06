#!/usr/bin/env python3
"""
Trading Strategy Definitions (Standalone)
기존 BacktestEngine 전략들과 동일한 로직을 독립 실행 가능한 형태로 재현.

각 전략은 MartingaleStrategy를 상속하며, 4가지 메서드만 구현:
  - _initialize_trigger(): 전략 초기화
  - _check_entry_trigger(candle): L1 진입 시그널
  - _check_additional_trigger(candle): L2+ 추가매수 시그널
  - _check_exit_trigger(candle): 전략 기반 청산 시그널
"""

from abc import ABC, abstractmethod
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List


@dataclass
class Trade:
    """완료된 매매 사이클."""
    entry_time: datetime
    exit_time: datetime
    entries: List[Dict]          # [{"level": 1, "price": 100, "quantity": 10, "time": ...}]
    exit_price: float
    direction: str = "long"      # "long" or "short"
    total_quantity: float = 0
    average_price: float = 0
    pnl: float = 0               # 절대 손익
    pnl_pct: float = 0           # 손익률 (소수, e.g., 0.05 = 5%)
    holding_seconds: float = 0
    cycle_start_equity: float = 0


class MartingaleStrategy(ABC):
    """
    마틴게일 기반 전략 베이스 클래스.
    기존 MartingaleBase와 동일한 포지션 관리/청산 로직을 재현.
    """

    name: str = "base"

    # 기본 파라미터 (COMMON_PARAMETER_FIELDS와 동일)
    DEFAULT_CONFIG = {
        "max_buy_count": 4,
        "lot_size_multiplier": 2.0,
        # MartingaleBase.initialize() 내부 기본값과 동일 (PARAMETER_SCHEMA 표시값과 다름!)
        "trailing_start_percent": 0.01,
        "trailing_stop_percent": 0.003,
        "max_loss_percent": 0.10,
        "betting_strategy": "fixed",
        "safety_margin_percent": 1.0,
        "cycle_max_hours": 0,
        "qty_mode": "fixed",
        "base_quantity": 1,
        "last_level_allin": "off",
        "require_lower_price": "off",
        "additional_buy_mode": "trigger",
        "additional_buy_step": 2.0,
        "additional_buy_step_ref": "last_entry",
        "use_martingale": "on",
        "trailing_on_last_level": "off",
        "leverage": 1,
        "position_side": "long",
    }

    def __init__(self, config: Dict[str, Any] = None):
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

        # Position state
        self.current_level = 0
        self.total_quantity = 0.0
        self.average_price = 0.0
        self.entries: List[Dict] = []
        self.peak_price = 0.0
        self.trailing_active = False
        self.is_short = False
        self.cycle_start_time: Optional[datetime] = None
        self._cycle_start_equity: Optional[float] = None

        # Resolved base qty (for percent mode)
        self._resolved_base_qty: Optional[float] = None

    @abstractmethod
    def _initialize_trigger(self):
        """전략별 초기화."""
        pass

    @abstractmethod
    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        """L1 진입: "long", "short", 또는 None."""
        pass

    @abstractmethod
    def _check_additional_trigger(self, candle: Dict) -> bool:
        """L2+ 추가매수: True/False."""
        pass

    def _check_exit_trigger(self, candle: Dict) -> bool:
        """전략 기반 청산 (기본: 사용 안 함)."""
        return False

    def calculate_quantity(self, level: int, price: float, cash: float, initial_capital: float) -> float:
        """
        레벨별 수량 계산. API _calculate_quantity와 동일.
        - safety_margin_percent 차감
        - int() 절삭 (한국주식 Kiwoom 동일)
        - cash <= 0 시 0 반환 (API cash guard 동일)
        """
        cfg = self.config
        multiplier = cfg["lot_size_multiplier"]
        leverage = cfg.get("leverage", 1)
        safety_pct = cfg.get("safety_margin_percent", 1.0) / 100.0
        is_crypto = cfg.get("exchange_name", "Kiwoom") != "Kiwoom"

        if cfg["qty_mode"] == "percent":
            if self._resolved_base_qty is None:
                # API: session equity (cash + position value) 기반
                equity = initial_capital  # 백테스트 시작 시 cash = initial_capital
                buying_power = equity * leverage
                self._resolved_base_qty = buying_power * cfg["base_quantity"] / 100 / price
            base = self._resolved_base_qty
        else:
            base = cfg["base_quantity"]

        qty = base * (multiplier ** (level - 1))

        # last_level_allin (API 동일)
        if cfg["last_level_allin"] == "on" and level == cfg["max_buy_count"]:
            available = max(cash, 0)
            safety_reserve = available * safety_pct
            usable = available - safety_reserve
            max_qty = usable * leverage / price if price > 0 else 0
            qty = max(qty, max_qty)

        # Cash guard (API _calculate_quantity와 동일)
        if qty > 0 and price > 0:
            available_cash = max(cash, 0)
            if available_cash <= 0:
                return 0
            safety_reserve = available_cash * safety_pct
            max_affordable = int((available_cash - safety_reserve) * leverage / price)
            if not is_crypto:
                qty = int(qty)  # Kiwoom: 정수 수량
            if qty > max_affordable:
                qty = max_affordable

        return max(0, qty)

    def check_exits(self, current_price: float, current_time: datetime) -> Optional[str]:
        """
        청산 조건 확인. 기존 _check_exits와 동일.
        Returns: "trailing_stop", "max_loss", "cycle_timeout", None
        """
        if self.current_level == 0:
            return None

        cfg = self.config
        price_return = self._calc_price_return(current_price)

        # Equity-based return (API 엔진과 동일): position_profit / cycle_start_equity
        position_profit = self._calc_pnl(current_price)
        if self._cycle_start_equity and self._cycle_start_equity > 0:
            current_return = position_profit / self._cycle_start_equity
        else:
            total_investment = self.average_price * self.total_quantity
            current_return = position_profit / total_investment if total_investment > 0 else 0

        # 1. Cycle time limit
        if cfg["cycle_max_hours"] > 0 and self.cycle_start_time:
            elapsed = (current_time - self.cycle_start_time).total_seconds() / 3600
            if elapsed >= cfg["cycle_max_hours"]:
                return "cycle_timeout"

        # 2. Update peak price (profit-based, API 엔진과 동일)
        if self.is_short:
            current_peak_profit = self._calc_pnl(self.peak_price) if self.peak_price > 0 else 0
            if self.peak_price <= 0 or position_profit > current_peak_profit:
                self.peak_price = current_price
        else:
            current_peak_profit = (self.peak_price - self.average_price) * self.total_quantity if self.peak_price > 0 else 0
            if position_profit > current_peak_profit:
                self.peak_price = current_price

        # 3. Trailing stop
        trailing_on_last = cfg["trailing_on_last_level"] == "on"
        can_trail = (not trailing_on_last) or (self.current_level >= cfg["max_buy_count"])

        if can_trail:
            if not self.trailing_active:
                if price_return >= (cfg["trailing_start_percent"] / 100):
                    self.trailing_active = True
                    self.peak_price = current_price

            if self.trailing_active:
                # Check trailing trigger
                if self.is_short:
                    if self.peak_price > 0:
                        rise = (current_price - self.peak_price) / self.peak_price
                        if rise >= (cfg["trailing_stop_percent"] / 100):
                            return "trailing_stop"
                else:
                    if self.peak_price > 0:
                        drop = (self.peak_price - current_price) / self.peak_price
                        if drop >= (cfg["trailing_stop_percent"] / 100):
                            return "trailing_stop"

        # 4. Max loss (equity-based return, API 엔진과 동일)
        if cfg["max_loss_percent"] > 0 and current_return <= -(cfg["max_loss_percent"] / 100):
            return "max_loss"

        return None

    def _calc_price_return(self, current_price: float) -> float:
        """포지션 수익률 (소수). 기존과 동일."""
        if self.average_price == 0:
            return 0
        if self.is_short:
            return (self.average_price - current_price) / self.average_price
        return (current_price - self.average_price) / self.average_price

    def _calc_pnl(self, current_price: float) -> float:
        """절대 손익. 기존과 동일."""
        if self.is_short:
            return (self.average_price - current_price) * self.total_quantity
        return (current_price - self.average_price) * self.total_quantity

    def add_entry(self, level: int, price: float, quantity: float, time: datetime):
        """포지션에 진입 추가."""
        if self.current_level == 0:
            self.average_price = price
            self.total_quantity = quantity
            self.cycle_start_time = time
        else:
            # VWAP
            total_cost = self.average_price * self.total_quantity + price * quantity
            self.total_quantity += quantity
            self.average_price = total_cost / self.total_quantity if self.total_quantity > 0 else 0

        self.current_level = level
        self.entries.append({
            "level": level,
            "price": price,
            "quantity": quantity,
            "time": time,
        })

    def close_position(self, exit_price: float, exit_time: datetime) -> Trade:
        """포지션 청산 -> Trade 생성."""
        pnl = self._calc_pnl(exit_price)
        pnl_pct = self._calc_price_return(exit_price)
        holding_sec = (exit_time - self.cycle_start_time).total_seconds() if self.cycle_start_time else 0

        trade = Trade(
            entry_time=self.cycle_start_time or exit_time,
            exit_time=exit_time,
            entries=list(self.entries),
            exit_price=exit_price,
            direction="short" if self.is_short else "long",
            total_quantity=self.total_quantity,
            average_price=self.average_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_seconds=holding_sec,
            cycle_start_equity=self._cycle_start_equity or 0,
        )

        # Reset state
        self.current_level = 0
        self.total_quantity = 0
        self.average_price = 0
        self.entries = []
        self.peak_price = 0
        self.trailing_active = False
        self.is_short = False
        self.cycle_start_time = None
        self._cycle_start_equity = None
        self._resolved_base_qty = None

        return trade

    def _check_require_lower(self, current_price: float) -> bool:
        """require_lower_price 가드."""
        if self.config["require_lower_price"] != "on":
            return True
        if not self.entries:
            return True
        last_entry_price = self.entries[-1]["price"]
        if self.is_short:
            return current_price > last_entry_price
        return current_price < last_entry_price

    def _check_step_trigger(self, current_price: float) -> bool:
        """additional_buy_mode="step" 자동 추가매수. API 엔진과 동일."""
        cfg = self.config
        ref_mode = cfg["additional_buy_step_ref"]

        if ref_mode == "avg_price":
            ref_price = self.average_price
        elif ref_mode == "initial_entry":
            ref_price = self.entries[0]["price"] if self.entries else current_price
        else:  # last_entry
            ref_price = self.entries[-1]["price"] if self.entries else current_price

        if ref_price == 0:
            return False

        if self.is_short:
            move_pct = (current_price - ref_price) / ref_price * 100
        else:
            move_pct = (ref_price - current_price) / ref_price * 100

        # initial_entry 모드: 누적 스텝 (L2=1*step, L3=2*step, ...)
        if ref_mode == "initial_entry":
            required_move = cfg["additional_buy_step"] * self.current_level
        else:
            required_move = cfg["additional_buy_step"]

        return move_pct >= required_move


# =============================================================================
# Strategy Implementations
# =============================================================================


class DipMartingaleStrategy(MartingaleStrategy):
    """
    눌림목 마틴게일.
    L1: 캔들 하락률 >= dip_percent
    L2+: 캔들 하락률 >= level_gap_percent
    """
    name = "dip_martingale"

    STRATEGY_DEFAULTS = {
        "dip_percent": 1.0,
        "level_gap_percent": 2.0,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)

    def _initialize_trigger(self):
        pass

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        dip_pct = self.config["dip_percent"] / 100.0
        if candle["open"] > 0:
            drop = (candle["open"] - candle["close"]) / candle["open"]
            if drop >= dip_pct:
                return "long"
        return None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        gap_pct = self.config["level_gap_percent"] / 100.0
        if candle["open"] > 0:
            drop = (candle["open"] - candle["close"]) / candle["open"]
            return drop >= gap_pct
        return False


class EmaMomentumStrategy(MartingaleStrategy):
    """
    EMA 모멘텀.
    L1: Golden cross (fast > slow) -> long, Dead cross -> short
    Exit: 반대 크로스
    """
    name = "ema_momentum"

    STRATEGY_DEFAULTS = {
        "ema_fast_period": 9,
        "ema_slow_period": 21,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._ema_fast = None
        self._ema_slow = None
        self._prev_diff = None
        self._candle_count = 0
        self._close_history: List[float] = []
        self._trigger_armed = True

    def _initialize_trigger(self):
        self._ema_fast = None
        self._ema_slow = None
        self._prev_diff = None
        self._candle_count = 0
        self._close_history = []
        self._trigger_armed = True
        self._last_crossover = None

    def _update_emas(self, close: float):
        self._candle_count += 1
        self._close_history.append(close)

        fast_period = self.config["ema_fast_period"]
        slow_period = self.config["ema_slow_period"]

        # Fast EMA
        if self._candle_count >= fast_period:
            if self._ema_fast is None:
                self._ema_fast = sum(self._close_history[-fast_period:]) / fast_period
            else:
                factor = 2.0 / (fast_period + 1)
                self._ema_fast += factor * (close - self._ema_fast)

        # Slow EMA
        if self._candle_count >= slow_period:
            if self._ema_slow is None:
                self._ema_slow = sum(self._close_history[-slow_period:]) / slow_period
            else:
                factor = 2.0 / (slow_period + 1)
                self._ema_slow += factor * (close - self._ema_slow)

    def _get_crossover(self) -> Optional[str]:
        """Golden cross / Dead cross 판별."""
        if self._ema_fast is None or self._ema_slow is None:
            return None

        curr_diff = self._ema_fast - self._ema_slow
        result = None

        if self._prev_diff is not None:
            if self._prev_diff <= 0 and curr_diff > 0:
                result = "golden_cross"
            elif self._prev_diff >= 0 and curr_diff < 0:
                result = "dead_cross"

        self._prev_diff = curr_diff
        return result

    def _on_candle(self, candle: Dict):
        """Update EMA on every candle (backend _on_candle와 동일)."""
        self._update_emas(candle["close"])
        self._last_crossover = self._get_crossover()

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        # EMA is already updated by _on_candle()
        cross = self._last_crossover

        if cross == "golden_cross" and self._trigger_armed:
            self._trigger_armed = False
            return "long"
        if cross == "dead_cross" and self._trigger_armed:
            self._trigger_armed = False
            pos_side = self.config.get("position_side", "long")
            if pos_side in ("short", "both"):
                return "short"
        return None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        # EMA is already updated by _on_candle()
        cross = self._last_crossover
        if self.is_short:
            return cross == "dead_cross"
        return cross == "golden_cross"

    def _check_exit_trigger(self, candle: Dict) -> bool:
        # EMA is already updated by _on_candle()
        if self._ema_fast is None or self._ema_slow is None:
            return False
        curr_diff = self._ema_fast - self._ema_slow
        if self.is_short:
            return curr_diff > 0  # Golden cross -> exit short
        return curr_diff < 0      # Dead cross -> exit long


class RsiMartingaleStrategy(MartingaleStrategy):
    """
    RSI 마틴게일.
    L1: RSI가 trigger_level 기준 돌파 시 진입
    Re-arm: RSI가 reset_level 기준 회복 시 재활성화
    """
    name = "rsi_martingale"

    STRATEGY_DEFAULTS = {
        "rsi_period": 14,
        "trigger_level": 30,
        "trigger_direction": "below",
        "reset_level": 50,
        "reset_direction": "above",
        "short_trigger_level": 70,
        "short_trigger_direction": "above",
        "short_reset_level": 50,
        "short_reset_direction": "below",
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._close_history: List[float] = []
        self._rsi = 50.0
        self._prev_rsi = 50.0
        self._long_armed = True
        self._short_armed = True

    def _initialize_trigger(self):
        self._close_history = []
        self._rsi = 50.0
        self._prev_rsi = 50.0
        self._long_armed = True
        self._short_armed = True

    def _calc_rsi(self) -> float:
        period = self.config["rsi_period"]
        if len(self._close_history) < period + 1:
            return 50.0

        changes = []
        for i in range(-period, 0):
            changes.append(self._close_history[i] - self._close_history[i - 1])

        gains = sum(c for c in changes if c > 0)
        losses = sum(-c for c in changes if c < 0)

        avg_gain = gains / period
        avg_loss = losses / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _check_cross(self, prev_val: float, curr_val: float, level: float, direction: str) -> bool:
        if direction == "below":
            return prev_val >= level and curr_val < level
        else:  # above
            return prev_val <= level and curr_val > level

    def _on_candle(self, candle: Dict):
        """Update RSI + re-arm on every candle (backend _on_candle와 동일)."""
        self._close_history.append(candle["close"])
        self._prev_rsi = self._rsi
        self._rsi = self._calc_rsi()

        cfg = self.config

        # Re-arm logic (backend _on_candle lines 159-169)
        if not self._long_armed:
            if self._check_cross(self._prev_rsi, self._rsi, cfg["reset_level"], cfg["reset_direction"]):
                self._long_armed = True

        if not self._short_armed:
            if self._check_cross(self._prev_rsi, self._rsi, cfg["short_reset_level"], cfg["short_reset_direction"]):
                self._short_armed = True

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        # RSI is already updated by _on_candle() — no duplicate update here
        if self._rsi < 0 or self._prev_rsi < 0:
            return None

        cfg = self.config
        pos_side = cfg.get("position_side", "long")

        # Long trigger
        if pos_side in ("long", "both") and self._long_armed:
            if self._check_cross(self._prev_rsi, self._rsi, cfg["trigger_level"], cfg["trigger_direction"]):
                self._long_armed = False
                return "long"

        # Short trigger
        if pos_side in ("short", "both") and self._short_armed:
            if self._check_cross(self._prev_rsi, self._rsi, cfg["short_trigger_level"], cfg["short_trigger_direction"]):
                self._short_armed = False
                return "short"

        return None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        # RSI is already updated by _on_candle()
        if self._rsi < 0 or self._prev_rsi < 0:
            return False

        cfg = self.config
        if self.is_short:
            if not self._short_armed:
                return False
            if self._check_cross(self._prev_rsi, self._rsi, cfg["short_trigger_level"], cfg["short_trigger_direction"]):
                self._short_armed = False
                return True
        else:
            if not self._long_armed:
                return False
            if self._check_cross(self._prev_rsi, self._rsi, cfg["trigger_level"], cfg["trigger_direction"]):
                self._long_armed = False
                return True
        return False


class TimeMomentumStrategy(MartingaleStrategy):
    """
    시간대 모멘텀.
    매일 start_time에 기준가 설정 -> delay_minutes 후 변동률 체크 -> 진입
    stop_time에 강제 청산.
    """
    name = "time_momentum"

    STRATEGY_DEFAULTS = {
        "start_time": "09:00",
        "stop_time": "15:00",
        "delay_minutes": 10,
        "direction": "rise",
        "target_percent": 2.0,
        "max_buy_count": 1,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._checked_today = False
        self._daily_ref_price: Optional[float] = None
        self._last_date: Optional[Any] = None
        self._force_exit = False

    def _initialize_trigger(self):
        self._checked_today = False
        self._daily_ref_price = None
        self._last_date = None
        self._force_exit = False

    def _parse_time(self, time_str: str):
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])

    def _on_new_candle(self, candle: Dict):
        """캔들마다 호출: 날짜/시간 체크."""
        ts = candle["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        current_date = ts.date()

        # New day reset
        if self._last_date != current_date:
            self._last_date = current_date
            self._checked_today = False
            self._daily_ref_price = None
            self._force_exit = False

        # Set reference price at start_time
        sh, sm = self._parse_time(self.config["start_time"])
        if self._daily_ref_price is None:
            if ts.hour > sh or (ts.hour == sh and ts.minute >= sm):
                self._daily_ref_price = candle["close"]

        # Force exit at stop_time
        eh, em = self._parse_time(self.config["stop_time"])
        if ts.hour > eh or (ts.hour == eh and ts.minute >= em):
            if self.current_level > 0:
                self._force_exit = True

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        self._on_new_candle(candle)

        if self._checked_today or self._daily_ref_price is None:
            return None

        ts = candle["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        sh, sm = self._parse_time(self.config["start_time"])
        trigger_time = datetime(ts.year, ts.month, ts.day, sh, sm) + timedelta(minutes=self.config["delay_minutes"])

        if ts < trigger_time:
            return None

        self._checked_today = True
        change = (candle["close"] - self._daily_ref_price) / self._daily_ref_price * 100

        target = self.config["target_percent"]
        direction = self.config["direction"]

        if direction == "fall":
            if change <= -target:
                return "long"
        else:  # rise
            if change >= target:
                return "long"

        return None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        return False  # 일반적으로 1회 매수

    def _check_exit_trigger(self, candle: Dict) -> bool:
        self._on_new_candle(candle)
        return self._force_exit


# =============================================================================
# New Strategies (chart_pattern, us_market_follow, funding_rate_arb, spot_futures_hedge)
# =============================================================================


class ChartPatternStrategy(MartingaleStrategy):
    """
    차트 패턴 전략.
    Double Bottom (W), V-Bottom, Triangle, Wedge 등 차트 패턴 감지 후 진입.
    Double Top (M), V-Top 등 패턴 감지 시 청산.
    API chart_pattern.py와 동일한 패턴 감지 로직.
    """
    name = "chart_pattern"

    STRATEGY_DEFAULTS = {
        "entry_patterns": "double_bottom",
        "exit_patterns": "",
        "lookback_candles": 20,
        "tolerance_percent": 1.5,
        "min_pattern_depth": 3.0,
        "breakout_confirm": "immediate",
        "cooldown_candles": 5,
        "max_buy_count": 3,
        "trailing_start_percent": 5.0,
        "trailing_stop_percent": 2.0,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._candle_history: deque = deque(maxlen=50)
        self._candles_since_signal: int = 999
        self._trigger_armed: bool = True

    def _initialize_trigger(self):
        self._candle_history = deque(maxlen=50)
        self._candles_since_signal = 999
        self._trigger_armed = True

    def _parse_patterns(self, raw) -> List[str]:
        if isinstance(raw, str):
            return [p.strip() for p in raw.split(",") if p.strip()]
        if isinstance(raw, list):
            return [p for p in raw if p]
        return []

    def _on_candle(self, candle: Dict):
        self._candle_history.append({
            'open': candle.get('open', candle['close']),
            'high': candle.get('high', candle['close']),
            'low': candle.get('low', candle['close']),
            'close': candle['close'],
            'volume': candle.get('volume', 0),
        })
        self._candles_since_signal += 1
        cooldown = int(self.config.get("cooldown_candles", 5))
        if not self._trigger_armed and self._candles_since_signal >= cooldown:
            self._trigger_armed = True

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        # _on_candle() already called by adapter — no duplicate call
        if not self._trigger_armed:
            return None

        lookback = int(self.config.get("lookback_candles", 20))
        if len(self._candle_history) < lookback:
            return None

        candles = list(self._candle_history)[-lookback:]
        entry_patterns = self._parse_patterns(self.config.get("entry_patterns", "double_bottom"))
        tolerance = float(self.config.get("tolerance_percent", 1.5)) / 100.0
        min_depth = float(self.config.get("min_pattern_depth", 3.0)) / 100.0
        confirm = self.config.get("breakout_confirm", "immediate")
        price = candle["close"]

        for pat in entry_patterns:
            detected = None
            if pat == "double_bottom":
                detected = self._detect_double_bottom(candles, price, tolerance, min_depth, confirm)
            elif pat == "v_bottom":
                detected = self._detect_v_bottom(candles, price, min_depth)
            elif pat == "triangle":
                detected = self._detect_triangle(candles, price, min_depth, "up")
            elif pat == "wedge":
                detected = self._detect_wedge(candles, price, "up")
            if detected:
                self._candles_since_signal = 0
                self._trigger_armed = False
                return "long"
        return None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        # _on_candle() already called by adapter — pattern detection uses current state
        return bool(self._check_entry_trigger(candle))

    def _check_exit_trigger(self, candle: Dict) -> bool:
        exit_patterns = self._parse_patterns(self.config.get("exit_patterns", ""))
        if not exit_patterns:
            return False

        lookback = int(self.config.get("lookback_candles", 20))
        if len(self._candle_history) < lookback:
            return False

        candles = list(self._candle_history)[-lookback:]
        tolerance = float(self.config.get("tolerance_percent", 1.5)) / 100.0
        min_depth = float(self.config.get("min_pattern_depth", 3.0)) / 100.0
        confirm = self.config.get("breakout_confirm", "immediate")
        price = candle["close"]

        for pat in exit_patterns:
            detected = None
            if pat == "double_top":
                detected = self._detect_double_top(candles, price, tolerance, min_depth, confirm)
            elif pat == "v_top":
                detected = self._detect_v_top(candles, price, min_depth)
            elif pat == "triangle":
                detected = self._detect_triangle(candles, price, min_depth, "down")
            elif pat == "wedge":
                detected = self._detect_wedge(candles, price, "down")
            if detected:
                return True
        return False

    # --- Pattern Detection (API chart_pattern.py 동일 로직) ---

    def _detect_double_bottom(self, candles, price, tolerance, min_depth, confirm) -> Optional[str]:
        lows = [c['low'] for c in candles]
        highs = [c['high'] for c in candles]
        min_idx1 = lows.index(min(lows))
        second_lows = [(i, lows[i]) for i in range(len(lows)) if abs(i - min_idx1) >= 3]
        if not second_lows:
            return None
        min_idx2, min_val2 = min(second_lows, key=lambda x: x[1])
        min_val1 = lows[min_idx1]
        avg_low = (min_val1 + min_val2) / 2
        if abs(min_val1 - min_val2) / avg_low > tolerance:
            return None
        left_idx, right_idx = min(min_idx1, min_idx2), max(min_idx1, min_idx2)
        if right_idx - left_idx < 3:
            return None
        neckline = max(highs[left_idx:right_idx + 1])
        depth = (neckline - avg_low) / neckline
        if depth < min_depth:
            return None
        if confirm == "close_above":
            if candles[-1]['close'] > neckline:
                return "double_bottom"
        elif confirm == "volume_confirm":
            avg_vol = sum(c['volume'] for c in candles[:-1]) / max(len(candles) - 1, 1)
            if price > neckline and candles[-1]['volume'] > avg_vol * 1.2:
                return "double_bottom"
        else:  # immediate
            if price > neckline:
                return "double_bottom"
        return None

    def _detect_v_bottom(self, candles, price, min_depth) -> Optional[str]:
        lows = [c['low'] for c in candles]
        closes = [c['close'] for c in candles]
        min_idx = lows.index(min(lows))
        min_price = lows[min_idx]
        if min_idx < 3 or min_idx > len(candles) - 3:
            return None
        pre_high = max(c['high'] for c in candles[:min_idx])
        decline = (pre_high - min_price) / pre_high
        post_high = max(c['high'] for c in candles[min_idx:])
        recovery = (post_high - min_price) / min_price if min_price > 0 else 0
        if decline < min_depth or recovery < min_depth * 0.7:
            return None
        if recovery < decline * 0.6:
            return None
        if price > closes[min_idx] * (1 + min_depth * 0.5):
            return "v_bottom"
        return None

    def _detect_double_top(self, candles, price, tolerance, min_depth, confirm) -> Optional[str]:
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        max_idx1 = highs.index(max(highs))
        second_highs = [(i, highs[i]) for i in range(len(highs)) if abs(i - max_idx1) >= 3]
        if not second_highs:
            return None
        max_idx2, max_val2 = max(second_highs, key=lambda x: x[1])
        max_val1 = highs[max_idx1]
        avg_high = (max_val1 + max_val2) / 2
        if abs(max_val1 - max_val2) / avg_high > tolerance:
            return None
        left_idx, right_idx = min(max_idx1, max_idx2), max(max_idx1, max_idx2)
        if right_idx - left_idx < 3:
            return None
        neckline = min(lows[left_idx:right_idx + 1])
        depth = (avg_high - neckline) / avg_high
        if depth < min_depth:
            return None
        if confirm == "close_above":
            if candles[-1]['close'] < neckline:
                return "double_top"
        elif confirm == "volume_confirm":
            avg_vol = sum(c['volume'] for c in candles[:-1]) / max(len(candles) - 1, 1)
            if price < neckline and candles[-1]['volume'] > avg_vol * 1.2:
                return "double_top"
        else:
            if price < neckline:
                return "double_top"
        return None

    def _detect_v_top(self, candles, price, min_depth) -> Optional[str]:
        highs = [c['high'] for c in candles]
        closes = [c['close'] for c in candles]
        max_idx = highs.index(max(highs))
        max_price = highs[max_idx]
        if max_idx < 3 or max_idx > len(candles) - 3:
            return None
        pre_low = min(c['low'] for c in candles[:max_idx])
        rise = (max_price - pre_low) / pre_low if pre_low > 0 else 0
        post_low = min(c['low'] for c in candles[max_idx:])
        decline = (max_price - post_low) / max_price if max_price > 0 else 0
        if rise < min_depth or decline < min_depth * 0.7:
            return None
        if decline < rise * 0.6:
            return None
        if price < closes[max_idx] * (1 - min_depth * 0.5):
            return "v_top"
        return None

    def _detect_triangle(self, candles, price, min_depth, direction) -> Optional[str]:
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        half = len(candles) // 2
        first_range = max(highs[:half]) - min(lows[:half])
        second_range = max(highs[half:]) - min(lows[half:])
        if second_range >= first_range * 0.9:
            return None
        high_trend = (highs[-1] - highs[0]) / highs[0] if highs[0] > 0 else 0
        low_trend = (lows[-1] - lows[0]) / lows[0] if lows[0] > 0 else 0
        avg_price = sum(c['close'] for c in candles) / len(candles)
        convergence = first_range - second_range
        if convergence / avg_price < min_depth * 0.3:
            return None
        recent_high = max(highs[-3:])
        recent_low = min(lows[-3:])
        if direction == "up":
            if price > recent_high and high_trend <= 0:
                return "triangle_up"
        else:
            if price < recent_low and low_trend >= 0:
                return "triangle_down"
        return None

    def _detect_wedge(self, candles, price, direction) -> Optional[str]:
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        n = len(candles)
        x_sum = sum(range(n))
        x2_sum = sum(i * i for i in range(n))
        high_xy = sum(i * highs[i] for i in range(n))
        low_xy = sum(i * lows[i] for i in range(n))
        high_y = sum(highs)
        low_y = sum(lows)
        denom = n * x2_sum - x_sum * x_sum
        if denom == 0:
            return None
        high_slope = (n * high_xy - x_sum * high_y) / denom
        low_slope = (n * low_xy - x_sum * low_y) / denom
        avg_price = (high_y + low_y) / (2 * n)
        high_slope_pct = high_slope / avg_price if avg_price > 0 else 0
        low_slope_pct = low_slope / avg_price if avg_price > 0 else 0
        if direction == "up":
            if high_slope < 0 and low_slope < 0:
                if low_slope_pct < high_slope_pct:
                    if price > max(highs[-3:]):
                        return "falling_wedge"
        else:
            if high_slope > 0 and low_slope > 0:
                if high_slope_pct < low_slope_pct:
                    if price < min(lows[-3:]):
                        return "rising_wedge"
        return None


class UsMarketFollowStrategy(MartingaleStrategy):
    """
    미국 증시 추종 전략.
    전일 미국 증시 변동률이 임계값을 넘으면 한국 장 시작에 진입.
    yfinance로 미국 지수 데이터를 가져옴.
    API us_market_follow.py와 동일한 로직.
    """
    name = "us_market_follow"

    STRATEGY_DEFAULTS = {
        "us_index": "^GSPC",
        "trigger_direction": "above",
        "us_change_threshold": 1.0,
        "entry_start_time": "09:00",
        "max_buy_count": 1,
        "last_level_allin": "on",
        "trailing_start_percent": 2.0,
        "trailing_stop_percent": 1.0,
        "max_loss_percent": 3.0,
        "cycle_max_hours": 6,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._daily_date = None
        self._checked_today = False
        self._us_change_map: Dict[str, float] = {}
        self._trigger_met = False

    def _initialize_trigger(self):
        self._daily_date = None
        self._checked_today = False
        self._us_change_map = {}
        self._trigger_met = False

    def preload_us_data(self, days: int = 365):
        """백테스트 시작 전 미국 지수 데이터를 미리 로드."""
        try:
            import yfinance as yf
            ticker = self.config.get("us_index", "^GSPC")
            period_map = {365: "1y", 180: "6mo", 90: "3mo", 30: "1mo"}
            period = period_map.get(days, "1y")
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if hist is None or len(hist) < 2:
                return
            for i in range(1, len(hist)):
                prev_close = float(hist["Close"].iloc[i - 1])
                curr_close = float(hist["Close"].iloc[i])
                change_pct = (curr_close - prev_close) / prev_close * 100
                date_str = str(hist.index[i].date())
                self._us_change_map[date_str] = change_pct
        except ImportError:
            pass
        except Exception:
            pass

    def _get_us_change_for_date(self, korean_date_str: str) -> float:
        """한국 날짜에 해당하는 미국 증시 변동률 조회."""
        d = datetime.strptime(korean_date_str, "%Y-%m-%d").date()
        for offset in range(1, 5):
            us_date = str(d - timedelta(days=offset))
            if us_date in self._us_change_map:
                return self._us_change_map[us_date]
        return 0.0

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        ts = candle["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        current_date = ts.date()

        # Daily reset
        if self._daily_date != current_date:
            self._daily_date = current_date
            self._checked_today = False
            self._trigger_met = False

        if self._checked_today:
            return None

        # entry_start_time 확인
        start_str = self.config.get("entry_start_time", "09:00")
        parts = start_str.split(":")
        sh, sm = int(parts[0]), int(parts[1])
        if ts.hour < sh or (ts.hour == sh and ts.minute < sm):
            return None

        self._checked_today = True

        # 미국 증시 변동률 확인
        us_change = self._get_us_change_for_date(current_date.strftime("%Y-%m-%d"))
        threshold = float(self.config.get("us_change_threshold", 1.0))
        direction = self.config.get("trigger_direction", "above")

        if direction == "above":
            self._trigger_met = us_change >= threshold
        elif direction == "below":
            self._trigger_met = us_change <= -threshold

        return "long" if self._trigger_met else None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        return False


class FundingRateArbStrategy(MartingaleStrategy):
    """
    펀딩비 차익거래 전략 (독립 백테스트용 간소화 버전).
    실제 펀딩레이트 데이터가 OHLCV에 포함되지 않으므로,
    가격 변동률을 펀딩레이트의 프록시로 사용.

    원본 API: 펀딩레이트 > entry_threshold -> SHORT (숏이 펀딩비 수령)
              펀딩레이트 < -entry_threshold -> LONG (롱이 펀딩비 수령)

    스킬 버전: 가격 모멘텀을 펀딩레이트 프록시로 사용한 방향성 거래 시뮬레이션.
    NOTE: 실제 펀딩비 수익은 시뮬레이션하지 않음.
    """
    name = "funding_rate_arb"

    STRATEGY_DEFAULTS = {
        "entry_rate_threshold": 0.03,
        "exit_rate_threshold": 0.005,
        "position_size_pct": 50.0,
        "proxy_lookback": 8,
        "max_buy_count": 1,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._close_history: List[float] = []
        self._proxy_rate: float = 0.0

    def _initialize_trigger(self):
        self._close_history = []
        self._proxy_rate = 0.0

    def _calc_proxy_funding_rate(self, close: float) -> float:
        """가격 변동률을 펀딩레이트 프록시로 사용."""
        self._close_history.append(close)
        lookback = int(self.config.get("proxy_lookback", 8))
        if len(self._close_history) < lookback + 1:
            return 0.0
        old_price = self._close_history[-lookback - 1]
        if old_price == 0:
            return 0.0
        change_pct = (close - old_price) / old_price * 100
        return change_pct / 100  # e.g., 1% change -> 0.01

    def _on_candle(self, candle: Dict):
        """Update proxy funding rate on every candle."""
        self._proxy_rate = self._calc_proxy_funding_rate(candle["close"])

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        # _proxy_rate already updated by _on_candle()
        entry_threshold = float(self.config.get("entry_rate_threshold", 0.03)) / 100

        if abs(self._proxy_rate) < entry_threshold:
            return None

        if self._proxy_rate > 0:
            # 양의 "펀딩레이트" -> SHORT (숏이 수령)
            pos_side = self.config.get("position_side", "long")
            if pos_side in ("short", "both"):
                return "short"
            return None
        else:
            # 음의 "펀딩레이트" -> LONG (롱이 수령)
            return "long"

    def _check_additional_trigger(self, candle: Dict) -> bool:
        return False

    def _check_exit_trigger(self, candle: Dict) -> bool:
        exit_threshold = float(self.config.get("exit_rate_threshold", 0.005)) / 100
        if abs(self._proxy_rate) < exit_threshold:
            return True
        entry_threshold = float(self.config.get("entry_rate_threshold", 0.03)) / 100
        if self.is_short and self._proxy_rate < -entry_threshold:
            return True
        if not self.is_short and self._proxy_rate > entry_threshold:
            return True
        return False


class SpotFuturesHedgeStrategy(MartingaleStrategy):
    """
    현선물 헤지 전략 (독립 백테스트용 간소화 버전).
    실제로는 Spot LONG + Futures SHORT 동시 진입으로 펀딩비 수령.
    독립 백테스트에서는 헤지 구조를 시뮬레이션할 수 없으므로,
    펀딩비 수령 기회를 가격 기반으로 근사.

    NOTE: 실제 헤지 수익은 시뮬레이션 불가. 진입/청산 타이밍만 백테스트.
    실전에서는 반드시 API 방식(live_binance.py)을 사용.
    """
    name = "spot_futures_hedge"

    STRATEGY_DEFAULTS = {
        "entry_rate_threshold": 0.05,
        "exit_rate_threshold": 0.01,
        "hedge_size_pct": 50.0,
        "proxy_lookback": 8,
        "max_buy_count": 1,
        "trailing_start_percent": 0.5,
        "trailing_stop_percent": 0.3,
    }

    def __init__(self, config=None):
        merged = {**self.STRATEGY_DEFAULTS, **(config or {})}
        super().__init__(merged)
        self._close_history: List[float] = []
        self._proxy_rate: float = 0.0

    def _initialize_trigger(self):
        self._close_history = []
        self._proxy_rate = 0.0

    def _calc_proxy_rate(self, close: float) -> float:
        self._close_history.append(close)
        lookback = int(self.config.get("proxy_lookback", 8))
        if len(self._close_history) < lookback + 1:
            return 0.0
        old_price = self._close_history[-lookback - 1]
        if old_price == 0:
            return 0.0
        return (close - old_price) / old_price

    def _on_candle(self, candle: Dict):
        """Update proxy rate on every candle."""
        self._proxy_rate = self._calc_proxy_rate(candle["close"])

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        # _proxy_rate already updated by _on_candle()
        entry_threshold = float(self.config.get("entry_rate_threshold", 0.05)) / 100
        if self._proxy_rate >= entry_threshold:
            return "long"
        return None

    def _check_additional_trigger(self, candle: Dict) -> bool:
        return False

    def _check_exit_trigger(self, candle: Dict) -> bool:
        exit_threshold = float(self.config.get("exit_rate_threshold", 0.01)) / 100
        if self._proxy_rate < exit_threshold:
            return True
        if self._proxy_rate < 0:
            return True
        return False


# =============================================================================
# Strategy Registry
# =============================================================================

STRATEGY_REGISTRY = {
    "dip_martingale": DipMartingaleStrategy,
    "ema_momentum": EmaMomentumStrategy,
    "rsi_martingale": RsiMartingaleStrategy,
    "time_momentum": TimeMomentumStrategy,
    "chart_pattern": ChartPatternStrategy,
    "us_market_follow": UsMarketFollowStrategy,
    "funding_rate_arb": FundingRateArbStrategy,
    "spot_futures_hedge": SpotFuturesHedgeStrategy,
}


def get_strategy(name: str, config: Dict[str, Any] = None) -> MartingaleStrategy:
    """이름으로 전략 인스턴스를 생성."""
    cls = STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}")
    return cls(config)


def list_strategies() -> Dict[str, str]:
    """등록된 전략 목록."""
    return {
        "dip_martingale": "눌림목 마틴게일 - 캔들 하락 시 단계별 매수, 반등 시 청산",
        "ema_momentum": "EMA 모멘텀 - EMA 골든/데드 크로스 기반 추세 추종",
        "rsi_martingale": "RSI 마틴게일 - RSI 과매도/과매수 기반 진입, 마틴게일 추가매수",
        "time_momentum": "시간대 모멘텀 - 특정 시간대 모멘텀 확인 후 진입",
        "chart_pattern": "차트 패턴 - Double Bottom, V-Bottom, Triangle 등 패턴 감지",
        "us_market_follow": "미국 증시 추종 - 전일 미국 증시 변동률 기반 진입",
        "funding_rate_arb": "펀딩비 차익 - 펀딩레이트 기반 방향성 거래 (선물 전용)",
        "spot_futures_hedge": "현선물 헤지 - Spot+Futures 델타 중립 펀딩비 수령",
    }
