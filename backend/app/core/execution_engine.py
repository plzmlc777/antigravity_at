"""
ExecutionEngine — Signal/Execution 분리 아키텍처의 핵심 모듈.

기존 전략 코드를 수정하지 않고, 시그널 생성과 실행 사이에
필터링/수정/승인 레이어를 삽입할 수 있는 구조.

Architecture:
    Strategy.on_data(candle)
        ↓ context.buy/sell 호출
    SignalInterceptContext (Phase 8)
        ↓ Signal 생성
    ExecutionEngine.evaluate(signal)
        ↓ ExecutionDecision (EXECUTE / REJECT / MODIFY)
    RealContext.buy/sell 실행

이 모듈은 Phase 7에서 Signal Protocol과 ExecutionEngine 인터페이스를 정의합니다.
Phase 8에서 SignalInterceptContext가 이 모듈을 사용합니다.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field


# =============================================================================
# Signal Protocol
# =============================================================================

class SignalSide(str, Enum):
    """매매 방향."""
    BUY = "buy"
    SELL = "sell"
    SHORT = "short"
    CLOSE_POSITION = "close_position"


class SignalAction(str, Enum):
    """ExecutionEngine의 판단 결과."""
    EXECUTE = "execute"     # 그대로 실행
    REJECT = "reject"       # 거부 (실행하지 않음)
    MODIFY = "modify"       # 수정 후 실행 (수량/가격 변경 등)


@dataclass
class Signal:
    """
    전략이 발생시킨 매매 시그널.

    기존 context.buy/sell 호출의 모든 파라미터를 포함하며,
    ExecutionEngine이 평가/필터링할 수 있는 구조화된 데이터.

    on_filled 콜백을 포함하여 기존 전략과의 호환성을 유지합니다.
    """
    # 필수 필드
    side: SignalSide
    symbol: str
    quantity: float
    price: float = 0.0
    order_type: str = "market"

    # 주문 옵션 (PendingOrderBook 연동)
    stop_price: float = 0.0
    trailing_delta: float = 0.0
    linked_orders: Optional[List[Dict]] = None

    # 콜백 (전략 호환성)
    on_filled: Optional[Callable] = None

    # 메타데이터
    metadata: Optional[Dict[str, Any]] = None
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: Optional[datetime] = None
    source: str = ""  # 시그널 발생 소스 (전략명 등)

    # 실행 결과 (ExecutionEngine이 채움)
    decision: Optional[ExecutionDecision] = None
    executed: bool = False
    exec_price: float = 0.0
    exec_quantity: float = 0.0
    exec_result: Optional[Dict[str, Any]] = None

    def copy_with(self, **overrides) -> Signal:
        """시그널 복사 (수정 실행 시 사용)."""
        import copy
        new = copy.copy(self)
        for k, v in overrides.items():
            setattr(new, k, v)
        new.signal_id = str(uuid.uuid4())[:8]  # 새 ID 부여
        return new


@dataclass
class ExecutionDecision:
    """
    ExecutionEngine의 시그널 평가 결과.

    action이 MODIFY인 경우, modified_params에 변경할 필드를 담습니다.
    예: {"quantity": 50} → 수량을 50으로 변경하여 실행
    """
    action: SignalAction
    reason: str = ""
    modified_params: Optional[Dict[str, Any]] = None
    filter_name: str = ""  # 어떤 필터가 판단했는지

    @staticmethod
    def execute(reason: str = "") -> ExecutionDecision:
        """실행 결정 생성 헬퍼."""
        return ExecutionDecision(action=SignalAction.EXECUTE, reason=reason)

    @staticmethod
    def reject(reason: str, filter_name: str = "") -> ExecutionDecision:
        """거부 결정 생성 헬퍼."""
        return ExecutionDecision(
            action=SignalAction.REJECT, reason=reason, filter_name=filter_name
        )

    @staticmethod
    def modify(modified_params: Dict[str, Any], reason: str = "", filter_name: str = "") -> ExecutionDecision:
        """수정 결정 생성 헬퍼."""
        return ExecutionDecision(
            action=SignalAction.MODIFY, reason=reason,
            modified_params=modified_params, filter_name=filter_name
        )


# =============================================================================
# Signal Filter Protocol
# =============================================================================

class ISignalFilter(ABC):
    """
    시그널 필터 인터페이스.

    ExecutionEngine의 필터 체인에 등록하여 시그널을 순차적으로 평가.
    하나의 필터가 REJECT하면 후속 필터는 평가하지 않음.
    MODIFY는 시그널 파라미터를 변경하고 다음 필터로 전달.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """필터 이름 (로깅/디버깅용)."""
        pass

    @abstractmethod
    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        """
        시그널 평가.

        Args:
            signal: 평가할 시그널
            context: 현재 실행 컨텍스트 (포지션, 잔고 등 참조)

        Returns:
            ExecutionDecision - EXECUTE(통과), REJECT(거부), MODIFY(수정)
        """
        pass


