"""지정가 손절 — 트리거와 체결이 다른 사건인가."""
import unittest
from app.composer_framework.kernel import (KernelState, KernelConfig, step,
                                           open_position, Action)
from app.composer_framework.policy import TradingPolicy


class _Hold(TradingPolicy):
    def decide(self, c):
        return Action.hold()


def _bar(o, h, l, c):
    return dict(open_price=o, high_price=h, low_price=l, close_price=c)


class TestStopLimit(unittest.TestCase):
    def _open(self, cfg):
        st = KernelState(cash=10000.0)
        act = Action(kind="enter_long", sl_price=99.0, tp_price=105.0)
        return open_position(st, "enter_long", _bar(100, 100, 100, 100),
                             "t0", act, cfg)

    def test_trigger_bar_does_not_fill(self):
        """손절가를 깬 봉에서는 체결되지 않는다 — 봉 안의 순서를 모른다."""
        cfg = KernelConfig(fee_rate=0.0005, sl_limit=True)
        st = self._open(cfg)
        st2, res = step(st, ts="t1", open_price=100, high_price=100.5,
                        low_price=98.5, close_price=99.5, prediction=0.0,
                        policy=_Hold(), cfg=cfg)
        self.assertEqual(len(res.closed), 0, "트리거 봉에서 체결됐다")
        self.assertTrue(st2.sl_armed, "트리거가 기록되지 않았다")

    def test_fills_when_price_returns(self):
        cfg = KernelConfig(fee_rate=0.0005, sl_limit=True)
        st = self._open(cfg)
        st, _ = step(st, ts="t1", open_price=100, high_price=100.5,
                     low_price=98.5, close_price=98.6, prediction=0.0,
                     policy=_Hold(), cfg=cfg)
        st, res = step(st, ts="t2", open_price=98.6, high_price=99.2,
                       low_price=98.5, close_price=99.1, prediction=0.0,
                       policy=_Hold(), cfg=cfg)
        self.assertEqual(len(res.closed), 1, "되돌아왔는데 체결 안 됐다")
        self.assertEqual(res.closed[0].exit_reason, "sl_limit")
        self.assertAlmostEqual(res.closed[0].exit_price, 99.0)

    def test_never_returns_stays_open(self):
        cfg = KernelConfig(fee_rate=0.0005, sl_limit=True)
        st = self._open(cfg)
        for i in range(5):
            st, res = step(st, ts=f"t{i}", open_price=98, high_price=98.2,
                           low_price=90, close_price=91, prediction=0.0,
                           policy=_Hold(), cfg=cfg)
            self.assertEqual(len(res.closed), 0)
        self.assertEqual(st.side, "long", "미체결인데 포지션이 사라졌다")

    def test_market_stop_unchanged(self):
        """`sl_limit=False` 는 기존 동작 그대로 — 깨는 순간 체결."""
        cfg = KernelConfig(fee_rate=0.0005)
        st = self._open(cfg)
        st, res = step(st, ts="t1", open_price=100, high_price=100.5,
                       low_price=98.5, close_price=99.5, prediction=0.0,
                       policy=_Hold(), cfg=cfg)
        self.assertEqual(len(res.closed), 1)
        self.assertEqual(res.closed[0].exit_reason, "sl")

    def test_sl_limit_is_maker(self):
        """지정가 손절은 메이커 — 수수료가 시장가 손절보다 싸다."""
        base = dict(fee_rate=0.0005, fee_rate_maker=0.0002)
        m = KernelConfig(**base)
        l = KernelConfig(**base, sl_limit=True)
        sm = self._open(m)
        sm, rm = step(sm, ts="t1", open_price=100, high_price=100.5,
                      low_price=98.5, close_price=99.5, prediction=0.0,
                      policy=_Hold(), cfg=m)
        sl = self._open(l)
        sl, _ = step(sl, ts="t1", open_price=100, high_price=100.5,
                     low_price=98.5, close_price=98.6, prediction=0.0,
                     policy=_Hold(), cfg=l)
        sl, rl = step(sl, ts="t2", open_price=98.6, high_price=99.2,
                      low_price=98.5, close_price=99.1, prediction=0.0,
                      policy=_Hold(), cfg=l)
        self.assertGreater(rl.closed[0].return_pct, rm.closed[0].return_pct,
                           "지정가 손절이 시장가보다 유리하지 않다")


if __name__ == "__main__":
    unittest.main()
