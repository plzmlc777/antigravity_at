"""Canon (정본) — 거래 판단·체결·회계의 **유일한** 구현.

  백테스트·페이퍼·실거래는 모두 이 한 판본을 따른다. 사본이 따로 존재하지
  않으므로 "어느 쪽이 맞는가"라는 질문 자체가 생기지 않는다.

  두 관문이 이 판본을 지킨다:
    · 골든 재생   — 오늘 판본이 **어제 판본과** 같은가 (회귀 방향)
    · 파리티 게이트 — 두 사본이 **서로** 같은가 (교차 방향)
  둘 중 하나라도 어긋나면 정본 이탈(non-canonical drift)이며 주문을 막는다.

왜 (정본 엔진 계획 2단계, .claude/plans/unified_execution_engine.md)
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
from typing import Any, Mapping, Optional

from .policy import Action, PolicyContext, TradingPolicy


@dataclass(frozen=True)
class KernelConfig:
    """실행 회계 파라미터. 두 드라이버의 현행 격차를 값으로 표현한다."""

    size_pct: float = 0.95
    fee_rate: float = 0.0004                    # 테이커 (기본)
    # 메이커 요율. None 이면 fee_rate 를 양쪽에 쓴다 = 종전 동작.
    #
    # 2026-08-13: LimitFill 을 넣고 보니 지정가 체결도 테이커로 계산되고 있었다.
    # 방향이 보수적(비용 과대)이라 위험하진 않지만 틀렸고, 메이커가 수익원인
    # 전략(MM·그리드)에서는 결론이 뒤집힌다.
    # 바이낸스 선물 VIP0: 메이커 2bp / 테이커 5bp.
    fee_rate_maker: Optional[float] = None
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
    # 진입이 메이커였는가. 숏은 진입 수수료도 **청산 시** 계상하므로(3a) 상태가
    # 기억해야 한다.
    entry_maker: bool = False


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
    # 한 바에 여러 청산이 날 수 있다(강제청산 + 부분청산, 사다리 정리 등).
    closed: tuple[ClosedTrade, ...] = ()
    opened: bool = False
    forced_exit_reason: Optional[str] = None
    equity: float = 0.0
    side_before: str = "flat"


def _fee(cfg: KernelConfig, maker: bool) -> float:
    """유효 수수료율. 메이커 요율이 없으면 종전대로 단일 요율을 쓴다."""
    if maker and cfg.fee_rate_maker is not None:
        return float(cfg.fee_rate_maker)
    return float(cfg.fee_rate)


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
          cfg: KernelConfig, frac: float = 1.0,
          exit_maker: bool = False) -> tuple[KernelState, ClosedTrade]:
    """포지션 청산. 롱/숏 회계는 여기 한 곳에만 있다.

    `frac` < 1.0 이면 **부분 청산**이다. 그만큼만 실현하고 나머지는 진입가와
    보유바수를 유지한다 — 남은 포지션은 같은 거래의 연속이지 새 거래가 아니다.
    기본값 1.0 이 현행(전량 청산)이다.
    """
    exit_price = float(exit_price)
    frac = max(0.0, min(1.0, float(frac)))
    qty, entry = st.qty * frac, st.entry_price
    f_in, f_out = _fee(cfg, st.entry_maker), _fee(cfg, exit_maker)
    if st.side == "long":
        proceeds = qty * exit_price * (1 - f_out)
        cost = qty * entry * (1 + f_in)
        ret = (proceeds - cost) / cost
        pnl = proceeds - cost
        cash = st.cash + proceeds
    else:  # short
        # 숏 수수료는 양다리 모두 **청산 시점**에 계상한다. 진입 시 차감하면
        # 구방식으로 이미 열려 있는 포지션이 진입 수수료를 낸 적 없는데 청산에서
        # 빼게 돼 보고 수익률과 현금 변화가 어긋난다. 완결 거래 기준으로는
        # 경제적으로 동일하다.
        gross = qty * (entry - exit_price)
        if cfg.apply_fee_to_short:
            fees = qty * entry * f_in + qty * exit_price * f_out
        else:
            fees = 0.0
        proceeds = gross - fees
        cost = qty * entry
        ret = proceeds / cost
        pnl = proceeds
        cash = st.cash + cost + proceeds

    trade = ClosedTrade(side=st.side, entry_ts=st.entry_ts, exit_ts=exit_ts,
                        entry_price=entry, exit_price=exit_price, qty=qty,
                        return_pct=float(ret), pnl_cash=float(pnl), exit_reason=reason)
    left = st.qty - qty
    if left <= 1e-12:
        after = KernelState(cash=cash, side="flat", qty=0.0, entry_price=0.0,
                            entry_ts=None, bars_held=0, sl_price=0.0, tp_price=0.0)
    else:
        # 부분 청산 — 남은 수량은 진입가·진입시각·보유바수·브래킷을 그대로 잇는다.
        after = replace(st, cash=cash, qty=left)
    return after, trade


def _bracket(action_price: Optional[float], entry: float,
             default_pct: Optional[float], sign: float) -> float:
    """브래킷 해석. None = policy 미지정 → 설정 기본값. 0.0 = 명시적 비활성."""
    if action_price is not None:
        return float(action_price)
    if default_pct is None:
        return 0.0
    return entry * (1.0 + sign * float(default_pct))


def open_position(st: KernelState, kind: str, bar: dict, ts: Any,
                  action: Action, cfg: KernelConfig) -> KernelState:
    """진입 또는 **추가 진입**. 체결가·수량은 규칙이 정한다 — 여기 분기는 없다.

    추가 진입(피라미딩)은 거래소와 같은 방식이다: 바이낸스 선물 단방향 모드는
    심볼당 포지션을 하나로 넷팅하고 진입가를 **가중평균**으로 관리한다. leg 를
    따로 들면 오히려 실제보다 세분화돼 실거래와 어긋난다.

    반대 방향 진입은 무시한다 — 뒤집으려면 먼저 청산해야 한다. 정본이 조용히
    뒤집으면 정책이 의도하지 않은 거래가 생긴다.
    """
    side = "long" if kind == "enter_long" else "short"
    if st.side != "flat" and st.side != side:
        return st

    px = action.fill.price(kind=kind, **bar)
    if px is None or px <= 0:
        return st                      # 지정가 미체결 등 — 정상 경로다
    px = float(px)

    sign_sl = -1.0 if side == "long" else +1.0
    sign_tp = +1.0 if side == "long" else -1.0
    sl = _bracket(action.sl_price, px, cfg.default_sl_pct, sign_sl)
    tp = _bracket(action.tp_price, px, cfg.default_tp_pct, sign_tp)

    qty = action.sizing.qty(cash=st.cash, price=px, sl_price=sl,
                            size_pct=cfg.size_pct,
                            fee_rate=_fee(cfg, bool(getattr(action.fill, "is_maker", False))),
                            side=side)
    if qty <= 0:
        return st

    maker = bool(getattr(action.fill, "is_maker", False))
    if side == "long":
        cost = qty * px * (1 + _fee(cfg, maker))
    else:
        cost = qty * px                # 담보만. 수수료는 청산 시 계상(3a 참조)
    if cost > st.cash:                 # 규칙이 과하게 잡으면 가용까지만
        if px <= 0:
            return st
        scale = st.cash / cost
        qty *= scale
        cost = st.cash
    if qty <= 0:
        return st

    if st.side == "flat":
        return KernelState(cash=st.cash - cost, side=side, qty=qty, entry_price=px,
                           entry_ts=ts, bars_held=0, sl_price=sl, tp_price=tp,
                           entry_maker=maker)

    # 추가 진입 — 가중평균 진입가. 보유바수는 **최초 진입 기준을 유지**한다
    # (보유 상한이 추가 진입 때마다 초기화되면 max_hold 가 무력해진다).
    total = st.qty + qty
    avg = (st.qty * st.entry_price + qty * px) / total
    return replace(st, cash=st.cash - cost, qty=total, entry_price=avg,
                   sl_price=sl if action.sl_price is not None else st.sl_price,
                   tp_price=tp if action.tp_price is not None else st.tp_price)


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
         policy: TradingPolicy, cfg: KernelConfig,
         features: Optional[Mapping[str, Any]] = None) -> tuple[KernelState, StepResult]:
    """바 하나를 처리한다. 순수 함수 — 부작용 없음.

    순서 (이 순서 자체가 계약이다):
      1) 보유 중이면 bars_held 증가  ← policy 가 보기 전에
      2) 강제청산(SL/TP) 판정        ← policy.decide 보다 먼저
      3) policy.decide
      4) 지시를 **순서대로** 적용 (청산 → 진입)
      5) 평가

    `policy.decide` 는 지시 **하나 또는 여러 개**를 반환할 수 있다. 여러 개는
    한 바에 사다리를 놓거나(그리드·마틴게일) 분할 진입할 때 쓴다. 하나만
    반환하면 예전과 완전히 같다.
    """
    st = state
    if st.side != "flat":
        st = replace(st, bars_held=st.bars_held + 1)
    side_before = st.side

    forced = _forced_exit(st, float(high_price), float(low_price))

    bar = {"open_price": float(open_price), "high_price": float(high_price),
           "low_price": float(low_price), "close_price": float(close_price)}
    ctx = PolicyContext(
        timestamp=ts, prediction=prediction,
        in_position=(st.side != "flat"), side=st.side,
        entry_price=st.entry_price, bars_held=st.bars_held,
        features=features if features is not None else {}, **bar,
    )
    decided = policy.decide(ctx)
    actions = tuple(decided) if isinstance(decided, (list, tuple)) else (decided,)
    primary = actions[0] if actions else Action.hold()

    closed: list[ClosedTrade] = []
    if forced is not None:
        # TP 는 쉬고 있던 지정가가 채워진 것(메이커), SL 은 스톱 발동(테이커).
        st, tr = close(st, forced[0], ts, forced[1], cfg,
                       exit_maker=(forced[1] == "tp"))
        closed.append(tr)

    opened = False
    for action in actions:
        if action.kind == "exit" and st.side != "flat" and forced is None:
            st, tr = close(st, float(open_price), ts,
                           action.note or cfg.policy_exit_reason, cfg,
                           frac=action.exit_frac)
            closed.append(tr)
        elif action.kind in ("enter_long", "enter_short"):
            before = st
            st = open_position(st, action.kind, bar, ts, action, cfg)
            opened = opened or (st is not before)

    return st, StepResult(action=primary, closed=tuple(closed), opened=opened,
                          forced_exit_reason=(forced[1] if forced else None),
                          equity=mark(st, close_price), side_before=side_before)
