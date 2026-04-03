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
        """포지션 청산 → Trade 생성."""
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

        # initial_entry 모드: 누적 스텝 (L2=1×step, L3=2×step, ...)
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
    L1: Golden cross (fast > slow) → long, Dead cross → short
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

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        self._update_emas(candle["close"])
        cross = self._get_crossover()

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
        cross = self._get_crossover()
        if self.is_short:
            return cross == "dead_cross"
        return cross == "golden_cross"

    def _check_exit_trigger(self, candle: Dict) -> bool:
        # Note: crossover already updated in entry check
        # Re-check current state
        if self._ema_fast is None or self._ema_slow is None:
            return False
        curr_diff = self._ema_fast - self._ema_slow
        if self.is_short:
            return curr_diff > 0  # Golden cross → exit short
        return curr_diff < 0      # Dead cross → exit long


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

    def _check_entry_trigger(self, candle: Dict) -> Optional[str]:
        self._close_history.append(candle["close"])
        self._prev_rsi = self._rsi
        self._rsi = self._calc_rsi()

        cfg = self.config
        pos_side = cfg.get("position_side", "long")

        # Re-arm logic
        if not self._long_armed:
            if self._check_cross(self._prev_rsi, self._rsi, cfg["reset_level"], cfg["reset_direction"]):
                self._long_armed = True

        if not self._short_armed:
            if self._check_cross(self._prev_rsi, self._rsi, cfg["short_reset_level"], cfg["short_reset_direction"]):
                self._short_armed = True

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
        cfg = self.config
        if self.is_short:
            return self._check_cross(self._prev_rsi, self._rsi, cfg["short_trigger_level"], cfg["short_trigger_direction"])
        return self._check_cross(self._prev_rsi, self._rsi, cfg["trigger_level"], cfg["trigger_direction"])


class TimeMomentumStrategy(MartingaleStrategy):
    """
    시간대 모멘텀.
    매일 start_time에 기준가 설정 → delay_minutes 후 변동률 체크 → 진입
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
# Strategy Registry
# =============================================================================

STRATEGY_REGISTRY = {
    "dip_martingale": DipMartingaleStrategy,
    "ema_momentum": EmaMomentumStrategy,
    "rsi_martingale": RsiMartingaleStrategy,
    "time_momentum": TimeMomentumStrategy,
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
    }
