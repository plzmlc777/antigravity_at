from abc import abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime
import math
import logging
from .base import BaseStrategy, IContext
from ..core.qty_rules import adjust_qty, adjust_price, EXCHANGE_QTY_RULES
from ..core.config import DEFAULT_EXCHANGE, DEFAULT_INITIAL_CAPITAL
from ..core.trading_hours import calc_trading_seconds
from ..core.constants import Signal, Side, Level, Mode

logger = logging.getLogger(__name__)


class MartingaleBase(BaseStrategy):
    """
    Base class for all Martingale-family strategies.
    Provides common position management, trailing stop, HODL protection,
    and cycle management. Subclasses only need to implement entry trigger logic.
    """

    # Subclasses must set PARAMETER_SCHEMA with their own trigger fields + BaseStrategy.COMMON_PARAMETER_FIELDS
    PARAMETER_SCHEMA = None

    def initialize(self):
        # Configuration parameters
        self.symbol = self.config.get("symbol", "UNKNOWN")
        self.max_buy_count = self.config.get("max_buy_count",
            self.config.get("max_levels", 4))  # backward-compat alias
        # 0 = unlimited (no cap on additional buys, bounded only by capital)
        if self.max_buy_count == 0:
            self.max_buy_count = 999999
        self.lot_size_multiplier = self.config.get("lot_size_multiplier",
            self.config.get("pyramid_multiplier", 2.0))  # backward-compat alias
        self.base_quantity = self.config.get("base_quantity", 1)
        self.qty_mode = self.config.get("qty_mode", "fixed")

        # Martingale toggle: off = force single entry (max_buy_count=1)
        use_mart = self.config.get("use_martingale", "on")
        if use_mart == "off" or use_mart is False:
            self.max_buy_count = 1

        self.trailing_start_percent = self.config.get("trailing_start_percent", 0.01)
        self.trailing_stop_percent = self.config.get("trailing_stop_percent", 0.003)
        self.max_loss_percent = self.config.get("max_loss_percent", 0.10)

        # Betting Strategy
        self.betting_strategy = self.config.get("betting_strategy",
            self.config.get("betting_mode", "fixed"))  # backward-compat alias

        # Safety margin: reserve this % of capital (not used for trading)
        self.safety_margin_percent = self.config.get("safety_margin_percent", 1.0)

        # Cycle time limit (0 = unlimited)
        self.cycle_max_hours = self.config.get("cycle_max_hours", 0)

        # Last level all-in mode (True = use remaining capital, False = standard qty)
        allin_val = self.config.get("last_level_allin", "off")
        self.last_level_allin = allin_val == "on" or allin_val is True

        # Trailing start only after reaching last level
        tll_val = self.config.get("trailing_on_last_level", "off")
        self.trailing_on_last_level = tll_val == "on" or tll_val is True

        # Require lower price: L2+ entry only when price < last entry price
        rlp_val = self.config.get("require_lower_price", "off")
        self.require_lower_price = rlp_val == "on" or rlp_val is True

        # Additional buy mode: trigger (strategy signal) or step (auto-buy on N% drop)
        self.additional_buy_mode = self.config.get("additional_buy_mode", "trigger")
        self.additional_buy_step = self.config.get("additional_buy_step", 2.0)
        self.additional_buy_step_ref = self.config.get("additional_buy_step_ref", "last_entry")

        # Futures: liquidation floor (force exit if price within N% of liquidation)
        self.liquidation_floor_pct = self.config.get("liquidation_floor_pct", 3.0)

        # Position side: "long" (default) or "short" (futures only)
        self.position_side = self.config.get("position_side", Side.LONG)
        if isinstance(self.position_side, str):
            self.position_side = self.position_side.lower()
        self.is_short = (self.position_side == Side.SHORT)

        # Tick execution: "tick" (default) or "candle" (check exits every tick, live only)
        self.tick_execution = self.config.get("tick_execution", "tick")

        # Cycle planning variables (calculated at cycle start)
        self.cycle_max_level = None
        self.cycle_reference_price = None
        self.cycle_start_time = None
        self._resolved_base_qty = None  # percent mode: resolved L1 qty
        self._cycle_start_equity = None  # 사이클 시작 시점 총 자산 (수익률 분모)

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

        # Pending order guard: prevents duplicate orders while async callback is pending
        self._pending_entry = False
        self._pending_exit = False

        # Hook for subclass-specific initialization
        self._initialize_trigger()

        # Reconstruct position state from DB execution records (survives PM2 restart)
        self._reconstruct_position_from_db()

    def _reconstruct_position_from_db(self):
        """
        Reconstruct position state from DB execution records after PM2 restart.
        Prevents the strategy from "forgetting" its open position.
        """
        try:
            from ..db.session import SessionLocal
            from ..models.live_trading import LiveTradeExecution, ExecutionStatus

            session_id = getattr(self.context, 'session_id', None)
            if not session_id:
                return

            db = SessionLocal()
            try:
                executions = db.query(LiveTradeExecution).filter(
                    LiveTradeExecution.session_id == session_id,
                    LiveTradeExecution.status == ExecutionStatus.FILLED
                ).order_by(LiveTradeExecution.signal_timestamp).all()

                if not executions:
                    return  # No trades yet, fresh session

                # 1. Count completed cycles and find last CLOSE index
                last_close_idx = -1
                paper_cycles = 0
                real_cycles = 0

                # Determine entry/close signal types based on position side
                # LONG: entry=BUY, close=SELL. SHORT: entry=SELL (with position_side=short metadata), close=BUY
                for i, ex in enumerate(executions):
                    metadata = ex.trade_metadata or {}
                    is_close = metadata.get("level") == Level.CLOSE
                    # Legacy: SELL without position_side metadata = LONG close
                    if not is_close and ex.signal_type == Signal.SELL and metadata.get("position_side", "").lower() != Side.SHORT:
                        is_close = True
                    if is_close:
                        is_paper = ex.is_paper if ex.is_paper is not None else True
                        if is_paper:
                            paper_cycles += 1
                        else:
                            real_cycles += 1
                        last_close_idx = i

                # 2. Restore cycle counters
                self.paper_cycle_id = paper_cycles
                self.real_cycle_id = real_cycles

                # 3. Get entry orders in current open cycle (after last CLOSE)
                open_buys = []
                for i, ex in enumerate(executions):
                    if i <= last_close_idx:
                        continue
                    metadata = ex.trade_metadata or {}
                    is_entry = False
                    if self.position_side == Side.BOTH:
                        # "both" mode: detect direction from metadata
                        if metadata.get("position_side", "").lower() == Side.SHORT and ex.signal_type == Signal.SELL:
                            is_entry = True
                        elif metadata.get("position_side", "").lower() == Side.LONG and ex.signal_type == Signal.BUY:
                            is_entry = True
                        elif ex.signal_type == Signal.BUY and metadata.get("position_side", "").lower() != Side.SHORT:
                            is_entry = True  # Legacy BUY without metadata = LONG
                    elif self.is_short:
                        # SHORT entries: SELL with position_side=short metadata
                        if ex.signal_type == Signal.SELL and metadata.get("position_side", "").lower() == Side.SHORT:
                            is_entry = True
                    else:
                        # LONG entries: BUY signal
                        if ex.signal_type == Signal.BUY:
                            is_entry = True
                    if is_entry:
                        open_buys.append(ex)

                if not open_buys:
                    if paper_cycles > 0 or real_cycles > 0:
                        self.context.log(
                            f"[{self._log_prefix}] DB restore: No open position. "
                            f"Cycles: paper={paper_cycles} real={real_cycles}"
                        )
                    return  # No open position, at L0

                # 4. Reconstruct position state from open BUYs
                total_qty = 0
                total_cost = 0.0
                entries = []
                max_level = 0

                for ex in open_buys:
                    qty = ex.filled_quantity or ex.requested_quantity or 0
                    price = ex.executed_price or ex.theoretical_price or 0
                    metadata = ex.trade_metadata or {}
                    level = metadata.get("level", len(entries) + 1)
                    if not isinstance(level, int):
                        level = len(entries) + 1

                    total_qty += qty
                    total_cost += price * qty
                    max_level = max(max_level, level)

                    entries.append({
                        "level": level,
                        "price": price,
                        "quantity": qty,
                        "time": ex.signal_timestamp.isoformat() if ex.signal_timestamp else ""
                    })

                if total_qty > 0:
                    self.current_level = max_level
                    self.total_quantity = int(total_qty)
                    self.average_price = total_cost / total_qty
                    self.entries = entries
                    self.reference_price = entries[0]["price"]
                    self.peak_price = max(e["price"] for e in entries)
                    self.cycle_start_time = open_buys[0].signal_timestamp

                    # "both" mode: restore is_short from first entry's metadata
                    if self.position_side == Side.BOTH and open_buys:
                        first_meta = open_buys[0].trade_metadata or {}
                        self.is_short = (first_meta.get("position_side", "").lower() == Side.SHORT)

                    self.context.log(
                        f"[{self._log_prefix}] Position RESTORED from DB: "
                        f"L{self.current_level}, {self.total_quantity} qty, "
                        f"Avg: {self.average_price:,.0f}, "
                        f"Cycles: paper={paper_cycles} real={real_cycles}"
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Position reconstruction failed: {e}")
            import traceback
            traceback.print_exc()

    def _calc_position_profit(self, current_price: float) -> float:
        """Direction-aware position profit calculation."""
        if self.is_short:
            return (self.average_price - current_price) * self.total_quantity
        return (current_price - self.average_price) * self.total_quantity

    def _calc_price_return(self, current_price: float) -> float:
        """Direction-aware price return from average cost."""
        if self.average_price <= 0:
            return 0
        if self.is_short:
            return (self.average_price - current_price) / self.average_price
        return (current_price - self.average_price) / self.average_price

    def _initialize_trigger(self):
        """Override in subclasses to initialize trigger-specific state."""
        pass

    @abstractmethod
    def _check_entry_trigger(self, data: Dict[str, Any]) -> Optional[str]:
        """Check if L1 initial entry condition is met.
        Return direction string: "long", "short", or None (no entry).
        When position_side is "long" or "short", MartingaleBase filters mismatched directions.
        When position_side is "both", the returned direction is used directly."""
        pass

    @abstractmethod
    def _check_additional_trigger(self, data: Dict[str, Any]) -> bool:
        """Check if L2+ additional entry condition is met. Return True to buy."""
        pass

    def _check_exits(self, current_price: float) -> bool:
        """Check price-based exit conditions. Returns True if position was liquidated.
        Shared between on_data() (candle close) and on_tick() (every tick).
        Direction-aware: works for both LONG and SHORT positions."""
        if self.current_level <= 0 or self.total_quantity <= 0:
            return False

        position_profit = self._calc_position_profit(current_price)
        # Equity-based return: use cycle start equity as denominator
        if self._cycle_start_equity and self._cycle_start_equity > 0:
            current_return = position_profit / self._cycle_start_equity
        else:
            total_investment = self.average_price * self.total_quantity
            current_return = position_profit / total_investment if total_investment > 0 else 0

        # Cycle time limit (거래시간 기준)
        if self.cycle_max_hours > 0 and self.cycle_start_time:
            current_time = self.context.get_time()
            exchange_name = self.config.get('exchange_name', DEFAULT_EXCHANGE)
            elapsed_hours = calc_trading_seconds(self.cycle_start_time, current_time, exchange_name) / 3600
            if elapsed_hours >= self.cycle_max_hours:
                side_label = "SHORT" if self.is_short else "LONG"
                self.context.log(f"[{self._log_prefix}] CYCLE TIME LIMIT! {elapsed_hours:.1f}h >= {self.cycle_max_hours}h. Close {side_label} @ {current_price:,.0f} (Return: {current_return*100:.2f}%)")
                self._liquidate(current_price)
                return True

        # Update peak price for trailing stop (direction-aware)
        # LONG: peak_price = highest price seen (profit improves as price rises)
        # SHORT: peak_price = lowest price seen (profit improves as price drops)
        if self.is_short:
            if self.peak_price <= 0 or current_price < self.peak_price:
                current_peak_profit = self._calc_position_profit(self.peak_price) if self.peak_price > 0 else 0
                if position_profit > current_peak_profit:
                    self.peak_price = current_price
        else:
            current_peak_profit = (self.peak_price - self.average_price) * self.total_quantity if self.peak_price > 0 else 0
            if position_profit > current_peak_profit:
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

        # Trailing Stop Activation (direction-aware via _calc_price_return)
        price_return = self._calc_price_return(current_price)
        last_level_reached = (self.current_level >= self.max_buy_count)
        if (self.trailing_start_percent > 0
                and not self.trailing_active
                and price_return >= (self.trailing_start_percent / 100)
                and (not self.trailing_on_last_level or last_level_reached)):
            self.trailing_active = True
            self.peak_price = current_price
            self.context.log(f"[{self._log_prefix}] Trailing Stop ACTIVATED. Price Return: {price_return*100:.2f}% (threshold: {self.trailing_start_percent}%)")

        # Trailing Stop Trigger (direction-aware)
        # LONG: drop from peak (high → low). SHORT: rise from trough (low → high)
        if self.trailing_active:
            if self.is_short:
                rise_from_trough = (current_price - self.peak_price) / self.peak_price if self.peak_price > 0 else 0
                if rise_from_trough >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[{self._log_prefix}] Trailing Stop TRIGGERED! Cover SHORT @ {current_price:,.0f} (Position Return: {current_return*100:.2f}%)")
                    self._liquidate(current_price)
                    return True
            else:
                drop_from_peak = (self.peak_price - current_price) / self.peak_price if self.peak_price > 0 else 0
                if drop_from_peak >= (self.trailing_stop_percent / 100):
                    self.context.log(f"[{self._log_prefix}] Trailing Stop TRIGGERED! Sell @ {current_price:,.0f} (Position Return: {current_return*100:.2f}%)")
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
        """Called on every tick when tick_execution='tick'. Checks exit conditions only.
        Entry logic remains candle-based (requires indicator data from completed candles)."""
        if self.tick_execution != "tick":
            return False
        if self.current_level <= 0 or self.total_quantity <= 0:
            return False
        self.last_price = price
        return self._check_exits(price)

    def _check_exit_trigger(self, data: Dict[str, Any]) -> bool:
        """Check if indicator-based exit condition is met. Return True to sell.
        Override in subclass for custom exit logic (e.g., RSI > 70, MACD dead cross).
        Called before trailing/stop-loss checks, after cycle time limit."""
        return False

    def preload_history(self, candles: list):
        """Preload indicator state from historical candles. Override in subclass."""
        pass

    def _on_candle(self, data: Dict[str, Any]):
        """Called on every candle before any logic. Override for indicator updates (e.g., RSI)."""
        pass

    def on_data(self, data: Dict[str, Any]):
        """Called on every price update"""
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

        # 2. Set Reference Price (Cycle Start)
        if self.reference_price is None:
            self.reference_price = current_price
            self.context.log(f"[{self._log_prefix}] Cycle started for {symbol}. Ref: {self.reference_price:,.0f}")

        # 3. Position Management (If holding)
        if self.current_level > 0 and self.total_quantity > 0:
            # 3a-2. Check Indicator-Based Exit (needs candle data → only on candle close)
            position_profit = self._calc_position_profit(current_price)
            # Equity-based return: use cycle start equity as denominator
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

            # Price-based exits (shared with on_tick via _check_exits)
            if self._check_exits(current_price):
                return

            # 3e. Check Additional Entry (L2+)
            if self.current_level < self.max_buy_count and not self.trailing_active:
                # Recalculate cycle_max_level if lost (e.g., after PM2 restart)
                if self.cycle_max_level is None and self.current_level > 0:
                    self.cycle_max_level = self._calculate_max_affordable_level(current_price)
                    self.context.log(f"[{self._log_prefix}] Cycle Plan restored: Max affordable level = L{self.cycle_max_level} @ {current_price:,.0f}")

                # Block further entries beyond the max affordable level for this cycle
                # Note: use 'is not None' to correctly handle cycle_max_level=0 (can't afford any level)
                if self.cycle_max_level is not None and self.current_level >= self.cycle_max_level:
                    pass  # Capital plan exhausted, no more entries
                else:
                    # Require worse price: LONG=lower price, SHORT=higher price
                    if self.require_lower_price and self.entries:
                        last_entry_price = self.entries[-1]["price"]
                        if self.is_short:
                            if current_price <= last_entry_price:
                                return
                        else:
                            if current_price >= last_entry_price:
                                return

                    # Determine entry signal based on additional_buy_mode
                    should_enter = False
                    if self.additional_buy_mode == "step" and self.entries:
                        # Step mode: LONG=auto-buy on price drop, SHORT=auto-short on price rise
                        ref_price = self._get_step_reference_price()
                        if ref_price > 0:
                            if self.is_short:
                                move_pct = (current_price - ref_price) / ref_price * 100
                            else:
                                move_pct = (ref_price - current_price) / ref_price * 100
                            # initial_entry: require cumulative steps (L2=1×step, L3=2×step, ...)
                            if self.additional_buy_step_ref == "initial_entry":
                                required_move = self.additional_buy_step * self.current_level
                            else:
                                required_move = self.additional_buy_step
                            should_enter = move_pct >= required_move
                    else:
                        # Trigger mode: use strategy's signal (default behavior)
                        should_enter = self._check_additional_trigger(data)

                    if should_enter:
                        # Guard: skip if already waiting for pending order
                        if self._pending_entry:
                            return

                        next_level = self.current_level + 1
                        qty = self._calculate_quantity(next_level, current_price)
                        if qty > 0:
                            self._pending_entry = True  # Lock until callback

                            # Callback invoked after order is FILLED or FAILED (async-safe)
                            def on_filled_callback(order_id, filled_qty, filled_price, metadata, _level=next_level):
                                self._pending_entry = False  # Unlock
                                if filled_qty > 0:  # Success
                                    self._add_position(filled_price, filled_qty, _level)
                                    self.context.log(f"[{self._log_prefix}] L{_level} Entry FILLED @ {filled_price:,.0f}. Avg: {self.average_price:,.0f}")
                                # else: async failure, already logged by context

                            actual_side = Side.SHORT if self.is_short else Side.LONG
                            entry_metadata = {"level": next_level, "position_side": actual_side}
                            if self.is_short:
                                result = self.context.short(symbol, qty, metadata=entry_metadata, on_filled=on_filled_callback)
                            else:
                                result = self.context.buy(symbol, qty, metadata=entry_metadata, on_filled=on_filled_callback)
                            if result.get("status") == "failed":
                                self._pending_entry = False  # Unlock on immediate failure
                                self.context.log(f"[{self._log_prefix}] L{next_level} Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

        # 4. Initial Entry (Level 1)
        elif self.current_level == 0:
            # Guard: skip if already waiting for pending order
            if self._pending_entry:
                return

            direction = self._check_entry_trigger(data)
            if direction:
                # Filter: when position_side is fixed ("long"/"short"), only allow matching direction
                if self.position_side != Side.BOTH and direction != self.position_side:
                    return

                # Dynamic direction: set is_short for this cycle
                self.is_short = (direction == Side.SHORT)

                # Record total equity BEFORE L1 entry (cycle return denominator)
                self._cycle_start_equity = self.context.get_total_equity()
                qty = self._calculate_quantity(1, current_price)
                if qty > 0:
                    self._pending_entry = True  # Lock until callback

                    # Callback invoked after order is FILLED or FAILED (async-safe)
                    def on_l1_filled(order_id, filled_qty, filled_price, metadata):
                        self._pending_entry = False  # Unlock
                        if filled_qty > 0:  # Success
                            self._add_position(filled_price, filled_qty, 1)
                            self.peak_price = filled_price
                            self.cycle_start_time = self.context.get_time()
                            self.context.log(f"[{self._log_prefix}] L1 Entry FILLED @ {filled_price:,.0f} (cycle_equity: {self._cycle_start_equity:,.0f})")
                        # else: async failure, already logged by context

                    actual_side = Side.SHORT if self.is_short else Side.LONG
                    entry_metadata = {"level": 1, "position_side": actual_side}
                    if self.is_short:
                        result = self.context.short(symbol, qty, metadata=entry_metadata, on_filled=on_l1_filled)
                    else:
                        result = self.context.buy(symbol, qty, metadata=entry_metadata, on_filled=on_l1_filled)
                    if result.get("status") == "failed":
                        self._pending_entry = False  # Unlock on immediate failure
                        self.context.log(f"[{self._log_prefix}] L1 Initial Entry FAILED: {result.get('reason', 'Unknown')} @ {current_price:,.0f}")

    def _get_leverage(self) -> int:
        """
        Get effective leverage for this strategy.
        Sources (priority order):
        - Paper mode: Always use config parameter (no real exchange dependency)
        - Real mode: Exchange futures data > config parameter > default 1
        """
        config_leverage = self.config.get("leverage", 1)

        # Paper mode: use config value directly (no exchange constraint)
        is_paper = getattr(self.context, 'is_paper', True)
        if is_paper:
            return config_leverage

        # Real mode: prefer actual exchange leverage for safety
        futures_data = self.context.get_futures_data(self.symbol)
        if futures_data and futures_data.get("leverage", 0) > 0:
            return futures_data["leverage"]
        return config_leverage

    def _log_prefix(self) -> str:
        """Log prefix for this strategy. Override in subclass if needed."""
        return "Martingale"

    def _add_position(self, price: float, quantity: int, level: int):
        new_total_qty = self.total_quantity + quantity
        self.average_price = ((self.average_price * self.total_quantity) + (price * quantity)) / new_total_qty
        self.total_quantity = new_total_qty
        self.current_level = level
        self.entries.append({"level": level, "price": price, "quantity": quantity, "time": str(self.context.get_time())})

    def _get_step_reference_price(self) -> float:
        """Get reference price for step-down additional buy mode."""
        if not self.entries:
            return 0
        if self.additional_buy_step_ref == "avg_price":
            return self.average_price
        elif self.additional_buy_step_ref == "initial_entry":
            return self.entries[0]["price"]
        else:  # "last_entry" (default)
            return self.entries[-1]["price"]

    def _liquidate(self, price: float):
        # Guard: skip if already waiting for pending exit order
        if self._pending_exit:
            return

        is_paper = getattr(self.context, 'is_paper', True)
        if is_paper:
            self.paper_cycle_id += 1
            cycle_id = self.paper_cycle_id
        else:
            self.real_cycle_id += 1
            cycle_id = self.real_cycle_id

        self._pending_exit = True  # Lock until callback

        # Callback invoked after sell is FILLED or FAILED (async-safe)
        def on_sell_filled(order_id, filled_qty, filled_price, metadata):
            self._pending_exit = False  # Unlock
            if filled_qty > 0:  # Success
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
            # else: async failure, already logged by context

        actual_side = Side.SHORT if self.is_short else Side.LONG
        close_metadata = {"level": Level.CLOSE, "cycle_id": cycle_id, "is_paper": is_paper, "cycle_start_equity": self._cycle_start_equity, "position_side": actual_side}
        if self.is_short:
            # SHORT position: close via close_position (buy to cover)
            try:
                result = self.context.close_position(self.symbol, metadata=close_metadata)
                # close_position may not support on_filled callback; handle synchronously
                if result.get("status") != "failed":
                    on_sell_filled(None, self.total_quantity, price, close_metadata)
                    return
            except (NotImplementedError, AttributeError):
                pass
            # Fallback: buy to cover
            result = self.context.buy(self.symbol, self.total_quantity, metadata=close_metadata, on_filled=on_sell_filled)
        else:
            result = self.context.sell(self.symbol, self.total_quantity, metadata=close_metadata, on_filled=on_sell_filled)
        if result.get("status") == "failed":
            self._pending_exit = False  # Unlock on immediate failure
            self.context.log(f"[{self._log_prefix}] CLOSE FAILED: {result.get('reason', 'Unknown')}")

    def _resolve_level_qty(self, level: int, price: float) -> float:
        """Calculate quantity for a given level (supports fractional qty for crypto).

        fixed mode:   effective_base * multiplier^(level-1)
                      effective_base = max(base_quantity, min_notional / price)
                      → ensures martingale progression works from actual investment level
        percent mode: L1 resolved once from (capital * base_quantity% / price),
                      then L2+ = resolved_L1 * multiplier^(level-1)
        """
        if self.qty_mode == "percent" and price > 0:
            # Resolve L1 base qty once per cycle, cache it
            if not hasattr(self, '_resolved_base_qty') or self._resolved_base_qty is None:
                # Use SESSION-SPECIFIC equity: cash + own position value
                # (not get_total_equity() which includes cross-session holdings from exchange sync)
                session_cash = getattr(self.context, 'cash', 0)
                own_position_value = self.total_quantity * price if self.total_quantity > 0 and price > 0 else 0
                equity = session_cash + own_position_value
                capital = equity if equity > 0 else getattr(self.context, 'initial_capital', DEFAULT_INITIAL_CAPITAL)
                leverage = self._get_leverage()
                # With leverage, buying power = capital * leverage
                buying_power = capital * leverage
                self.context.log(f"[{self._log_prefix}] Capital for qty calc: {capital:,.0f} x {leverage}x = {buying_power:,.0f} (session: cash={session_cash:,.0f} + position={own_position_value:,.0f})")
                self._resolved_base_qty = buying_power * self.base_quantity / 100 / price
            return self._resolved_base_qty * (self.lot_size_multiplier ** (level - 1))

        # Fixed mode: resolve effective base once per cycle
        raw_base = float(self.base_quantity)
        if price > 0 and (not hasattr(self, '_resolved_base_qty') or self._resolved_base_qty is None):
            exchange_name = self.config.get('exchange_name', DEFAULT_EXCHANGE)
            rules = EXCHANGE_QTY_RULES.get(exchange_name, {})
            min_notional = float(rules.get('min_notional', 0))
            step_size = float(rules.get('step_size', 0.00001))
            if min_notional > 0 and raw_base * price < min_notional and step_size > 0:
                # Bump effective base to meet min_notional so multiplier works correctly
                self._resolved_base_qty = math.ceil(min_notional / price / step_size) * step_size
            else:
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
        exchange_name = self.config.get('exchange_name', DEFAULT_EXCHANGE)
        remaining_cash = usable_capital

        for level in range(1, self.max_buy_count + 1):
            raw_qty = self._resolve_level_qty(level, price)
            # Use adjusted qty with simulated remaining cash for accurate cost
            adj_qty = adjust_qty(raw_qty, exchange_name=exchange_name,
                                 price=price, available_cash=remaining_cash * leverage)
            if adj_qty <= 0:
                break
            level_cost = adj_qty * price / leverage  # Margin required (not full notional)
            cumulative_cost += level_cost

            if cumulative_cost <= usable_capital:
                max_level = level
                remaining_cash = usable_capital - cumulative_cost
            else:
                break

        return max_level

    def _adjust_qty_for_exchange(self, qty: float, price: float) -> float:
        """거래소별 수량 보정 (중앙집중화된 qty_rules 사용)."""
        exchange_name = self.config.get('exchange_name', DEFAULT_EXCHANGE)
        available_cash = getattr(self.context, 'cash', None)
        return adjust_qty(qty, exchange_name=exchange_name, price=price, available_cash=available_cash)

    def _adjust_price_for_exchange(self, price: float) -> float:
        """거래소별 가격 보정 (tick size 기준 반올림)."""
        if price <= 0:
            return 0
        exchange_name = self.config.get('exchange_name', DEFAULT_EXCHANGE)
        # Live 모드: adapter에서 심볼별 동적 필터 조회
        symbol_filters = None
        if hasattr(self.context, 'adapter') and hasattr(self.context.adapter, 'get_symbol_precision'):
            filters = self.context.adapter.get_symbol_precision(self.symbol)
            # exchangeInfo가 실제 로드된 경우만 사용 (기본 fallback 딕셔너리 무시)
            if hasattr(self.context.adapter, '_symbol_filters') and self.symbol in self.context.adapter._symbol_filters:
                symbol_filters = filters
        return adjust_price(price, exchange_name=exchange_name, symbol_filters=symbol_filters)

    def _calculate_quantity(self, level: int, price: float = None) -> float:
        if price is None:
            price = getattr(self, 'last_price', 0)

        if price <= 0:
            return self._adjust_qty_for_exchange(self._resolve_level_qty(level, price), price)

        if self.cycle_max_level is None or level == 1:
            self.cycle_max_level = self._calculate_max_affordable_level(price)
            self.cycle_reference_price = price
            self.context.log(f"[{self._log_prefix}] Cycle Plan: Max affordable level = L{self.cycle_max_level} @ {price:,.0f}")

        effective_max_level = min(self.cycle_max_level, self.max_buy_count)

        if level >= effective_max_level and effective_max_level > 0:
            standard_qty = self._resolve_level_qty(level, price)

            # Check if all-in mode is enabled for final level
            if self.last_level_allin:
                available_cash = getattr(self.context, 'cash', 0)
                safety_reserve = available_cash * (self.safety_margin_percent / 100)
                usable_capital = available_cash - safety_reserve
                lev = self._get_leverage()

                # All-in: invest remaining capital ONLY (with leverage buying power)
                max_qty = usable_capital * lev / price if price > 0 else 0
                self.context.log(f"[{self._log_prefix}] L{level} FINAL LEVEL (ALL-IN): cash={available_cash:,.0f}, lev={lev}x → {max_qty:.1f} qty")
                qty = self._adjust_qty_for_exchange(max_qty, price)
            else:
                self.context.log(f"[{self._log_prefix}] L{level} FINAL LEVEL: Standard qty → {standard_qty} qty")
                qty = self._adjust_qty_for_exchange(standard_qty, price)
        else:
            qty = self._adjust_qty_for_exchange(self._resolve_level_qty(level, price), price)

        # ── Cash guard: NEVER exceed session's available capital ──
        if qty > 0 and price > 0:
            available_cash = max(getattr(self.context, 'cash', 0), 0)
            if available_cash <= 0:
                self.context.log(f"[{self._log_prefix}] CASH GUARD: No cash available, blocking L{level}")
                return 0
            leverage = self._get_leverage()
            safety_reserve = available_cash * (self.safety_margin_percent / 100)
            # With leverage, buying power = (cash - reserve) * leverage / price
            max_affordable = int((available_cash - safety_reserve) * leverage / price)
            if qty > max_affordable:
                self.context.log(f"[{self._log_prefix}] CASH GUARD: L{level} qty {qty} → {max_affordable} (cash: {available_cash:,.0f}, lev: {leverage}x)")
                qty = max_affordable

        return qty

    def get_state(self) -> Dict[str, Any]:
        cur_price = getattr(self, 'last_price', 0)
        # Fallback to context price when last_price is 0 (e.g., after restart with no ticks)
        if cur_price == 0 and hasattr(self, 'context') and self.context:
            cur_price = self.context.get_current_price(self.symbol)
        dip_percent = (self.reference_price - cur_price) / self.reference_price if self.reference_price else 0

        position_profit = self._calc_position_profit(cur_price) if self.average_price > 0 else 0
        total_investment = self.average_price * self.total_quantity if self.average_price > 0 else 0
        profit_percent = position_profit / total_investment if total_investment > 0 else 0

        # Target price: direction-aware, adjusted to exchange tick size
        if self.average_price > 0:
            if self.is_short:
                target_price = self.average_price * (1 - self.trailing_start_percent / 100.0)
            else:
                target_price = self.average_price * (1 + self.trailing_start_percent / 100.0)
            target_price = self._adjust_price_for_exchange(target_price)
        else:
            target_price = 0

        # Stop loss price: direction-aware
        avg = self.average_price
        if avg > 0 and self.max_loss_percent > 0:
            if self.is_short:
                stop_loss_price = avg * (1 + self.max_loss_percent / 100.0)
            else:
                stop_loss_price = avg * (1 - self.max_loss_percent / 100.0)
            stop_loss_price = self._adjust_price_for_exchange(stop_loss_price)
        else:
            stop_loss_price = 0

        # Trailing exit price: based on peak_price when trailing is active
        if self.trailing_active and self.peak_price > 0 and self.trailing_stop_percent > 0:
            if self.is_short:
                trailing_exit_price = self.peak_price * (1 + self.trailing_stop_percent / 100.0)
            else:
                trailing_exit_price = self.peak_price * (1 - self.trailing_stop_percent / 100.0)
            trailing_exit_price = self._adjust_price_for_exchange(trailing_exit_price)
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
            # Pending order status (for UI indicator)
            "pending_entry": getattr(self, '_pending_entry', False),
            "pending_exit": getattr(self, '_pending_exit', False),
        }

    @property
    def _strategy_id(self) -> str:
        """Override in subclass to return strategy registry ID."""
        return "martingale_base"
