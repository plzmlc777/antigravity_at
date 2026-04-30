"""
KR Paper Cycle Runner — 매일 EOD 1회 발화.

Usage:
    cd backend && source venv/bin/activate
    # 새 세션 생성 (1회만)
    python3 run_kr_paper_cycle.py --create --session 061090_s2_seed --start 2026-04-14 \
        --capital 3000000 --bb-period 25 --bb-std 2.0 --buy-size-pct 0.7

    # 매일 cycle 실행
    python3 run_kr_paper_cycle.py --session 061090_s2_seed
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.paper_runner import PaperRunner
from app.kr_strategy_pool.strategies.s2_bb_reversion import S2BBReversion


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True, help="paper session id")
    p.add_argument("--create", action="store_true", help="create new session")
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2026-04-14", help="paper start date (for create)")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--bb-period", type=int, default=25)
    p.add_argument("--bb-std", type=float, default=2.0)
    p.add_argument("--buy-size-pct", type=float, default=0.7,
                   help="buy size as fraction of cash (lower for safer maxDD)")
    p.add_argument("--capital-gate-dd", type=float, default=-15.0)
    args = p.parse_args()

    runner = PaperRunner(engine)

    if args.create:
        params = {
            "bb_period": args.bb_period,
            "bb_std": args.bb_std,
            "buy_size_pct": args.buy_size_pct,
            "force_eod_exit": True,
        }
        session = runner.create_session(
            session_id=args.session,
            symbol=args.symbol,
            strategy_class=S2BBReversion,
            params=params,
            start_date=args.start,
            initial_capital=args.capital,
            capital_gate_dd_pct=args.capital_gate_dd,
        )
        print(f"Created session: {args.session}")
        print(f"  symbol={session.symbol}  start={session.start_date}  capital=₩{session.initial_capital:,}")
        print(f"  params={session.params}")
        print(f"  meta: {runner.session_meta_path(args.session)}")

    session = runner.load_session(args.session)
    if not session:
        print(f"ERROR: session {args.session} not found", file=sys.stderr)
        sys.exit(1)

    print(f"\nRunning cycle for {args.session}...")
    print(f"  status={session.status}  cycles_so_far={session.cycle_count}")

    cycle = await runner.run_cycle(session, S2BBReversion)
    print(f"\n=== Cycle result ===")
    for k, v in cycle.items():
        if isinstance(v, float):
            print(f"  {k:<22} {v:+,.4f}" if "pct" in k or "drawdown" in k else f"  {k:<22} {v:,.2f}")
        else:
            print(f"  {k:<22} {v}")

    print(f"\n=== Session state ===")
    print(f"  status              {session.status}")
    print(f"  cycle_count         {session.cycle_count}")
    print(f"  last_final_equity   ₩{session.last_final_equity:,.0f}")
    print(f"  last_return_pct     {session.last_return_pct:+.2f}%")
    print(f"  last_max_dd         {session.last_max_dd:.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
