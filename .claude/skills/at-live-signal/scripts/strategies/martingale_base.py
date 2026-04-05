"""
Skill-local MartingaleBase — backend 의존성 완전 제거.

backend/app/strategies/martingale_base.py 의 경량 복사본.
제거된 의존성:
- DB (SessionLocal, LiveBotSession, LiveTradeExecution)
- qty_rules (adjust_qty, adjust_price, EXCHANGE_QTY_RULES)
- config (DEFAULT_EXCHANGE, DEFAULT_INITIAL_CAPITAL)
- trading_hours (calc_trading_seconds)

핵심 트레이딩 로직은 100% 동일하게 유지:
- 트레일링 스탑, 손절, 사이클 시간 제한
- 마틴게일 레벨 관리, 포지션 사이징
- on_data → _on_candle → _check_exit_trigger → _check_exits → entry/additional
- on_tick (틱 기반 청산)
"""

from abc import abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import math
import logging
from .base import BaseStrategy, IContext, Signal, Side, Level, Mode

logger = logging.getLogger(__name__)

# ── Defaults (inlined from backend config) ──
DEFAULT_INITIAL_CAPITAL = 500


class MartingaleBase(BaseStrategy):
    """
    Base class for all Martingale-family strategies.
    Skill-local version — no DB, no exchange-specific rules.
    Trading logic is 100% identical to backend version.
    """

    PARAMETER_SCHEMA = None

    def initialize(self):
        # Configuration parameters
        self.symbol = self.config.get("symbol", "UNKNOWN")
        self.max_buy_count = self.config.get("max_buy_count",
            self.config.get("max_levels", 4))
        if self.max_buy_count == 0:
            self.max_buy_count = 999999
        self.lot_size_multiplier = self.config.get("lot_size_multiplier",
            self.config.get("pyramid_multiplier", 2.0))
        self.base_quantity = self.config.get("base_quantity", 1)
        self.qty_mode = self.config.get("qty_mode", "fixed")

        use_mart = self.config.get("use_martingale", "on")
        if use_mart == "off" or use_mart is False:
            self.max_buy_count = 1

        self.trailing_start_percent = self.config.get("trailing_start_percent", 0.01)
        self.trailing_stop_percent = self.config.get("trailing_stop_percent", 0.003)
        self.max_loss_percent = self.config.get("max_loss_percent", 0.10)

        self.betting_strategy = self.config.get("betting_strategy",
            self.config.get("betting_mode", "fixed"))

        self.safety_margin_percent = self.config.get("safety_margin_percent", 1.0)
        self.cycle_max_hours = self.config.get("cycle_max_hours", 0)

        allin_val = self.config.get("last_level_allin", "off")
        self.last_level_allin = allin_val == "on" or allin_val is True

        tll_val = self.config.get("trailing_on_last_level", "off")
        self.trailing_on_last_level = tll_val == "on" or tll_val is True

        rlp_val = self.config.get("require_lower_price", "off")
        self.require_lower_price = rlp_val == "on" or rlp_val is True

        self.additional_buy_mode = self.config.get("additional_buy_mode", "trigger")
        self.additional_buy_step = self.config.get("additional_buy_step", 2.0)
        self.additional_buy_step_ref = self.config.get("additional_buy_step_ref", "last_entry")

        self.liquidation_floor_pct = self.config.get("liquidation_floor_pct", 3.0)

        self.position_side = self.config.get("position_side", Side.LONG)
        if isinstance(self.position_side, str):
            self.position_side = self.position_side.lower()
        self.is_short = (self.position_side == Side.SHORT)

        self.tick_execution = self.config.get("tick_execution", "tick")

        # Cycle planning variables
        self.cycle_max_level = None
        self.cycle_reference_price = None
        self.cycle_start_time = None
        self._resolved_base_qty = None
        self._cycle_start_equity = None

        # State variables
        self.current_level = 0
        self.reference_price = None
        self.peak_price = 0
        self.average_price = 0
        self.total_quantity = 0
        self.trailing_active = False
        self.is_hodl = False
        self.last_trade_time = None
        self.current_trading_date = None
        self.entries = []
        self.paper_cycle_id = 0
        self.real_cycle_id = 0

        # Pending order guard
        self._pending_entry = False
        self._pending_exit = False

        # Hook for subclass-specific initialization
        self._initialize_trigger()

        # Skill mode: no DB reconstruction (SkillContext handles state)

    # ── Direction-aware helpers ──

    def _calc_position_profit(self, current_price: float) -> float:
        if self.is_short:
            return (self.average_price - current_price) * self.total_quantity
        return (current_price - self.average_price) * self.total_quantity

    def _calc_price_return(self, current_price: float) -> float:
        if self.average_price <= 0:
            return 0
        if self.is_short:
            return (self.average_price - current_price) / self.average_price
        return (current_price - self.average_price) / self.average_price

    # ── Subclass hooks ──

    def _initialize_trigger(self):
        pass

    @abstractmethod
    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        pass

    @abstractmethod
    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        pass

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        return False

    def preload_history(self, candles: list):
        pass

    def _on_candle(self, data: Dict[str, Any]):
        pass

    # ── Exit checks ──

    def _check_exits(self, current_price: float) -> bool:
        if self.current_level <= 0 or self.total_quantity <= 0:
            return False

        position_profit = self._calc_position_profit(current_price)
        if self._cycle_start_equity and self._cycle_start_equity > 0:
            current_return = position_profit / self._cycle_start_equity
        else:
            total_investment = self.average_price * self.total_quantity
            current_return = position_profit / total_investment if total_investment > 0 else 0

        # Cycle time limit (simple elapsed hours — no trading-hours calc)
        if self.cycle_max_hours > 0 and self.cycle_start_time:
            current_time = self.context.get_time()
            elapsed_hours = (current_time - self.cycle_start_time).total_seconds() / 3600
            if elapsed_hours >= self.cycle_max_hours:
                side_label = "SHORT" if self.is_short else "LONG"
                self.context.log(f"[{self._log_prefix}] CYCLE TIME LIMIT! {elapsed_hours:.1f}h >= {self.cycle_max_hours}h. Close {side_label} @ {current_price:,.0f} (Return: {current_return*100:.2f}%)")
                self._liquidate(current_price)
                return True

        # Update peak price (direction-aware)
        if self.is_short:
            if self.peak_price <= 0 or current_price < self.peak_price:
                current_peak_profit = self._calc_position_profit(self.peak_price) if self.peak_price > 0 else 0
                if self._calc_position_profit(current_price) > current_peak_profit:
                    self.peak_price = current_price
        else:
            current_peak_profit = (self.peak_price - self.average_price) * self.total_quantity if self.peak_price > 0 else 0
            if self._calc_position_profit(current_price) > current_peak_profit:
                self.peak_price = current_price

        # Futures: Liquidation Floor Check
        leverage = self._get_leverage()
        if leverage > 1:
            futures_data = self.context.get_futures_data(self.symbol)
            liq_price = futures_data.get("liquidation_price", 0)
            if liq_price > 0 and self.liquidation_floor_pct > 0:
                liq_distance = abs(current_price - liq_price) / current_price if current_price > 0 else 1.0
                if liq_distance <= (self.liquidation_floor_pct / 100):
                    self.context.log(f"[{self._log_prefix}] LIQUIDATION FLOOR! Price {current_price:,.2f} within {liq_distance*100:.2f}% of liquidation {liq_price:,.2f}. FORCE EXIT!")
                    self._liquidate(current_price)
                    return True

        # Trailing Stop Activation
        price_return = self._calc_price_return(current_price)
        last_level_reached = (self.current_level >= self.max_buy_count)
        if (self.trailing_start_percent > 0
                and not self.trailing_active
                and price_return >= (self.trailing_start_percent / 100)
                and (not self.trailing_on_last_level or last_level_reached)):
            self.trailing_active = True
            self.peak_price = current_price
            self.context.log(f"[{self._log_prefix}] Trailing Stop ACTIVATED. Price Return: {price_return*100:.2f}% (threshold: {self.trailing_start_percent}%)")

        # Trailing Stop Trigger
        if self.trailing_active:
            if self.is_short:
                rise_from_trough = (current_price - self.peak_price) / self.peak_price if self.peak_price > 0 else 0
                if rise_from_trough >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[{self._log_prefix}] Trailing Stop TRIGGERED! Cover SHORT @ {current_price:,.0f} (Return: {current_return*100:.2f}%)")
                    self._liquidate(current_price)
                    return True
            else:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price if self.peak_price > 0 else 0
                if drop_from_peak >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[{self._log_prefix}] Trailing Stop TRIGGERED! Sell @ {current_price:,.0f} (Return: {current_return*100:.2f}%)")
                    self._liquidate(current_price)
                    return True

        # Max Loss Stop-Loss
        if self.max_loss_percent > 0 and current_return <= -(self.max_loss_percent / 100):
            side_label = "Cover SHORT" if self.is_short else "Sell"
            self.context.log(f"[{self._log_prefix}] MAX LOSS TRIGGERED! Loss {current_return*100:.1f}% >= -{self.max_loss_percent}%. {side_label} @ {current_price:,.0f}")
            self._liquidate(current_price)
            return True

        return False

    def on_tick(self, price: float, timestamp=None) -> bool:
        if self.tick_execution != "tick":
            return False
        if self.current_level <= 0 or self.total_quantity <= 0:
            return False
        self.last_price = price
        return self._check_exits(price)

    # ── Main on_data ──

    def on_data(self, data: Dict[str, Any]):
        self._on_candle(data)
        current_time = self.context.get_time()
        current_date = current_time.date()
        current_price = data['close']
        self.last_price = current_price
        symbol = self.symbol

        # 1. Reset cycle on new day (if no position)
        if self.current_trading_date != current_date:
            self.current_trading_date = current_date
            if self.current_level == 0:
                self.reference_price = None
                self.context.log(f"[{self._log_prefix}] New day {current_date}. Resetting reference price.")

        # 2. Set Reference Price
        if self.reference_price is None:
            self.reference_price = current_price
            self.context.log(f"[{self._log_prefix}] Cycle started for {symbol}. Ref: {self.reference_price:,.0f}")

        # 3. Position Management (If holding)
        if self.current_level > 0 and self.total_quantity > 0:
            # Check Indicator-Based Exit
            position_profit = self._calc_position_profit(current_price)
            if self._cycle_start_equity and self._cycle_start_equity > 0:
                current_return = position_profit / self._cycle_start_equity
            else:
                total_investment = self.average_price * self.total_quantity
                current_return = position_profit / total_investment if total_investment > 0 else 0

            if self._check_exit_trigger(data):
                side_label = "Cover SHORT" if self.is_short else "Sell"
                self.context.log(f"[{self._log_prefix}] EXIT TRIGGER! {side_label} @ {current_price:,.0f} (Return: {current_return*100:.2f}%)")
                self._liquidate(current_price)
                return

            # Price-based exits
            if self._check_exits(current_price):
                return

            # Check Additional Entry (L2+)
            if self.current_level < self.max_buy_count and not self.trailing_active:
                if self.cycle_max_level is None and self.current_level > 0:
                    self.cycle_max_level = self._calculate_max_affordable_level(current_price)
                    self.context.log(f"[{self._log_prefix}] Cycle Plan restored: Max affordable level = L{self.cycle_max_level} @ {current_price:,.0f}")

                if self.cycle_max_level is not None and self.current_level >= self.cycle_max_level:
                    pass
                else:
                    # Require worse price
                    if self.require_lower_price and self.entries:
                        last_entry_price = self.entries[-1]["price"]
                        if self.is_short:
                            if current_price <= last_entry_price:
                                return
                        else:
                            if current_price >= last_entry_price:
                                return

                    # Determine entry signal
                    should_enter = False
                    if self.additional_buy_mode == "step" and self.entries:
                        ref_price = self._get_step_reference_price()
                        if ref_price > 0:
                            if self.is_short:
                                move_pct = (current_price - ref_price) / ref_price * 100
                            else:
                                move_pct = (ref_price - current_price) / ref_price * 100
                            if self.additional_buy_step_ref == "initial_entry":
                                required_move = self.additional_buy_step * self.current_level
                            else:
                                required_move = self.additional_buy_step
                            should_enter = move_pct >= required_move
                    else:
                        should_enter = self._check_additional_trigger(data)

                    if should_enter:
                        if self._pending_entry:
                            return

                        next_level = self.current_level + 1
                        qty = self._calculate_quantity(next_level, current_price)
                        if qty > 0:
                            self._pending_entry = True

                            def on_filled_callback(order_id, filled_qty, filled_price, metadata, _level=next_level):
                                self._pending_entry = False
                                if filled_qty > 0:
                                    self._add_position(filled_price, filled_qty, _level)
                                    self.context.log(f"[{self._log_prefix}] L{_level} Entry FILLED @ {filled_price:,.0f}. Avg: {self.average_price:,.0f}")

                            actual_side = Side.SHORT if self.is_short else Side.LONG
                            entry_metadata = {"level": next_level, "position_side": actual_side}
                            if self.is_short:
                                result = self.context.short(symbol, qty, metadata=entry_metadata, on_filled=on_filled_callback)
                            else:
                                result = self.context.buy(symbol, qty, metadata=entry_metadata, on_filled=on_filled_callback)
                            if result.get("status") == "failed":
                                self._pending_entry = False
                                self.context.log(f"[{self._log_prefix}] L{next_level} Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

        # 4. Initial Entry (Level 1)
        elif self.current_level == 0:
            if self._pending_entry:
                return

            direction = self._check_entry_trigger(data)
            if direction:
                if self.position_side != Side.BOTH and direction != self.position_side:
                    return

                self.is_short = (direction == Side.SHORT)
                self._cycle_start_equity = self.context.get_total_equity()
                qty = self._calculate_quantity(1, current_price)
                if qty > 0:
                    self._pending_entry = True

                    def on_l1_filled(order_id, filled_qty, filled_price, metadata):
                        self._pending_entry = False
                        if filled_qty > 0:
                            self._add_position(filled_price, filled_qty, 1)
                            self.peak_price = filled_price
                            self.cycle_start_time = self.context.get_time()
                            self.context.log(f"[{self._log_prefix}] L1 Entry FILLED @ {filled_price:,.0f} (cycle_equity: {self._cycle_start_equity:,.0f})")

                    actual_side = Side.SHORT if self.is_short else Side.LONG
                    entry_metadata = {"level": 1, "position_side": actual_side}
                    if self.is_short:
                        result = self.context.short(symbol, qty, metadata=entry_metadata, on_filled=on_l1_filled)
                    else:
                        result = self.context.buy(symbol, qty, metadata=entry_metadata, on_filled=on_l1_filled)
                    if result.get("status") == "failed":
                        self._pending_entry = False
                        self.context.log(f"[{self._log_prefix}] L1 Initial Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

    # ── Helpers ──

    def _get_leverage(self) -> int:
        config_leverage = self.config.get("leverage", 1)
        is_paper = getattr(self.context, 'is_paper', True)
        if is_paper:
            return config_leverage
        futures_data = self.context.get_futures_data(self.symbol)
        if futures_data and futures_data.get("leverage", 0) > 0:
            return futures_data["leverage"]
        return config_leverage

    @property
    def _log_prefix(self) -> str:
        return "Martingale"

    def _add_position(self, price: float, quantity: int, level: int):
        new_total_qty = self.total_quantity + quantity
        self.average_price = ((self.average_price * self.total_quantity) + (price * quantity)) / new_total_qty
        self.total_quantity = new_total_qty
        self.current_level = level
        self.entries.append({"level": level, "price": price, "quantity": quantity, "time": str(self.context.get_time())})

    def _get_step_reference_price(self) -> float:
        if not self.entries:
            return 0
        if self.additional_buy_step_ref == "avg_price":
            return self.average_price
        elif self.additional_buy_step_ref == "initial_entry":
            return self.entries[0]["price"]
        else:
            return self.entries[-1]["price"]

    def _liquidate(self, price: float):
        if self._pending_exit:
            return

        is_paper = getattr(self.context, 'is_paper', True)
        if is_paper:
            self.paper_cycle_id += 1
            cycle_id = self.paper_cycle_id
        else:
            self.real_cycle_id += 1
            cycle_id = self.real_cycle_id

        self._pending_exit = True

        def on_sell_filled(order_id, filled_qty, filled_price, metadata):
            self._pending_exit = False
            if filled_qty > 0:
                if self.betting_strategy == "fixed":
                    self.context.reset_cycle_capital()

                self.current_level = 0
                self.total_quantity = 0
                self.average_price = 0
                self.peak_price = 0
                self.trailing_active = False
                self.is_hodl = False
                self.reference_price = None
                self.entries = []
                self.cycle_max_level = None
                self.cycle_reference_price = None
                self.cycle_start_time = None
                self._resolved_base_qty = None
                self._cycle_start_equity = None
                self.context.log(f"[{self._log_prefix}] Cycle {cycle_id} CLOSED @ {filled_price:,.0f}")

        actual_side = Side.SHORT if self.is_short else Side.LONG
        close_metadata = {"level": Level.CLOSE, "cycle_id": cycle_id, "is_paper": is_paper, "cycle_start_equity": self._cycle_start_equity, "position_side": actual_side}
        if self.is_short:
            try:
                result = self.context.close_position(self.symbol, metadata=close_metadata)
                if result.get("status") != "failed":
                    on_sell_filled(None, self.total_quantity, price, close_metadata)
                    return
            except (NotImplementedError, AttributeError):
                pass
            result = self.context.buy(self.symbol, self.total_quantity, metadata=close_metadata, on_filled=on_sell_filled)
        else:
            result = self.context.sell(self.symbol, self.total_quantity, metadata=close_metadata, on_filled=on_sell_filled)
        if result.get("status") == "failed":
            self._pending_exit = False
            self.context.log(f"[{self._log_prefix}] CLOSE FAILED: {result.get('reason', 'Unknown')}")

    # ── Quantity calculation (simplified — no exchange-specific rules) ──

    def _resolve_level_qty(self, level: int, price: float) -> float:
        if self.qty_mode == "percent" and price > 0:
            if not hasattr(self, '_resolved_base_qty') or self._resolved_base_qty is None:
                session_cash = getattr(self.context, 'cash', 0)
                own_position_value = self.total_quantity * price if self.total_quantity > 0 and price > 0 else 0
                equity = session_cash + own_position_value
                capital = equity if equity > 0 else getattr(self.context, 'initial_capital', DEFAULT_INITIAL_CAPITAL)
                leverage = self._get_leverage()
                buying_power = capital * leverage
                self.context.log(f"[{self._log_prefix}] Capital for qty calc: {capital:,.0f} x {leverage}x = {buying_power:,.0f}")
                self._resolved_base_qty = buying_power * self.base_quantity / 100 / price
            return self._resolved_base_qty * (self.lot_size_multiplier ** (level - 1))

        raw_base = float(self.base_quantity)
        if price > 0 and (not hasattr(self, '_resolved_base_qty') or self._resolved_base_qty is None):
            self._resolved_base_qty = raw_base

        effective_base = getattr(self, '_resolved_base_qty', None) or raw_base
        return effective_base * (self.lot_size_multiplier ** (level - 1))

    def _calculate_max_affordable_level(self, price: float) -> int:
        available_cash = getattr(self.context, 'cash', 0)
        safety_reserve = available_cash * (self.safety_margin_percent / 100)
        usable_capital = available_cash - safety_reserve
        leverage = self._get_leverage()

        if price <= 0 or usable_capital <= 0:
            return 0

        cumulative_cost = 0
        max_level = 0
        remaining_cash = usable_capital

        for level in range(1, self.max_buy_count + 1):
            raw_qty = self._resolve_level_qty(level, price)
            adj_qty = int(raw_qty) if raw_qty >= 1 else raw_qty
            if adj_qty <= 0:
                break
            level_cost = adj_qty * price / leverage
            cumulative_cost += level_cost

            if cumulative_cost <= usable_capital:
                max_level = level
                remaining_cash = usable_capital - cumulative_cost
            else:
                break

        return max_level

    def _calculate_quantity(self, level: int, price: float = None) -> float:
        if price is None:
            price = getattr(self, 'last_price', 0)

        if price <= 0:
            return self._resolve_level_qty(level, price)

        if self.cycle_max_level is None or level == 1:
            self.cycle_max_level = self._calculate_max_affordable_level(price)
            self.cycle_reference_price = price
            self.context.log(f"[{self._log_prefix}] Cycle Plan: Max affordable level = L{self.cycle_max_level} @ {price:,.0f}")

        effective_max_level = min(self.cycle_max_level, self.max_buy_count)

        if level >= effective_max_level and effective_max_level > 0:
            standard_qty = self._resolve_level_qty(level, price)

            if self.last_level_allin:
                available_cash = getattr(self.context, 'cash', 0)
                safety_reserve = available_cash * (self.safety_margin_percent / 100)
                usable_capital = available_cash - safety_reserve
                lev = self._get_leverage()
                max_qty = usable_capital * lev / price if price > 0 else 0
                self.context.log(f"[{self._log_prefix}] L{level} FINAL LEVEL (ALL-IN): cash={available_cash:,.0f}, lev={lev}x → {max_qty:.1f} qty")
                qty = int(max_qty) if max_qty >= 1 else max_qty
            else:
                self.context.log(f"[{self._log_prefix}] L{level} FINAL LEVEL: Standard qty → {standard_qty} qty")
                qty = int(standard_qty) if standard_qty >= 1 else standard_qty
        else:
            raw = self._resolve_level_qty(level, price)
            qty = int(raw) if raw >= 1 else raw

        # Cash guard
        if qty > 0 and price > 0:
            available_cash = max(getattr(self.context, 'cash', 0), 0)
            if available_cash <= 0:
                self.context.log(f"[{self._log_prefix}] CASH GUARD: No cash available, blocking L{level}")
                return 0
            leverage = self._get_leverage()
            safety_reserve = available_cash * (self.safety_margin_percent / 100)
            max_affordable = int((available_cash - safety_reserve) * leverage / price)
            if qty > max_affordable:
                self.context.log(f"[{self._log_prefix}] CASH GUARD: L{level} qty {qty} → {max_affordable}")
                qty = max_affordable

        return qty

    # ── State ──

    def get_state(self) -> Dict[str, Any]:
        cur_price = getattr(self, 'last_price', 0)
        if cur_price == 0 and hasattr(self, 'context') and self.context:
            cur_price = self.context.get_current_price(self.symbol)
        dip_percent = (self.reference_price - cur_price) / self.reference_price if self.reference_price else 0

        position_profit = self._calc_position_profit(cur_price) if self.average_price > 0 else 0
        total_investment = self.average_price * self.total_quantity if self.average_price > 0 else 0
        profit_percent = position_profit / total_investment if total_investment > 0 else 0

        if self.average_price > 0:
            if self.is_short:
                target_price = self.average_price * (1 - self.trailing_start_percent / 100.0)
            else:
                target_price = self.average_price * (1 + self.trailing_start_percent / 100.0)
        else:
            target_price = 0

        avg = self.average_price
        if avg > 0 and self.max_loss_percent > 0:
            if self.is_short:
                stop_loss_price = avg * (1 + self.max_loss_percent / 100.0)
            else:
                stop_loss_price = avg * (1 - self.max_loss_percent / 100.0)
        else:
            stop_loss_price = 0

        if self.trailing_active and self.peak_price > 0 and self.trailing_stop_percent > 0:
            if self.is_short:
                trailing_exit_price = self.peak_price * (1 + self.trailing_stop_percent / 100.0)
            else:
                trailing_exit_price = self.peak_price * (1 - self.trailing_stop_percent / 100.0)
        else:
            trailing_exit_price = 0

        return {
            "strategy_id": self._strategy_id,
            "current_level": self.current_level,
            "max_buy_count": self.max_buy_count,
            "average_price": self.average_price,
            "total_quantity": self.total_quantity,
            "peak_price": self.peak_price,
            "trailing_active": self.trailing_active,
            "is_hodl": self.is_hodl,
            "reference_price": self.reference_price,
            "symbol": self.symbol,
            "current_price": cur_price,
            "dip_percent": dip_percent,
            "profit_percent": profit_percent,
            "target_profit_pct": self.trailing_start_percent,
            "target_price": target_price,
            "max_loss_pct": self.max_loss_percent,
            "trailing_stop_pct": self.trailing_stop_percent,
            "stop_loss_price": stop_loss_price,
            "trailing_exit_price": trailing_exit_price,
            "entries": self.entries,
            "require_lower_price": self.require_lower_price,
            "position_side": Side.SHORT if self.is_short else Side.LONG,
            "position_side_config": self.position_side,
            "paper_cycle_id": self.paper_cycle_id,
            "real_cycle_id": self.real_cycle_id,
            "cycle_id": self.paper_cycle_id if getattr(self.context, 'is_paper', True) else self.real_cycle_id,
            "pending_entry": getattr(self, '_pending_entry', False),
            "pending_exit": getattr(self, '_pending_exit', False),
        }

    @property
    def _strategy_id(self) -> str:
        return "martingale_base"
