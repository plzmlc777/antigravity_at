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
from app.kr_strategy_pool.strategies.s8_supertrend import S8Supertrend
from app.kr_strategy_pool.strategies.s9_volume_spike import S9VolumeSpike
from app.kr_strategy_pool.strategies.s10_obv_trend import S10ObvTrend
from app.kr_strategy_pool.strategies.s11_keltner_breakout import S11KeltnerBreakout
from app.kr_strategy_pool.strategies.s12_closing_range_breakout import S12ClosingRangeBreakout
from app.kr_strategy_pool.strategies.s13_last_hour_momentum import S13LastHourMomentum
from app.kr_strategy_pool.strategies.s14_daily_trend_5m_pullback import S14DailyTrend5mPullback
from app.kr_strategy_pool.strategies.s15_inside_bar_breakout import S15InsideBarBreakout
from app.kr_strategy_pool.strategies.s16_stochastic_reversion import S16StochasticReversion
from app.kr_strategy_pool.strategies.s17_williams_r_reversion import S17WilliamsRReversion
from app.kr_strategy_pool.strategies.s18_zscore_reversion import S18ZScoreReversion
from app.kr_strategy_pool.strategies.s19_ema_cross import S19EmaCross
from app.kr_strategy_pool.strategies.s20_ichimoku import S20IchimokuMomentum
from app.kr_strategy_pool.strategies.s21_adx_rsi import S21AdxRsi
from app.kr_strategy_pool.strategies.s22_mfi_reversion import S22MfiReversion
from app.kr_strategy_pool.strategies.s23_atr_channel_reversion import S23AtrChannelReversion
from app.kr_strategy_pool.strategies.s24_natr_filter_rsi import S24NatrFilterRsi
from app.kr_strategy_pool.strategies.s25_lunch_fade import S25LunchFade
from app.kr_strategy_pool.strategies.s26_open_drive import S26OpenDrive
from app.kr_strategy_pool.strategies.s27_15m_ema_trend import S27_15mEmaTrend
from app.kr_strategy_pool.strategies.s28_daily_atr_filter import S28DailyAtrFilter
from app.kr_strategy_pool.strategies.s29_engulfing import S29BullishEngulfing
from app.kr_strategy_pool.strategies.s30_pin_bar import S30BullishPinBar


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29", help="안정화 phase 시작일")
    p.add_argument("--end", default=None)
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--pool", default="full",
                   choices=["full", "quality"],
                   help="full=30, quality=8 filtered")
    args = p.parse_args()

    print(f"Loading 1m feed for {args.symbol} from {args.start}...")
    feed = fetch_1m_feed(engine, args.symbol, start_date=args.start, end_date=args.end)
    print(f"  loaded {len(feed)} 1m bars")
    print(f"  range: {feed[0]['timestamp']} ~ {feed[-1]['timestamp']}")

    t = KrTournament(args.symbol, feed, args.capital, exchange_name="Kiwoom")

    if args.pool == "quality":
        print(f"\nUsing quality 8-pool")
        for cls in [S2BBReversion, S4OpeningRangeBreakout, S9VolumeSpike,
                    S13LastHourMomentum, S16StochasticReversion, S18ZScoreReversion,
                    S20IchimokuMomentum, S25LunchFade]:
            t.add(cls)
    else:
        for cls in [S1RsiReversion, S2BBReversion, S3GapFill, S4OpeningRangeBreakout,
                    S5VwapReversion, S6DonchianBreakout, S7MacdCross,
                    S8Supertrend, S9VolumeSpike, S10ObvTrend, S11KeltnerBreakout,
                    S12ClosingRangeBreakout, S13LastHourMomentum,
                    S14DailyTrend5mPullback, S15InsideBarBreakout,
                    S16StochasticReversion, S17WilliamsRReversion, S18ZScoreReversion,
                    S19EmaCross, S20IchimokuMomentum, S21AdxRsi, S22MfiReversion,
                    S23AtrChannelReversion, S24NatrFilterRsi, S25LunchFade,
                    S26OpenDrive, S27_15mEmaTrend, S28DailyAtrFilter,
                    S29BullishEngulfing, S30BullishPinBar]:
            t.add(cls)

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
