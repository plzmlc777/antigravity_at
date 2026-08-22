"""호가단위 반올림 — 과학적 표기 틱에서 0 이 나오던 결함 회귀 시험.

2026-08-22 실계좌: `adjust_price('DOGEUSDT', 0.09618)` 이 **0.0** 을 냈다.
tickSize '0.000010' → float 1e-05 → `str()` 이 '1e-05' 라 점이 없고,
자체 자릿수 계산이 0 을 내서 `round(0.09618, 0)` = 0.0 이 됐다.
거래소는 -4001 로 거절한다. **틱 < 0.0001 인 종목 전부**가 막혀 있었다.
"""
import unittest

from app.adapters.binance_base import BinanceBaseAdapter


class _Stub(BinanceBaseAdapter):
    """거래소 접속 없이 필터만 주입한다."""

    def __init__(self, tick: str):
        self._tick = tick

    def get_symbol_precision(self, symbol: str) -> dict:
        return {"tickSize": self._tick}


class TestAdjustPrice(unittest.TestCase):
    def test_scientific_notation_tick_keeps_precision(self):
        # 결함의 정확한 재현 조건 — 뒤에 0 이 붙은 소수 틱
        self.assertAlmostEqual(_Stub("0.000010").adjust_price("X", 0.09618),
                               0.09618, places=8)
        self.assertAlmostEqual(_Stub("0.00001").adjust_price("X", 0.09618),
                               0.09618, places=8)
        self.assertAlmostEqual(_Stub("0.000001").adjust_price("X", 0.0961834),
                               0.096183, places=8)

    def test_never_returns_zero_for_positive_price(self):
        """0 은 이 저장소에서 **시장가 신호**다. 지정가가 조용히 시장가로
        바뀌면 슬리피지 전제가 통째로 깨진다 — 틱보다 작으면 한 틱으로 올린다."""
        for tick in ("0.000010", "0.00001", "0.0001", "0.001", "0.01"):
            for px in (0.09618, 0.002441, 1.5, 90000.0):
                out = _Stub(tick).adjust_price("X", px)
                self.assertGreater(out, 0.0,
                                   f"tick={tick} px={px} → {out} (0 이면 시장가로 둔갑)")
        # 틱보다 작은 가격 → 정확히 한 틱
        self.assertAlmostEqual(_Stub("0.01").adjust_price("X", 0.002), 0.01)

    def test_ordinary_ticks_unchanged(self):
        self.assertAlmostEqual(_Stub("0.10").adjust_price("X", 90000.04), 90000.0)
        self.assertAlmostEqual(_Stub("0.01").adjust_price("X", 1.234), 1.23)

    def test_non_positive_price_passes_through(self):
        # price<=0 은 MARKET 신호로 쓰인다 — 손대지 않는다
        self.assertEqual(_Stub("0.01").adjust_price("X", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
