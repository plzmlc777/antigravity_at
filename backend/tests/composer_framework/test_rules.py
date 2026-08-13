"""규칙(Sizing / Fill) 계약 + 정본의 새 능력 테스트.

정본은 클래스가 아니라 모듈 함수라 상속으로 행동을 바꿀 수 없다. 대신 전략마다
달라지는 두 축 — **얼마나(Sizing)** 와 **어떻게 체결(Fill)** — 만 다형으로 뺐다.
그래서 규칙이 정본의 순수성을 깨뜨리지 않는지가 핵심이고, 여기서 강제한다.

규칙 계약
  1. 상태를 갖지 않는다 — 같은 인스턴스를 여러 번 호출해도 결과가 같다
  2. 순수하다 — 같은 입력이면 같은 출력
  3. 체결 불가는 예외가 아니라 None (지정가가 안 닿는 건 정상이다)
  4. 기본 규칙(FULL_FRACTION / MARKET_OPEN)은 현행 동작과 같다

새 능력
  · 크기 비율 · 고정 명목 · 위험 기준 사이징
  · 지정가 · 스톱 체결
  · 추가 진입(가중평균) · 부분 청산
  · 한 바에 여러 지시 (사다리)

실행:
  cd backend && python3 -m unittest tests.composer_framework.test_rules -v
"""
from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.composer_framework.kernel import (  # noqa: E402
    KernelConfig, KernelState, close, open_position, step,
)
from app.composer_framework.policy import Action, PolicyContext, TradingPolicy  # noqa: E402
from app.composer_framework.rules import (  # noqa: E402
    FULL_FRACTION, MARKET_OPEN, FractionSizing, LimitFill, MarketOpenFill,
    NotionalSizing, RiskSizing, StopFill, build_fill, build_sizing,
)

TS = datetime(2026, 8, 13)
CFG = KernelConfig(size_pct=0.95, fee_rate=0.0004)
BAR = dict(open_price=100.0, high_price=105.0, low_price=95.0, close_price=101.0)


def bar_at(px: float) -> dict:
    return {"open_price": px, "high_price": px, "low_price": px, "close_price": px}


class Scripted(TradingPolicy):
    """정해진 지시를 순서대로 내는 정책. 한 원소가 리스트면 그 바에 여러 지시."""

    def __init__(self, script):
        self.script, self.i = list(script), 0

    def decide(self, c: PolicyContext):
        out = self.script[self.i] if self.i < len(self.script) else Action.hold()
        self.i += 1
        return out


# ─────────────────────────── 규칙 계약 ───────────────────────────

class TestRuleContract(unittest.TestCase):

    ALL_SIZING = [FractionSizing(1.0), FractionSizing(0.25),
                  NotionalSizing(500.0), RiskSizing(0.01)]
    ALL_FILL = [MarketOpenFill(), LimitFill(99.0), StopFill(103.0)]

    def test_sizing_is_stateless_and_pure(self):
        kw = dict(cash=1000.0, price=100.0, sl_price=95.0, size_pct=0.95,
                  fee_rate=0.0004, side="long")
        for r in self.ALL_SIZING:
            a, b = r.qty(**kw), r.qty(**kw)
            self.assertEqual(a, b, f"{type(r).__name__} 이 호출마다 다른 값을 낸다")

    def test_fill_is_stateless_and_pure(self):
        for r in self.ALL_FILL:
            a = r.price(kind="enter_short", **BAR)
            b = r.price(kind="enter_short", **BAR)
            self.assertEqual(a, b, f"{type(r).__name__} 이 호출마다 다른 값을 낸다")

    def test_rules_hold_no_mutable_state(self):
        """frozen dataclass 라 호출로 내부가 바뀔 수 없다."""
        for r in self.ALL_SIZING + self.ALL_FILL:
            with self.assertRaises(Exception):
                setattr(r, "value", 999)

    def test_defaults_match_current_behavior(self):
        self.assertIsInstance(FULL_FRACTION, FractionSizing)
        self.assertEqual(FULL_FRACTION.value, 1.0)
        self.assertIsInstance(MARKET_OPEN, MarketOpenFill)
        self.assertEqual(MARKET_OPEN.price(kind="enter_short", **BAR), BAR["open_price"])

    def test_builder_rejects_unknown_mode(self):
        """조용한 기본값 대체 금지 — 교훈 #88(설정이 소리 없이 사라지는 병)."""
        with self.assertRaises(ValueError):
            build_sizing({"mode": "없는모드"})
        with self.assertRaises(ValueError):
            build_fill({"mode": "없는모드"})

    def test_builder_roundtrip(self):
        self.assertEqual(build_sizing({"mode": "fraction", "value": 0.5}),
                         FractionSizing(0.5))
        self.assertEqual(build_fill({"mode": "limit", "limit_price": 12.5}),
                         LimitFill(12.5))


