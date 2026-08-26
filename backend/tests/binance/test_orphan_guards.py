"""2026-08-27 고아 사고를 재현하고, 세 가드가 막는지 증명한다."""
import sys, asyncio
sys.path.insert(0, "/home/mint/auto_trading/backend")
sys.path.insert(0, "/home/mint/auto_trading/backend/scripts/binance")
from rsi_live_broker import LiveBroker, LiveOrder


class _Adapter:
    """거래소 대역. fail_n 번은 -1021 로 죽고 그 뒤엔 응답한다."""
    def __init__(self, fail_n=0, pos_qty=2245.0):
        self.fail_n, self.pos_qty, self.synced = fail_n, pos_qty, 0

    async def _signed_get(self, url, params=None):
        if "positionRisk" in url:
            if self.fail_n > 0:
                self.fail_n -= 1
                raise RuntimeError("Binance API Error [-1021]: Timestamp "
                                   "for this request is outside of the recvWindow.")
            if self.pos_qty <= 0:
                return []
            return [{"symbol": "TRXUSDT", "positionAmt": str(self.pos_qty)}]
        return []

    async def sync_server_time(self):
        self.synced += 1

    async def get_outstanding_orders(self):
        return [{"symbol": "TRXUSDT", "order_id": "1", "price": 0.36199,
                 "quantity": 2245.0}] if self.tp_alive else []

    async def get_open_algo_orders(self, symbol=""):
        return [{"symbol": "TRXUSDT", "algoId": "9"}] if self.sl_alive else []


def mk(fail_n=0, pos_qty=2245.0, tp=True, sl=True):
    b = LiveBroker(account_id=8, notional_usd=752.0, dry_run=True)
    a = _Adapter(fail_n, pos_qty)
    a.tp_alive, a.sl_alive = tp, sl
    b._adapter = a
    b.tp_orders["TRXUSDT"] = LiveOrder("TRXUSDT", "1", 0.36199, 2245.0)
    b.sl_orders["TRXUSDT"] = LiveOrder("TRXUSDT", "9", 0.3335041, 2245.0)
    return b, a


ok = True
def chk(name, cond):
    global ok
    ok &= bool(cond)
    print(f"  {'✔' if cond else '✗'} {name}")

# ① -1021 한 번 → 재동기 후 재시도로 살아난다
b, a = mk(fail_n=1)
r = b.positions(strict=True)
chk(f"-1021 1회 → 재동기 {a.synced}회 후 조회 성공 {r}", r == {"TRXUSDT": 2245.0} and a.synced == 1)

# ② 계속 실패 → strict 는 None (빈 딕셔너리와 구분)
b, a = mk(fail_n=9)
chk("계속 실패 → strict=True 는 None", b.positions(strict=True) is None)

# ③ 조회 실패 사이클 → 청산 판정을 아예 하지 않는다  ← 사고의 첫 단추
b, a = mk(fail_n=9)
f = b.detect_exit_fills({"TRXUSDT"})
chk(f"조회 실패 → 청산 0건 {f}", f == {})
chk("장부(익절·손절)가 살아 있다", "TRXUSDT" in b.tp_orders and "TRXUSDT" in b.sl_orders)

# ④ 포지션은 안 보이는데 익절·손절이 둘 다 살아 있다 → 청산으로 세지 않는다
b, a = mk(fail_n=0, pos_qty=0.0, tp=True, sl=True)
f = b.detect_exit_fills({"TRXUSDT"})
chk(f"양쪽 잔존 → 청산 0건 {f}", f == {})
chk("장부 유지", "TRXUSDT" in b.tp_orders and "TRXUSDT" in b.sl_orders)

# ⑤ 정상 익절 — 익절만 사라졌다 → 여전히 잡는다
b, a = mk(fail_n=0, pos_qty=0.0, tp=False, sl=True)
f = b.detect_exit_fills({"TRXUSDT"})
chk(f"익절만 소멸 → tp 로 판정 {f}", f.get("TRXUSDT", ("", 0))[0] == "tp")

# ⑥ 정상 손절 — 손절만 사라졌다 → 여전히 잡는다
b, a = mk(fail_n=0, pos_qty=0.0, tp=True, sl=False)
f = b.detect_exit_fills({"TRXUSDT"})
chk(f"손절만 소멸 → sl 로 판정 {f}", f.get("TRXUSDT", ("", 0))[0] == "sl")

print("\n결과:", "전부 의도대로" if ok else "**어긋남 있음**")
raise SystemExit(0 if ok else 1)
