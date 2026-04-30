"""
KR 전략 토너먼트 실행 스크립트.

Usage:
    cd backend && source venv/bin/activate
    python3 run_kr_tournament.py [--symbol 061090] [--start 2025-12-29] [--capital 3000000]
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.kr_strategy_pool.data_utils import fetch_1m_feed
from app.kr_strategy_pool.tournament import KrTournament
from app.kr_strategy_pool.strategies.s1_rsi_reversion import S1RsiReversion
from app.kr_strategy_pool.strategies.s2_bb_reversion import S2BBReversion
from app.kr_strategy_pool.strategies.s3_gap_fill import S3GapFill
from app.kr_strategy_pool.strategies.s4_opening_range_breakout import S4OpeningRangeBreakout
from app.kr_strategy_pool.strategies.s5_vwap_reversion import S5VwapReversion
from app.kr_strategy_pool.strategies.s6_donchian_breakout import S6DonchianBreakout
from app.kr_strategy_pool.strategies.s7_macd_cross import S7MacdCross


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29", help="안정화 phase 시작일")
    p.add_argument("--end", default=None)
    p.add_argument("--capital", type=int, default=3_000_000)
    args = p.parse_args()

    print(f"Loading 1m feed for {args.symbol} from {args.start}...")
    feed = fetch_1m_feed(engine, args.symbol, start_date=args.start, end_date=args.end)
    print(f"  loaded {len(feed)} 1m bars")
    print(f"  range: {feed[0]['timestamp']} ~ {feed[-1]['timestamp']}")

    t = KrTournament(args.symbol, feed, args.capital, exchange_name="Kiwoom")
    t.add(S1RsiReversion)
    t.add(S2BBReversion)
    t.add(S3GapFill)
    t.add(S4OpeningRangeBreakout)
    t.add(S5VwapReversion)
    t.add(S6DonchianBreakout)
    t.add(S7MacdCross)

    print(f"\nRunning {len(t.entries)} strategies on {args.symbol} (capital ₩{args.capital:,})...")
    results = await t.run_all()

    # rank by return
    ranked = KrTournament.rank(results, metric="return_pct")
    print("\n=== TOURNAMENT RESULT (sorted by return %) ===")
    print(KrTournament.format_table(ranked))

    # extra: friction breakdown
    print("\n=== Detail ===")
    for r in ranked:
        print(
            f"  {r.name:<25} TF={r.timeframe:<3} return={r.return_pct:+7.2f}%  "
            f"trades={r.trades:<3}  fee+tax={r.friction:>9,.0f}  "
            f"final={r.final_equity:>11,.0f}"
            + (f"  [{r.note}]" if r.note else "")
        )


if __name__ == "__main__":
    asyncio.run(main())