# ─────────────────────────── 크기 규칙 ───────────────────────────

class TestSizing(unittest.TestCase):

    def test_fraction_scales_linearly(self):
        st = KernelState(cash=1000.0)
        full = open_position(st, "enter_short", bar_at(100.0), TS,
                             Action(kind="enter_short"), CFG)
        half = open_position(st, "enter_short", bar_at(100.0), TS,
                             Action(kind="enter_short", sizing=FractionSizing(0.5)), CFG)
        self.assertAlmostEqual(half.qty, full.qty / 2, places=10)

    def test_notional_is_absolute(self):
        st = KernelState(cash=100000.0)
        s = open_position(st, "enter_short", bar_at(50.0), TS,
                          Action(kind="enter_short", sizing=NotionalSizing(500.0)), CFG)
        self.assertAlmostEqual(s.qty, 10.0, places=10)      # 500 / 50

    def test_risk_sizing_uses_stop_distance(self):
        """손실 허용 1% / 손절까지 5 → 수량 = 1000*0.01/5 = 2"""
        st = KernelState(cash=1000.0)
        s = open_position(st, "enter_short", bar_at(100.0), TS,
                          Action(kind="enter_short", sl_price=105.0,
                                 sizing=RiskSizing(0.01)), CFG)
        self.assertAlmostEqual(s.qty, 2.0, places=10)

    def test_risk_sizing_refuses_without_stop(self):
        """손절이 없으면 크기를 정할 근거가 없다 — 조용히 전량으로 떨어지면 안 된다."""
        st = KernelState(cash=1000.0)
        s = open_position(st, "enter_short", bar_at(100.0), TS,
                          Action(kind="enter_short", sl_price=0.0,
                                 sizing=RiskSizing(0.01)), CFG)
        self.assertEqual(s.side, "flat")

    def test_sizing_never_exceeds_cash(self):
        st = KernelState(cash=100.0)
        s = open_position(st, "enter_short", bar_at(10.0), TS,
                          Action(kind="enter_short", sizing=NotionalSizing(1e9)), CFG)
        self.assertLessEqual(s.qty * s.entry_price, 100.0 + 1e-9)
        self.assertGreaterEqual(s.cash, -1e-9)


# ─────────────────────────── 체결 규칙 ───────────────────────────

class TestFill(unittest.TestCase):

    def test_limit_fills_only_when_touched(self):
        st = KernelState(cash=1000.0)
        hit = open_position(st, "enter_short", BAR, TS,
                            Action(kind="enter_short", fill=LimitFill(104.0)), CFG)
        self.assertEqual(hit.side, "short")
        self.assertAlmostEqual(hit.entry_price, 104.0)   # 체결가 = 지정가
        miss = open_position(st, "enter_short", BAR, TS,
                             Action(kind="enter_short", fill=LimitFill(120.0)), CFG)
        self.assertEqual(miss.side, "flat", "닿지 않은 지정가가 체결됐다")

    def test_limit_miss_is_not_an_error(self):
        """미체결은 정상 경로 — 상태를 그대로 돌려준다."""
        st = KernelState(cash=1000.0, side="flat")
        out = open_position(st, "enter_long", BAR, TS,
                            Action(kind="enter_long", fill=LimitFill(1.0)), CFG)
        self.assertIs(out, st)

    def test_stop_is_opposite_direction_of_limit(self):
        st = KernelState(cash=1000.0)
        # 숏 스톱: 저가가 뚫려야 체결
        hit = open_position(st, "enter_short", BAR, TS,
                            Action(kind="enter_short", fill=StopFill(96.0)), CFG)
        self.assertEqual(hit.side, "short")
        miss = open_position(st, "enter_short", BAR, TS,
                             Action(kind="enter_short", fill=StopFill(90.0)), CFG)
        self.assertEqual(miss.side, "flat")


# ─────────────────── 추가 진입 · 부분 청산 · 사다리 ───────────────────

