"""정본(Canon) 계약 테스트 — 정본 엔진 2단계.

정본이 거래 판단의 유일한 구현이 됐으므로, 그 계약을 코드로 강제한다.
계약이 깨지면 두 실행기가 **동시에** 틀린다 — 파리티 게이트는 통과하는데
현실과 어긋나는 상태가 된다. 골든/파리티로는 못 잡는 층이다.

계약 (kernel.py = 정본, 상단 docstring 과 같은 목록):
  1. step() 은 순수 함수 — 같은 입력이면 같은 출력, 입력 상태를 변형하지 않음
  2. 강제청산(SL/TP) 판정은 policy.decide 보다 먼저
  3. bars_held 는 policy.decide 가 보기 전에 증가
  4. 브래킷 0.0 은 비활성이며 가격 수준으로 읽히지 않음
  5. 진입은 그 바의 시가에 체결
  6. 두 사본의 현행 격차는 KernelConfig 로 표현된다 (행동 변경 0)

실행:
  cd backend && python3 -m unittest tests.composer_framework.test_kernel -v
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
    KernelConfig,
    KernelState,
    close,
    mark,
    open_position,
    step,
)
from app.composer_framework.policy import Action, PolicyContext, TradingPolicy  # noqa: E402

TS = datetime(2026, 8, 12)


class Recorder(TradingPolicy):
    """decide() 가 본 컨텍스트를 기록하는 정책."""

    def __init__(self, action_fn=None):
        self.seen: list[PolicyContext] = []
        self._fn = action_fn or (lambda c: Action.hold())

    def decide(self, c: PolicyContext) -> Action:
        self.seen.append(c)
        return self._fn(c)


def enter_short(sl=0.0, tp=0.0):
    return lambda c: (Action.hold() if c.in_position
                      else Action(kind="enter_short", sl_price=sl, tp_price=tp))


BAR = dict(open_price=100.0, high_price=105.0, low_price=95.0, close_price=101.0)
CFG = KernelConfig(size_pct=0.95, fee_rate=0.0004)


def bar_at(px: float) -> dict:
    """가격 하나짜리 최소 바 — 시장가 규칙은 시가만 본다."""
    return {"open_price": px, "high_price": px, "low_price": px, "close_price": px}


class TestPurity(unittest.TestCase):

    def test_step_does_not_mutate_input_state(self):
        st = KernelState(cash=1000.0)
        before = replace(st)
        step(st, ts=TS, prediction=1.0, policy=Recorder(enter_short()), cfg=CFG, **BAR)
        self.assertEqual(st, before, "step() 이 입력 상태를 변형했다 — 순수 함수가 아니다")

    def test_step_is_deterministic(self):
        st = KernelState(cash=1000.0)
        a, ra = step(st, ts=TS, prediction=1.0, policy=Recorder(enter_short()),
                     cfg=CFG, **BAR)
        b, rb = step(st, ts=TS, prediction=1.0, policy=Recorder(enter_short()),
                     cfg=CFG, **BAR)
        self.assertEqual(a, b)
        self.assertEqual(ra.equity, rb.equity)


class TestOrdering(unittest.TestCase):

    def test_forced_exit_evaluated_before_decide(self):
        """SL 이 닿은 바에서는 policy 가 무엇을 반환하든 강제청산이 이긴다."""
        st = KernelState(cash=1000.0, side="short", qty=10.0, entry_price=100.0,
                         entry_ts=TS, sl_price=104.0, tp_price=0.0)
        pol = Recorder(lambda c: Action.hold())          # 정책은 계속 보유하려 한다
        new, res = step(st, ts=TS, prediction=1.0, policy=pol, cfg=CFG, **BAR)
        self.assertEqual(res.forced_exit_reason, "sl")
        self.assertEqual(len(res.closed), 1)
        self.assertEqual(res.closed[0].exit_price, 104.0)
        self.assertEqual(new.side, "flat")

    def test_bars_held_incremented_before_policy_sees_it(self):
        """진입 다음 바에서 policy 는 bars_held=1 을 봐야 한다.

        2026-08-08: 뒤에 올려서 policy 가 0 을 봤고 Day-30 전략이 Day-31 에
        청산됐다. R-3 검증 기준은 `entry_idx + hold_days`.
        """
        st = KernelState(cash=1000.0, side="short", qty=1.0, entry_price=100.0,
                         entry_ts=TS, bars_held=0)
        pol = Recorder()
        step(st, ts=TS, prediction=1.0, policy=pol, cfg=CFG, **BAR)
        self.assertEqual(pol.seen[0].bars_held, 1)

    def test_bars_held_zero_while_flat(self):
        pol = Recorder()
        step(KernelState(cash=1000.0), ts=TS, prediction=1.0, policy=pol,
             cfg=CFG, **BAR)
        self.assertEqual(pol.seen[0].bars_held, 0)
        self.assertFalse(pol.seen[0].in_position)


class TestBrackets(unittest.TestCase):

    def test_zero_bracket_never_fires(self):
        """0.0 은 비활성. 수준으로 읽으면 `high >= 0` 이 항상 참이라 즉시 청산된다."""
        st = KernelState(cash=1000.0, side="short", qty=1.0, entry_price=100.0,
                         entry_ts=TS, sl_price=0.0, tp_price=0.0)
        _, res = step(st, ts=TS, prediction=1.0, policy=Recorder(), cfg=CFG, **BAR)
        self.assertIsNone(res.forced_exit_reason)
        self.assertEqual(res.closed, ())

    def test_none_bracket_uses_config_default(self):
        """policy 미지정(None) → 설정 기본값. 오케스트레이터의 SL4%/TP10% 재현."""
        cfg = replace(CFG, default_sl_pct=0.04, default_tp_pct=0.10)
        st = open_position(KernelState(cash=1000.0), "enter_short", bar_at(100.0), TS,
                           Action(kind="enter_short"), cfg)
        self.assertAlmostEqual(st.sl_price, 104.0)
        self.assertAlmostEqual(st.tp_price, 90.0)
        stl = open_position(KernelState(cash=1000.0), "enter_long", bar_at(100.0), TS,
                            Action(kind="enter_long"), cfg)
        self.assertAlmostEqual(stl.sl_price, 96.0)
        self.assertAlmostEqual(stl.tp_price, 110.0)

    def test_none_bracket_without_default_is_disabled(self):
        """백테스터 재현 — 기본값이 없으면 브래킷은 비활성(0.0)이다."""
        st = open_position(KernelState(cash=1000.0), "enter_short", bar_at(100.0), TS,
                           Action(kind="enter_short"), CFG)
        self.assertEqual(st.sl_price, 0.0)
        self.assertEqual(st.tp_price, 0.0)

    def test_explicit_zero_stays_zero_even_with_default(self):
        """0.0 을 명시한 경우는 기본값이 있어도 비활성이어야 한다.

        2026-08-08 사고의 핵심: `or` 가 0.0 과 None 을 뭉개 선언한 적 없는
        10% 익절이 장착됐다.
        """
        cfg = replace(CFG, default_sl_pct=0.04, default_tp_pct=0.10)
        st = open_position(KernelState(cash=1000.0), "enter_short", bar_at(100.0), TS,
                           Action(kind="enter_short", sl_price=0.0, tp_price=0.0), cfg)
        self.assertEqual(st.sl_price, 0.0)
        self.assertEqual(st.tp_price, 0.0)


class TestExecution(unittest.TestCase):

    def test_entry_fills_at_bar_open(self):
        _, res = step(KernelState(cash=1000.0), ts=TS, prediction=1.0,
                      policy=Recorder(enter_short()), cfg=CFG, **BAR)
        self.assertTrue(res.opened)

    def test_entry_price_is_open_not_close(self):
        st, _ = step(KernelState(cash=1000.0), ts=TS, prediction=1.0,
                     policy=Recorder(enter_short()), cfg=CFG, **BAR)
        self.assertEqual(st.entry_price, BAR["open_price"])

    def test_no_entry_when_cash_exhausted(self):
        st = open_position(KernelState(cash=0.0), "enter_short", bar_at(100.0), TS,
                           Action(kind="enter_short"), CFG)
        self.assertEqual(st.side, "flat")

    def test_short_close_charges_both_legs(self):
        st = KernelState(cash=0.0, side="short", qty=1.0, entry_price=100.0, entry_ts=TS)
        _, tr = close(st, 100.0, TS, "t", CFG)
        # 가격 변화 없음 → 수수료만큼 손실. 왕복 8bp(편도 4bp x 진입가+청산가)
        self.assertAlmostEqual(tr.return_pct, -0.0008, places=12)

    def test_short_fee_can_be_disabled_for_ab(self):
        cfg = replace(CFG, apply_fee_to_short=False)
        st = KernelState(cash=0.0, side="short", qty=1.0, entry_price=100.0, entry_ts=TS)
        _, tr = close(st, 100.0, TS, "t", cfg)
        self.assertAlmostEqual(tr.return_pct, 0.0, places=15)

    def test_mark_short_returns_collateral(self):
        st = KernelState(cash=0.0, side="short", qty=1.0, entry_price=100.0, entry_ts=TS)
        self.assertAlmostEqual(mark(st, 100.0), 100.0)   # 담보 100, 손익 0
        self.assertAlmostEqual(mark(st, 90.0), 110.0)    # 10 이익


class TestPolicyExitReason(unittest.TestCase):
    """청산 사유 기본값 — 3c~3f(2026-08-13)에서 **통일**했다.

    종전: backtester "policy" / orchestrator "policy_exit" — 같은 상황을 두
    실행기가 다른 이름으로 기록했다. 골든 1,025거래에 둘 다 0건이라(모든 정책이
    명시적 note 를 넘긴다) 통일해도 행동은 안 바뀌는 **잠재 격차**였다.

    통일 전 이 클래스는 격차를 살아 있는 채로 못박고 있었고, 통일하자 실패했다.
    그 실패가 곧 수정의 증거다.
    """

    def _exit_once(self, cfg):
        st = KernelState(cash=1000.0, side="short", qty=1.0, entry_price=100.0,
                         entry_ts=TS)
        _, res = step(st, ts=TS, prediction=1.0,
                      policy=Recorder(lambda c: Action.exit_("")), cfg=cfg, **BAR)
        return res.closed[0].exit_reason

    def test_default_is_unified(self):
        self.assertEqual(self._exit_once(CFG), "policy_exit")

    def test_still_configurable(self):
        """통일했다고 설정을 없애진 않았다 — 다른 드라이버가 생기면 필요하다."""
        self.assertEqual(self._exit_once(replace(CFG, policy_exit_reason="custom")),
                         "custom")

    def test_explicit_note_wins(self):
        st = KernelState(cash=1000.0, side="short", qty=1.0, entry_price=100.0,
                         entry_ts=TS)
        _, res = step(st, ts=TS, prediction=1.0,
                      policy=Recorder(lambda c: Action.exit_("max_hold")), cfg=CFG, **BAR)
        self.assertEqual(res.closed[0].exit_reason, "max_hold")


class TestConfigUnification(unittest.TestCase):
    """3c~3f — 코드에 박혀 있던 값들이 설정으로 나왔는가."""

    def test_close_at_end_is_config(self):
        """백테스트는 끝에서 정리, 라이브는 들고 간다 — 코드가 아니라 설정이 정한다."""
        self.assertFalse(KernelConfig().close_at_end)          # 기본 = 라이브
        self.assertTrue(replace(KernelConfig(), close_at_end=True).close_at_end)

    def test_fee_constants_are_named_per_market(self):
        """시장마다 요율이 다르므로 하나로 통일할 수 없다 — 이름으로 드러낸다."""
        from app.composer_framework.kernel import (
            DEFAULT_FEE_RATE, FEE_KR_EQUITY, FEE_MAKER_BINANCE_FUTURES,
            FEE_TAKER_BINANCE_FUTURES,
        )
        self.assertLess(FEE_MAKER_BINANCE_FUTURES, FEE_TAKER_BINANCE_FUTURES)
        self.assertEqual(DEFAULT_FEE_RATE, FEE_KR_EQUITY)      # 종전 기본값 보존


if __name__ == "__main__":
    unittest.main(verbosity=2)
