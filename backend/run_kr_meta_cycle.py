"""
KR Meta-Strategy Paper Cycle Runner — Phase 5 wire-in.

Usage:
    cd backend && source venv/bin/activate

    # Create session (1회)
    python3 run_kr_meta_cycle.py --create --session 061090_meta_seed \\
        --start 2026-05-04 --capital 3000000 \\
        --meta-model runs/kr_paper/models/meta_lgbm_v3.pkl

    # Daily cron cycle
    python3 run_kr_meta_cycle.py --session 061090_meta_seed
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.meta_paper_runner import MetaPaperRunner
from app.kr_strategy_pool.meta_strategy_registry import META_STRATEGY_REGISTRY


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True)
    p.add_argument("--create", action="store_true")
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2026-05-04")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--meta-model", default="runs/kr_paper/models/meta_lgbm.pkl")
    p.add_argument("--meta-min-sharpe", type=float, default=0.5)
    p.add_argument("--meta-confidence-min", type=float, default=0.3)
    p.add_argument("--meta-fallback", default="s40_vwap_atr_1m5m")
    p.add_argument("--capital-gate-dd", type=float, default=-15.0)
    args = p.parse_args()

    runner = MetaPaperRunner(engine, META_STRATEGY_REGISTRY)

    if args.create:
        s = runner.create_session(
            session_id=args.session,
            symbol=args.symbol,
            start_date=args.start,
            meta_model_path=args.meta_model,
            meta_pool=list(META_STRATEGY_REGISTRY.keys()),
            initial_capital=args.capital,
            meta_min_sharpe=args.meta_min_sharpe,
            meta_confidence_min=args.meta_confidence_min,
            meta_fallback_strategy=args.meta_fallback,
            capital_gate_dd_pct=args.capital_gate_dd,
        )
        print(f"Created meta session: {args.session}")
        print(f"  symbol={s.symbol}  start={s.start_date}  capital=₩{s.initial_capital:,}")
        print(f"  pool={len(s.meta_pool)} strategies")
        print(f"  meta_model={s.meta_model_path}")
        print(f"  gates: min_sharpe={s.meta_min_sharpe}, confidence={s.meta_confidence_min}, "
              f"fallback={s.meta_fallback_strategy}")
        print(f"  capital_gate_dd={s.capital_gate_dd_pct}%")

    session = runner.load_session(args.session)
    if not session:
        print(f"ERROR: session {args.session} not found", file=sys.stderr)
        sys.exit(1)

    print(f"\nRunning meta cycle for {args.session}...")
    print(f"  status={session.status}  cycles_so_far={session.cycle_count}")

    cycle = await runner.run_cycle(session)
    print(f"\n=== Meta cycle result ===")
    print(f"  data_last_ts        {cycle['data_last_ts']}")
    print(f"  data_bars           {cycle['data_bars']:,}")
    print(f"  top1_strategy       {cycle['top1_strategy']}")
    print(f"  top1_predicted_sh   {cycle['top1_predicted_sharpe']:+.3f}")
    print(f"  confidence          {cycle['confidence']:+.3f}")
    print(f"  safety_gate         {cycle['safety_gate']}")
    print(f"  chosen_strategy     {cycle['chosen_strategy']}")
    print(f"  mode                {cycle['mode']}")
    if cycle["mode"] != "cash_hold":
        print(f"  final_equity        ₩{cycle['final_equity']:,.0f}")
        print(f"  return_pct          {cycle['return_pct']:+.4f}%")
        print(f"  max_drawdown        {cycle['max_drawdown']:+.2f}%")
        print(f"  sharpe              {cycle['sharpe']}")
        print(f"  trades_count        {cycle['trades_count']}")

    print(f"\n=== Session state ===")
    print(f"  status              {session.status}")
    print(f"  cycle_count         {session.cycle_count}")
    print(f"  last_strategy       {session.last_selected_strategy}")
    if session.last_final_equity is not None:
        print(f"  last_final_equity   ₩{session.last_final_equity:,.0f}")
        print(f"  last_return_pct     {session.last_return_pct:+.2f}%")
        print(f"  last_max_dd         {session.last_max_dd:.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
