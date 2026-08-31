#!/usr/bin/env python3
"""왕복 손익분기 — 판 값에서 되살 상한을 뽑는다.

두 가지 모드가 있고, **쓸 수 있으면 실측을 쓴다.**

  1) 매도 전 (시나리오)
     아직 안 팔았으면 비용률을 모른다. 여러 요율에 대한 표를 낸다.
     python -m scripts.live.kr_roundtrip --sell-price 42000 --qty 3441

  2) 매도 후 (실측)
     매도 캠페인 상태 파일에서 실제 체결·수수료·세금을 읽어 매수 상한을
     산출한다. 가정이 하나도 안 들어간다.
     python -m scripts.live.kr_roundtrip --from-campaign runs/kr_campaign/061090_sell_20260826.json

  `--target-profit` 을 주면 그만큼 남기는 매수 상한을 낸다. 안 주면 본전이다.
  나온 값을 매수 캠페인의 `--bound-price` 로 그대로 넣으면 된다.

⚠ 페이퍼 매도에는 실측 비용이 없다. 페이퍼 원장의 수수료·세금은 0 이고
   그건 "비용이 없다"가 아니라 "안 재졌다"는 뜻이다. 페이퍼 상태로
   `--from-campaign` 을 돌리면 경고와 함께 시나리오 표로 넘어간다.
"""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.services.kr_roundtrip import (  # noqa: E402
    RoundTrip, cost_scenarios, required_gap_pct,
)


def _print_scenarios(sell_price: float, qty: int, target_profit: float):
    print(f"\n[시나리오] 매도 평균가 {sell_price:,.0f}원 · {qty:,}주 "
          f"(총 {sell_price*qty:,.0f}원)")
    print("  실측 비용이 없어 요율별 표를 낸다. 대표님 요율에 맞는 행을 보시라.\n")
    print(f"  {'거래세':>7} {'수수료':>8} {'왕복비용':>9} {'필요하락':>9} "
          f"{'본전 매수가':>12} {'목표포함':>12}")
    print("  " + "-" * 62)
    for r in cost_scenarios(sell_price):
        rt = RoundTrip(qty=qty, sell_notional=sell_price * qty,
                       sell_fee=sell_price * qty * r["fee_rate_pct"] / 100,
                       sell_tax=sell_price * qty * r["tax_rate_pct"] / 100,
                       buy_fee_rate=r["fee_rate_pct"] / 100)
        with_target = rt.buy_bound_tick(target_profit) if target_profit else 0
        print(f"  {r['tax_rate_pct']:>6.3f}% {r['fee_rate_pct']:>7.4f}% "
              f"{r['total_cost_pct']:>8.3f}% {r['required_gap_pct']:>8.3f}% "
              f"{r['breakeven_buy']:>12,}"
              f"{(f'{with_target:>12,}' if target_profit else '           -')}")
    print("\n  왕복 손익분기는 **수량과 무관**하다 — 요율만의 함수다.")
    if target_profit:
        print(f"  '목표포함' 은 {target_profit:,.0f}원을 남기려면 그 이하로 사야 한다는 뜻.")


def _from_campaign(path: Path, target_profit: float, buy_fee_rate_override):
    data = json.loads(path.read_text())
    cfg = data["config"]
    summary = data["summary"]
    sessions = data.get("sessions", [])

    if cfg["side"] != "sell":
        raise SystemExit(f"매도 캠페인이 아니다: side={cfg['side']}")

    qty = summary["filled_qty"]
    if qty <= 0:
        raise SystemExit("체결 수량이 0 이라 왕복을 계산할 수 없다")
    notional = summary["filled_notional"]

    # 회차 원장에서 실측 비용을 모은다
    fees = tax = 0.0
    measured = False
    for s in sessions:
        led = s.get("ledger")
        if not led or not Path(led).exists():
            continue
        sd = json.loads(Path(led).read_text()).get("summary", {})
        fees += float(sd.get("fees", 0) or 0)
        tax += float(sd.get("tax", 0) or 0)
        measured = measured or bool(sd.get("cost_measured"))

    print(f"[캠페인] {cfg['campaign_id']} — {cfg['symbol']} 매도")
    print(f"  체결 {qty:,}주 · 평균 {summary['avg_price']:,.0f}원 "
          f"· 총액 {notional:,.0f}원")

    if not measured or (fees == 0 and tax == 0):
        print("\n  ⚠ 실측 비용이 없다 (페이퍼이거나 비용이 안 찍혔다).")
        print("     0원을 '비용 없음'으로 읽으면 매수 상한이 높게 나와 손해를 본다.")
        print("     시나리오 표로 넘어간다.")
        _print_scenarios(summary["avg_price"], qty, target_profit)
        return 0

    rt = RoundTrip(qty=qty, sell_notional=notional, sell_fee=fees, sell_tax=tax,
                   buy_fee_rate=(buy_fee_rate_override
                                 if buy_fee_rate_override is not None
                                 else fees / notional))
    bound = rt.buy_bound_tick(target_profit)
    print(f"\n[실측 비용]")
    print(f"  위탁수수료 {fees:,.0f}원 ({rt.implied_sell_fee_rate*100:.4f}%)")
    print(f"  거래세     {tax:,.0f}원 ({rt.implied_tax_rate*100:.4f}%)")
    print(f"  순수취     {rt.net_proceeds:,.0f}원")
    print(f"\n[매수 상한]")
    print(f"  본전 매수가 {rt.buy_bound_tick(0):,}원 "
          f"(매도평균 대비 {(rt.sell_avg - rt.buy_bound_tick(0))/rt.sell_avg*100:.3f}% 아래)")
    if target_profit:
        print(f"  목표 {target_profit:,.0f}원 포함 → {bound:,}원")
    chk = rt.profit_at(bound)
    print(f"\n  이 값에 되사면: 지출 {chk['total_spent']:,.0f}원 · "
          f"손익 {chk['profit']:+,.0f}원 ({chk['profit_pct']:+.4f}%)")
    print(f"\n  → 매수 캠페인에 이렇게 넣으면 된다:")
    print(f"     --side buy --qty {qty} --bound-price {bound}")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="왕복(매도→매수) 손익분기와 매수 상한 산출",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--from-campaign", help="매도 캠페인 상태 파일 경로")
    p.add_argument("--sell-price", type=float, help="시나리오용 매도 평균가")
    p.add_argument("--qty", type=int, default=1, help="시나리오용 수량")
    p.add_argument("--target-profit", type=float, default=0.0,
                   help="최소 남기고 싶은 이익(원)")
    p.add_argument("--buy-fee-rate", type=float, default=None,
                   help="매수 수수료율 (미지정 시 실측 매도 요율과 같다고 본다)")
    a = p.parse_args()

    if a.from_campaign:
        return _from_campaign(Path(a.from_campaign), a.target_profit, a.buy_fee_rate)
    if a.sell_price:
        _print_scenarios(a.sell_price, a.qty, a.target_profit)
        return 0
    raise SystemExit("--from-campaign 또는 --sell-price 중 하나가 필요하다")


if __name__ == "__main__":
    sys.exit(main())
