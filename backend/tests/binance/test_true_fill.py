"""2026-08-29 MUSDT 를 재현 — 청산가를 추측이 아니라 체결 내역에서 가져오는가."""
import sys
sys.path.insert(0, "/home/mint/auto_trading/backend")
sys.path.insert(0, "/home/mint/auto_trading/backend/scripts/binance")
from rsi_live_broker import LiveBroker, LiveOrder


class _Adapter:
    """거래소 대역. 실제 MUSDT 체결(부분체결 4건 @0.9970)을 흉내낸다."""
    def __init__(self, tp=False, sl=False, trades=True, fail=False):
        self.tp_alive, self.sl_alive, self.trades, self.fail = tp, sl, trades, fail

    async def _signed_get(self, url, params=None):
        if "positionRisk" in url:
            return []                       # 포지션 없음
        if "userTrades" in url:
            if self.fail:
                raise RuntimeError("Binance API Error [-1021]")
            if not self.trades:
                return []
            return [  # 진입(BUY) 뒤 청산(SELL) — 꼬리의 연속 SELL 만 집계돼야 한다
                {"side": "BUY",  "qty": "751", "price": "1.0019"},
                {"side": "SELL", "qty": "61",  "price": "0.9970"},
                {"side": "SELL", "qty": "61",  "price": "0.9970"},
                {"side": "SELL", "qty": "61",  "price": "0.9970"},
                {"side": "SELL", "qty": "568", "price": "0.9970"},
            ]
        return []

    async def get_outstanding_orders(self):
        return [{"symbol": "MUSDT", "order_id": "1", "price": 1.0641,
                 "quantity": 751.0}] if self.tp_alive else []

    async def get_open_algo_orders(self, symbol=""):
        return [{"symbol": "MUSDT", "algoId": "9"}] if self.sl_alive else []


def mk(**kw):
    b = LiveBroker(account_id=8, notional_usd=752.0, dry_run=True)
    b._adapter = _Adapter(**kw)
    b.tp_orders["MUSDT"] = LiveOrder("MUSDT", "1", 1.0641, 751.0)
    b.sl_orders["MUSDT"] = LiveOrder("MUSDT", "9", 0.99695, 751.0)
    b.entry_ms["MUSDT"] = 1
    return b


ok = True
def chk(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(f"  {'✔' if cond else '✗'} {name:<54}{extra}")

# ① 그날의 상황 — 둘 다 사라졌다 → 체결가를 되찾아야 한다
f = mk(tp=False, sl=False).detect_exit_fills({"MUSDT"})
why, px = f.get("MUSDT", ("", 0))
chk("둘 다 소멸 → 실체결 0.9970 회수", abs(px - 0.9970) < 1e-9, f"({why}, {px})")
chk("  옛 동작(0.0 반환)이 아니다", px > 0)

# ② 손절만 소멸 — 주문가와 실체결이 같으면 그대로
f = mk(tp=True, sl=False).detect_exit_fills({"MUSDT"})
why, px = f.get("MUSDT", ("", 0))
chk("손절만 소멸 → sl 로 판정 · 실체결가", why == "sl" and abs(px - 0.9970) < 1e-9,
    f"({why}, {px})")

# ③ 체결 내역이 비었다 → 0 (추정치임을 상위에 알린다)
f = mk(tp=False, sl=False, trades=False).detect_exit_fills({"MUSDT"})
chk("체결 내역 없음 → 0 (조용히 지어내지 않는다)", f.get("MUSDT") == ("unknown", 0.0))

# ④ 조회가 실패해도 죽지 않는다
f = mk(tp=False, sl=False, fail=True).detect_exit_fills({"MUSDT"})
chk("조회 실패 → 예외 없이 0", f.get("MUSDT") == ("unknown", 0.0))

# ⑤ 꼬리의 연속 SELL 만 — 진입 BUY 가 섞이면 안 된다
px, qty = mk().closing_fill("MUSDT")
chk("청산 수량 751 (진입 BUY 미포함)", abs(qty - 751.0) < 1e-9, f"(qty={qty})")

print("\n결과:", "전부 의도대로" if ok else "**어긋남 있음**")
raise SystemExit(0 if ok else 1)