class TestPyramidAndPartial(unittest.TestCase):

    def test_pyramid_uses_weighted_average_entry(self):
        """거래소(단방향 넷팅)와 같은 회계. leg 를 따로 들면 실제와 어긋난다."""
        st = KernelState(cash=1000.0)
        st = open_position(st, "enter_short", bar_at(100.0), TS,
                           Action(kind="enter_short", sizing=NotionalSizing(100.0)), CFG)
        st = open_position(st, "enter_short", bar_at(50.0), TS,
                           Action(kind="enter_short", sizing=NotionalSizing(100.0)), CFG)
        self.assertAlmostEqual(st.qty, 1.0 + 2.0, places=10)
        self.assertAlmostEqual(st.entry_price, (1.0 * 100 + 2.0 * 50) / 3.0, places=10)

    def test_pyramid_keeps_original_bars_held(self):
        """추가 진입 때마다 보유바수가 초기화되면 max_hold 가 무력해진다."""
        st = KernelState(cash=1000.0, side="short", qty=1.0, entry_price=100.0,
                         entry_ts=TS, bars_held=7)
        st2 = open_position(st, "enter_short", bar_at(100.0), TS,
                            Action(kind="enter_short", sizing=NotionalSizing(10.0)), CFG)
        self.assertEqual(st2.bars_held, 7)

    def test_opposite_side_entry_is_ignored(self):
        st = KernelState(cash=1000.0, side="short", qty=1.0, entry_price=100.0,
                         entry_ts=TS)
        out = open_position(st, "enter_long", bar_at(100.0), TS,
                            Action(kind="enter_long"), CFG)
        self.assertIs(out, st, "정본이 조용히 포지션을 뒤집었다")

    def test_partial_exit_keeps_remainder(self):
        st = KernelState(cash=0.0, side="short", qty=10.0, entry_price=100.0,
                         entry_ts=TS, bars_held=4, sl_price=150.0)
        after, tr = close(st, 90.0, TS, "부분", CFG, frac=0.3)
        self.assertAlmostEqual(tr.qty, 3.0, places=10)
        self.assertAlmostEqual(after.qty, 7.0, places=10)
        self.assertEqual(after.side, "short")
        self.assertAlmostEqual(after.entry_price, 100.0)   # 같은 거래의 연속
        self.assertEqual(after.bars_held, 4)
        self.assertAlmostEqual(after.sl_price, 150.0)

    def test_full_exit_flattens(self):
        st = KernelState(cash=0.0, side="short", qty=10.0, entry_price=100.0, entry_ts=TS)
        after, _ = close(st, 90.0, TS, "전량", CFG, frac=1.0)
        self.assertEqual(after.side, "flat")
        self.assertEqual(after.qty, 0.0)

    def test_ladder_in_one_bar(self):
        """한 바에 여러 지시 — 그리드·마틴게일의 기본 형태."""
        ladder = [Action(kind="enter_short", sizing=NotionalSizing(100.0),
                         fill=LimitFill(p)) for p in (101.0, 103.0, 120.0)]
        st, res = step(KernelState(cash=10000.0), ts=TS, prediction=-1.0,
                       policy=Scripted([ladder]), cfg=CFG, **BAR)
        # 101·103 은 고가 105 에 닿고, 120 은 안 닿는다 → 두 단만 체결
        self.assertEqual(st.side, "short")
        self.assertAlmostEqual(st.qty, 100.0 / 101.0 + 100.0 / 103.0, places=10)
        self.assertTrue(res.opened)

    def test_single_action_behaves_as_before(self):
        """지시를 하나만 반환하면 예전과 완전히 같다 (행동 변경 0)."""
        one = Action(kind="enter_short")
        a, _ = step(KernelState(cash=1000.0), ts=TS, prediction=-1.0,
                    policy=Scripted([one]), cfg=CFG, **BAR)
        b, _ = step(KernelState(cash=1000.0), ts=TS, prediction=-1.0,
                    policy=Scripted([[one]]), cfg=CFG, **BAR)
        self.assertEqual(a, b)


