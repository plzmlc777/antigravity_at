"""
SkillContext — IContext 구현체로, 스킬 전략 러너에서 사용.

Python 전략 모듈(martingale_base 등)이 요구하는 IContext 인터페이스를 구현.
로컬 시뮬레이션으로 포지션/자금을 추적하고, on_filled 콜백을 지원하며,
동시에 REST API로 엔진에 시그널을 기록합니다.

LiveContext의 핵심 동작을 재현:
- buy/sell/short/close_position: 즉시 체결 시뮬레이션 + on_filled 콜백
- holdings, cash, equity 추적
- get_current_price, get_time, get_futures_data 등
- process_pending_orders (limit/stop 주문 지원)
"""

import json
import logging
import sys
import urllib.request
import urllib.error
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ─── Bootstrap: backend on sys.path so position_math is importable ──────
# Phase 3d: shared pure math (calc_cash_delta, cap_qty_by_cash) lives in
# backend/app/core/position_math.py — same pattern as binance_market_snapshot
# and symbol_score (Phase 3b/3c). Stdlib-only module, no httpx/SQLAlchemy.
_SCRIPT_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPT_DIR.parent.parent.parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.position_math import (  # noqa: E402
    calc_cash_delta as _calc_cash_delta,
    cap_qty_by_cash as _cap_qty_by_cash,
    realized_pnl_simple as _realized_pnl_simple,
)

logger = logging.getLogger("skill_context")


