"""
Selector-Guided Simulation — full_v1.jsonl의 selector 추천대로 매일 운영했다면.

방법:
  1. full_v1.jsonl에서 selected 전략의 변화 지점(switching points) 추출
  2. 각 segment에 대해:
     - 시작 자본: 이전 segment 최종 자본 (첫 segment는 initial_capital)
     - 전략: selector가 그 segment 동안 추천한 전략
     - 데이터: segment의 시작~끝 날짜 기간
  3. 누적 P&L 계산 및 S2 단독 운영과 비교

가정:
  - selector switching = 즉시 적용 (실거래의 EOD 결정 → 다음날 매매와 같음)
  - segment 진입 시 모든 포지션 청산되고 새 전략 시작 (구현 단순화)
  - 각 segment는 KrBacktestEngine으로 독립 backtest
"""
import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.core.kr_backtest_engine import KrBacktestEngine
from app.kr_strategy_pool.base import KrStrategyBase
from app.kr_strategy_pool.data_utils import fetch_1m_feed, resample_ohlcv
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


STRATEGY_BY_NAME: Dict[str, Type[KrStrategyBase]] = {
    "s1_rsi_reversion": S1RsiReversion,
    "s2_bb_reversion": S2BBReversion,
    "s3_gap_fill": S3GapFill,
    "s4_orb": S4OpeningRangeBreakout,
    "s5_vwap_reversion": S5VwapReversion,
    "s6_donchian_breakout": S6DonchianBreakout,
    "s7_macd_cross": S7MacdCross,
    "s8_supertrend": S8Supertrend,
    "s9_volume_spike": S9VolumeSpike,
    "s10_obv_trend": S10ObvTrend,
    "s11_keltner_breakout": S11KeltnerBreakout,
    "s12_closing_range_breakout": S12ClosingRangeBreakout,
    "s13_last_hour_momentum": S13LastHourMomentum,
    "s14_daily_trend_5m_pullback": S14DailyTrend5mPullback,
    "s15_inside_bar_breakout": S15InsideBarBreakout,
    "s16_stochastic_reversion": S16StochasticReversion,
    "s17_williams_r_reversion": S17WilliamsRReversion,
    "s18_zscore_reversion": S18ZScoreReversion,
    "s19_ema_cross": S19EmaCross,
    "s20_ichimoku_momentum": S20IchimokuMomentum,
    "s21_adx_rsi": S21AdxRsi,
    "s22_mfi_reversion": S22MfiReversion,
    "s23_atr_channel_reversion": S23AtrChannelReversion,
    "s24_natr_filter_rsi": S24NatrFilterRsi,
    "s25_lunch_fade": S25LunchFade,
    "s26_open_drive": S26OpenDrive,
    "s27_15m_ema_trend": S27_15mEmaTrend,
    "s28_daily_atr_filter": S28DailyAtrFilter,
    "s29_bullish_engulfing": S29BullishEngulfing,
    "s30_bullish_pin_bar": S30BullishPinBar,
}

# Optimized wrappers (grid sweep best params)
from app.kr_strategy_pool.strategies_optimized import (
    S2OptBBReversion, S5OptVwapReversion, S13OptLastHourMomentum,
    S16OptStochasticReversion, S25OptLunchFade, S26OptOpenDrive,
)
STRATEGY_BY_NAME["s2_opt_bb_reversion"] = S2OptBBReversion
STRATEGY_BY_NAME["s5_opt_vwap_reversion"] = S5OptVwapReversion
STRATEGY_BY_NAME["s13_opt_last_hour_momentum"] = S13OptLastHourMomentum
STRATEGY_BY_NAME["s16_opt_stochastic_reversion"] = S16OptStochasticReversion
STRATEGY_BY_NAME["s25_opt_lunch_fade"] = S25OptLunchFade
STRATEGY_BY_NAME["s26_opt_open_drive"] = S26OptOpenDrive

