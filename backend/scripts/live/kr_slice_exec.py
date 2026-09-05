#!/usr/bin/env python3
"""키움 국내주식 **분할 체결 하네스** — 얇은 종목에 대량 주문을 한도 안에서 채운다.

계약
    매수는 `--limit-price` **이하**로만, 매도는 그 가격 **이상**으로만 낸다.
    지정가만 쓴다. 시장가는 이 도구가 절대 쓰지 않는다. 한도 안에서 못 채운
    수량은 미체결로 남기고 원장에 적는다 — 한도를 넘겨서 채우지 않는다.

쓰는 순서 (예비비행 → 본실행)
    페이퍼는 계좌를 안 주면 5번(키움 로컬 테스트)에서 돈다. 실주문(--live)은
    계좌를 반드시 명시해야 하고, 안 주면 실행을 거부한다.

    1) 계좌 확인
       python -m scripts.live.kr_slice_exec --list-accounts
    2) 호가 응답 확인 (처음 한 번, 종목 하나로)
       python -m scripts.live.kr_slice_exec --account-id 5 --probe-orderbook 005930
    3) 페이퍼 — 주문을 내지 않고 실시간 호가로 체결을 판정한다 (기본값)
       python -m scripts.live.kr_slice_exec --account-id 5 \\
           --symbol 005930 --side buy --qty 5000 --limit-price 74000 \\
           --slices 20 --interval 20 --wait 15 --pov 0.25
    4) 본실행 — `--live` 를 명시해야 실주문이 나간다
       ... 위와 같은 인자 + --live

페이퍼가 무엇을 재고 무엇을 못 재나
    잰다   : 한도 안에 실제로 얼마나 물량이 있었는지, 그 물량을 슬라이스로
             나눠 먹었을 때 평균 체결가가 얼마인지, 계획 시간 안에 목표
             수량이 채워지는지.
    못 잰다: 줄서기(메이커) 체결. 호가만으로는 내 앞의 대기 물량을 알 수
             없어 **인정하지 않는다**. 매수는 매도호가가 내 가격까지 내려와야
             체결로 친다. 그래서 `--mode passive` 는 체결 0 이 자주 나오고,
             그게 정상이다. 체결 규모를 보려면 `--mode cross` 로 재라.

안전장치
    · `--live` 없으면 주문은 한 건도 안 나간다 (페이퍼가 기본값).
    · 실서버 계좌면 배너 출력 후 카운트다운(`--yes` 로 생략).
    · Ctrl+C / 예외 / 정상 종료 어느 경로로 끝나도 **우리 미체결은 전량 취소**.
    · 정규장 창(기본 09:00~15:15) 밖에서는 새 주문을 내지 않는다.
    · 슬라이스마다 원장 저장 — 중간에 죽어도 기록이 남는다.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from app.core import security  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402,F401  (mapper 해석용)
from app.models.account import ExchangeAccount  # noqa: E402
from app.adapters.kiwoom_real import KiwoomRealAdapter  # noqa: E402
from app.adapters.kiwoom_real import (  # noqa: E402
    MARKET_KRX, MARKET_NXT, MARKET_SOR,
)
from app.services.kr_slice_executor import (  # noqa: E402
    EXEC_LIVE, EXEC_PAPER, KRSliceExecutor, MODE_CROSS, MODE_PASSIVE,
    SCHED_ASAP, SCHED_TWAP, SliceConfig,
)

# 페이퍼 조회 계좌 — **날짜별로 돌려 쓴다.**
#
# 한 계좌에만 조회를 몰면 나머지 계좌가 놀다가 "미사용"으로 앱키가 해지된다.
# 2026-09-04 에 실제로 계좌 1·13·4 가 그렇게 막혔고, 매일 수백 회 조회를
# 받던 계좌 5 만 살아남았다. 조회 전용이며 주문은 이 경로로 나가지 않는다
# (페이퍼는 ReadOnlyAdapter 가 막고, --live 는 계좌 명시를 요구한다).
def paper_account_order():
    try:
        from app.services.kr_quote_accounts import quote_account_order
        return quote_account_order()
    except Exception:
        return [5]


PAPER_DEFAULT_ACCOUNT_ID = 5   # 폴백용 (로테이션 실패 시)


def _load_account(account_id=None, account_name=None):
    db = SessionLocal()
    try:
        q = db.query(ExchangeAccount).filter(ExchangeAccount.exchange_name == "Kiwoom")
        if account_id:
            acc = q.filter(ExchangeAccount.id == account_id).first()
        elif account_name:
            acc = q.filter(ExchangeAccount.account_name == account_name).first()
        else:
            acc = None
        if not acc:
            raise SystemExit("키움 계좌를 찾지 못했다. --list-accounts 로 확인하라")
        return {
            "id": acc.id,
            "name": acc.account_name,
            "account_no": acc.account_number or "",
            "is_virtual": bool(acc.is_virtual),
            "api_url": acc.api_url or "",
            "app_key": security.decrypt_key(acc.encrypted_access_key or ""),
            "secret_key": security.decrypt_key(acc.encrypted_secret_key or ""),
        }
    finally:
        db.close()


def _list_accounts():
    db = SessionLocal()
    try:
        rows = db.query(ExchangeAccount).filter(
            ExchangeAccount.exchange_name == "Kiwoom"
        ).all()
        print(f"{'id':>4}  {'계좌명':<24} {'서버':<8} 계좌번호")
        for a in rows:
            print(f"{a.id:>4}  {(a.account_name or ''):<24} "
                  f"{'모의' if a.is_virtual else '실서버':<8} {a.account_number or ''}")
    finally:
        db.close()


def _build_adapter(acc):
    if not acc["app_key"] or not acc["secret_key"]:
        raise SystemExit(f"계좌 {acc['id']} 의 API 키가 비어 있다")
    return KiwoomRealAdapter(
        app_key=acc["app_key"],
        secret_key=acc["secret_key"],
        account_no=acc["account_no"],
        account_name=acc["name"],
        api_url=acc["api_url"],
        is_virtual=acc["is_virtual"],
    )


async def _probe_orderbook(adapter, symbol, a_market=MARKET_KRX):
    """호가 응답의 **실제 키 이름**을 눈으로 확인한다. 추측으로 파서를 쓰지 않기 위해서."""
    book = await adapter.get_orderbook(symbol, market=a_market)
    print(json.dumps({k: v for k, v in book.items() if k != "raw"},
                     ensure_ascii=False, indent=2))
    if book.get("raw") is not None:
        print("\n⚠ 파싱 실패 — 응답 원문 키 목록:")
        raw = book["raw"]
        if isinstance(raw, dict):
            for k in sorted(raw.keys()):
                print(f"   {k} = {raw[k]!r}")
        else:
            print(raw)
        print("\n→ 위 키 이름을 kiwoom_real.get_orderbook 의 후보 목록에 추가하면 된다")
    else:
        print("\n호가 파싱 정상 — pov(참여율) 제한을 쓸 수 있다")


async def _countdown(sec, banner):
    print(banner)
    for i in range(sec, 0, -1):
        print(f"  {i}초 후 시작 — 중단하려면 Ctrl+C", end="\r", flush=True)
        await asyncio.sleep(1)
    print(" " * 50, end="\r")


async def main_async(a):
    if a.list_accounts:
        _list_accounts()
        return 0

    account_id, account_src = a.account_id, "지정"
    if not account_id and not a.account_name:
        if a.live:
            raise SystemExit(
                "실주문(--live)은 계좌를 반드시 명시해야 한다. "
                "--account-id 를 지정하라 (--list-accounts 로 확인)"
            )
        order = paper_account_order() or [PAPER_DEFAULT_ACCOUNT_ID]
        account_id, account_src = order[0], f"조회 로테이션 {order}"

    acc = _load_account(account_id, a.account_name)
    adapter = _build_adapter(acc)

    if a.probe_orderbook:
        await _probe_orderbook(adapter, a.probe_orderbook, a.market)
        return 0

    if not (a.symbol and a.side and a.qty and a.limit_price):
        raise SystemExit("--symbol --side --qty --limit-price 는 필수다")

    cfg = SliceConfig(
        symbol=a.symbol,
        side=a.side,
        total_qty=a.qty,
        limit_price=a.limit_price,
        slices=a.slices,
        slice_qty=a.slice_qty,
        interval_sec=a.interval,
        wait_sec=a.wait,
        place_mode=a.mode,
        market=a.market,
        schedule_mode=a.schedule,
        offset_ticks=a.offset_ticks,
        pov=a.pov,
        rest_when_outside=not a.no_rest,
        deadline_sec=a.deadline,
        max_slices=a.max_slices,
        close_hhmm=a.close_hhmm,
        open_hhmm=a.open_hhmm,
        ignore_session_window=a.ignore_session,
        max_notional=a.max_notional,
        exec_mode=EXEC_LIVE if a.live else EXEC_PAPER,
        poll_sec=a.poll_sec,
        paper_take_ratio=a.paper_take_ratio,
        run_id=a.run_id or "",
        out_dir=a.out_dir,
    )

    if acc["is_virtual"]:
        server = "모의서버"
    elif a.live:
        server = "★ 실서버 · 실주문 ★"
    else:
        server = "실서버(조회 전용 — 주문 경로 차단)"
    print("=" * 64)
    print(f" 계좌   : [{acc['id']}] {acc['name']}  ({server}, {acc['account_no']})"
          f"{'' if account_src == '지정' else f'  ← {account_src}'}")
    print(f" 종목   : {cfg.symbol}   시장 {cfg.market}")
    print(f" 방향   : {cfg.side.upper()}  {cfg.total_qty:,}주")
    print(f" 한도   : {cfg.limit_price:,}원 {'이하로만 매수' if cfg.side=='buy' else '이상으로만 매도'}")
    print(f" 분할   : {cfg.slices}조각 × 기본 {cfg.base_slice_qty:,}주 "
          f"/ 간격 {cfg.interval_sec}s / 대기 {cfg.wait_sec}s")
    print(f" 배치   : {cfg.place_mode} offset={cfg.offset_ticks}틱 pov={cfg.pov}")
    if a.live:
        print(f" 모드   : 실주문 (LIVE)")
    else:
        print(f" 모드   : 페이퍼 (주문 없음 · 실시간 호가로 체결 판정, "
              f"폴링 {cfg.poll_sec}s, 잔량인정 {cfg.paper_take_ratio:.0%})")
    print("=" * 64)

    executor = KRSliceExecutor(adapter, cfg, notify=lambda m: print(m, flush=True))

    pf = await executor.run_preflight()
    print("\n[사전점검]")
    print(json.dumps(pf, ensure_ascii=False, indent=2, default=str))
    if a.preflight_only:
        return 0 if pf.get("ok") else 1
    if not pf.get("ok"):
        print("\n차단 사유가 있어 실행하지 않는다.")
        return 1

    if a.live and not a.yes:
        await _countdown(5, f"\n{server} 실주문을 시작한다.")

    print()
    summary = await executor.run()
    print("\n[요약]")
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        description="키움 국내주식 분할 체결 하네스 (지정가 한도 + 슬라이스)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--list-accounts", action="store_true", help="키움 계좌 목록")
    p.add_argument("--account-id", type=int,
                   help=f"미지정 시 페이퍼는 계좌 {PAPER_DEFAULT_ACCOUNT_ID}, "
                        f"실주문(--live)은 지정 필수")
    p.add_argument("--account-name")
    p.add_argument("--probe-orderbook", metavar="SYMBOL",
                   help="호가 응답 원문 키 확인 (처음 한 번)")

    p.add_argument("--symbol")
    p.add_argument("--side", choices=["buy", "sell"])
    p.add_argument("--qty", type=int, help="총 목표 수량(주)")
    p.add_argument("--limit-price", type=int,
                   help="매수: 이 가격 이하로만 / 매도: 이 가격 이상으로만")

    p.add_argument("--slices", type=int, default=10)
    p.add_argument("--slice-qty", type=int, default=0, help="0이면 총량/조각수")
    p.add_argument("--interval", type=float, default=20.0, help="슬라이스 간격(초)")
    p.add_argument("--wait", type=float, default=15.0, help="주문 후 체결 대기(초)")
    p.add_argument("--mode", choices=[MODE_PASSIVE, MODE_CROSS], default=MODE_PASSIVE,
                   help="passive=내 편 호가에 줄서기(메이커) / cross=상대 호가 치기")
    p.add_argument("--market", choices=[MARKET_KRX, MARKET_NXT, MARKET_SOR],
                   default=MARKET_KRX,
                   help="KRX(기본) / NXT(넥스트레이드) / SOR(통합호가+자동라우팅)")
    p.add_argument("--schedule", choices=[SCHED_TWAP, SCHED_ASAP], default=SCHED_TWAP,
                   help="twap=조각을 마감까지 균등 배분(기본) / asap=체결되는 대로")
    p.add_argument("--offset-ticks", type=int, default=0,
                   help="+면 공격적(매수는 위, 매도는 아래). 한도는 넘지 않는다")
    p.add_argument("--pov", type=float, default=0.0,
                   help="한도 내 호가잔량의 이 비율까지만 (0~1). 수량을 줄이는 쪽으로만 작동")
    p.add_argument("--no-rest", action="store_true",
                   help="현재 호가가 한도 밖이면 걸어두지 않고 건너뛴다")

    p.add_argument("--deadline", type=float, default=1800.0, help="전체 상한(초)")
    p.add_argument("--max-slices", type=int, default=200)
    p.add_argument("--max-notional", type=float, default=0.0, help="총 체결금액 상한(원)")
    p.add_argument("--open-hhmm", default="09:00")
    p.add_argument("--close-hhmm", default="15:15",
                   help="이 시각 이후 새 주문 금지 (종가 동시호가 회피)")
    p.add_argument("--ignore-session", action="store_true",
                   help="정규장 창 검사를 끈다 (시간외 등 특수 상황)")

    p.add_argument("--live", action="store_true", help="실주문 (없으면 페이퍼)")
    p.add_argument("--poll-sec", type=float, default=2.0,
                   help="페이퍼: 체결 판정용 호가 폴링 간격(초)")
    p.add_argument("--paper-take-ratio", type=float, default=1.0,
                   help="페이퍼: 보이는 잔량 중 내가 먹을 수 있다고 볼 비율 (0~1)")
    p.add_argument("--yes", action="store_true", help="실주문 카운트다운 생략")
    p.add_argument("--preflight-only", action="store_true", help="사전점검만 하고 종료")
    p.add_argument("--run-id", default="")
    p.add_argument("--out-dir", default="runs/kr_slice_exec")
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        sys.exit(asyncio.run(main_async(args)))
    except KeyboardInterrupt:
        print("\n중단됨 — 미체결은 종료 경로에서 취소된다")
        sys.exit(130)
