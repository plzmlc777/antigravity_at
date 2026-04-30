"""
KR Daily Dynamic Selection Runner.

7개 전략 풀을 최근 30일 데이터로 평가 → 1위 + 레짐 진단을 JSON으로 저장.
PM2 cron이 매일 호출.

Usage:
    cd backend && source venv/bin/activate
    python3 run_kr_selector.py --symbol 061090 --output runs/kr_paper/selector/latest_061090.json
"""
import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed, resample_ohlcv
from app.kr_strategy_pool.regime_detector import detect_regime
from app.kr_strategy_pool.dynamic_selector import DynamicSelector
from app.kr_strategy_pool.strategies.s1_rsi_reversion import S1RsiReversion
from app.kr_strategy_pool.strategies.s2_bb_reversion import S2BBReversion
from app.kr_strategy_pool.strategies.s3_gap_fill import S3GapFill
from app.kr_strategy_pool.strategies.s4_opening_range_breakout import S4OpeningRangeBreakout
from app.kr_strategy_pool.strategies.s5_vwap_reversion import S5VwapReversion
from app.kr_strategy_pool.strategies.s6_donchian_breakout import S6DonchianBreakout
from app.kr_strategy_pool.strategies.s7_macd_cross import S7MacdCross


POOL = [
    S1RsiReversion, S2BBReversion, S3GapFill, S4OpeningRangeBreakout,
    S5VwapReversion, S6DonchianBreakout, S7MacdCross,
]


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--lookback-days", type=int, default=45)
    p.add_argument("--regime-window", type=int, default=30)
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--output", default=None, help="JSON output path")
    p.add_argument("--min-trades", type=int, default=5)
    p.add_argument("--max-dd", type=float, default=-25.0)
    args = p.parse_args()

    today = date.today()
    start = today - timedelta(days=args.lookback_days)
    feed_1m = fetch_1m_feed(engine, args.symbol, start_date=str(start))
    if not feed_1m:
        print(f"ERROR: no data for {args.symbol} since {start}", file=sys.stderr)
        sys.exit(1)
    feed_daily = resample_ohlcv(feed_1m, "1D")
    print(f"data: {len(feed_1m)} 1m / {len(feed_daily)} daily (lookback {args.lookback_days}d)")

    # 1) Regime
    regime = detect_regime(feed_daily, lookback=args.regime_window)
    print(f"regime: vol={regime.vol_regime}({regime.metrics.get('vol_std',0):.2f}%) "
          f"trend={regime.trend}({regime.metrics.get('autocorr_lag1',0):+.4f}) "
          f"range={regime.range_phase} liq={regime.liquidity}")

    # 2) Selection
    sel = DynamicSelector(
        symbol=args.symbol, strategy_pool=POOL, capital=args.capital,
        min_trades=args.min_trades, max_dd_threshold=args.max_dd,
    )
    result = await sel.select(feed_1m, regime=regime)

    print(f"\n=== Evaluations ===")
    for e in sorted(result.all_evaluations, key=lambda x: x.score, reverse=True):
        st = e.reject_reason if e.rejected else "OK"
        print(f"  {e.name:<22} ret={e.return_pct:>+7.2f}% sh={e.sharpe or 0:>6.2f} "
              f"wr={e.win_rate or 0:>5.1f}% dd={e.max_drawdown or 0:>+7.2f}% "
              f"n={e.trades:>4} score={e.score:>7.2f}  {st}")

    if result.selected:
        print(f"\n  SELECTED: {result.selected.name} (score {result.selected.score:.2f}, "
              f"conf {result.confidence:.2f})")
    else:
        print(f"\n  SELECTED: NONE")

    # 3) Persist
    report = {
        "ts": datetime.now().isoformat(),
        "symbol": args.symbol,
        "lookback_days": args.lookback_days,
        "regime": regime.as_dict(),
        "evaluations": [e.as_dict() for e in result.all_evaluations],
        "selected": result.selected.as_dict() if result.selected else None,
        "confidence": result.confidence,
    }
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n  saved: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
