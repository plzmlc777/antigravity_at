"""
Meta-Strategy MoE Phase 1 acceptance — backtest all 10 multi-TF strategies (s40-s49)
under identical conditions and write results to runs/kr_paper/sweeps/multi_tf_pool_v1.jsonl.

Usage:
  python3 multi_tf_pool_eval.py --start 2026-03-01 --end 2026-04-30
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.kr_strategy_pool.tournament import KrTournament

from app.kr_strategy_pool.strategies.s40_vwap_atr_1m5m import S40_VWAP_ATR_1m5m
from app.kr_strategy_pool.strategies.s41_bb_trend_5m1h import S41_BB_Trend_5m1h
from app.kr_strategy_pool.strategies.s42_rsi_macd_1m import S42_RSI_MACD_1m
from app.kr_strategy_pool.strategies.s43_donchian_atr_1m1h import S43_Donchian_ATR_1m1h
from app.kr_strategy_pool.strategies.s44_ema_time_1m1h import S44_EMA_Time_1m1h
from app.kr_strategy_pool.strategies.s46_triple_vote_1m5m1h import S46_TripleVote_1m5m1h
from app.kr_strategy_pool.strategies.s47_bb_volume_5m import S47_BB_Volume_5m
from app.kr_strategy_pool.strategies.s49_vwap_lunch_1m5m import S49_VWAP_Lunch_1m5m
from app.kr_strategy_pool.strategies.s50_supertrend_adx_1m1h import S50_Supertrend_ADX_1m1h
from app.kr_strategy_pool.strategies.s51_williams_volume_5m import S51_Williams_Volume_5m
from app.kr_strategy_pool.strategies.s52_natr_low_revert_5m import S52_NATR_Low_Revert_5m
from app.kr_strategy_pool.strategies.s53_volume_breakout_1m1h import S53_Volume_Breakout_1m1h

POOL = [
    S40_VWAP_ATR_1m5m,
    S41_BB_Trend_5m1h,
    S42_RSI_MACD_1m,
    S43_Donchian_ATR_1m1h,
    S44_EMA_Time_1m1h,
    S46_TripleVote_1m5m1h,
    S47_BB_Volume_5m,
    S49_VWAP_Lunch_1m5m,
    S50_Supertrend_ADX_1m1h,
    S51_Williams_Volume_5m,
    S52_NATR_Low_Revert_5m,
    S53_Volume_Breakout_1m1h,
]


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2026-03-01")
    p.add_argument("--end", default="2026-04-30")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--out", default="multi_tf_pool_v1.jsonl")
    args = p.parse_args()

    print(f"Loading 1m feed {args.symbol} {args.start}..{args.end}")
    feed_1m = fetch_1m_feed(engine, args.symbol,
                            start_date=args.start, end_date=args.end)
    print(f"  bars: {len(feed_1m)}  first={feed_1m[0]['timestamp']}  last={feed_1m[-1]['timestamp']}")

    tour = KrTournament(args.symbol, feed_1m, args.capital, exchange_name="Kiwoom")
    for cls in POOL:
        tour.add(cls)

    started = datetime.now()
    results = await tour.run_all()
    elapsed = (datetime.now() - started).total_seconds()

    out_dir = Path(__file__).resolve().parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / args.out

    with open(out_path, "w") as f:
        for r in results:
            row = {
                "strategy": r.name,
                "strategy_class": r.strategy_class,
                "timeframe": r.timeframe,
                "return_pct": r.return_pct,
                "pnl": r.pnl,
                "trades": r.trades,
                "sharpe": r.sharpe,
                "max_drawdown": r.max_drawdown,
                "win_rate": r.win_rate,
                "friction": r.friction,
                "final_equity": r.final_equity,
                "initial_capital": r.initial_capital,
                "note": r.note,
                "start": args.start,
                "end": args.end,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nElapsed: {elapsed:.1f}s")
    print(f"Output : {out_path}\n")

    ranked = KrTournament.rank(results, metric="return_pct")
    print(KrTournament.format_table(ranked))

    # 추가: sharpe 기준 ranking + 비고
    print("\n--- by sharpe ---")
    for r in sorted(results, key=lambda x: -(x.sharpe or -1e9)):
        sh = f"{r.sharpe:.2f}" if r.sharpe is not None else "n/a"
        print(f"  {r.name:<32}  ret={r.return_pct:+7.2f}%  sh={sh:>5}  n={r.trades:>4}  {r.note}")


if __name__ == "__main__":
    asyncio.run(main())
