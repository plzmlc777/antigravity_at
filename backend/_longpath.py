# -*- coding: utf-8 -*-
"""🔬 롱 경로 검증 — 실거래 브로커를 **DRY 로** 태워 방향별 출력을 비교한다.

왜 이 방식인가
  `--live --dry-run` 으로 엔진을 통째로 돌리면 `broker.notify` 가 dry_run
  게이트를 안 타서 **가짜 진입 알림이 텔레그램으로 나간다.** 정지 중에
  체결이 난 것처럼 보인다. 그래서 엔진이 쓰는 **같은 브로커 클래스**를
  직접 태운다 — open/arm_stop/close 는 전부 dry_run 에서 [DRY] 만 찍는다.

⚠ 주문·레버리지 변경 없음. ensure_leverage 는 dry_run 에서 조기 반환한다.
⚠ 실계좌 상태(state.json·HALT_ENTRY)를 건드리지 않는다 — 원장을 안 연다.
"""
import logging, sys
logging.basicConfig(level=logging.INFO, format="%(message)s")
from scripts.binance.kine_live_broker import KineLiveBroker

SYM = "ASTRUSDT"     # 지금 계좌8 이 들고 있는 유동 종목
NOTIONAL = 115.0

b = KineLiveBroker(account_id=15, leverage=1, dry_run=True)
b.connect()
print(f"\n■ 어댑터 결선 — 방향별 주문 함수가 둘 다 있나")
for fn in ("place_buy_order", "place_short_order", "place_algo_stop",
           "close_position", "set_leverage", "adjust_price", "adjust_quantity"):
    print(f"   {fn:<20} {'있음' if callable(getattr(b._adapter, fn, None)) else '**없음**'}")

px = None
try:
    px = float(b._adapter.get_symbol_price(SYM)) if callable(
        getattr(b._adapter, "get_symbol_price", None)) else None
except Exception:
    pass
if not px:
    import urllib.request, json
    px = float(json.load(urllib.request.urlopen(
        f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={SYM}",
        timeout=15))["price"])
print(f"\n■ 기준가 {SYM} = {px:.8g} · 명목 ${NOTIONAL}")

for short in (True, False):
    lab = "숏" if short else "롱"
    print(f"\n──────── {lab} 경로 ────────")
    qty, why = b.size(SYM, NOTIONAL, px)
    print(f"size()      수량 {qty:.8g} {('· ' + why) if why else ''}")
    print(f"ensure_lev  {b.ensure_leverage(SYM)}x")
    r = b.open(SYM, short, px, NOTIONAL)
    print(f"open()      반환 {r}")
    b.arm_stop(SYM, short, px, 5.0)
    trig = px * ((1 + 0.05) if short else (1 - 0.05))
    print(f"            손절 트리거 이론값 {trig:.8g} "
          f"({'진입가 위' if short else '진입가 아래'})")
    b.close(SYM, short)
    print(f"entry_fill  체결 방향 = {'SELL' if short else 'BUY'}")
    print(f"closing_fill 체결 방향 = {'BUY' if short else 'SELL'}")
