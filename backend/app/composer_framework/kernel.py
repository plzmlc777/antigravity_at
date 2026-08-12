"""ExecutionKernel — 거래 판단·체결·회계의 **유일한** 구현.

왜 (통합 실행기 계획 2단계, .claude/plans/unified_execution_engine.md)
  같은 거래 루프가 `backtester.py` 와 `orchestrator.py` 에 각각 손으로 작성돼
  있었다. 둘의 차이가 2026-08-08 사고를 냈다 — 같은 policy, 다른 실행기, 다른
  전략, 실자금 43일. 브래킷 기본값(`or 0.0` vs `or price*0.90`)과 `bars_held`
  off-by-one 이 그것이다. 두 번째 구현이 존재하는 한 같은 사고는 반복된다.

  그래서 바 하나를 처리하는 로직을 여기로 모은다. 백테스터와 오케스트레이터는
  **이 함수를 호출하는 루프**로만 남는다.

계약
  · `step()` 은 순수 함수다. 파일·DB·시계·난수를 건드리지 않는다.
    같은 입력 → 같은 출력. (골든 재생이 이 성질에 의존한다)
  · 강제청산(SL/TP) 판정은 **항상** `policy.decide` 보다 먼저.
  · `bars_held` 는 `policy.decide` 가 보기 **전에** 증가한다.
    (2026-08-08: 뒤에 올려서 policy 가 1 적은 값을 봤고, Day-30 전략이 Day-31 에
     청산됐다. R-3 검증 기준은 `entry_idx + hold_days` 이므로 backtester 가 맞다)
  · 브래킷 `0.0` 은 **비활성**이며 절대 가격 수준으로 읽지 않는다.
    (`high >= 0` / `low <= 0` 은 항상 참이라 진입 즉시 0원에 청산된다)
  · 진입은 그 바의 **시가**에 체결한다. 현행 유지 — "다음 바 시가 체결"로 바꾸는
    것은 전 전략 재판정을 부르므로 통합 범위 밖이다(계획서 §7).

행동 변경 0 원칙
  2단계는 **결과를 1비트도 바꾸지 않는다.** 현재 두 실행기의 격차는 없애는 게
  아니라 `KernelConfig` 로 **표현**해서 각자 지금 행동을 유지시킨다.
  격차 해소는 3단계에서 항목별로 따로 한다.
    · backtester   : 브래킷 기본값 없음(None → 0.0 = 비활성)
    · orchestrator : 브래킷 기본값 SL4% / TP10% (D2, 3b 에서 해소 예정)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Optional

from .policy import Action, PolicyContext, TradingPolicy


@dataclass(frozen=True)
class KernelConfig:
    """실행 회계 파라미터. 두 드라이버의 현행 격차를 값으로 표현한다."""

    size_pct: float = 0.95
    fee_rate: float = 0.0004
    # 2026-08-12 수정: 숏에 수수료가 아예 부과되지 않던 결함. False 는 구동작
    # 재현(A/B 측정) 전용이며 운영에서 쓰지 말 것.
    apply_fee_to_short: bool = True
    # policy 가 브래킷을 **지정하지 않았을 때**(None) 적용할 기본값.
    # None = 브래킷 비활성. 0.0 을 명시적으로 준 경우는 언제나 비활성이다.
    default_sl_pct: Optional[float] = None      # 진입가 대비 손절 폭
    default_tp_pct: Optional[float] = None      # 진입가 대비 익절 폭
    # policy 가 note 없이 exit 한 경우의 사유 문자열. 두 드라이버가 서로 다른
    # 기본값을 써 왔다(backtester "policy" / orchestrator "policy_exit").
    # 2단계는 행동을 바꾸지 않으므로 값으로 표현만 한다. 통일은 3단계 몫.
    policy_exit_reason: str = "policy"


@dataclass(frozen=True)
class KernelState:
    """한 심볼의 포지션·현금 상태. 드라이버가 영속화 형식으로 변환해 보관한다."""

    cash: float
    side: str = "flat"                 # "flat" | "long" | "short"
    qty: float = 0.0
    entry_price: float = 0.0
    entry_ts: Any = None               # 드라이버가 넣는 불투명 값 (거래기록용)
    bars_held: int = 0
    sl_price: float = 0.0              # 0.0 = 비활성
    tp_price: float = 0.0


@dataclass
class ClosedTrade:
    side: str
    entry_ts: Any
    exit_ts: Any
    entry_price: float
    exit_price: float
    qty: float
    return_pct: float
    pnl_cash: float
    exit_reason: str


@dataclass
class StepResult:
    action: Action
    closed: Optional[ClosedTrade] = None
    opened: bool = False
    forced_exit_reason: Optional[str] = None
    equity: float = 0.0
    side_before: str = "flat"


def _forced_exit(st: KernelState, high: float, low: float) -> Optional[tuple[float, str]]:
    """SL/TP 가 바 안에서 닿았는지. 0.0 은 비활성이므로 수준으로 읽지 않는다."""
    if st.side == "long":
        if st.sl_price > 0 and low <= st.sl_price:
            return st.sl_price, "sl"
        if st.tp_price > 0 and high >= st.tp_price:
            return st.tp_price, "tp"
    elif st.side == "short":
        if st.sl_price > 0 and high >= st.sl_price:
            return st.sl_price, "sl"
        if st.tp_price > 0 and low <= st.tp_price:
            return st.tp_price, "tp"
    return None


def close(st: KernelState, exit_price: float, exit_ts: Any, reason: str,
          cfg: KernelConfig) -> tuple[KernelState, ClosedTrade]:
    """포지션 청산. 롱/숏 회계는 여기 한 곳에만 있다."""
    exit_price = float(exit_price)
    qty, entry = st.qty, st.entry_price
    if st.side == "long":
        proceeds = qty * exit_price * (1 - cfg.fee_rate)
        cost = qty * entry * (1 + cfg.fee_rate)
        ret = (proceeds - cost) / cost
        pnl = proceeds - cost
        cash = st.cash + proceeds
    else:  # short
        # 숏 수수료는 양다리 모두 **청산 시점**에 계상한다. 진입 시 차감하면
        # 구방식으로 이미 열려 있는 포지션이 진입 수수료를 낸 적 없는데 청산에서
        # 빼게 돼 보고 수익률과 현금 변화가 어긋난다. 완결 거래 기준으로는
        # 경제적으로 동일하다.
        f = cfg.fee_rate if cfg.apply_fee_to_short else 0.0
        gross = qty * (entry - exit_price)
        fees = qty * entry * f + qty * exit_price * f
        proceeds = gross - fees
        cost = qty * entry
        ret = proceeds / cost
        pnl = proceeds
        cash = st.cash + cost + proceeds

    trade = ClosedTrade(side=st.side, entry_ts=st.entry_ts, exit_ts=exit_ts,
                        entry_price=entry, exit_price=exit_price, qty=qty,
                        return_pct=float(ret), pnl_cash=float(pnl), exit_reason=reason)
    flat = KernelState(cash=cash, side="flat", qty=0.0, entry_price=0.0,
                       entry_ts=None, bars_held=0, sl_price=0.0, tp_price=0.0)
    return flat, trade


def _bracket(action_price: Optional[float], entry: float,
             default_pct: Optional[float], sign: float) -> float:
    """브래킷 해석. None = policy 미지정 → 설정 기본값. 0.0 = 명시적 비활성."""
    if action_price is not None:
        return float(action_price)
    if default_pct is None:
        return 0.0
    return entry * (1.0 + sign * float(default_pct))


def open_position(st: KernelState, kind: str, price: float, ts: Any,
                  action: Action, cfg: KernelConfig) -> KernelState:
    price = float(price)
    if kind == "enter_long":
        denom = price * (1 + cfg.fee_rate)
        qty = (st.cash * cfg.size_pct) / denom
        if qty <= 0:
            return st
        cash = st.cash - qty * denom
        sl = _bracket(action.sl_price, price, cfg.default_sl_pct, -1.0)
        tp = _bracket(action.tp_price, price, cfg.default_tp_pct, +1.0)
        side = "long"
    else:  # enter_short — 담보만 예치, 수수료는 청산 시 계상
        qty = (st.cash * cfg.size_pct) / price
        if qty <= 0:
            return st
        cash = st.cash - qty * price
        sl = _bracket(action.sl_price, price, cfg.default_sl_pct, +1.0)
        tp = _bracket(action.tp_price, price, cfg.default_tp_pct, -1.0)
        side = "short"
    return KernelState(cash=cash, side=side, qty=qty, entry_price=price,
                       entry_ts=ts, bars_held=0, sl_price=sl, tp_price=tp)


def mark(st: KernelState, close_price: float) -> float:
    """평가금액. 숏은 담보를 되돌려 더한다."""
    c = float(close_price)
    if st.side == "long":
        return st.cash + st.qty * c
    if st.side == "short":
        return st.cash + st.qty * (st.entry_price - c) + st.qty * st.entry_price
    return st.cash


def step(state: KernelState, *, ts: Any, open_price: float, high_price: float,
         low_price: float, close_price: float, prediction: float,
         policy: TradingPolicy, cfg: KernelConfig) -> tuple[KernelState, StepResult]:
    """바 하나를 처리한다. 순수 함수 — 부작용 없음.

    순서 (이 순서 자체가 계약이다):
      1) 보유 중이면 bars_held 증가  ← policy 가 보기 전에
      2) 강제청산(SL/TP) 판정        ← policy.decide 보다 먼저
      3) policy.decide
      4) 청산 적용 (강제 우선, 없으면 policy 의 exit)
      5) 플랫이면 진입
      6) 평가
    """
    st = state
    if st.side != "flat":
        st = replace(st, bars_held=st.bars_held + 1)
    side_before = st.side

    forced = _forced_exit(st, float(high_price), float(low_price))

    ctx = PolicyContext(
        timestamp=ts, prediction=prediction,
        open_price=float(open_price), high_price=float(high_price),
        low_price=float(low_price), close_price=float(close_price),
        in_position=(st.side != "flat"), side=st.side,
        entry_price=st.entry_price, bars_held=st.bars_held,
    )
    action = policy.decide(ctx)

    closed: Optional[ClosedTrade] = None
    if forced is not None:
        st, closed = close(st, forced[0], ts, forced[1], cfg)
    elif action.kind == "exit" and st.side != "flat":
        st, closed = close(st, float(open_price), ts,
                           action.note or cfg.policy_exit_reason, cfg)

    opened = False
    if st.side == "flat" and action.kind in ("enter_long", "enter_short"):
        before = st
        st = open_position(st, action.kind, float(open_price), ts, action, cfg)
        opened = st is not before and st.side != "flat"

    return st, StepResult(action=action, closed=closed, opened=opened,
                          forced_exit_reason=(forced[1] if forced else None),
                          equity=mark(st, close_price), side_before=side_before)