class SkillContext:
    """
    스킬 전략 러너용 IContext 구현.

    특징:
    - 로컬 시뮬레이션 (포지션/자금/평균가 추적)
    - on_filled 콜백 즉시 호출 (마틴게일 상태 추적용)
    - REST API로 엔진에 시그널 기록 (비교 검증용)
    - LiveContext와 동일한 인터페이스
    """

    def __init__(
        self,
        session_id: str,
        api_url: str,
        initial_capital: float,
        config: Dict[str, Any],
        submit_to_engine: bool = True,
    ):
        self.session_id = session_id
        self.api_url = api_url
        self.initial_capital = initial_capital
        self.config = config
        self.submit_to_engine = submit_to_engine

        # State
        self.cash = initial_capital
        self._holdings: Dict[str, int] = {}
        self._avg_costs: Dict[str, float] = {}
        self.price_map: Dict[str, float] = {}
        self.current_timestamp: datetime = datetime.now()
        self._is_paper = True
        self._is_futures = True

        # Futures data
        self._leverage = config.get("leverage", 1)
        self._futures_data_cache: Dict[str, Dict[str, Any]] = {}

        # Trade log
        self.trades: List[Dict] = []
        self.logs: List[str] = []
        self.equity_curve: List[Dict] = []

        # Pending orders (for limit/stop)
        self._pending_orders: List[Dict] = []

        # Callback tracking
        self._order_callbacks: Dict[str, Callable] = {}

        # Exclusive gate (no-op for skill)
        self._exclusive_gate: Optional[Callable] = None

        # Orders paused flag
        self.orders_paused = False

        # Config snapshot
        self._config_snapshot = None

    # =========================================================================
    # Price & Time
    # =========================================================================

    def get_current_price(self, symbol: str) -> float:
        return self.price_map.get(symbol, 0.0)

    def get_time(self) -> datetime:
        return self.current_timestamp

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_paper(self) -> bool:
        return self._is_paper

    @is_paper.setter
    def is_paper(self, value: bool):
        self._is_paper = value

    @property
    def is_futures(self) -> bool:
        return self._is_futures

    @property
    def holdings(self) -> Dict[str, int]:
        return dict(self._holdings)

    # =========================================================================
    # Equity & Futures Data
    # =========================================================================

    def get_total_equity(self) -> float:
        equity = self.cash
        for symbol, qty in self._holdings.items():
            price = self.price_map.get(symbol, 0.0)
            equity += abs(qty) * price / self._leverage
        return equity

    def get_futures_data(self, symbol: str) -> Dict[str, Any]:
        return self._futures_data_cache.get(symbol, {
            "leverage": self._leverage,
            "liquidation_price": 0,
            "mark_price": self.price_map.get(symbol, 0),
            "funding_rate": 0,
            "unrealized_pnl": 0,
            "position_side": self.config.get("position_side", "long"),
            "position_qty": self._holdings.get(symbol, 0),
            "entry_price": self._avg_costs.get(symbol, 0),
            "adl_quantile": 0,
        })

    def update_futures_data(self, symbol: str, data: Dict[str, Any]):
        self._futures_data_cache[symbol] = data

    def set_config_snapshot(self, config: Dict[str, Any], strategy_id: str = None, symbol: str = None):
        self._config_snapshot = {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "params": config,
            "snapshot_at": datetime.now().isoformat(),
        }

    # =========================================================================
    # Logging
    # =========================================================================

    def log(self, message: str):
        ts = self.current_timestamp.strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.logs.append(entry)
        logger.info(f"[SkillCtx] {message}")

    # =========================================================================
    # Order Execution — Local Simulation + REST Submission
    # =========================================================================

    def buy(self, symbol: str, quantity: int, price: float = 0,
            order_type: str = "market", metadata: Dict[str, Any] = None,
            on_filled: Callable = None, **kwargs) -> Dict[str, Any]:

        exec_price = price if price > 0 else self.price_map.get(symbol, 0)
        if exec_price <= 0:
            return {"status": "failed", "reason": "no_price"}

        # Cash guard — Phase 3d: shared with LiveContext
        leverage = self._leverage
        is_close = metadata and metadata.get("close_position")
        if not is_close and self.initial_capital > 0 and quantity > 0:
            capped_qty, was_capped = _cap_qty_by_cash(
                qty=quantity, price=exec_price,
                available_cash=self.cash, leverage=leverage,
                is_futures=True,
            )
            if was_capped:
                if capped_qty <= 0:
                    self.log(f"BUY BLOCKED: Insufficient cash ({self.cash:,.2f})")
                    return {"status": "failed", "reason": "insufficient_cash"}
                self.log(f"BUY QTY CAPPED: {quantity} → {capped_qty}")
                quantity = capped_qty

        order_id = str(uuid.uuid4())[:8]

        # Local state update
        prev_qty = self._holdings.get(symbol, 0)
        prev_cost = self._avg_costs.get(symbol, 0) * abs(prev_qty)
        new_qty = prev_qty + quantity
        self._holdings[symbol] = new_qty
        if new_qty > 0:
            self._avg_costs[symbol] = (prev_cost + exec_price * quantity) / new_qty

        # Cash delta — Phase 3d: shared with LiveContext (futures long entry)
        self.cash += _calc_cash_delta(
            signal_type="BUY", price=exec_price, qty=quantity,
            is_futures=True, leverage=leverage,
            position_side=self.config.get("position_side", "long"),
        )

        result = {
            "type": "buy", "symbol": symbol, "price": exec_price,
            "quantity": quantity, "time": self.current_timestamp.isoformat(),
            "order_id": order_id, "status": "queued", "metadata": metadata or {},
        }

        self.trades.append(result)

        # Submit to engine for recording
        if self.submit_to_engine:
            self._submit_to_api("buy", symbol, quantity, exec_price, order_type, metadata)

        # Fire on_filled callback (critical for martingale state tracking)
        if on_filled:
            try:
                on_filled(
                    order_id=order_id,
                    filled_qty=quantity,
                    filled_price=exec_price,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error(f"on_filled callback error: {e}")

        return result

    def sell(self, symbol: str, quantity: int, price: float = 0,
             order_type: str = "market", metadata: Dict[str, Any] = None,
             on_filled: Callable = None, **kwargs) -> Dict[str, Any]:

        exec_price = price if price > 0 else self.price_map.get(symbol, 0)
        if exec_price <= 0:
            return {"status": "failed", "reason": "no_price"}

        order_id = str(uuid.uuid4())[:8]

        # Calculate PnL — Phase 3d: shared math (long exit)
        avg_cost = self._avg_costs.get(symbol, 0)
        realized_pnl = _realized_pnl_simple("long", avg_cost, exec_price, quantity)

        # Local state update
        self._holdings[symbol] = self._holdings.get(symbol, 0) - quantity
        if self._holdings[symbol] <= 0:
            self._holdings.pop(symbol, None)
            self._avg_costs.pop(symbol, None)

        # Cash delta — Phase 3d: shared with LiveContext (futures long exit)
        self.cash += _calc_cash_delta(
            signal_type="SELL", price=exec_price, qty=quantity,
            is_futures=True, leverage=self._leverage,
            position_side="long", realized_pnl=realized_pnl,
        )

        result = {
            "type": "sell", "symbol": symbol, "price": exec_price,
            "quantity": quantity, "time": self.current_timestamp.isoformat(),
            "order_id": order_id, "status": "queued",
            "realized_pnl": round(realized_pnl, 4),
            "metadata": metadata or {},
        }

        self.trades.append(result)

        if self.submit_to_engine:
            self._submit_to_api("sell", symbol, quantity, exec_price, order_type, metadata)

        if on_filled:
            try:
                on_filled(
                    order_id=order_id,
                    filled_qty=quantity,
                    filled_price=exec_price,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error(f"on_filled callback error: {e}")

        return result

    def short(self, symbol: str, quantity: float, price: float = 0,
              metadata: Dict[str, Any] = None, on_filled: Callable = None,
              **kwargs) -> Dict[str, Any]:

        exec_price = price if price > 0 else self.price_map.get(symbol, 0)
        if exec_price <= 0:
            return {"status": "failed", "reason": "no_price"}

        order_id = str(uuid.uuid4())[:8]
        quantity = int(quantity)

        # Local state (negative holdings for short)
        prev_qty = self._holdings.get(symbol, 0)
        prev_cost = self._avg_costs.get(symbol, 0) * abs(prev_qty)
        new_qty = prev_qty - quantity  # negative for short
        self._holdings[symbol] = new_qty
        if abs(new_qty) > 0:
            self._avg_costs[symbol] = (prev_cost + exec_price * quantity) / abs(new_qty)

        # Cash delta — Phase 3d: shared with LiveContext (futures short entry)
        self.cash += _calc_cash_delta(
            signal_type="SELL", price=exec_price, qty=quantity,
            is_futures=True, leverage=self._leverage,
            position_side="short",
        )

        result = {
            "type": "short", "symbol": symbol, "price": exec_price,
            "quantity": quantity, "time": self.current_timestamp.isoformat(),
            "order_id": order_id, "status": "queued", "metadata": metadata or {},
        }

        self.trades.append(result)

        if self.submit_to_engine:
            self._submit_to_api("short", symbol, quantity, exec_price, "market", metadata)

        if on_filled:
            try:
                on_filled(
                    order_id=order_id,
                    filled_qty=quantity,
                    filled_price=exec_price,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error(f"on_filled callback error: {e}")

        return result

    def close_position(self, symbol: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        qty = abs(self._holdings.get(symbol, 0))
        if qty <= 0:
            return {"status": "failed", "reason": "no_position"}

        exec_price = self.price_map.get(symbol, 0)
        is_short = self._holdings.get(symbol, 0) < 0
        avg_cost = self._avg_costs.get(symbol, 0)

        # Phase 3d: shared PnL math
        side = "short" if is_short else "long"
        realized_pnl = _realized_pnl_simple(side, avg_cost, exec_price, qty)

        # Clear position
        self._holdings.pop(symbol, None)
        self._avg_costs.pop(symbol, None)

        # Cash delta — Phase 3d: shared with LiveContext (position close)
        # Close direction: long exit = SELL, short exit = BUY
        close_signal = "BUY" if is_short else "SELL"
        self.cash += _calc_cash_delta(
            signal_type=close_signal, price=exec_price, qty=qty,
            is_futures=True, leverage=self._leverage,
            position_side=side, realized_pnl=realized_pnl,
        )

        result = {
            "status": "success", "symbol": symbol, "price": exec_price,
            "quantity": qty, "realized_pnl": round(realized_pnl, 4),
            "message": f"Closed {'SHORT' if is_short else 'LONG'} {qty} @ {exec_price}",
        }

        self.trades.append(result)

        if self.submit_to_engine:
            self._submit_to_api("close_position", symbol, 0, exec_price, "market", metadata)

        return result

    # =========================================================================
    # Pending Orders (Limit/Stop)
    # =========================================================================

    def process_pending_orders(self, candle: Dict[str, Any] = None):
        """대기 주문 체결 확인 — 현재는 market 주문만 지원, 추후 확장."""
        pass

    def cancel_order(self, order_id: str) -> bool:
        return False

    def cancel_all_orders(self):
        pass

    # =========================================================================
    # Capital Management
    # =========================================================================

    def update_equity(self):
        equity = self.get_total_equity()
        self.equity_curve.append({
            "time": self.current_timestamp.isoformat(),
            "equity": equity,
        })

    def reset_cycle_capital(self):
        self.cash = self.initial_capital

    # =========================================================================
    # REST API Submission (for recording in engine)
    # =========================================================================

    def _submit_to_api(self, side: str, symbol: str, quantity: float,
                       price: float, order_type: str = "market",
                       metadata: Dict[str, Any] = None):
        """POST /submit-signal로 시그널을 엔진에 기록."""
        try:
            url = f"{self.api_url}/api/v1/live/session/{self.session_id}/submit-signal"
            payload = {
                "side": side,
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "order_type": order_type,
                "source": "skill:strategy_runner",
                "metadata": metadata or {},
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as e:
            logger.warning(f"Failed to submit signal to engine: {e}")

    # =========================================================================
    # Utility
    # =========================================================================

    def _get_leverage(self, symbol: str) -> int:
        fd = self._futures_data_cache.get(symbol)
        if fd and fd.get("leverage"):
            return fd["leverage"]
        return self._leverage

    def calculate_pnl(self, symbol: str = None) -> float:
        """현재까지의 실현 PnL 합계."""
        return sum(t.get("realized_pnl", 0) for t in self.trades if t.get("realized_pnl"))
