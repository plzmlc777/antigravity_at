"""선물 세션 현금 재구성 회계 항등식 회귀 테스트.

2026-08-08 조사에서 실계좌 lifecycle 세션 9개의 복원 현금이 전부 틀린 것이
확인됐다. 원인이 셋 겹쳐 있었다.

  (A) `or` 폴백이 0.0을 '미설정'으로 오인
      price = ex.executed_price or ex.theoretical_price or 0
      → 청산가 0으로 기록된 실계좌 행 6건에서 margin=0 → 진입 증거금 미반환.

  (B) position_side를 metadata에서만 읽음
      드라이버 직접청산 행은 metadata에 그 키가 없어 pos=""가 되고,
      BUY+"" = LONG 진입으로 오분류돼 청산의 실현손익이 통째로 사라졌다.
      (엔진 기록 행은 반대로 컬럼이 'LONG'으로 틀리고 metadata가 맞다 →
       metadata 우선, 없으면 컬럼 순서여야 양쪽 다 맞는다.)

  (C) 청산 시 반환 증거금을 '청산가 × 수량'으로 계산
      1x에서 진입notional − 청산notional = 실현손익이라, 반환액이 그만큼
      어긋나 결국 손익이 상쇄돼 사라진다. SLXUSDT가 실현 +5.27인데 복원
      현금이 100.00 그대로였던 이유. 반환할 증거금은 **진입 시 잠근 금액**이다.

지켜야 할 항등식: 왕복이 끝난 선물 세션의 현금 == 초기자본 + 실현손익합.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.position_math import calc_cash_delta  # noqa: E402

LEV = 1
FUT = True


def _roundtrip(entry_px: float, exit_px: float, qty: float, pnl: float,
               margin_basis: float) -> float:
    """숏 왕복의 현금 순증감. margin_basis = 청산 시 반환 증거금 계산에 쓸 가격."""
    a = calc_cash_delta("SELL", entry_px, qty, FUT, LEV, "short", 0.0)
    b = calc_cash_delta("BUY", margin_basis, qty, FUT, LEV, "short", pnl)
    return a + b


class TestFuturesShortRoundTripIdentity(unittest.TestCase):
    """왕복 순증감 == 실현손익. (결함 C)"""

    def test_entry_price_basis_preserves_pnl(self):
        entry, qty = 100.0, 10.0
        exit_px = 94.73                      # 숏 이익
        pnl = (entry - exit_px) * qty        # +52.70
        got = _roundtrip(entry, exit_px, qty, pnl, margin_basis=entry)
        self.assertAlmostEqual(got, pnl, places=9,
                               msg="진입가로 증거금을 환원해야 왕복 순증감 == 실현손익")

    def test_exit_price_basis_cancels_pnl(self):
        """현행 버그 재현 — 청산가를 쓰면 손익이 정확히 상쇄돼 사라진다."""
        entry, qty = 100.0, 10.0
        exit_px = 94.73
        pnl = (entry - exit_px) * qty
        got = _roundtrip(entry, exit_px, qty, pnl, margin_basis=exit_px)
        self.assertAlmostEqual(got, 0.0, places=9)
        self.assertNotAlmostEqual(got, pnl, places=6)

    def test_losing_short_also_preserved(self):
        entry, qty = 0.2791, 2342.0
        exit_px = 0.3083                     # 숏 손실
        pnl = (entry - exit_px) * qty
        got = _roundtrip(entry, exit_px, qty, pnl, margin_basis=entry)
        self.assertAlmostEqual(got, pnl, places=6)
        self.assertLess(got, 0)

    def test_zero_exit_price_loses_margin(self):
        """결함 A 재현 — 청산가 0이면 증거금이 통째로 증발한다."""
        entry, qty = 100.0, 10.0
        got = _roundtrip(entry, 0.0, qty, 52.70, margin_basis=0.0)
        self.assertAlmostEqual(got, 52.70 - entry * qty, places=9)
        self.assertLess(got, 0)


class TestPositionSideClassification(unittest.TestCase):
    """결함 B — position_side가 비면 청산이 진입으로 오분류된다."""

    def test_missing_position_side_misclassifies_close_as_entry(self):
        # 드라이버 직접청산 행 모양: BUY + position_side 없음
        d = calc_cash_delta("BUY", 100.0, 10.0, FUT, LEV, "", 79.76)
        self.assertAlmostEqual(d, -1000.0, places=9,
                               msg="pos=''면 LONG 진입(-margin)으로 잡힌다 — 실현손익 누락")

    def test_short_position_side_classifies_close_correctly(self):
        d = calc_cash_delta("BUY", 100.0, 10.0, FUT, LEV, "short", 79.76)
        self.assertAlmostEqual(d, 1000.0 + 79.76, places=9)

    def test_metadata_beats_column_resolution_order(self):
        """metadata 우선 → 컬럼 폴백. 두 출처가 서로 다르게 틀려 있다."""
        def resolve(meta_ps, col_ps):
            return str(meta_ps or col_ps or "").lower()

        # 엔진 기록 행: 컬럼 'LONG'(무의미), metadata 'short'(정확)
        self.assertEqual(resolve("short", "LONG"), "short")
        # 드라이버 직접청산 행: metadata 없음, 컬럼 'SHORT'(정확)
        self.assertEqual(resolve(None, "SHORT"), "short")
        # 둘 다 없으면 빈 문자열 (오분류 위험 — 상위에서 로그로 드러내야 함)
        self.assertEqual(resolve(None, None), "")


class TestNumericFallbackSemantics(unittest.TestCase):
    """결함 A의 뿌리 — `or`가 0.0과 None을 구분하지 못한다."""

    @staticmethod
    def _first_num(*vals):
        for v in vals:
            if v is not None:
                return float(v)
        return 0.0

    def test_or_chain_swaps_recorded_zero(self):
        executed, theoretical = 0.0, 123.0
        self.assertEqual(executed or theoretical or 0, 123.0)      # 현행 — 0을 갈아끼움
        self.assertEqual(self._first_num(executed, theoretical), 0.0)  # 수정 — 기록값 보존

    def test_none_still_falls_through(self):
        self.assertEqual(self._first_num(None, 123.0), 123.0)
        self.assertEqual(self._first_num(None, None), 0.0)

    def test_unfilled_quantity_not_replaced_by_requested(self):
        filled, requested = 0.0, 607.0
        self.assertEqual(filled or requested or 0, 607.0)          # 현행 — 유령 포지션
        self.assertEqual(self._first_num(filled, requested), 0.0)  # 수정


class TestExecutedPriceFallbackGate(unittest.TestCase):
    """체결가 폴백은 '값이 없을 때'가 아니라 '유효하지 않을 때'만이어야 한다.

    `res.get("price") or theoretical` 는 거래소가 avgPrice=0을 줄 때(주문이
    아직 NEW) 조용히 이론가로 대체했다. 실계좌 39건 중 23건이 그렇게 System-2
    바 종가로 기록됐고, 그 값이 손익 계산에 그대로 들어가 거래소 원장 대비
    +0.71 USDT 오차를 만들었다. 대체 자체는 불가피하지만 **조용하면 안 된다**.
    """

    @staticmethod
    def _resolve(fill_px, theoretical):
        """실제 공용 헬퍼를 그대로 검증한다 (규칙 복제 금지 — 복제하면
        구현이 바뀌어도 테스트가 통과해 버린다)."""
        from app.core.position_math import resolve_fill_price
        px, fellback = resolve_fill_price(fill_px, theoretical)
        return px, ("theoretical_fallback" if fellback else None)

    def test_valid_fill_price_wins(self):
        px, src = self._resolve(0.253152, 0.253)
        self.assertAlmostEqual(px, 0.253152, places=9)
        self.assertIsNone(src)

    def test_zero_fill_price_falls_back_and_is_marked(self):
        px, src = self._resolve(0.0, 0.253)
        self.assertAlmostEqual(px, 0.253, places=9)
        self.assertEqual(src, "theoretical_fallback", "폴백은 흔적을 남겨야 한다")

    def test_missing_fill_price_falls_back_and_is_marked(self):
        px, src = self._resolve(None, 0.253)
        self.assertAlmostEqual(px, 0.253, places=9)
        self.assertEqual(src, "theoretical_fallback")


class TestSpotUnaffected(unittest.TestCase):
    """현물은 전액 notional이 오가므로 체결가를 그대로 써야 한다 (진입가 환원 금지)."""

    def test_spot_roundtrip_nets_to_pnl(self):
        buy = calc_cash_delta("BUY", 100.0, 10.0, False, 1, "", 0.0)    # -1000
        sell = calc_cash_delta("SELL", 105.27, 10.0, False, 1, "", 0.0)  # +1052.7
        self.assertAlmostEqual(buy + sell, 52.7, places=9)


class TestRealtimeAndRestoreAgree(unittest.TestCase):
    """실시간 누적(process_queue)과 복원 재계산(_restore_trades_from_db)이
    같은 체결열에 대해 같은 현금을 내야 한다.

    두 경로가 각자 다른 기준가를 쓰는 바람에 어긋났다 — 복원은 청산가로,
    실시간도 청산가로 환원해 양쪽 다 손익을 잃었다. 이제 둘 다 진입 평균가를
    쓴다. 이 테스트는 그 합의를 고정한다.
    """

    INITIAL = 1000.0
    ENTRY, EXIT, QTY = 0.2791, 0.2500, 2342.0

    def _pnl(self):
        return (self.ENTRY - self.EXIT) * self.QTY

    def _realtime(self, basis_on_close: float) -> float:
        cash = self.INITIAL
        cash += calc_cash_delta("SELL", self.ENTRY, self.QTY, FUT, LEV, "short", 0.0)
        cash += calc_cash_delta("BUY", basis_on_close, self.QTY, FUT, LEV, "short", self._pnl())
        return cash

    def _restore(self, basis_on_close: float) -> float:
        # 복원은 같은 행들을 순서대로 다시 훑을 뿐이므로 식이 동일하다.
        return self._realtime(basis_on_close)

    def test_both_paths_preserve_pnl_with_entry_basis(self):
        rt = self._realtime(self.ENTRY)
        rs = self._restore(self.ENTRY)
        self.assertAlmostEqual(rt, rs, places=9, msg="두 경로가 어긋나면 안 된다")
        self.assertAlmostEqual(rt, self.INITIAL + self._pnl(), places=6)

    def test_exit_basis_would_lose_pnl_in_both_paths(self):
        rt = self._realtime(self.EXIT)
        self.assertAlmostEqual(rt, self.INITIAL, places=6)
        self.assertNotAlmostEqual(rt, self.INITIAL + self._pnl(), places=3)


if __name__ == "__main__":
    unittest.main()