class TestFeaturesAndFees(unittest.TestCase):
    """정책이 피처를 보는가 / 수수료가 체결 방식을 아는가."""

    def test_policy_receives_features(self):
        """ATR 손절이 가능해지는 지점 — 정책이 그 바의 피처를 본다."""
        seen = {}

        class Peek(TradingPolicy):
            def decide(self, c):
                seen.update(dict(c.features))
                return Action.hold()

        step(KernelState(cash=1000.0), ts=TS, prediction=0.0, policy=Peek(),
             cfg=CFG, features={"atr": 3.5, "regime": 1.0}, **BAR)
        self.assertEqual(seen.get("atr"), 3.5)

    def test_features_default_empty(self):
        """features 를 안 넘기면 빈 매핑 — 기존 정책은 영향 없다."""
        seen = {}

        class Peek(TradingPolicy):
            def decide(self, c):
                seen["n"] = len(c.features)
                return Action.hold()

        step(KernelState(cash=1000.0), ts=TS, prediction=0.0, policy=Peek(),
             cfg=CFG, **BAR)
        self.assertEqual(seen["n"], 0)

    def test_atr_stop_is_expressible(self):
        """피처로 받은 ATR 로 손절을 잡는다 — 정본 수정 없이."""

        class AtrStop(TradingPolicy):
            def decide(self, c):
                if c.in_position:
                    return Action.hold()
                atr = float(c.features.get("atr", 0.0))
                return Action(kind="enter_short", sl_price=c.open_price + 2 * atr)

        st, _ = step(KernelState(cash=1000.0), ts=TS, prediction=-1.0,
                     policy=AtrStop(), cfg=CFG, features={"atr": 3.0}, **BAR)
        self.assertAlmostEqual(st.sl_price, 100.0 + 6.0)

    def test_maker_rate_applies_to_limit_fill(self):
        cfg = replace(CFG, fee_rate=0.0005, fee_rate_maker=0.0002)
        st = KernelState(cash=10000.0)
        st = open_position(st, "enter_short", BAR, TS,
                           Action(kind="enter_short", fill=LimitFill(104.0)), cfg)
        self.assertTrue(st.entry_maker)
        _, tr = close(st, 104.0, TS, "t", cfg, exit_maker=True)
        # 가격 변화 없음 → 왕복 메이커 수수료만
        self.assertAlmostEqual(tr.return_pct, -2 * 0.0002, places=12)

    def test_taker_rate_applies_to_market_fill(self):
        cfg = replace(CFG, fee_rate=0.0005, fee_rate_maker=0.0002)
        st = open_position(KernelState(cash=10000.0), "enter_short", bar_at(100.0), TS,
                           Action(kind="enter_short"), cfg)
        self.assertFalse(st.entry_maker)
        _, tr = close(st, 100.0, TS, "t", cfg, exit_maker=False)
        self.assertAlmostEqual(tr.return_pct, -2 * 0.0005, places=12)

    def test_no_maker_rate_means_single_rate(self):
        """fee_rate_maker=None 이면 종전과 동일 — 행동 변경 0."""
        st = open_position(KernelState(cash=10000.0), "enter_short", BAR, TS,
                           Action(kind="enter_short", fill=LimitFill(104.0)), CFG)
        _, tr = close(st, 104.0, TS, "t", CFG, exit_maker=True)
        self.assertAlmostEqual(tr.return_pct, -2 * CFG.fee_rate, places=12)

    def test_tp_is_maker_sl_is_taker(self):
        """TP 는 쉬던 지정가가 채워진 것, SL 은 스톱 발동."""
        cfg = replace(CFG, fee_rate=0.0005, fee_rate_maker=0.0002)
        base = KernelState(cash=0.0, side="short", qty=1.0, entry_price=100.0,
                           entry_ts=TS, sl_price=105.0, tp_price=95.0)

        class Hold(TradingPolicy):
            def decide(self, c):
                return Action.hold()

        _, res_tp = step(base, ts=TS, prediction=0.0, policy=Hold(), cfg=cfg,
                         open_price=100.0, high_price=101.0, low_price=94.0,
                         close_price=95.0)
        _, res_sl = step(base, ts=TS, prediction=0.0, policy=Hold(), cfg=cfg,
                         open_price=100.0, high_price=106.0, low_price=99.0,
                         close_price=105.0)
        self.assertEqual(res_tp.forced_exit_reason, "tp")
        self.assertEqual(res_sl.forced_exit_reason, "sl")
        # 청산 쪽 요율이 다르므로 수수료 총액이 다르다
        self.assertNotAlmostEqual(
            res_tp.closed[0].return_pct + 0.05,      # tp: +5% 수익
            res_sl.closed[0].return_pct - 0.05, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
