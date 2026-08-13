"""정본이 호출하는 **규칙** — 크기(Sizing)와 체결(Fill).

왜 여기에 상속을 두는가
  정본(kernel.py)은 클래스가 아니라 모듈 함수다. 상속으로 행동을 바꿀 수 없게
  물리적으로 막아 둔 것이다 — 2026-08-08 사고가 "실행기가 둘이라 같은 policy 가
  다른 전략이 된" 것이었기 때문이다.

  하지만 전략마다 실제로 달라지는 축이 둘 있다: **얼마나 들어가는가**와
  **어떻게 체결되는가**. 이걸 정본 안의 분기로 처리하면 전략이 늘 때마다 정본이
  자란다. 그래서 이 두 축만 다형으로 빼고, 정본은 규칙을 호출만 한다:

      px  = action.fill.price(...)          # 분기 없음
      qty = action.sizing.qty(...)          # 분기 없음

  새 전략 = 새 규칙 클래스. **정본은 한 줄도 바뀌지 않는다.**

규칙의 계약 (test_rules.py 가 강제한다)
  · **상태를 갖지 않는다.** 생성자 인자는 설정값뿐이고 호출 간 아무것도 기억하지
    않는다. 규칙이 상태를 들면 정본이 순수 함수인 의미가 없어진다.
  · **순수하다.** 파일·DB·시계·난수 금지. 같은 입력이면 같은 출력.
  · 체결 불가는 예외가 아니라 `None` 이다. 지정가가 안 닿는 건 정상이다.

기본값은 현행과 같다
  `FULL_FRACTION` / `MARKET_OPEN` 이 지금까지의 동작이다. 기존 정책은 한 줄도
  바꾸지 않아도 되고, 골든/파리티가 그대로 통과하는 것이 그 증거다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


# ─────────────────────────── 크기 규칙 ───────────────────────────

class SizingRule(ABC):
    """진입 수량을 정한다. 현금 차감은 정본이 한다 — 여기서는 수량만 낸다."""

    @abstractmethod
    def qty(self, *, cash: float, price: float, sl_price: float,
            size_pct: float, fee_rate: float, side: str) -> float:
        """수량. 0 이하를 반환하면 정본이 진입을 건너뛴다."""


@dataclass(frozen=True)
class FractionSizing(SizingRule):
    """가용 자본 대비 비율. `value=1.0` 이 현행(설정 상한 전량)이다.

    분할 진입은 같은 신호에 대해 작은 value 로 여러 번 넣으면 된다 —
    사다리를 규칙이 기억할 필요가 없다(기억하면 상태가 생긴다).
    """

    value: float = 1.0

    def qty(self, *, cash, price, sl_price, size_pct, fee_rate, side) -> float:
        if price <= 0:
            return 0.0
        budget = cash * size_pct * self.value
        denom = price * (1 + fee_rate) if side == "long" else price
        return budget / denom


@dataclass(frozen=True)
class NotionalSizing(SizingRule):
    """고정 명목(USDT). 실거래 드라이버가 링크당 쓰는 방식과 같은 개념."""

    notional: float

    def qty(self, *, cash, price, sl_price, size_pct, fee_rate, side) -> float:
        if price <= 0:
            return 0.0
        cap = cash * size_pct
        denom = price * (1 + fee_rate) if side == "long" else price
        return min(self.notional, cap) / denom


@dataclass(frozen=True)
class RiskSizing(SizingRule):
    """손절까지의 거리로 크기를 정한다 — 변동성 타깃팅·Kelly 계열의 자연스러운 형태.

    `risk_frac` 만큼만 잃도록 수량을 잡는다: |진입가 − 손절가| × 수량 = 현금 × risk_frac.
    손절이 없으면(0.0) 크기를 정할 근거가 없으므로 **0 을 반환해 진입하지 않는다.**
    조용히 전량으로 떨어지면 위험 관리가 아니라 그 반대가 된다.
    """

    risk_frac: float = 0.01
    max_frac: float = 1.0          # 자본 대비 상한 (레버리지 폭주 방지)

    def qty(self, *, cash, price, sl_price, size_pct, fee_rate, side) -> float:
        if price <= 0 or sl_price <= 0:
            return 0.0
        per_unit = abs(price - sl_price)
        if per_unit <= 0:
            return 0.0
        q = (cash * self.risk_frac) / per_unit
        denom = price * (1 + fee_rate) if side == "long" else price
        return min(q, cash * size_pct * self.max_frac / denom)


# ─────────────────────────── 체결 규칙 ───────────────────────────

class FillRule(ABC):
    """그 바에서 체결되는가, 되면 얼마에. 안 되면 None.

    `is_maker` 는 그 체결이 **호가를 제공한 쪽**인지를 말한다. 지정가는 메이커,
    시장가·스톱은 테이커다. 수수료가 이걸 알아야 한다 — 모르면 지정가 체결도
    테이커 요율로 계산돼 MM·그리드처럼 메이커가 수익원인 전략에서 결론이 뒤집힌다.
    """

    #: 호가를 제공한 체결인가 (메이커). 기본은 테이커.
    is_maker: bool = False

    @abstractmethod
    def price(self, *, kind: str, open_price: float, high_price: float,
              low_price: float, close_price: float) -> Optional[float]:
        ...


@dataclass(frozen=True)
class MarketOpenFill(FillRule):
    """그 바 시가에 시장가 체결 — 현행 동작.

    정책이 바 종가를 보고 판단한 뒤 그 바 시가에 체결하는 구조적 lookahead 가
    있다(계획서 §7). 통합 범위 밖으로 둔 항목이며, 여기서 바꾸면 전 전략을
    다시 판정해야 한다.
    """

    def price(self, *, kind, open_price, high_price, low_price, close_price):
        return float(open_price) if open_price > 0 else None


@dataclass(frozen=True)
class LimitFill(FillRule):
    """쉬고 있는 지정가. 바 안에서 가격이 닿아야 체결되고 체결가는 지정가다.

      매수 지정가 L → 저가가 L 이하로 내려와야 채워진다
      매도(숏) 지정가 L → 고가가 L 이상으로 올라와야 채워진다

    큐 우선순위를 가정하므로 **낙관적**이다 — 실제로는 닿아도 안 채워질 수 있다.
    그래서 기본 체결 규칙은 여전히 시장가이고 지정가는 명시할 때만 쓴다.
    """

    limit_price: float
    is_maker: bool = True          # 호가를 제공하고 기다린다 → 메이커 요율

    def price(self, *, kind, open_price, high_price, low_price, close_price):
        L = float(self.limit_price)
        if L <= 0:
            return None
        if kind == "enter_long":
            return L if float(low_price) <= L else None
        if kind == "enter_short":
            return L if float(high_price) >= L else None
        return None


@dataclass(frozen=True)
class StopFill(FillRule):
    """돌파 체결. 지정가와 방향이 반대다 — 불리한 쪽으로 뚫려야 들어간다.

      매수 스톱 S → 고가가 S 이상으로 올라와야 체결
      매도(숏) 스톱 S → 저가가 S 이하로 내려와야 체결

    슬리피지는 모형에 없다(체결가 = S). 돌파 주문은 실제로 밀리므로 이 가정은
    낙관적이다 — 백테스트가 스톱 계열을 좋게 낼 수 있음을 알고 써야 한다.
    """

    stop_price: float

    def price(self, *, kind, open_price, high_price, low_price, close_price):
        S = float(self.stop_price)
        if S <= 0:
            return None
        if kind == "enter_long":
            return S if float(high_price) >= S else None
        if kind == "enter_short":
            return S if float(low_price) <= S else None
        return None


# 기본값 — 현행 동작. 상태가 없으므로 모듈 단일 인스턴스로 공유해도 안전하다.
FULL_FRACTION: SizingRule = FractionSizing(1.0)
MARKET_OPEN: FillRule = MarketOpenFill()


# ─────────────────────────── 스펙 조립 ───────────────────────────
# 정책이 JSON kwargs 로 규칙을 받을 수 있게 하는 얇은 조립기.
# ⚠ 교훈 #88 — 팩토리가 인자를 버리면 설정이 조용히 사라진다. 여기서는
#   알 수 없는 mode 를 **예외로 터뜨린다.** 조용한 기본값 대체 금지.

_SIZING = {"fraction": FractionSizing, "notional": NotionalSizing, "risk": RiskSizing}
_FILL = {"market": MarketOpenFill, "limit": LimitFill, "stop": StopFill}


def build_sizing(spec: Any) -> SizingRule:
    if spec is None:
        return FULL_FRACTION
    if isinstance(spec, SizingRule):
        return spec
    d = dict(spec)
    mode = d.pop("mode", "fraction")
    if mode not in _SIZING:
        raise ValueError(f"알 수 없는 sizing mode: {mode!r} (가능: {sorted(_SIZING)})")
    return _SIZING[mode](**d)


def build_fill(spec: Any) -> FillRule:
    if spec is None:
        return MARKET_OPEN
    if isinstance(spec, FillRule):
        return spec
    d = dict(spec)
    mode = d.pop("mode", "market")
    if mode not in _FILL:
        raise ValueError(f"알 수 없는 fill mode: {mode!r} (가능: {sorted(_FILL)})")
    return _FILL[mode](**d)
