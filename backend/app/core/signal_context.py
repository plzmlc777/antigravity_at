"""
SignalInterceptContext — 어떤 IContext든 래핑하여 ExecutionEngine을 통해
시그널을 평가하는 프록시 컨텍스트.

기존 전략 코드를 수정하지 않고, buy/sell/short/close_position 호출을
가로채어 ExecutionEngine.evaluate()를 거친 후 실제 실행합니다.

사용법:
    # 기존 컨텍스트 생성
    real_context = WaterfallBacktestContext(feeds, ...)

    # ExecutionEngine 생성
    engine = PassthroughExecutor()  # 또는 FilterChainExecutor + 필터

    # 프록시 래핑
    context = SignalInterceptContext(real_context, engine)

    # 전략에 프록시 전달 (전략은 차이를 모름)
    strategy = MyStrategy(context, config)
    strategy.on_data(candle)  # buy/sell 호출 시 ExecutionEngine 거침
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

from .execution_engine import (
    Signal, SignalSide, SignalAction,
    ExecutionDecision, IExecutionEngine, PassthroughExecutor,
)

logger = logging.getLogger(__name__)


class SignalInterceptContext:
    """
    IContext 프록시 — ExecutionEngine을 통한 시그널 평가 레이어.

    모든 IContext 메서드를 내부 컨텍스트에 위임하되,
    buy/sell/short/close_position만 가로채어 Signal → evaluate → execute 흐름을 거칩니다.

    특징:
    - 기존 전략 코드 수정 불필요
    - on_filled 콜백 호환 (실행 시에만 호출)
    - 모든 시그널 기록 (실행/거부 모두)
    - PassthroughExecutor 사용 시 기존 동작과 100% 동일
    """

    def __init__(self, inner: Any, engine: IExecutionEngine = None):
        """
        Args:
            inner: 실제 실행을 담당하는 IContext 구현체
                   (WaterfallBacktestContext, LiveContext 등)
            engine: 시그널 평가 엔진 (None이면 PassthroughExecutor 사용)
        """
        self._inner = inner
        self._engine = engine or PassthroughExecutor()
        self._signals: List[Signal] = []
        self._default_source = "strategy"

    # =========================================================================
    # Intercepted Methods — Signal → ExecutionEngine → RealContext
    # =========================================================================

    def buy(self, symbol: str, quantity: int, price: float = 0,
            order_type: str = "market", metadata: Dict[str, Any] = None,
            on_filled: Callable = None, **kwargs) -> Dict[str, Any]:

        signal = self._create_signal(
            SignalSide.BUY, symbol, quantity, price, order_type,
            metadata, on_filled, **kwargs
        )
        return self._process_signal(signal, on_filled, **kwargs)

    def sell(self, symbol: str, quantity: int, price: float = 0,
             order_type: str = "market", metadata: Dict[str, Any] = None,
             on_filled: Callable = None, **kwargs) -> Dict[str, Any]:

        signal = self._create_signal(
            SignalSide.SELL, symbol, quantity, price, order_type,
            metadata, on_filled, **kwargs
        )
        return self._process_signal(signal, on_filled, **kwargs)

    def short(self, symbol: str, quantity: float, price: float = 0,
              order_type: str = "market", metadata: Dict[str, Any] = None,
              on_filled: Callable = None, **kwargs) -> Dict[str, Any]:

        signal = self._create_signal(
            SignalSide.SHORT, symbol, quantity, price, order_type,
            metadata, on_filled, **kwargs
        )
        return self._process_signal(signal, on_filled, **kwargs)

    def close_position(self, symbol: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        signal = self._create_signal(
            SignalSide.CLOSE_POSITION, symbol, 0, 0, "market", metadata, None
        )

        decision = self._engine.evaluate(signal, self._inner)
        signal.decision = decision

        if decision.action == SignalAction.REJECT:
            signal.executed = False
            signal.exec_result = {"status": "filtered", "reason": decision.reason}
            self._engine.on_signal_rejected(signal)
            self._signals.append(signal)
            return signal.exec_result

        # close_position은 MODIFY 무의미 → 그대로 실행
        result = self._inner.close_position(symbol, metadata)
        signal.executed = result.get("status") != "failed"
        signal.exec_result = result
        self._engine.on_signal_executed(signal)
        self._signals.append(signal)

        logger.info(
            f"[SignalIntercept] Result: executed={signal.executed} "
            f"status={result.get('status', '?')} "
            f"price={signal.exec_price} qty={signal.exec_quantity}"
        )

        return result

    # =========================================================================
    # Core Processing Logic
    # =========================================================================

    def _create_signal(self, side: SignalSide, symbol: str, quantity: float,
                       price: float, order_type: str, metadata: Dict[str, Any],
                       on_filled: Callable, **kwargs) -> Signal:
        try:
            timestamp = self._inner.get_time()
        except Exception:
            timestamp = datetime.now()

        try:
            current_price = self._inner.get_current_price(symbol)
        except Exception:
            current_price = 0

        return Signal(
            side=side,
            symbol=symbol,
            quantity=quantity,
            price=price if price > 0 else current_price,
            order_type=order_type,
            stop_price=kwargs.get('stop_price', 0),
            trailing_delta=kwargs.get('trailing_delta', 0),
            linked_orders=kwargs.get('linked_orders'),
            on_filled=on_filled,
            metadata=metadata,
            timestamp=timestamp,
            source=self._default_source,
        )

    def _process_signal(self, signal: Signal, on_filled: Callable,
                        **kwargs) -> Dict[str, Any]:
        """Signal → evaluate → execute/reject."""

        decision = self._engine.evaluate(signal, self._inner)
        signal.decision = decision

        logger.info(
            f"[SignalIntercept] [{signal.source}] {signal.side.value} {signal.symbol} "
            f"qty={signal.quantity} price={signal.price} "
            f"→ {decision.action.value}"
            f"{(' reason=' + decision.reason) if decision.reason else ''}"
        )

        # REJECT → 실행하지 않음
        if decision.action == SignalAction.REJECT:
            signal.executed = False
            signal.exec_result = {"status": "filtered", "reason": decision.reason}
            self._engine.on_signal_rejected(signal)
            self._signals.append(signal)
            return signal.exec_result

        # MODIFY → 시그널 파라미터가 이미 evaluate()에서 변경됨
        # (FilterChainExecutor가 signal 속성을 직접 수정)

        # EXECUTE / MODIFY → 실제 컨텍스트에 실행 위임
        result = self._dispatch(signal, on_filled, **kwargs)

        # 실행 결과 기록
        if result.get("status") not in ("failed", "pending"):
            signal.executed = True
            signal.exec_price = result.get("price", signal.price)
            signal.exec_quantity = result.get("quantity", signal.quantity)
        else:
            signal.executed = False

        signal.exec_result = result
        self._engine.on_signal_executed(signal)
        self._signals.append(signal)
        return result

    def _dispatch(self, signal: Signal, on_filled: Callable,
                  **kwargs) -> Dict[str, Any]:
        """시그널을 실제 컨텍스트의 buy/sell/short로 라우팅."""
        if signal.side == SignalSide.BUY:
            return self._inner.buy(
                signal.symbol, int(signal.quantity), signal.price,
                signal.order_type, signal.metadata, on_filled, **kwargs
            )
        elif signal.side == SignalSide.SELL:
            return self._inner.sell(
                signal.symbol, int(signal.quantity), signal.price,
                signal.order_type, signal.metadata, on_filled, **kwargs
            )
        elif signal.side == SignalSide.SHORT:
            # NOTE: LiveContext.short() has no order_type param (unlike buy/sell),
            # so it is omitted here — short is market-only for now. Limit-order
            # short (entry slippage guard) requires adding order_type to short().
            return self._inner.short(
                signal.symbol, int(signal.quantity), signal.price,
                signal.metadata, on_filled, **kwargs
            )
        else:
            return {"status": "failed", "reason": f"Unknown side: {signal.side}"}

    # =========================================================================
    # Delegated Methods — 내부 컨텍스트에 그대로 위임
    # =========================================================================

    @property
    def holdings(self) -> Dict[str, int]:
        return self._inner.holdings

    @property
    def is_paper(self) -> bool:
        return self._inner.is_paper

    def get_current_price(self, symbol: str) -> float:
        return self._inner.get_current_price(symbol)

    def get_time(self) -> datetime:
        return self._inner.get_time()

    def log(self, message: str):
        self._inner.log(message)

    def get_total_equity(self) -> float:
        return self._inner.get_total_equity()

    def get_futures_data(self, symbol: str) -> Dict[str, Any]:
        return self._inner.get_futures_data(symbol)

    def process_pending_orders(self, candle: Dict[str, Any] = None):
        if hasattr(self._inner, 'process_pending_orders'):
            self._inner.process_pending_orders(candle)

    def cancel_order(self, order_id: str) -> bool:
        if hasattr(self._inner, 'cancel_order'):
            return self._inner.cancel_order(order_id)
        return False

    def cancel_all_orders(self):
        if hasattr(self._inner, 'cancel_all_orders'):
            self._inner.cancel_all_orders()

    def update_equity(self):
        if hasattr(self._inner, 'update_equity'):
            self._inner.update_equity()

    def reset_cycle_capital(self):
        if hasattr(self._inner, 'reset_cycle_capital'):
            self._inner.reset_cycle_capital()

    # =========================================================================
    # Dynamic Attribute Delegation — 위에 정의되지 않은 속성은 inner에 위임
    # =========================================================================

    def __getattr__(self, name: str):
        """명시적으로 정의되지 않은 속성은 내부 컨텍스트에서 조회."""
        # __getattr__은 일반 조회 실패 시에만 호출됨 (위의 명시적 메서드가 우선)
        return getattr(self._inner, name)

    # =========================================================================
    # External Signal Submission (Skill / API)
    # =========================================================================

    def submit_external_signal(
        self, side: str, symbol: str, quantity: float,
        price: float = 0, order_type: str = "market",
        metadata: Dict[str, Any] = None, source: str = "skill",
    ) -> Dict[str, Any]:
        """
        외부 소스(스킬, API 등)에서 시그널을 수신하여 ExecutionEngine으로 평가.

        Args:
            side: "buy", "sell", "short", "close_position"
            symbol: 종목 코드
            quantity: 수량 (close_position이면 0)
            price: 가격 (0이면 현재가)
            order_type: "market", "limit" 등
            metadata: 추가 메타데이터
            source: 시그널 소스 (e.g. "skill:rsi_analysis")
        """
        side_map = {
            "buy": SignalSide.BUY,
            "sell": SignalSide.SELL,
            "short": SignalSide.SHORT,
            "close_position": SignalSide.CLOSE_POSITION,
        }
        signal_side = side_map.get(side.lower())
        if not signal_side:
            return {"status": "failed", "reason": f"Unknown side: {side}"}

        try:
            timestamp = self._inner.get_time()
        except Exception:
            timestamp = datetime.now()

        try:
            current_price = self._inner.get_current_price(symbol)
        except Exception:
            current_price = 0

        signal = Signal(
            side=signal_side,
            symbol=symbol,
            quantity=quantity,
            price=price if price > 0 else current_price,
            order_type=order_type,
            metadata=metadata,
            timestamp=timestamp,
            source=source,
        )

        # close_position은 별도 처리
        if signal_side == SignalSide.CLOSE_POSITION:
            decision = self._engine.evaluate(signal, self._inner)
            signal.decision = decision

            logger.info(
                f"[SignalIntercept] [{source}] close_position {symbol} "
                f"→ {decision.action.value}"
            )

            if decision.action == SignalAction.REJECT:
                signal.executed = False
                signal.exec_result = {"status": "filtered", "reason": decision.reason}
                self._engine.on_signal_rejected(signal)
                self._signals.append(signal)
                return signal.exec_result

            result = self._inner.close_position(symbol, metadata)
            signal.executed = result.get("status") != "failed"
            signal.exec_result = result
            self._engine.on_signal_executed(signal)
            self._signals.append(signal)
            return result

        # buy/sell/short → 기존 _process_signal 파이프라인 사용
        return self._process_signal(signal, on_filled=None)

    # =========================================================================
    # Signal Access
    # =========================================================================

    @property
    def signals(self) -> List[Signal]:
        """캡처된 모든 시그널 반환."""
        return self._signals

    @property
    def executed_signals(self) -> List[Signal]:
        """실행된 시그널만 반환."""
        return [s for s in self._signals if s.executed]

    @property
    def rejected_signals(self) -> List[Signal]:
        """거부된 시그널만 반환."""
        return [s for s in self._signals if s.decision and s.decision.action == SignalAction.REJECT]

    def get_signal_stats(self) -> Dict[str, Any]:
        """시그널 통계."""
        buy_count = sum(1 for s in self._signals if s.side == SignalSide.BUY)
        sell_count = sum(1 for s in self._signals if s.side in (SignalSide.SELL, SignalSide.CLOSE_POSITION))
        short_count = sum(1 for s in self._signals if s.side == SignalSide.SHORT)
        executed = sum(1 for s in self._signals if s.executed)
        rejected = sum(1 for s in self._signals
                       if s.decision and s.decision.action == SignalAction.REJECT)

        return {
            "total": len(self._signals),
            "buy": buy_count,
            "sell": sell_count,
            "short": short_count,
            "executed": executed,
            "rejected": rejected,
            "execution_rate": f"{executed / len(self._signals) * 100:.1f}%" if self._signals else "0%",
        }