# =============================================================================
# ExecutionEngine Interface
# =============================================================================

class IExecutionEngine(ABC):
    """
    실행 엔진 인터페이스.

    시그널을 받아서 필터 체인을 통과시킨 후 최종 실행 결정을 내립니다.
    """

    @abstractmethod
    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        """시그널을 평가하여 실행 결정을 반환."""
        pass

    @abstractmethod
    def on_signal_executed(self, signal: Signal):
        """시그널 실행 후 호출 (통계/로깅용)."""
        pass

    @abstractmethod
    def on_signal_rejected(self, signal: Signal):
        """시그널 거부 후 호출 (통계/로깅용)."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """실행 엔진 통계 반환."""
        pass


# =============================================================================
# PassthroughExecutor — 기본 실행 엔진 (모든 시그널 통과)
# =============================================================================

class PassthroughExecutor(IExecutionEngine):
    """
    모든 시그널을 그대로 실행하는 기본 실행 엔진.
    기존 동작과 동일 — 필터 없이 모든 시그널을 EXECUTE.

    SignalInterceptContext와 결합 시 기존 v1 엔진과 동일한 결과를 보장.
    """

    def __init__(self):
        self._executed_count = 0
        self._rejected_count = 0
        self._signals: List[Signal] = []

    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        """모든 시그널 무조건 실행."""
        return ExecutionDecision.execute()

    def on_signal_executed(self, signal: Signal):
        self._executed_count += 1
        self._signals.append(signal)

    def on_signal_rejected(self, signal: Signal):
        self._rejected_count += 1
        self._signals.append(signal)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "engine": "passthrough",
            "executed": self._executed_count,
            "rejected": self._rejected_count,
            "total": self._executed_count + self._rejected_count,
        }

    @property
    def signals(self) -> List[Signal]:
        return self._signals


# =============================================================================
# FilterChainExecutor — 필터 체인 기반 실행 엔진
# =============================================================================

class FilterChainExecutor(IExecutionEngine):
    """
    필터 체인을 통해 시그널을 순차 평가하는 실행 엔진.

    사용법:
        engine = FilterChainExecutor()
        engine.add_filter(MaxPositionFilter(max_qty=100))
        engine.add_filter(TimeRestrictionFilter(start=9, end=15))

    필터 평가 순서:
    1. 첫 번째 필터 → EXECUTE → 다음 필터
    2. 첫 번째 필터 → REJECT → 즉시 거부 (후속 필터 스킵)
    3. 첫 번째 필터 → MODIFY → 파라미터 변경 후 다음 필터
    """

    def __init__(self):
        self._filters: List[ISignalFilter] = []
        self._executed_count = 0
        self._rejected_count = 0
        self._modified_count = 0
        self._signals: List[Signal] = []
        self._rejection_reasons: Dict[str, int] = {}  # filter_name → count

    def add_filter(self, f: ISignalFilter) -> FilterChainExecutor:
        """필터 추가 (체이닝 지원)."""
        self._filters.append(f)
        return self

    def remove_filter(self, name: str) -> bool:
        """이름으로 필터 제거."""
        before = len(self._filters)
        self._filters = [f for f in self._filters if f.name != name]
        return len(self._filters) < before

    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        """필터 체인 순차 평가."""
        if not self._filters:
            return ExecutionDecision.execute()

        current_signal = signal
        for f in self._filters:
            decision = f.evaluate(current_signal, context)

            if decision.action == SignalAction.REJECT:
                decision.filter_name = f.name
                return decision

            if decision.action == SignalAction.MODIFY and decision.modified_params:
                # 시그널 파라미터 수정 후 다음 필터로 전달
                for key, value in decision.modified_params.items():
                    if hasattr(current_signal, key):
                        setattr(current_signal, key, value)
                self._modified_count += 1

        return ExecutionDecision.execute()

    def on_signal_executed(self, signal: Signal):
        self._executed_count += 1
        self._signals.append(signal)

    def on_signal_rejected(self, signal: Signal):
        self._rejected_count += 1
        self._signals.append(signal)
        if signal.decision and signal.decision.filter_name:
            name = signal.decision.filter_name
            self._rejection_reasons[name] = self._rejection_reasons.get(name, 0) + 1

    def get_stats(self) -> Dict[str, Any]:
        return {
            "engine": "filter_chain",
            "filters": [f.name for f in self._filters],
            "executed": self._executed_count,
            "rejected": self._rejected_count,
            "modified": self._modified_count,
            "total": self._executed_count + self._rejected_count,
            "rejection_reasons": self._rejection_reasons,
        }

    @property
    def signals(self) -> List[Signal]:
        return self._signals


# =============================================================================
# 내장 필터 예시
# =============================================================================

class MaxPositionSizeFilter(ISignalFilter):
    """최대 포지션 크기 제한 필터."""

    def __init__(self, max_quantity: float):
        self._max_quantity = max_quantity

    @property
    def name(self) -> str:
        return f"max_position_size({self._max_quantity})"

    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        if signal.side in (SignalSide.BUY, SignalSide.SHORT):
            current_holdings = getattr(context, 'holdings', {})
            current_qty = current_holdings.get(signal.symbol, 0)
            if current_qty + signal.quantity > self._max_quantity:
                allowed = max(0, self._max_quantity - current_qty)
                if allowed <= 0:
                    return ExecutionDecision.reject(
                        f"Position limit reached: {current_qty}/{self._max_quantity}"
                    )
                return ExecutionDecision.modify(
                    {"quantity": allowed},
                    f"Quantity reduced: {signal.quantity} → {allowed}"
                )
        return ExecutionDecision.execute()


class MaxConsecutiveLossFilter(ISignalFilter):
    """연속 손실 횟수 제한 필터. N회 연속 손실 후 신규 진입 차단."""

    def __init__(self, max_consecutive: int = 3):
        self._max_consecutive = max_consecutive
        self._consecutive_losses = 0

    @property
    def name(self) -> str:
        return f"max_consecutive_loss({self._max_consecutive})"

    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        # 진입 시그널만 필터링 (청산은 항상 허용)
        if signal.side in (SignalSide.BUY, SignalSide.SHORT):
            if self._consecutive_losses >= self._max_consecutive:
                return ExecutionDecision.reject(
                    f"Consecutive losses: {self._consecutive_losses}/{self._max_consecutive}"
                )
        return ExecutionDecision.execute()

    def on_trade_closed(self, pnl: float):
        """사이클 종료 시 호출하여 연속 손실 추적."""
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0


class TimeRestrictionFilter(ISignalFilter):
    """거래 시간 제한 필터. 지정 시간대 외 진입 차단."""

    def __init__(self, start_hour: int = 9, end_hour: int = 15,
                 start_minute: int = 0, end_minute: int = 20):
        self._start_hour = start_hour
        self._start_minute = start_minute
        self._end_hour = end_hour
        self._end_minute = end_minute

    @property
    def name(self) -> str:
        return f"time_restriction({self._start_hour}:{self._start_minute:02d}-{self._end_hour}:{self._end_minute:02d})"

    def evaluate(self, signal: Signal, context: Any) -> ExecutionDecision:
        # 청산은 항상 허용
        if signal.side in (SignalSide.SELL, SignalSide.CLOSE_POSITION):
            return ExecutionDecision.execute()

        try:
            now = context.get_time() if hasattr(context, 'get_time') else datetime.now()
            start = now.replace(hour=self._start_hour, minute=self._start_minute, second=0)
            end = now.replace(hour=self._end_hour, minute=self._end_minute, second=0)
            if not (start <= now <= end):
                return ExecutionDecision.reject(
                    f"Outside trading hours: {now.strftime('%H:%M')}"
                )
        except Exception:
            pass

        return ExecutionDecision.execute()
