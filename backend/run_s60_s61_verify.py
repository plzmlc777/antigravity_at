"""S60/S61 baseline + IS/OOS verification.

Step 1 of validation flow:
  1. Run S60_005930 + S61_122630 with DEFAULT_PARAMS on full available data
  2. Run on IS (2025-05~2025-10) and OOS (2025-11~2026-04) splits
  3. Compare against docstring claims (S60: IS sharpe 4.32 / OOS 4.10,
     S61: IS sharpe 10.36 / OOS 7.83)

Output: backend/runs/kr_paper/sweeps/s60_s61_baseline.jsonl
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.core.kr_backtest_engine import KrBacktestEngine
from app.kr_strategy_pool.strategies.s60_instflow_consensus import S60_InstFlowConsensus
from app.kr_strategy_pool.strategies.s61_frgn_trend_leverage import S61_FrgnTrendLeverage


CASES = [
    {"name": "S60_005930", "symbol": "005930", "cls": S60_InstFlowConsensus,
     "params": dict(S60_InstFlowConsensus.DEFAULT_PARAMS)},
    {"name": "S61_122630", "symbol": "122630", "cls": S61_FrgnTrendLeverage,
     "params": dict(S61_FrgnTrendLeverage.DEFAULT_PARAMS)},
]

# IS/OOS split (each ~6 months)
IS_END = "2025-10-31"
OOS_START = "2025-11-01"


async def run_backtest(cls, symbol, params, start, end, capital=3_000_000):
    feed = fetch_1m_feed(engine, symbol, start_date=start, end_date=end)
    if not feed:
        return {"error": "no feed", "n_bars": 0}
    eng = KrBacktestEngine(cls, exchange_name="Kiwoom")
    cfg = {"symbol": symbol, **params}
    stats = await eng.run_single_backtest(
        config=cfg, feed=feed, initial_capital=capital, symbol=symbol,
    )
    return {
        "n_bars": len(feed),
        "feed_first": feed[0]["timestamp"],
        "feed_last": feed[-1]["timestamp"],
        "return_pct": stats.get("return_pct"),
        "sharpe": stats.get("sharpe_ratio"),
        "win_rate": stats.get("win_rate"),
        "max_drawdown": stats.get("max_drawdown"),
        "trades_count": stats.get("trades_count"),
        "final_equity": stats.get("final_equity"),
    }


async def main():
    out_dir = Path(__file__).parent / "runs" / "kr_paper" / "sweeps"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "s60_s61_baseline.jsonl"
    rows = []

    for case in CASES:
        print(f"\n=== {case['name']} ({case['symbol']}) — DEFAULT_PARAMS ===")
        print(f"  params: {json.dumps(case['params'])}")

        # FULL period (everything available)
        full = await run_backtest(case["cls"], case["symbol"], case["params"],
                                  start=None, end=None)
        print(f"  [FULL]   bars={full['n_bars']:>6}  ret={full['return_pct']:>+8.2f}%  "
              f"sharpe={full['sharpe']:>6.2f}  winR={full['win_rate']:>5.1f}%  "
              f"maxDD={full['max_drawdown']:>+7.2f}%  trades={full['trades_count']}")

        # IS (~2025-05 ~ 2025-10)
        is_res = await run_backtest(case["cls"], case["symbol"], case["params"],
                                    start=None, end=IS_END)
        print(f"  [IS]     bars={is_res['n_bars']:>6}  ret={is_res['return_pct']:>+8.2f}%  "
              f"sharpe={is_res['sharpe']:>6.2f}  winR={is_res['win_rate']:>5.1f}%  "
              f"maxDD={is_res['max_drawdown']:>+7.2f}%  trades={is_res['trades_count']}")

        # OOS (~2025-11 ~ 2026-04)
        oos = await run_backtest(case["cls"], case["symbol"], case["params"],
                                 start=OOS_START, end=None)
        print(f"  [OOS]    bars={oos['n_bars']:>6}  ret={oos['return_pct']:>+8.2f}%  "
              f"sharpe={oos['sharpe']:>6.2f}  winR={oos['win_rate']:>5.1f}%  "
              f"maxDD={oos['max_drawdown']:>+7.2f}%  trades={oos['trades_count']}")

        rows.append({
            "case": case["name"],
            "symbol": case["symbol"],
            "params": case["params"],
            "full": full,
            "is": is_res,
            "oos": oos,
        })

    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
