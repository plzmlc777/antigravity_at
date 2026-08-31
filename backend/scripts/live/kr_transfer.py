#!/usr/bin/env python3
"""N차 분할 계좌 이전 오케스트레이터 — 지금 뭘 할 차례인지 알려준다.

이 도구는 **주문을 내지 않는다.** 계획을 세우고, 상태를 기억하고, 다음에
실행할 명령을 출력한다. 실제 매매는 `kr_campaign` 이 한다. 3~4주짜리
작업에서 자동 실행보다 사람이 확인하고 누르는 쪽이 안전하다.

쓰는 순서
    1) N 을 고른다 — 회차 수별 위험을 비교한다
       python -m scripts.live.kr_transfer --compare --symbol 061090

    2) 계획을 만든다
       python -m scripts.live.kr_transfer --init \\
         --symbol 061090 --qty 3441 --legs 3 --sell-bound 41000 \\
         --from-account 13 --to-account 1

    3) 이후로는 이것만 반복한다
       python -m scripts.live.kr_transfer --next      # 할 일과 명령
       python -m scripts.live.kr_transfer --sync      # 캠페인 결과 반영

    4) 사람이 표시해야 하는 두 지점
       --mark-transferring   매도 대금으로 계좌 이전을 시작했다
       --mark-transferred    이전 입금을 확인했다

회차 상태는 pending → selling → sold → transferring → buying → done 순으로만
간다. 건너뛰지 않는다 — 건너뛰면 이전 안 된 돈으로 매수를 걸게 된다.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from app.services.kr_transfer import (  # noqa: E402
    BUYING, DONE, PENDING, SELLING, SOLD, TRANSFERRING,
    TransferConfig, TransferLeg, TransferPlan, compare_leg_counts,
)
from scripts.live.kr_slice_exec import (  # noqa: E402
    PAPER_DEFAULT_ACCOUNT_ID, _build_adapter, _load_account,
)

STAGE_KR = {PENDING: "대기", SELLING: "매도중", SOLD: "매도완료",
            TRANSFERRING: "이전중", BUYING: "매수중", DONE: "완료"}


def _state_path(a) -> Path:
    return Path(a.out_dir) / f"{a.transfer_id}.json"


def _load(a) -> TransferPlan:
    p = _state_path(a)
    if not p.exists():
        raise SystemExit(f"이전 계획이 없다: {p}\n  --init 으로 먼저 만들라")
    return TransferPlan.load(p)


async def _compare(a):
    acc = _load_account(a.account_id or PAPER_DEFAULT_ACCOUNT_ID, None)
    adapter = _build_adapter(acc)
    daily = await adapter.get_daily_candles(a.symbol) or []
    rows = compare_leg_counts(daily, a.compare_legs, gap_days=a.gap_days,
                              buy_days=a.buy_days, cost_gap_pct=a.cost_gap,
                              leg_spacing_days=a.leg_spacing)
    print(f"[회차 수 비교] {a.symbol} · 일봉 {len(daily)}개 · "
          f"공백 {a.gap_days}일 / 매수 {a.buy_days}일 / 왕복비용 {a.cost_gap}%\n")
    print(f"  {'N':>3} {'표본':>5} {'소요일':>7} {'손실확률':>9} "
          f"{'중앙':>8} {'하위5%':>9} {'최악':>9}")
    print("  " + "-" * 56)
    for r in rows:
        print(f"  {r['legs']:>3} {r['samples']:>5} {r['calendar_days_span']:>6}일 "
              f"{r['loss_prob']*100:>8.1f}% {r['median_pct']:>+7.2f}% "
              f"{r['p05_pct']:>+8.2f}% {r['worst_pct']:>+8.2f}%")
    print("\n  ⚠ 절대 수치는 낙관적이다 (그날 저가에 전량 체결 가정). "
          "N 사이의 **상대 비교**로만 쓰라.")
    if rows:
        best = min(rows, key=lambda r: (r["loss_prob"], -r["worst_pct"]))
        print(f"\n  손실확률·꼬리 기준 최선: N={best['legs']} "
              f"(손실 {best['loss_prob']*100:.1f}%, 최악 {best['worst_pct']:+.2f}%, "
              f"소요 {best['calendar_days_span']}일)")
    return 0


def _print_status(plan: TransferPlan):
    cfg = plan.cfg
    s = plan.summary()
    print("=" * 72)
    print(f" 이전 : {cfg.transfer_id}  ({cfg.symbol})")
    print(f" 규모 : {cfg.total_qty:,}주 → {cfg.legs}회 분할 "
          f"{cfg.split_quantities()}")
    print(f" 계좌 : {cfg.from_account_id or '?'} → {cfg.to_account_id or '?'}"
          f"   매도 하한 {cfg.sell_bound_price:,}원")
    print("-" * 72)
    print(f" {'회차':>4} {'수량':>7} {'상태':>8} {'매도':>18} {'매수':>18} {'손익':>12}")
    for lg in plan.legs:
        sell = f"{lg.sell_filled:,}@{lg.sell_avg:,.0f}" if lg.sell_filled else "-"
        buy = f"{lg.buy_filled:,}@{lg.buy_avg:,.0f}" if lg.buy_filled else "-"
        pnl = f"{lg.profit:+,.0f}" if lg.buy_filled else "-"
        print(f" {lg.seq:>4} {lg.qty:>7,} {STAGE_KR.get(lg.status, lg.status):>8} "
              f"{sell:>18} {buy:>18} {pnl:>12}")
    print("-" * 72)
    print(f" 누계 : 매도 {s['sold_qty']:,}주 · 매수 {s['bought_qty']:,}주 · "
          f"실현손익 {s['realized_profit']:+,.0f}원")
    print("=" * 72)


def _print_next(plan: TransferPlan):
    na = plan.next_action()
    print(f"\n[다음 할 일] {na['message']}")
    if na.get("command"):
        print(f"\n  {na['command']}")
    if na.get("then"):
        print(f"\n  → {na['then']}")
    bb = na.get("buy_bound")
    if bb and not bb.get("ok"):
        print(f"\n  ⚠ 매수 상한 산출 불가: {bb.get('reason')}")
    elif bb and bb.get("ok"):
        print(f"\n  매수 상한 {bb['bound_price']:,}원 "
              f"(본전 {bb['breakeven']:,} · 매도평균 대비 -{bb['required_gap_pct']:.3f}%)")


def _sync(plan: TransferPlan, campaign_dir: Path) -> int:
    """캠페인 상태 파일을 읽어 회차 상태를 갱신한다."""
    changed = 0
    for lg in plan.legs:
        for kind in ("sell", "buy"):
            cid = f"{plan.cfg.transfer_id}_L{lg.seq}_{kind}"
            path = campaign_dir / f"{cid}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            summ = data["summary"]
            # 회차 원장에서 실측 비용을 모은다
            fees = tax = 0.0
            for sess in data.get("sessions", []):
                led = sess.get("ledger")
                if led and Path(led).exists():
                    sd = json.loads(Path(led).read_text()).get("summary", {})
                    fees += float(sd.get("fees", 0) or 0)
                    tax += float(sd.get("tax", 0) or 0)

            if kind == "sell":
                if summ["filled_qty"] != lg.sell_filled:
                    changed += 1
                lg.sell_campaign_id = cid
                lg.sell_filled = summ["filled_qty"]
                lg.sell_avg = summ["avg_price"]
                lg.sell_fee, lg.sell_tax = fees, tax
                if lg.status in (PENDING, SELLING):
                    if summ["remaining_qty"] <= 0 and summ["filled_qty"] > 0:
                        lg.status = SOLD
                        lg.sell_done_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                    elif summ["filled_qty"] > 0 or summ["sessions_used"] > 0:
                        lg.status = SELLING
            else:
                if summ["filled_qty"] != lg.buy_filled:
                    changed += 1
                lg.buy_campaign_id = cid
                lg.buy_filled = summ["filled_qty"]
                lg.buy_avg = summ["avg_price"]
                lg.buy_fee = fees
                if lg.status in (TRANSFERRING, BUYING):
                    lg.status = DONE if summ["remaining_qty"] <= 0 and summ["filled_qty"] > 0 \
                        else BUYING
                    if lg.status == DONE:
                        lg.buy_done_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return changed


async def main_async(a):
    if a.compare:
        if not a.symbol:
            raise SystemExit("--compare 에는 --symbol 이 필요하다")
        return await _compare(a)

    if a.init:
        for req in ("symbol", "qty", "legs", "sell_bound"):
            if not getattr(a, req):
                raise SystemExit(f"--init 에는 --{req.replace('_', '-')} 가 필요하다")
        cfg = TransferConfig(
            symbol=a.symbol, total_qty=a.qty, legs=a.legs,
            sell_bound_price=a.sell_bound,
            from_account_id=a.from_account or 0, to_account_id=a.to_account or 0,
            min_profit_per_leg=a.min_profit, expected_gap_days=a.gap_days,
            transfer_id=a.transfer_id or "", out_dir=a.out_dir)
        if cfg.state_path().exists() and not a.force:
            raise SystemExit(f"이미 있다: {cfg.state_path()}\n  덮어쓰려면 --force")
        plan = TransferPlan(cfg)
        plan.save()
        print(f"이전 계획 생성: {cfg.state_path()}")
        _print_status(plan)
        _print_next(plan)
        return 0

    plan = _load(a)

    if a.sync:
        n = _sync(plan, Path(a.campaign_dir))
        plan.save()
        print(f"동기화 완료 ({n}건 갱신)")
        _print_status(plan)
        _print_next(plan)
        return 0

    if a.mark_transferring or a.mark_transferred:
        lg = plan.current
        if lg is None:
            raise SystemExit("모든 회차가 끝났다")
        if a.mark_transferring:
            if lg.status != SOLD:
                raise SystemExit(
                    f"{lg.seq}회차 상태가 '{STAGE_KR.get(lg.status)}' 다. "
                    f"매도완료 상태에서만 이전을 시작할 수 있다")
            lg.status = TRANSFERRING
            lg.transfer_started_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            print(f"{lg.seq}회차 이전 시작 표시 ({lg.transfer_started_at})")
        else:
            if lg.status != TRANSFERRING:
                raise SystemExit(
                    f"{lg.seq}회차 상태가 '{STAGE_KR.get(lg.status)}' 다. "
                    f"이전중 상태에서만 입금 확인을 표시할 수 있다")
            lg.status = BUYING
            lg.transfer_done_at = datetime.now().strftime("%Y-%m-%d %H:%M")
            bb = plan.buy_bound_for(lg)
            if bb.get("ok"):
                lg.buy_bound = bb["bound_price"]
            print(f"{lg.seq}회차 입금 확인 표시 ({lg.transfer_done_at})")
        plan.save()
        _print_next(plan)
        return 0

    _print_status(plan)
    if a.next or not a.status:
        _print_next(plan)
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        description="N차 분할 계좌 이전 오케스트레이터 (주문은 내지 않는다)",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--compare", action="store_true", help="회차 수(N)별 위험 비교")
    p.add_argument("--init", action="store_true", help="이전 계획 생성")
    p.add_argument("--status", action="store_true", help="진행 상황")
    p.add_argument("--next", action="store_true", help="다음 할 일")
    p.add_argument("--sync", action="store_true", help="캠페인 결과 반영")
    p.add_argument("--mark-transferring", action="store_true", help="계좌 이전 시작 표시")
    p.add_argument("--mark-transferred", action="store_true", help="입금 확인 표시")

    p.add_argument("--symbol")
    p.add_argument("--qty", type=int)
    p.add_argument("--legs", type=int, help="N — 몇 회에 나눌 것인가")
    p.add_argument("--sell-bound", type=int, help="매도 하한가")
    p.add_argument("--from-account", type=int)
    p.add_argument("--to-account", type=int)
    p.add_argument("--min-profit", type=float, default=0.0, help="회차당 최소 이익(원)")
    p.add_argument("--gap-days", type=int, default=3, help="계좌 이전 예상 소요일")

    p.add_argument("--compare-legs", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6])
    p.add_argument("--buy-days", type=int, default=5)
    p.add_argument("--cost-gap", type=float, default=0.2)
    p.add_argument("--leg-spacing", type=int, default=5, help="회차 간격(거래일)")

    p.add_argument("--account-id", type=int, help="시세 조회용 (기본 페이퍼 계좌)")
    p.add_argument("--transfer-id", default="")
    p.add_argument("--out-dir", default="runs/kr_transfer")
    p.add_argument("--campaign-dir", default="runs/kr_campaign")
    p.add_argument("--force", action="store_true")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.transfer_id == "" and not (args.init or args.compare):
        args.transfer_id = ""   # _load 에서 경로로 확인
    try:
        sys.exit(asyncio.run(main_async(args)))
    except KeyboardInterrupt:
        print("\n중단됨")
        sys.exit(130)
