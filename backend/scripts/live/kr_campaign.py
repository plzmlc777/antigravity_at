#!/usr/bin/env python3
"""다일 분할 캠페인 하네스 — 며칠에 걸쳐 한 종목을 다 팔거나 다 산다.

`kr_slice_exec.py` 가 하루 안의 한 세션을 다룬다면, 이쪽은 그 위층이다.
"일주일 안에 3,441주 전량, 최대한 높게"를 회차별 목표 수량과 회차별 한도가로
번역하고, 회차 결과를 상태 파일에 누적해 다음 회차로 넘긴다.

무엇이 보장되고 무엇이 안 되나
    보장   : **하한가 아래로는 한 주도 안 판다** (매수면 상한 위로 안 산다).
             이건 기한보다 우선한다.
    안 됨  : 기한 안 전량 소진. 시장이 한도가까지 안 오면 물량은 남는다.
             남기는 것이 설계다 — 그게 싫으면 하한을 낮춰야 한다.

쓰는 순서
    1) 계획만 본다 (주문·조회 외 아무것도 안 함)
       python -m scripts.live.kr_campaign --plan \\
         --symbol 061090 --side sell --qty 3441 --bound-price 41000 --sessions 5
    2) 오늘 회차를 페이퍼로 돌린다 (계좌 5, 주문 경로 차단)
       python -m scripts.live.kr_campaign --run \\
         --symbol 061090 --side sell --qty 3441 --bound-price 41000 --sessions 5
    3) 진행 상황
       python -m scripts.live.kr_campaign --status --campaign-id 061090_sell_20260826
    4) 실거래는 --live 와 --account-id 를 함께 명시해야 한다

회차는 날짜가 아니라 **실행 횟수**로 센다. 휴장일을 달력으로 판정하지 않는다.
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

from app.services.kr_campaign import (  # noqa: E402
    REF_LAST_CLOSE, REF_OPEN, Campaign, CampaignConfig, SessionRecord,
    estimate_volume, rehearse,
)
from app.adapters.kiwoom_real import (  # noqa: E402
    MARKET_KRX, MARKET_NXT, MARKET_SOR,
)
from app.services.kr_slice_executor import (  # noqa: E402
    EXEC_LIVE, EXEC_PAPER, KRSliceExecutor, MODE_CROSS, MODE_PASSIVE,
    SCHED_ASAP, SCHED_TWAP, SliceConfig,
)
from scripts.live.kr_slice_exec import (  # noqa: E402
    PAPER_DEFAULT_ACCOUNT_ID, _build_adapter, _list_accounts, _load_account,
)


async def _market_context(adapter, cfg: CampaignConfig):
    """기준가·현재가·예상 거래량. 전부 API 원본에서 가져온다."""
    px = await adapter.get_current_price(cfg.symbol, market=cfg.market)
    market_price = float(px.get("price", 0) or 0)

    daily = await adapter.get_daily_candles(cfg.symbol, market=cfg.market) or []
    recent = daily[-(cfg.volume_lookback + 1):]

    vols = [int(c.get("volume", 0) or 0) for c in recent[:-1]] or \
           [int(c.get("volume", 0) or 0) for c in recent]
    expected_volume = estimate_volume(vols)

    if cfg.ref_mode == REF_OPEN and recent:
        ref = float(recent[-1].get("open", 0) or 0) or market_price
        ref_src = "당일 시가"
    elif len(recent) >= 2:
        ref = float(recent[-2].get("close", 0) or 0) or market_price
        ref_src = "전일 종가"
    else:
        ref = market_price
        ref_src = "현재가(일봉 부족)"

    return {
        "market_price": market_price,
        "name": px.get("name", cfg.symbol),
        "ref_price": ref,
        "ref_source": ref_src,
        "expected_volume": expected_volume,
        "volume_samples": vols,
    }


def _print_plan(cfg: CampaignConfig, camp: Campaign, ctx, plan):
    side_kr = "매도" if cfg.is_sell else "매수"
    bound_kr = "하한" if cfg.is_sell else "상한"
    print("=" * 70)
    print(f" 캠페인 : {cfg.campaign_id}")
    print(f" 종목   : {ctx['name']} ({cfg.symbol})  현재가 {ctx['market_price']:,.0f}원"
          f"  [{cfg.market}]")
    print(f" 목표   : {side_kr} {cfg.total_qty:,}주 / {cfg.sessions}회차")
    print(f" {bound_kr}   : {cfg.bound_price:,}원 "
          f"({'이 아래로는 안 판다' if cfg.is_sell else '이 위로는 안 산다'})")
    print(f" 진행   : {camp.filled_qty:,}/{cfg.total_qty:,}주 "
          f"({camp.filled_qty/cfg.total_qty*100:.1f}%) · 잔여 {camp.remaining_qty:,}주")
    print("-" * 70)
    print(f" 이번 회차 : {plan['seq']}/{plan['of']}"
          f"{'  ← 마지막' if plan['is_last_session'] else ''}")
    print(f" 기준가    : {ctx['ref_price']:,.0f}원 ({ctx['ref_source']})")
    print(f" 요구 우위 : {plan['required_edge_pct']:+.2f}%"
          f"  → 한도가 {plan['limit_price']:,}원"
          f"{'  (하한/상한에 걸림)' if plan['limit_is_bound'] else ''}")
    gap = (plan['limit_price'] - ctx['market_price']) / ctx['market_price'] * 100 \
        if ctx['market_price'] else 0
    print(f" 현재가 대비: {gap:+.2f}%  "
          f"({'시장이 올라와야 체결' if (cfg.is_sell and gap > 0) else ''}"
          f"{'시장이 내려와야 체결' if (not cfg.is_sell and gap < 0) else ''}"
          f"{'지금 체결 가능' if (cfg.is_sell and gap <= 0) or (not cfg.is_sell and gap >= 0) else ''})")
    print(f" 목표 수량 : {plan['target_qty']:,}주"
          f"  (균등 {plan['even_split']:,} / 거래량상한 {plan['volume_cap']:,}"
          f"{' / 기회 배수 적용' if plan['opportunity'] else ''})")
    print(f" 예상 거래량: {plan['expected_volume']:,}주 "
          f"(최근 {len(ctx['volume_samples'])}일 평균, 표본 {ctx['volume_samples']})")
    print("=" * 70)


async def main_async(a):
    if a.list_accounts:
        _list_accounts()
        return 0

    if a.status:
        if not a.campaign_id:
            raise SystemExit("--status 에는 --campaign-id 가 필요하다")
        path = Path(a.out_dir) / f"{a.campaign_id}.json"
        if not path.exists():
            raise SystemExit(f"캠페인 상태 파일이 없다: {path}")
        data = json.loads(path.read_text())
        print(json.dumps(data["summary"], ensure_ascii=False, indent=2))
        print("\n=== 회차 이력 ===")
        for s in data.get("sessions", []):
            print(f"  #{s['seq']} {s['date']} 한도 {s['limit_price']:,} "
                  f"목표 {s['target_qty']:,} → 체결 {s['filled_qty']:,} "
                  f"@{s['avg_price']:,.0f} ({s['stop_reason']})")
        return 0

    if not (a.symbol and a.side and a.qty and a.bound_price):
        raise SystemExit("--symbol --side --qty --bound-price 는 필수다")

    cfg = CampaignConfig(
        symbol=a.symbol, side=a.side, total_qty=a.qty, bound_price=a.bound_price,
        sessions=a.sessions, start_edge_pct=a.start_edge, end_edge_pct=a.end_edge,
        ref_mode=a.ref_mode, daily_pov_cap=a.daily_pov_cap,
        volume_lookback=a.volume_lookback,
        opportunity_edge_pct=a.opportunity_edge, opportunity_mult=a.opportunity_mult,
        slices=a.slices, interval_sec=a.interval, wait_sec=a.wait, poll_sec=a.poll_sec,
        place_mode=a.mode, schedule_mode=a.schedule, market=a.market, pov=a.pov,
        campaign_id=a.campaign_id or "", out_dir=a.out_dir,
    )

    account_id = a.account_id
    if not account_id and not a.account_name:
        if a.live:
            raise SystemExit("실주문(--live)은 --account-id 를 반드시 명시해야 한다")
        account_id = PAPER_DEFAULT_ACCOUNT_ID
    acc = _load_account(account_id, a.account_name)
    adapter = _build_adapter(acc)

    camp = Campaign.load_or_create(cfg)
    ctx = await _market_context(adapter, cfg)
    plan = camp.plan(ctx["ref_price"], ctx["market_price"], ctx["expected_volume"])

    print(f" 계좌   : [{acc['id']}] {acc['name']} "
          f"({'실서버·실주문' if a.live else '조회 전용 — 주문 경로 차단'})")
    _print_plan(cfg, camp, ctx, plan)

    if camp.remaining_qty <= 0:
        print("\n캠페인이 이미 끝났다. 잔여 0주.")
        return 0
    if plan["target_qty"] <= 0:
        print("\n이번 회차 목표가 0주다. 실행하지 않는다.")
        return 0

    if a.rehearse:
        daily = await adapter.get_daily_candles(cfg.symbol, market=cfg.market) or []
        rh = rehearse(cfg, daily, windows=a.rehearse_windows)
        print("\n[과거 리허설] — 같은 정책을 지난 창들에 돌려본 결과")
        if not rh.get("ok"):
            print("  " + rh.get("reason", "실패"))
        else:
            print(f"  창 {rh['windows']}개 중 전량 소진 {rh['complete_windows']}개 "
                  f"({rh['complete_rate']*100:.0f}%) · 중앙 소진율 "
                  f"{rh['median_fill_rate']*100:.0f}%")
            print(f"  평균 체결가 중앙 {rh['median_avg_price']:,.0f}원 "
                  f"(범위 {rh['avg_price_range'][0]:,.0f}~{rh['avg_price_range'][1]:,.0f})")
            for r in rh["results"]:
                mark = "완료" if r["complete"] else f"잔여 {r['remaining_qty']:,}"
                print(f"\n  ▸ {r['start_date']} 시작 → {mark} "
                      f"({r['filled_qty']:,}/{cfg.total_qty:,}주, 평균 {r['avg_price']:,.0f}원)")
                # 판정 기준을 그대로 보여준다 — 매도는 그날 고가가 한도에
                # 닿았는지, 매수는 저가가 닿았는지. 반대쪽을 찍으면 읽는
                # 사람이 판정을 오해한다.
                probe_key, probe_kr = ("high", "고가") if cfg.is_sell else ("low", "저가")
                for d in r["days"]:
                    hit = "체결" if d["reachable"] else "미달"
                    print(f"      {d['date']} 한도 {d['limit']:>7,} "
                          f"{probe_kr} {d[probe_key]:>7,.0f} {hit} "
                          f"목표 {d['target']:>5,} → {d['filled']:>5,}주 "
                          f"(잔여 {d['remaining']:,})")
        print(f"\n  ⚠ 낙관적 근사다. 일봉 고가가 한도에 닿으면 팔린 것으로 쳤고, "
              f"내 물량이 호가를 미는 효과는 없다.")
        if not a.run:
            return 0

    if a.plan_only:
        print("\n--plan 이라 계획만 냈다. 실행하려면 --run 을 쓰라.")
        return 0

    # ── 오늘 회차 실행 ──
    slice_cfg = SliceConfig(
        symbol=cfg.symbol, side=cfg.side,
        total_qty=plan["target_qty"], limit_price=plan["limit_price"],
        slices=cfg.slices, interval_sec=cfg.interval_sec, wait_sec=cfg.wait_sec,
        poll_sec=cfg.poll_sec, place_mode=cfg.place_mode,
        schedule_mode=cfg.schedule_mode, market=cfg.market, pov=cfg.pov,
        deadline_sec=a.deadline, max_slices=a.max_slices,
        open_hhmm=a.open_hhmm, close_hhmm=a.close_hhmm,
        ignore_session_window=a.ignore_session,
        exec_mode=EXEC_LIVE if a.live else EXEC_PAPER,
        run_id=f"{cfg.campaign_id}_s{plan['seq']}",
        out_dir=str(Path(cfg.out_dir) / "sessions"),
    )

    executor = KRSliceExecutor(adapter, slice_cfg, notify=lambda m: print(m, flush=True))
    pf = await executor.run_preflight()
    for w in pf.get("warnings", []):
        print(f"[주의] {w}")
    if not pf.get("ok"):
        for b in pf.get("blockers", []):
            print(f"[차단] {b}")
        print("\n사전점검이 막았다. 이번 회차는 기록하지 않는다.")
        return 1

    if a.live and not a.yes:
        print("\n★ 실주문을 시작한다. 중단하려면 Ctrl+C")
        for i in range(5, 0, -1):
            print(f"  {i}초...", end="\r", flush=True)
            await asyncio.sleep(1)
        print(" " * 30, end="\r")

    print()
    result = await executor.run()

    camp.sessions.append(SessionRecord(
        seq=plan["seq"],
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        ref_price=ctx["ref_price"],
        required_edge_pct=plan["required_edge_pct"],
        limit_price=plan["limit_price"],
        target_qty=plan["target_qty"],
        filled_qty=result["filled_qty"],
        avg_price=result["avg_price"],
        remaining_after=camp.remaining_qty - result["filled_qty"],
        expected_volume=plan["expected_volume"],
        opportunity=plan["opportunity"],
        exec_mode=result["exec_mode"],
        stop_reason=result["stop_reason"],
        ledger=result["ledger"],
    ))
    camp.save()

    print("\n[캠페인 누계]")
    print(json.dumps(camp.summary(), ensure_ascii=False, indent=2))
    if camp.remaining_qty > 0:
        print(f"\n잔여 {camp.remaining_qty:,}주 · 남은 회차 {camp.sessions_left}회. "
              f"다음 회차는 같은 명령을 다시 실행하면 된다.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        description="키움 다일 분할 캠페인 (하한가 불가침 + 회차별 목표)",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)

    p.add_argument("--plan", dest="plan_only", action="store_true", help="계획만 산출")
    p.add_argument("--run", action="store_true", help="오늘 회차 실행")
    p.add_argument("--status", action="store_true", help="진행 상황 조회")
    p.add_argument("--rehearse", action="store_true",
                   help="과거 일봉에 이 정책을 돌려 소진 가능성을 본다")
    p.add_argument("--rehearse-windows", type=int, default=8)
    p.add_argument("--list-accounts", action="store_true")

    p.add_argument("--symbol")
    p.add_argument("--side", choices=["buy", "sell"])
    p.add_argument("--qty", type=int, help="캠페인 총 목표 수량")
    p.add_argument("--bound-price", type=int,
                   help="매도: 이 아래로 안 판다 / 매수: 이 위로 안 산다. 기한보다 우선")
    p.add_argument("--sessions", type=int, default=5, help="몇 회차로 나눌 것인가")
    p.add_argument("--start-edge", type=float, default=1.2,
                   help="첫 회차에 기준가 대비 요구할 우위(%%)")
    p.add_argument("--end-edge", type=float, default=0.0, help="마지막 회차의 요구 우위(%%)")
    p.add_argument("--ref-mode", choices=[REF_LAST_CLOSE, REF_OPEN], default=REF_OPEN,
                   help="기준가. 기본은 당일 시가 (전일 종가는 갭이 큰 날 어긋난다)")
    p.add_argument("--daily-pov-cap", type=float, default=0.10,
                   help="그날 예상 거래량의 이 비율까지만")
    p.add_argument("--volume-lookback", type=int, default=5)
    p.add_argument("--opportunity-edge", type=float, default=2.0,
                   help="기준가 대비 이만큼 유리하면 그날 더 실행")
    p.add_argument("--opportunity-mult", type=float, default=2.0)

    # 기본값은 정규장 6시간을 덮는다 — 12 × (1500+300) = 21,600초.
    # 짧게 잡으면 한도가에 시장이 닿는 순간 주문이 시장에 없다.
    p.add_argument("--slices", type=int, default=12)
    p.add_argument("--interval", type=float, default=300.0)
    p.add_argument("--wait", type=float, default=1500.0)
    p.add_argument("--poll-sec", type=float, default=30.0)
    p.add_argument("--mode", choices=[MODE_PASSIVE, MODE_CROSS], default=MODE_CROSS)
    p.add_argument("--market", choices=[MARKET_KRX, MARKET_NXT, MARKET_SOR],
                   default=MARKET_KRX,
                   help="KRX(기본) / NXT(넥스트레이드) / SOR(통합호가+자동라우팅)")
    p.add_argument("--schedule", choices=[SCHED_TWAP, SCHED_ASAP], default=SCHED_TWAP,
                   help="twap=조각을 마감까지 균등 배분(기본) / asap=체결되는 대로")
    p.add_argument("--pov", type=float, default=0.25)
    p.add_argument("--deadline", type=float, default=7200.0)
    p.add_argument("--max-slices", type=int, default=400)
    p.add_argument("--open-hhmm", default="09:00")
    p.add_argument("--close-hhmm", default="15:15")
    p.add_argument("--ignore-session", action="store_true")

    p.add_argument("--account-id", type=int)
    p.add_argument("--account-name")
    p.add_argument("--live", action="store_true", help="실주문 (없으면 페이퍼)")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--campaign-id", default="")
    p.add_argument("--out-dir", default="runs/kr_campaign")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if not (args.plan_only or args.run or args.status or args.list_accounts):
        args.plan_only = True   # 기본은 계획만. 실행은 명시해야 한다.
    try:
        sys.exit(asyncio.run(main_async(args)))
    except KeyboardInterrupt:
        print("\n중단됨")
        sys.exit(130)
