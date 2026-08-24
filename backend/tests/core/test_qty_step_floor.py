# -*- coding: utf-8 -*-
"""stepSize 내림이 한 스텝을 잃지 않는가 — 회귀 시험.

⚠ 2026-08-24 실계좌 결함 — `math.floor(171.1 / 0.1) * 0.1` 이 **171.0** 을
  냈다. 171.1 / 0.1 이 부동소수로 1710.9999999999998 이기 때문이다.
  포지션 171.1 을 청산하는데 171.0 만 나가 **0.1 이 남았고**, 장부와
  거래소가 어긋났다(고아 포지션 — 2026-07-27 사고와 같은 모양).

  진입에서도 조용히 한 스텝 덜 샀다. 청산 잔량으로 **드러나서야** 보였다.
  이 결함은 키움 포함 모든 어댑터가 쓰는 공용 경로에 있었다.
"""
import unittest

from app.core.qty_rules import _step_ceil, _step_floor, adjust_qty


class StepFloorTest(unittest.TestCase):
    # 전부 스텝의 정확한 배수 — **그대로** 나와야 한다
    EXACT = [(171.1, 0.1),        # 실제 사고 값
             (222.2, 0.1),
             (0.3, 0.1),
             (1.1, 0.1),
             (2.675, 0.001),
             (93.0, 1.0),
             (0.007, 0.001),
             (12345.6, 0.1)]

    def test_keeps_exact_multiples(self):
        for qty, step in self.EXACT:
            with self.subTest(qty=qty, step=step):
                got = _step_floor(qty, step)
                self.assertAlmostEqual(
                    got, qty, places=10,
                    msg=f"{qty} 는 {step} 의 정확한 배수인데 {got} 로 깎였다")

    def test_rounds_down(self):
        for qty, step, want in ((171.15, 0.1, 171.1), (0.35, 0.1, 0.3),
                                (2.6759, 0.001, 2.675), (93.9, 1.0, 93.0)):
            with self.subTest(qty=qty):
                self.assertAlmostEqual(_step_floor(qty, step), want, places=10)

    def test_ceil_rounds_up(self):
        for qty, step, want in ((171.05, 0.1, 171.1), (0.31, 0.1, 0.4),
                                (93.1, 1.0, 94.0)):
            with self.subTest(qty=qty):
                self.assertAlmostEqual(_step_ceil(qty, step), want, places=10)

    def test_adjust_qty_does_not_shave_a_step(self):
        """공용 경로에서도 같아야 한다 — 실제 주문이 지나는 곳이다."""
        filters = {"stepSize": "0.1", "minQty": "0.1", "minNotional": "5"}
        got = adjust_qty(171.1, exchange_name="BinanceFutures",
                         price=0.05489, symbol_filters=filters)
        self.assertAlmostEqual(
            got, 171.1, places=10,
            msg=f"청산 수량이 {got} — 포지션 171.1 에서 먼지가 남는다")

    def test_int_exchange_unaffected(self):
        """정수 수량 거래소(키움)는 그대로여야 한다."""
        self.assertEqual(adjust_qty(10.9, exchange_name="Kiwoom", price=1000), 10)


if __name__ == "__main__":
    unittest.main()
