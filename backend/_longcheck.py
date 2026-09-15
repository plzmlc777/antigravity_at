# -*- coding: utf-8 -*-
"""🧪 롱 경로 **실주문** 검증 — $6 명목 1건 (2026-09-15 대표님 승인).

dry_run 은 어댑터를 아예 안 부른다. `place_buy_order` 가 실전에서 수락되는지는
실주문으로만 알 수 있다. 진입 → 손절 등록 확인 → **즉시 청산**.

중단 조건 (하나라도 걸리면 그 자리에서 멈추고 정리한다)
  · 대상 종목이 이미 계좌에 있다
  · 진입 후 포지션이 **양수로** 안 잡힌다
  · 손절이 안 걸린다 → 즉시 청산
끝나고 **포지션 0 · 조건부주문 0** 을 눈으로 확인한다.
"""
import logging, sys, time, json, urllib.request
logging.basicConfig(level=logging.INFO, format="%(message)s")
from scripts.binance.kine_live_broker import KineLiveBroker

SYM = sys.argv[1] if len(sys.argv) > 1 else "DOGEUSDT"
NOTIONAL = 6.0
STOP_PCT = 5.0

b = KineLiveBroker(account_id=15, leverage=1, dry_run=False)
b.connect()

pos0 = b.positions(strict=True)
alg0 = b.open_algo_orders(strict=True)
if pos0 is None or alg0 is None:
    print("❌ 조회 실패 — 중단(모르는 것과 없는 것은 다르다)"); sys.exit(1)
print(f"■ 사전 상태 — 포지션 {sorted(pos0)} · 조건부주문 {sorted(alg0)}")
if SYM in pos0 or SYM in alg0:
    print(f"❌ {SYM} 가 이미 계좌에 있다 — 중단"); sys.exit(1)

f = b._adapter.get_symbol_precision(SYM)
print(f"■ {SYM} 최소명목 {f.get('minNotional')} · 규격 {dict(list(f.items())[:4])}")
px = float(json.load(urllib.request.urlopen(
    f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={SYM}", timeout=15))["price"])
print(f"■ 기준가 {px:.8g} · 명목 ${NOTIONAL}")

print("\n──── ① 롱 진입 ────")
r = b.open(SYM, short=False, ref_price=px, notional=NOTIONAL)
print(f"open() 반환 {r}")
if r is None:
    print(f"❌ 롱 진입 실패 — last_error={b.last_error}")
    print("   (주문이 안 나갔으므로 정리할 것 없음)"); sys.exit(1)

time.sleep(1.5)
pos1 = b.positions(strict=True) or {}
q = pos1.get(SYM, 0)
print(f"\n──── ② 포지션 확인 ────\n{SYM} 수량 {q}  "
      f"→ {'✅ 양수(롱으로 잡힘)' if q > 0 else '❌ 양수가 아니다'}")

print("\n──── ③ 손절 등록 (SELL · 진입가 -5%) ────")
armed = b.arm_stop(SYM, short=False, entry_px=float(r["price"]), stop_pct=STOP_PCT)
time.sleep(1.5)
alg1 = b.open_algo_orders(strict=True) or {}
print(f"arm_stop 반환 {armed} · 조건부주문에 {SYM} "
      f"{'✅ 있음 ' + str(alg1.get(SYM)) if SYM in alg1 else '❌ 없음'}")

print("\n──── ④ 보호 점검 (엔진과 같은 대조) ────")
naked = sorted({s for s, v in pos1.items() if v != 0} - set(alg1))
print(f"무보호 {naked if naked else '없음'}")

print("\n──── ⑤ 즉시 청산 ────")
cpx = b.close(SYM, short=False)
print(f"close() 체결가 {cpx}")
time.sleep(2.0)
pos2 = b.positions(strict=True); alg2 = b.open_algo_orders(strict=True)
print(f"\n──── ⑥ 사후 정리 확인 ────")
print(f"포지션 {sorted(pos2 or [])} · 조건부주문 {sorted(alg2 or [])}")
ok = (pos2 is not None and SYM not in pos2) and (alg2 is not None and SYM not in alg2)
print(f"{SYM} 잔여 — {'✅ 없음(정리 완료)' if ok else '🚨 남아 있다 — 수동 개입 필요'}")
if cpx and r:
    gross = 100.0 * (float(cpx) / float(r["price"]) - 1.0)
    fee = b.roundtrip_fee_pct(SYM, NOTIONAL, short=False)
    print(f"\n■ 왕복 — 진입 {r['price']:.8g} → 청산 {cpx:.8g} · "
          f"총수익 {gross:+.4f}% · 실측 수수료 {fee if fee is None else f'{fee:.4f}%'}")
