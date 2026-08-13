"""숏 수수료 회귀 테스트 + 실행기 격차 고정 (통합 실행기 1단계).

배경 (2026-08-12)
  `_close_position` 의 숏 분기에 수수료 항이 아예 없었다. 롱 분기에만
  `fee_rate` 가 곱해져 있었고 최초 커밋(70ffae67, 2026-05-07) 이후 3개월간
  손대지 않았다. 실자금 전략(신상저격수)이 숏 전용이다.

  브래킷 0.0 의미와 bars_held 는 `test_bracket_semantics.py` 가 이미 덮고
  있으므로 여기서 반복하지 않는다.

무엇을 고정하나
  1) 숏에 수수료가 실제로 붙는다 (수정 회귀)
  2) 감소분이 정확히 fee*(2-r) — `short_fee_rebacktest.py` 가 재시뮬레이션
     대신 정확식을 쓴 근거. 깨지면 그 재백테스트의 결론이 무효다.
  3) 수수료가 거래 시퀀스를 바꾸지 않는다 — 같은 근거의 다른 절반
  4) 두 실행기의 숏 수수료 식이 같다 — 2026-08-08 사고("같은 policy, 다른
     실행기, 다른 전략")의 재발 감지
  5) **D2 격차는 아직 살아 있다** — backtester 는 미설정 브래킷을 비활성으로,
     orchestrator 는 SL4%/TP10% 로 처리한다. 통합 계획 3b 에서 해소 대상.
     해소하면 이 테스트가 실패하고, 그때 뒤집는 것이 수정의 증거가 된다.

실행:
  cd backend && python3 -m unittest tests.composer_framework.test_short_fee -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.composer_framework.backtester import GenericBacktester  # noqa: E402
from app.composer_framework.orchestrator import PaperOrchestrator  # noqa: E402
from app.composer_framework.paper_session import PaperSession, SessionStore  # noqa: E402
from app.composer_framework.policy import Action, PolicyContext, TradingPolicy  # noqa: E402

FEE = 0.0004


class ShortHold(TradingPolicy):
    """플랫이면 숏 진입, hold 바 뒤 청산. 브래킷은 인자로 제어."""

    def __init__(self, hold: int = 3, sl=0.0, tp=0.0, unset: bool = False):
        self.hold, self._sl, self._tp, self.unset = hold, sl, tp, unset

    def decide(self, c: PolicyContext) -> Action:
        if c.in_position:
            return Action.exit_("time") if c.bars_held >= self.hold else Action.hold()
        if self.unset:
            return Action(kind="enter_short")          # sl/tp 미지정 = None
        return Action(kind="enter_short", sl_price=self._sl, tp_price=self._tp)


def bars(n: int = 40, start: float = 100.0, drift: float = -0.01) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=n, freq="1D")
    px = start * (1 + drift) ** np.arange(n)
    return pd.DataFrame({"open": px, "close": px * 1.001,
                         "high": px * 1.01, "low": px * 0.99}, index=idx)


def bt_run(df, pol, **kw):
    b = GenericBacktester(initial_capital=1e6, size_pct=0.95, fee_rate=FEE, **kw)
    return b._simulate(symbol="T", bars=df, predictions=pd.Series(1.0, index=df.index),
                       policy=pol)


def orch_run(df, pol, tmpdir):
    """orchestrator 의 체결·회계 헬퍼만 직접 구동 (pipeline 우회)."""
    store = SessionStore(str(tmpdir))
    sess = PaperSession(session_id="d", name="d", symbol="T",
                        pipeline_spec={}, initial_capital=1e6, fee_rate=FEE)
    store.save(sess)
    orch = PaperOrchestrator(store)
    for i in range(len(df)):
        bar, ts = df.iloc[i], df.index[i]
        if sess.side != "flat":
            sess.bars_held += 1
        ctx = PolicyContext(timestamp=ts.to_pydatetime(), prediction=1.0,
                            open_price=float(bar["open"]), high_price=float(bar["high"]),
                            low_price=float(bar["low"]), close_price=float(bar["close"]),
                            in_position=(sess.side != "flat"), side=sess.side,
                            entry_price=sess.entry_price, bars_held=sess.bars_held)
        forced = orch._check_forced_exit(sess, bar)
        action = pol.decide(ctx)
        if forced:
            store.append_trade("d", orch._close_position(
                sess, forced["price"], ts, forced["reason"], 1.0))
        elif action.kind == "exit" and sess.side != "flat":
            store.append_trade("d", orch._close_position(
                sess, float(bar["open"]), ts, action.note or "policy", 1.0))
        if sess.side == "flat" and action.kind == "enter_short":
            orch._open_short(sess, float(bar["open"]), ts, action, 1.0)
    return sess, store.read_trades("d")


class TestShortFee(unittest.TestCase):

    def test_short_fee_is_applied(self):
        """수정 회귀 — 숏 수익률이 수수료만큼 낮아진다."""
        df = bars()
        off = bt_run(df, ShortHold(), apply_fee_to_short=False)
        on = bt_run(df, ShortHold())
        self.assertEqual(on.n_trades, off.n_trades)
        self.assertGreater(on.n_trades, 0)
        for a, b in zip(off.trades, on.trades):
            self.assertLess(b.return_pct, a.return_pct)

    def test_reduction_equals_fee_times_two_minus_r(self):
        """감소분 = fee*(2-r). `short_fee_rebacktest.py` 정확식의 근거."""
        df = bars()
        off = bt_run(df, ShortHold(), apply_fee_to_short=False)
        on = bt_run(df, ShortHold())
        for a, b in zip(off.trades, on.trades):
            self.assertAlmostEqual(b.return_pct - a.return_pct,
                                   -FEE * (2.0 - a.return_pct), places=12)

    def test_fee_does_not_change_trade_sequence(self):
        """수수료는 거래 타이밍을 바꾸지 않는다.

        PolicyContext 에 현금 필드가 없어 정책 판단이 자본에 의존하지 않는다.
        이 불변식이 깨지면 정확식 재백테스트가 재시뮬레이션과 달라진다.
        """
        df = bars(60)
        off = bt_run(df, ShortHold(), apply_fee_to_short=False)
        on = bt_run(df, ShortHold())
        key = lambda k: [(t.entry_ts, t.exit_ts, t.side, t.entry_price,
                          t.exit_price, t.exit_reason) for t in k.trades]
        self.assertEqual(key(off), key(on))

    def test_both_engines_agree_on_short_fee(self):
        """두 실행기의 숏 수수료 식이 같아야 한다 (2026-08-08 사고 재발 감지)."""
        df = bars()
        k = bt_run(df, ShortHold())
        with tempfile.TemporaryDirectory() as td:
            _, trades = orch_run(df, ShortHold(), td)
        self.assertEqual(len(trades), k.n_trades)
        self.assertGreater(k.n_trades, 0)
        for a, b in zip(k.trades, trades):
            self.assertAlmostEqual(a.return_pct, float(b["return_pct"]), places=12)

    def test_long_unaffected_by_short_fee_flag(self):
        """롱 회계는 이 수정의 영향을 받지 않는다."""
        df = bars(30, drift=+0.01)

        class LongHold(ShortHold):
            def decide(self, c):
                if c.in_position:
                    return Action.exit_("time") if c.bars_held >= self.hold else Action.hold()
                return Action(kind="enter_long", sl_price=0.0, tp_price=0.0)

        off = bt_run(df, LongHold(), apply_fee_to_short=False)
        on = bt_run(df, LongHold())
        self.assertGreater(on.n_trades, 0)
        for a, b in zip(off.trades, on.trades):
            self.assertAlmostEqual(a.return_pct, b.return_pct, places=15)


class TestKnownDivergence(unittest.TestCase):
    """아직 해소되지 않은 격차를 **살아 있는 채로** 고정한다.

    통합 계획 3b 에서 해소하면 이 테스트가 실패한다. 그때 이름을
    `test_default_bracket_converges` 로 바꾸고 단언을 뒤집는 것이 수정의
    증거다 — 격차가 조용히 사라지거나 조용히 되살아나지 않는다.
    """

    def test_default_bracket_converges(self):
        """D2 — 미설정(None) 브래킷 처리가 두 실행기에서 **같아졌다**. (3b, 2026-08-13)

          종전 backtester  : action.sl_price or 0.0   → 비활성
          종전 orchestrator: price*1.04 / price*0.90  → SL 4% / TP 10% 를 임의 부여
          현재 양쪽        : 비활성. 브래킷은 policy 가 선언한 것만 존재한다.

        정책이 절대 청산하지 않게 두고(hold=999) 가격을 계속 떨어뜨린다.
        종전에는 선언한 적 없는 익절이 있는 쪽만 중간에 빠져나와 두 실행기가
        **다른 전략**이 됐다. 이제 양쪽 다 끝까지 들고 간다.
        """
        df = bars(40, drift=-0.01)          # 숏에 유리 → 예전이라면 팬텀 TP 에 닿는다
        k = bt_run(df, ShortHold(hold=999, unset=True))
        with tempfile.TemporaryDirectory() as td:
            _, trades = orch_run(df, ShortHold(hold=999, unset=True), td)
        self.assertTrue(all(t.exit_reason not in ("sl", "tp") for t in k.trades),
                        "backtester 가 미설정 브래킷을 수준으로 읽었다")
        self.assertTrue(
            all(t["exit_reason"] not in ("sl", "tp") for t in trades),
            "orchestrator 가 선언한 적 없는 브래킷을 장착했다 — D2 가 되살아났다")
        # 청산 자체가 없어야 한다 (policy 도 청산 안 하고 브래킷도 없다)
        self.assertEqual(len(trades), 0,
                         "브래킷이 없는데 청산이 발생했다")

    def test_no_shipped_policy_omits_brackets(self):
        """브래킷 기본값이 사라졌으므로, policy 가 빠뜨리면 **보호 장치가 없다.**

        3b 는 "선언한 적 없는 익절"이라는 함정을 없앴지만, 반대로 "선언을
        잊으면 손절이 없다"는 함정을 연다. 출하되는 policy 가 진입 시 브래킷을
        반드시 채우는지 여기서 강제한다.
        """
        from app.composer_framework import policy as P

        cases = [
            (P.LongOnlyThresholdPolicy(), 1.0),
            (P.LongShortThresholdPolicy(), 1.0),
            (P.LongShortThresholdPolicy(), -1.0),
            (P.LifecycleDecayEarlyExitPolicy(), -1.0),
            (P.FundingReversalPolicy(), 5.0),
            (P.FundingReversalPolicy(), -5.0),
        ]
        for pol, pred in cases:
            c = PolicyContext(timestamp=None, prediction=pred, open_price=100.0,
                              high_price=101.0, low_price=99.0, close_price=100.5,
                              in_position=False, side="flat")
            a = pol.decide(c)
            if not a.kind.startswith("enter"):
                continue
            name = type(pol).__name__
            self.assertIsNotNone(a.sl_price, f"{name}: 진입인데 sl_price 가 None")
            self.assertIsNotNone(a.tp_price, f"{name}: 진입인데 tp_price 가 None")
            self.assertGreater(float(a.sl_price), 0.0,
                               f"{name}: 손절이 비활성(0.0) — 무방비 진입")

    def test_backtester_force_closes_residual_at_end(self):
        """D6 — backtester 만 마지막 바에서 잔여 포지션을 `eod` 로 청산한다.

        orchestrator 는 라이브 세션이라 열어 둔다. 정당한 설계 차이이고 파리티
        게이트도 `eod` 를 비교에서 제외한다. 커널로 옮길 때 `close_at_end`
        설정으로 표현해야 한다.
        """
        df = bars(10)
        k = bt_run(df, ShortHold(hold=999))
        self.assertTrue(any(t.exit_reason == "eod" for t in k.trades))


if __name__ == "__main__":
    unittest.main(verbosity=2)