# Adaptive sizing wrappers
from app.kr_strategy_pool.strategies_adaptive import (
    S2BBAdaptive, S5VwapAdaptive, S16StochasticAdaptive,
    S18ZScoreAdaptive, S25LunchFadeAdaptive,
)
STRATEGY_BY_NAME["s2_opt_bb_adaptive"] = S2BBAdaptive
STRATEGY_BY_NAME["s5_opt_vwap_adaptive"] = S5VwapAdaptive
STRATEGY_BY_NAME["s16_opt_stochastic_adaptive"] = S16StochasticAdaptive
STRATEGY_BY_NAME["s18_zscore_adaptive"] = S18ZScoreAdaptive
STRATEGY_BY_NAME["s25_opt_lunch_fade_adaptive"] = S25LunchFadeAdaptive

PARAMS = {
    "bb_period": 25,
    "bb_std": 2.0,
    "buy_size_pct": 0.7,
    "force_eod_exit": True,
}


@dataclass
class Segment:
    start_day: int
    end_day: int
    start_cutoff: str
    end_cutoff: str
    strategy_name: str

    def __str__(self):
        return (f"D{self.start_day}-D{self.end_day} "
                f"({self.start_cutoff}~{self.end_cutoff}) "
                f"{self.strategy_name}")


def extract_segments(jsonl_path: Path, lookback_warmup_days: int = 5) -> List[Segment]:
    """
    selector 결과 JSONL을 읽어서 selected 전략의 연속 구간(segment)을 추출.
    첫 N일은 selector lookback 부족 → 무조건 default 전략(s2)으로 적용.
    """
    rows = []
    with open(jsonl_path) as f:
        for ln in f:
            if ln.strip():
                rows.append(json.loads(ln))

    # 처음 N일은 default
    for i in range(min(lookback_warmup_days, len(rows))):
        rows[i]["selected"] = "s2_bb_reversion"

    segments: List[Segment] = []
    cur_strategy = None
    cur_start_day = None
    cur_start_cutoff = None
    prev_day = None
    prev_cutoff = None

    for r in rows:
        sel = r.get("selected") or "s2_bb_reversion"
        if sel != cur_strategy:
            # close previous
            if cur_strategy is not None:
                segments.append(Segment(
                    start_day=cur_start_day, end_day=prev_day,
                    start_cutoff=cur_start_cutoff, end_cutoff=prev_cutoff,
                    strategy_name=cur_strategy,
                ))
            cur_strategy = sel
            cur_start_day = r["day"]
            cur_start_cutoff = r["cutoff"]
        prev_day = r["day"]
        prev_cutoff = r["cutoff"]

    if cur_strategy is not None:
        segments.append(Segment(
            start_day=cur_start_day, end_day=prev_day,
            start_cutoff=cur_start_cutoff, end_cutoff=prev_cutoff,
            strategy_name=cur_strategy,
        ))
    return segments


