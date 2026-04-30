"""
KR Paper Cycle Runner — 매일 EOD 1회 발화.

Usage:
    cd backend && source venv/bin/activate

    # 새 세션 생성 (1회만)
    python3 run_kr_paper_cycle.py --create --session 061090_s2_seed --start 2026-04-14 \
        --capital 3000000 --strategy s2_bb_reversion \
        --params '{"bb_period":25,"bb_std":2.0,"buy_size_pct":0.7}'

    # 매일 cycle 실행 (기존 session, strategy는 메타에서 자동 로드)
    python3 run_kr_paper_cycle.py --session 061090_s2_seed
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Type

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.base import KrStrategyBase
from app.kr_strategy_pool.paper_runner import PaperRunner

# Strategy registry — strategy_name → class
from app.kr_strategy_pool.strategies.s2_bb_reversion import S2BBReversion
from app.kr_strategy_pool.strategies.s16_stochastic_reversion import S16StochasticReversion
from app.kr_strategy_pool.strategies.s31_robust_confirmation import S31RobustConfirmation
from app.kr_strategy_pool.strategies.s31_1m_variants import (
    S31_1m_SamePeriod, S31_1m_PeriodX3, S31_1m_PeriodX5,
)
from app.kr_strategy_pool.strategies.s31_adaptive_confirmation import (
    S31AdaptiveConfirmation,
)
from app.kr_strategy_pool.strategies_optimized import (
    S2OptBBReversion, S5OptVwapReversion, S16OptStochasticReversion,
)


STRATEGY_REGISTRY: dict[str, Type[KrStrategyBase]] = {
    "s2_bb_reversion": S2BBReversion,
    "s2_opt_bb_reversion": S2OptBBReversion,
    "s5_opt_vwap_reversion": S5OptVwapReversion,
    "s16_stochastic_reversion": S16StochasticReversion,
    "s16_opt_stochastic_reversion": S16OptStochasticReversion,
    "s31_robust_confirmation": S31RobustConfirmation,
    "s31_1m_same_period": S31_1m_SamePeriod,
    "s31_1m_period_x3": S31_1m_PeriodX3,
    "s31_1m_period_x5": S31_1m_PeriodX5,
    "s31_adaptive_confirmation": S31AdaptiveConfirmation,
}


def get_strategy_class(name: str) -> Type[KrStrategyBase]:
    if name not in STRATEGY_REGISTRY:
        raise ValueError(
            f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}"
        )
    return STRATEGY_REGISTRY[name]


def parse_params(s: str | None) -> dict:
    if not s:
        return {}
    return json.loads(s)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True, help="paper session id")
    p.add_argument("--create", action="store_true", help="create new session")
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2026-04-14", help="paper start date (for create)")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--strategy", default=None,
                   help="strategy name (registry key); for --create only")
    p.add_argument("--params", default=None,
                   help="strategy params as JSON string (for --create)")
    p.add_argument("--capital-gate-dd", type=float, default=-15.0)
    # backward compat: legacy flags
    p.add_argument("--bb-period", type=int, default=None)
    p.add_argument("--bb-std", type=float, default=None)
    p.add_argument("--buy-size-pct", type=float, default=None)
    args = p.parse_args()

    runner = PaperRunner(engine)

    if args.create:
        # strategy 결정 — 우선순위: --strategy > KR_PAPER_STRATEGY env > default 's2_bb_reversion'
        strat_name = (
            args.strategy
            or os.environ.get("KR_PAPER_STRATEGY")
            or "s2_bb_reversion"
        )
        strategy_class = get_strategy_class(strat_name)

        # params: --params JSON 우선, 없으면 legacy 인자 합성
        params = parse_params(args.params)
        if not params:
            # legacy: bb_period/bb_std/buy_size_pct만 있으면 합성
            params = {"force_eod_exit": True}
            if args.bb_period is not None:
                params["bb_period"] = args.bb_period
            if args.bb_std is not None:
                params["bb_std"] = args.bb_std
            if args.buy_size_pct is not None:
                params["buy_size_pct"] = args.buy_size_pct

        session = runner.create_session(
            session_id=args.session,
            symbol=args.symbol,
            strategy_class=strategy_class,
            params=params,
            start_date=args.start,
            initial_capital=args.capital,
            capital_gate_dd_pct=args.capital_gate_dd,
        )
        print(f"Created session: {args.session}")
        print(f"  symbol={session.symbol}  strategy={strat_name}")
        print(f"  start={session.start_date}  capital=₩{session.initial_capital:,}")
        print(f"  params={session.params}")
        print(f"  meta: {runner.session_meta_path(args.session)}")

    session = runner.load_session(args.session)
    if not session:
        print(f"ERROR: session {args.session} not found", file=sys.stderr)
        sys.exit(1)

    # 메타에 저장된 strategy_name으로 class 동적 로드
    strategy_class = get_strategy_class(session.strategy_name)

    print(f"\nRunning cycle for {args.session}...")
    print(f"  strategy={session.strategy_name}  status={session.status}  "
          f"cycles_so_far={session.cycle_count}")

    cycle = await runner.run_cycle(session, strategy_class)
    print(f"\n=== Cycle result ===")
    for k, v in cycle.items():
        if isinstance(v, float):
            print(
                f"  {k:<22} {v:+,.4f}"
                if "pct" in k or "drawdown" in k
                else f"  {k:<22} {v:,.2f}"
            )
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
