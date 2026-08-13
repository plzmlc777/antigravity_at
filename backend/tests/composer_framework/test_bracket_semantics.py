"""브래킷(SL/TP) 의미 + bars_held 회귀 테스트.

2026-08-08 사고 재발 방지. 두 결함이 실자금 43일을 오염시켰고 둘 다
"정상 범위 밖" 경계값에서만 드러났다 — 기존 테스트는 tp_pct=0.10 같은
정상값만 써서 전부 통과하고 있었다.

  (1) 브래킷 0.0의 의미 충돌
      정책은 tp_pct>=1.0일 때 tp_price=0.0을 "익절 없음"으로 반환하는데
      orchestrator가 `action.tp_price or price*0.90`으로 받아 0.0을 "미설정"
      으로 오인 → 선언한 적 없는 10% 익절이 장착됐다. 코호트 측정상 거래당
      기대수익 +6.43% → +0.03%로 엣지가 소멸하는 규칙이다.

  (2) bars_held off-by-one
      orchestrator가 policy 호출 *뒤에* bars_held를 올려서 policy가 항상 1
      적은 값을 봤다 → max_hold_bars가 1바 늦게 발동(Day-30 전략이 Day-31에
      청산). R-3 검증 기준(`entry_idx + hold_days`)과 backtester가 맞고
      orchestrator가 틀렸다.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.composer_framework.orchestrator import PaperOrchestrator  # noqa: E402
from app.composer_framework.paper_session import PaperSession  # noqa: E402
from app.composer_framework.policy import (  # noqa: E402
    Action,
    LifecycleDecayEarlyExitPolicy,
    PolicyContext,
)

ORCH = PaperOrchestrator.__new__(PaperOrchestrator)  # store 불요 (헬퍼만 호출)


def _session(**kw) -> PaperSession:
    return PaperSession(session_id="t", name="t", symbol="TESTUSDT",
                        initial_capital=1_000_000.0, fee_rate=0.0004, **kw)


class TestBracketZeroMeansDisabled(unittest.TestCase):
    """0.0 = 명시적 비활성. 기본값으로 덮어쓰면 안 된다."""

    def test_short_tp_zero_stays_zero(self):
        s = _session()
        act = Action(kind="enter_short", sl_price=0.3645, tp_price=0.0)
        PaperOrchestrator._open_short(ORCH, s, 0.243, pd.Timestamp("2026-08-03"), act, -1.0)
        self.assertEqual(s.tp_price, 0.0, "tp_price 0.0이 폴백으로 덮어써졌다 — 팬텀 TP 재발")
        self.assertAlmostEqual(s.sl_price, 0.3645, places=9)

    def test_long_tp_zero_stays_zero(self):
        s = _session()
        act = Action(kind="enter_long", sl_price=96.0, tp_price=0.0)
        PaperOrchestrator._open_long(ORCH, s, 100.0, pd.Timestamp("2026-08-03"), act, 1.0)
        self.assertEqual(s.tp_price, 0.0)

    def test_none_means_unset_and_no_bracket_is_armed(self):
        """None(정책 미지정)에도 **아무 브래킷도 장착하지 않는다.** (3b, 2026-08-13)

        종전에는 None 을 "기본값 적용"으로 읽어 SL 4% / TP 10% 를 임의로 달았다.
        backtester 는 같은 경우 비활성으로 뒀으므로, 같은 policy 가 두 실행기에서
        다른 전략이 됐다(격차 D2). 2026-08-08 사고 — 선언한 적 없는 10% 익절이
        실자금 43일을 오염시킨 것 — 이 바로 이 계열이다.

        이제 브래킷은 **policy 가 선언한 것만** 존재한다. 0.0(명시적 비활성)과
        None(미지정)은 여전히 구분되지만, 결과는 둘 다 "브래킷 없음"이다.

        대신 "선언을 잊으면 손절이 없다"는 위험이 생기므로,
        `test_short_fee.TestKnownDivergence.test_no_shipped_policy_omits_brackets`
        가 출하 policy 들이 브래킷을 반드시 채우는지 강제한다.
        """
        s = _session()
        act = Action(kind="enter_short", sl_price=None, tp_price=None)
        PaperOrchestrator._open_short(ORCH, s, 100.0, pd.Timestamp("2026-08-03"), act, -1.0)
        self.assertEqual(s.sl_price, 0.0, "선언한 적 없는 손절이 장착됐다")
        self.assertEqual(s.tp_price, 0.0, "선언한 적 없는 익절이 장착됐다 — D2 재발")


class TestForcedExitIgnoresDisabledBrackets(unittest.TestCase):
    """브래킷 0.0을 가격으로 읽으면 `high >= 0`이 매 바 참 → 가격 0에 즉시 청산."""

    def _bar(self, high, low):
        return pd.Series({"open": (high + low) / 2, "high": high,
                          "low": low, "close": (high + low) / 2})

    def test_short_zero_brackets_never_fire(self):
        s = _session(side="short", entry_price=0.243, sl_price=0.0, tp_price=0.0, qty=100)
        self.assertIsNone(PaperOrchestrator._check_forced_exit(ORCH, s, self._bar(0.30, 0.20)))

    def test_long_zero_brackets_never_fire(self):
        s = _session(side="long", entry_price=100.0, sl_price=0.0, tp_price=0.0, qty=100)
        self.assertIsNone(PaperOrchestrator._check_forced_exit(ORCH, s, self._bar(120.0, 80.0)))

    def test_short_sl_still_fires_when_set(self):
        s = _session(side="short", entry_price=0.243, sl_price=0.3645, tp_price=0.0, qty=100)
        got = PaperOrchestrator._check_forced_exit(ORCH, s, self._bar(0.37, 0.30))
        self.assertIsNotNone(got)
        self.assertEqual(got["reason"], "sl")

    def test_short_tp_does_not_fire_at_old_phantom_level(self):
        """진입가×0.90(옛 팬텀 TP 수준)을 찍어도 tp가 0이면 발화 없음."""
        s = _session(side="short", entry_price=0.243, sl_price=0.3645, tp_price=0.0, qty=100)
        self.assertIsNone(PaperOrchestrator._check_forced_exit(ORCH, s, self._bar(0.2431, 0.2187)))


class TestLifecyclePolicyDeclaresNoTakeProfit(unittest.TestCase):
    """운영 스펙(tp_pct=1.0)은 '익절 없음'을 뜻한다 — 정책 계약 고정."""

    def test_tp_pct_one_yields_zero_tp(self):
        pol = LifecycleDecayEarlyExitPolicy(entry_threshold=0.5, exit_signal_threshold=0.5,
                                            sl_pct=0.5, tp_pct=1.0, max_hold_bars=30)
        act = pol.decide(PolicyContext(
            timestamp=None, prediction=-1.0, open_price=0.243, high_price=0.25,
            low_price=0.24, close_price=0.2431, in_position=False, side="flat",
            entry_price=0.0, bars_held=0))
        self.assertEqual(act.kind, "enter_short")
        self.assertEqual(act.tp_price, 0.0)
        self.assertAlmostEqual(act.sl_price, 0.243 * 1.5, places=9)


class TestBarsHeldParity(unittest.TestCase):
    """policy가 보는 bars_held는 backtester의 `i - entry_idx`와 같아야 한다.

    orchestrator 루프를 그대로 흉내낸다: 진입 바에서 0, 다음 바에서 1.
    """

    def test_bars_held_is_one_on_bar_after_entry(self):
        s = _session()
        act = Action(kind="enter_short", sl_price=150.0, tp_price=0.0)
        # 진입 바: side=flat이므로 증가 없음, policy는 0을 본다
        self.assertEqual(s.side, "flat")
        seen_at_entry = s.bars_held
        PaperOrchestrator._open_short(ORCH, s, 100.0, pd.Timestamp("2026-08-01"), act, -1.0)
        self.assertEqual(seen_at_entry, 0)
        self.assertEqual(s.bars_held, 0, "진입 직후 bars_held는 0")

        # 다음 바: side!=flat → policy가 읽기 전에 증가 (orchestrator 루프와 동일)
        if s.side != "flat":
            s.bars_held += 1
        self.assertEqual(s.bars_held, 1,
                         "진입 다음 바에서 policy는 1을 봐야 한다 (backtester: i-entry_idx=1)")

    def test_max_hold_fires_at_exact_bar(self):
        """max_hold_bars=30이면 진입 후 30번째 바에서 time 청산."""
        pol = LifecycleDecayEarlyExitPolicy(entry_threshold=0.5, exit_signal_threshold=0.5,
                                            sl_pct=0.5, tp_pct=1.0, max_hold_bars=30)
        ctx = lambda n: PolicyContext(  # noqa: E731
            timestamp=None, prediction=-1.0, open_price=100.0, high_price=101.0,
            low_price=99.0, close_price=100.0, in_position=True, side="short",
            entry_price=100.0, bars_held=n)
        self.assertEqual(pol.decide(ctx(29)).kind, "hold")
        act30 = pol.decide(ctx(30))
        self.assertEqual(act30.kind, "exit")
        self.assertEqual(act30.note, "time")


if __name__ == "__main__":
    unittest.main()