async def run_segment(
    strategy_name: str,
    feed_5m: List[Dict[str, Any]],
    initial_capital: int,
    symbol: str,
) -> Dict[str, Any]:
    cls = STRATEGY_BY_NAME[strategy_name]
    eng = KrBacktestEngine(cls, exchange_name="Kiwoom")
    return await eng.run_single_backtest(
        config={"symbol": symbol, **PARAMS},
        feed=feed_5m, initial_capital=initial_capital, symbol=symbol,
    )


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--initial-capital", type=int, default=3_000_000)
    p.add_argument("--full-jsonl", default="runs/kr_paper/sim/full_v1.jsonl")
    p.add_argument("--start-data", default="2025-12-29",
                   help="data fetch start (안정화 phase 시작일과 일치)")
    args = p.parse_args()

    jsonl_path = Path(__file__).resolve().parent / args.full_jsonl
    if not jsonl_path.exists():
        print(f"ERROR: {jsonl_path} not found", file=sys.stderr)
        sys.exit(1)

    segments = extract_segments(jsonl_path)
    print(f"Extracted {len(segments)} segments from {jsonl_path.name}:")
    for s in segments:
        print(f"  {s}")

    # 데이터 한 번 fetch
    print(f"\nLoading 1m feed for {args.symbol} from {args.start_data}...")
    feed_1m_all = fetch_1m_feed(engine, args.symbol, start_date=args.start_data)
    feed_5m_all = resample_ohlcv(feed_1m_all, "5min")
    print(f"  total: {len(feed_5m_all)} 5m bars")

    # 각 segment 백테스트
    print(f"\n=== Selector-Guided Simulation ===")
    print(f"{'segment':<5} {'strategy':<22} {'days':<10} {'capital_in':>12} "
          f"{'return':>8} {'capital_out':>12} {'sharpe':>7} {'maxDD':>7} {'trades':>6}")
    print("-" * 110)

    capital = args.initial_capital
    seg_results = []
    for idx, seg in enumerate(segments, 1):
        # segment 데이터: start_cutoff 첫봉 ~ end_cutoff 마지막봉
        feed_seg = [c for c in feed_5m_all
                    if seg.start_cutoff <= c["timestamp"][:10] <= seg.end_cutoff]
        if not feed_seg:
            print(f"  {idx:<5} {seg.strategy_name:<22} (no data)")
            continue

        stats = await run_segment(seg.strategy_name, feed_seg, capital, args.symbol)
        ret = stats.get("return_pct", 0.0)
        sh = stats.get("sharpe_ratio") or 0
        mdd = stats.get("max_drawdown") or 0
        n = stats.get("trades_count", 0)
        capital_out = stats.get("final_equity", capital)

        days_str = f"D{seg.start_day}-{seg.end_day}"
        print(f"  {idx:<5} {seg.strategy_name:<22} {days_str:<10} "
              f"{capital:>12,.0f} {ret:>+7.2f}% {capital_out:>12,.0f} "
              f"{sh:>7.2f} {mdd:>+7.2f}% {n:>6}")

        seg_results.append({
            "segment": idx,
            "strategy": seg.strategy_name,
            "start_day": seg.start_day,
            "end_day": seg.end_day,
            "start_cutoff": seg.start_cutoff,
            "end_cutoff": seg.end_cutoff,
            "capital_in": capital,
            "return_pct": ret,
            "capital_out": capital_out,
            "sharpe": sh,
            "max_drawdown": mdd,
            "trades": n,
        })
        capital = capital_out

    print("-" * 110)
    final_return = (capital / args.initial_capital - 1) * 100
    print(f"\n{'FINAL':<33} {'':<10} {args.initial_capital:>12,.0f} "
          f"{final_return:>+7.2f}% {capital:>12,.0f}")

    # S2-only 비교
    print(f"\n=== Comparison: Selector-Guided vs S2-Only ===")
    s2_stats = await run_segment("s2_bb_reversion", feed_5m_all, args.initial_capital, args.symbol)
    s2_ret = s2_stats.get("return_pct", 0.0)
    s2_eq = s2_stats.get("final_equity", args.initial_capital)
    s2_sh = s2_stats.get("sharpe_ratio") or 0
    s2_mdd = s2_stats.get("max_drawdown") or 0
    s2_n = s2_stats.get("trades_count", 0)

    print(f"{'mode':<22} {'return':>8} {'capital':>12} {'sharpe':>7} {'maxDD':>7} {'trades':>6}")
    print("-" * 70)
    print(f"{'S2-only baseline':<22} {s2_ret:>+7.2f}% {s2_eq:>12,.0f} "
          f"{s2_sh:>7.2f} {s2_mdd:>+7.2f}% {s2_n:>6}")
    print(f"{'Selector-guided':<22} {final_return:>+7.2f}% {capital:>12,.0f} "
          f"{'n/a':>7} {'n/a':>7} {sum(s['trades'] for s in seg_results):>6}")
    print()
    delta = final_return - s2_ret
    print(f"  ΔReturn (selector - S2): {delta:+.2f}pp")
    print(f"  selector-guided final equity: ₩{capital:,.0f}")
    print(f"  S2-only final equity        : ₩{s2_eq:,.0f}")
    print(f"  difference                  : ₩{capital - s2_eq:+,.0f}")

    # 저장
    out_path = jsonl_path.parent / f"selector_guided_{args.full_jsonl.split('/')[-1].replace('.jsonl','')}.json"
    with open(out_path, "w") as f:
        json.dump({
            "segments": seg_results,
            "selector_guided_final": {
                "return_pct": final_return,
                "final_equity": capital,
            },
            "s2_only_baseline": {
                "return_pct": s2_ret,
                "final_equity": s2_eq,
                "sharpe": s2_sh,
                "max_drawdown": s2_mdd,
                "trades": s2_n,
            },
            "delta_return_pp": delta,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  saved: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
