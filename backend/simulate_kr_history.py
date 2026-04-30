"""
Back-Paper Simulation — 안정화 phase 시작일(2025-12-29)부터 오늘까지
매일 1일씩 데이터를 incremental하게 추가하며 시스템이 매일 어떻게 행동했을지 재현.

매 거래일 d에 대해:
  1. start_date ~ d까지의 데이터로 paper cycle 1회 (S2 BB Reversion 단독)
  2. 같은 데이터로 동적 selector 1회 (lookback 30 거래일 기반)
  3. cycle 결과 + selector 결과 + regime 라벨을 JSONL에 누적

출력: backend/runs/kr_paper/sim/<run_id>.jsonl
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
from app.core.kr_backtest_engine import KrBacktestEngine
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


FULL_POOL = [
    S1RsiReversion, S2BBReversion, S3GapFill, S4OpeningRangeBreakout,
    S5VwapReversion, S6DonchianBreakout, S7MacdCross,
    S8Supertrend, S9VolumeSpike, S10ObvTrend, S11KeltnerBreakout,
    S12ClosingRangeBreakout, S13LastHourMomentum,
    S14DailyTrend5mPullback, S15InsideBarBreakout,
    S16StochasticReversion, S17WilliamsRReversion, S18ZScoreReversion,
    S19EmaCross, S20IchimokuMomentum, S21AdxRsi, S22MfiReversion,
    S23AtrChannelReversion, S24NatrFilterRsi, S25LunchFade,
    S26OpenDrive, S27_15mEmaTrend, S28DailyAtrFilter,
    S29BullishEngulfing, S30BullishPinBar,
]

QUALITY_POOL = [
    S2BBReversion, S4OpeningRangeBreakout, S9VolumeSpike,
    S13LastHourMomentum, S16StochasticReversion, S18ZScoreReversion,
    S20IchimokuMomentum, S25LunchFade,
]

# Optimized — grid sweep best params 적용 wrapper들 + 그대로 두는 것들
from app.kr_strategy_pool.strategies_optimized import (
    S2OptBBReversion, S5OptVwapReversion, S13OptLastHourMomentum,
    S16OptStochasticReversion, S25OptLunchFade, S26OptOpenDrive,
)

OPTIMIZED_POOL = [
    S16OptStochasticReversion,    # +9.10% Sharpe 4.35 (k=9, 20/75)
    S5OptVwapReversion,           # +6.09% Sharpe 2.33 (lower=0.005) ⭐ NEW
    S2OptBBReversion,             # walk-forward sweep best (bb=25, std=2.0)
    S26OptOpenDrive,              # +4.03% Sharpe 1.73 ⭐ NEW
    S13OptLastHourMomentum,       # +2.90% Sharpe 1.11 ⭐ NEW
    S25OptLunchFade,              # +1.54% Sharpe 2.16 (12:00-13:00)
    S18ZScoreReversion,           # default — return +4.33%
    S20IchimokuMomentum,          # default — phase winner
]

# OOS-validated — IS + OOS 둘 다 흑자 + Sharpe>0.5인 전략만
# walk_forward_sweep.py에서 ROBUST 판정받은 6개 (S1 제외 시 5개)
ROBUST_POOL = [
    S16OptStochasticReversion,    # IS sh3.13 / OOS sh2.88, OOS ret +2.57%
    S5OptVwapReversion,           # IS sh1.71 / OOS sh1.67, OOS ret +4.36%
    S2OptBBReversion,             # IS sh1.16 / OOS sh2.13, OOS ret +4.42%
    S18ZScoreReversion,           # IS sh1.16 / OOS sh2.13, OOS ret +3.27%
    S25OptLunchFade,              # IS sh1.19 / OOS sh2.43, OOS ret +1.48%
]

# Robust 5-pool + Volatility-Adaptive Position Sizing (Step 1 enhancement)
from app.kr_strategy_pool.strategies_adaptive import (
    S2BBAdaptive, S5VwapAdaptive, S16StochasticAdaptive,
    S18ZScoreAdaptive, S25LunchFadeAdaptive,
)
ROBUST_ADAPTIVE_POOL = [
    S16StochasticAdaptive, S5VwapAdaptive, S2BBAdaptive,
    S18ZScoreAdaptive, S25LunchFadeAdaptive,
]

# Phase 5 — Robust + Foreign signals 결합 pool
# 목적: 박스권 phase → S31 (mean reversion), 추세/회복 phase → S33B (외국인 시그널)
# selector가 환경에 따라 자동 전환할 수 있는지 검증.
from app.kr_strategy_pool.strategies.s31_1m_variants import S31_1m_PeriodX3
from app.kr_strategy_pool.strategies.s33_foreign_signal import (
    S33A_ForeignCum, S33B_BothPositive, S33C_ForeignZScore, S33D_BigBuyersSum,
)

ROBUST_FOREIGN_POOL = [
    S31_1m_PeriodX3,         # 박스권 winner (OOS +19.15%)
    S33B_BothPositive,        # 추세/회복 winner (OOS +8.03%)
    S33D_BigBuyersSum,        # big buyers signal (OOS +6.30%)
    S16OptStochasticReversion,  # mean reversion alternative
    S5OptVwapReversion,       # mean reversion alternative
]

POOL = FULL_POOL  # 기본 (--pool 인자로 변경 가능)

PARAMS = {
    "bb_period": 25,
    "bb_std": 2.0,
    "buy_size_pct": 0.7,
    "force_eod_exit": True,
}


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="061090")
    p.add_argument("--start", default="2025-12-29",
                   help="paper start (안정화 phase 시작)")
    p.add_argument("--capital", type=int, default=3_000_000)
    p.add_argument("--run-id", default=None,
                   help="output run id (default: timestamp)")
    p.add_argument("--include-selector", action="store_true",
                   help="매일 7-pool selector 평가도 수행 (시간 4-5x 증가)")
    p.add_argument("--pool", default="full",
                   choices=["full", "quality", "optimized", "robust", "robust_adaptive", "robust_foreign"],
                   help="full=30, quality=8, optimized=8, robust=5, robust_adaptive=5, "
                        "robust_foreign=5 (S31+S33B+S33D+S16+S5 phase-cross alpha)")
    args = p.parse_args()
    if args.pool == "quality":
        pool = QUALITY_POOL
    elif args.pool == "optimized":
        pool = OPTIMIZED_POOL
    elif args.pool == "robust":
        pool = ROBUST_POOL
    elif args.pool == "robust_adaptive":
        pool = ROBUST_ADAPTIVE_POOL
    elif args.pool == "robust_foreign":
        pool = ROBUST_FOREIGN_POOL
    else:
        pool = FULL_POOL
    print(f"Pool: {args.pool} ({len(pool)} strategies)")

    run_id = args.run_id or f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir = Path(__file__).resolve().parent / "runs" / "kr_paper" / "sim"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.jsonl"

    print(f"Loading 1m feed for {args.symbol} from {args.start}...")
    feed_1m_all = fetch_1m_feed(engine, args.symbol, start_date=args.start)
    feed_5m_all = resample_ohlcv(feed_1m_all, "5min")
    print(f"  total: {len(feed_1m_all)} 1m / {len(feed_5m_all)} 5m bars")

    # 거래일 리스트 (5m 봉의 date set)
    trading_days = sorted({c["timestamp"][:10] for c in feed_5m_all})
    print(f"  trading days: {len(trading_days)} ({trading_days[0]} ~ {trading_days[-1]})")
    print(f"\nSimulating {'paper + selector' if args.include_selector else 'paper only'}...")
    print(f"output: {out_path}")
    print()

    # 헤더
    print(f"{'day':>3} {'cutoff':<10} {'bars':>5} "
          f"{'ret%':>7} {'sh':>5} {'mdd%':>7} {'wr%':>5} {'n':>4} {'eq':>10}", end="")
    if args.include_selector:
        print(f"  {'regime':<24} {'selected':<22}")
    else:
        print()

    started = datetime.now()
    results = []

    # selector 객체는 한 번만 생성
    if args.include_selector:
        selector = DynamicSelector(
            symbol=args.symbol, strategy_pool=pool, capital=args.capital,
            min_trades=5, max_dd_threshold=-25.0,
        )

    with open(out_path, "w") as f_out:
        for i, cutoff in enumerate(trading_days, 1):
            # 그날까지 봉만 (intraday 끝까지 포함)
            feed_subset_5m = [c for c in feed_5m_all if c["timestamp"][:10] <= cutoff]
            if not feed_subset_5m:
                continue

            # ── Paper cycle (S2 단독)
            eng = KrBacktestEngine(S2BBReversion, exchange_name="Kiwoom")
            stats = await eng.run_single_backtest(
                config={"symbol": args.symbol, **PARAMS},
                feed=feed_subset_5m,
                initial_capital=args.capital,
                symbol=args.symbol,
            )
            ret = stats.get("return_pct", 0.0)
            sh = stats.get("sharpe_ratio") or 0
            mdd = stats.get("max_drawdown") or 0
            wr = stats.get("win_rate") or 0
            n = stats.get("trades_count", 0)
            eq = stats.get("final_equity", args.capital)

            row = {
                "day": i, "cutoff": cutoff,
                "bars_5m": len(feed_subset_5m),
                "return_pct": ret, "sharpe": sh,
                "max_drawdown": mdd, "win_rate": wr,
                "trades": n, "final_equity": eq,
            }

            # ── Selector (옵션)
            if args.include_selector:
                feed_subset_1m = [c for c in feed_1m_all if c["timestamp"][:10] <= cutoff]
                feed_subset_daily = resample_ohlcv(feed_subset_1m, "1D")
                regime = detect_regime(feed_subset_daily, lookback=30) if len(feed_subset_daily) >= 5 else None
                sel_result = await selector.select(feed_subset_1m, regime=regime)
                row["regime"] = regime.as_dict() if regime else None
                row["selected"] = sel_result.selected.name if sel_result.selected else None
                row["selected_score"] = sel_result.selected.score if sel_result.selected else None
                row["selector_confidence"] = sel_result.confidence

                regime_str = (
                    f"{regime.vol_regime}/{regime.trend}/{regime.range_phase}/{regime.liquidity}"
                    if regime else "n/a"
                )
                sel_str = row["selected"] or "NONE"
                print(f"{i:>3} {cutoff:<10} {len(feed_subset_5m):>5} "
                      f"{ret:>+7.2f} {sh:>5.2f} {mdd:>+7.2f} {wr:>5.1f} {n:>4} {eq:>10,.0f}  "
                      f"{regime_str:<24} {sel_str:<22}")
            else:
                print(f"{i:>3} {cutoff:<10} {len(feed_subset_5m):>5} "
                      f"{ret:>+7.2f} {sh:>5.2f} {mdd:>+7.2f} {wr:>5.1f} {n:>4} {eq:>10,.0f}")

            f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
            results.append(row)

    elapsed = (datetime.now() - started).total_seconds()
    print(f"\nElapsed: {elapsed:.1f}s for {len(results)} days")
    print(f"Output : {out_path}")

    # 종합 통계
    if results:
        last = results[-1]
        print(f"\n=== Final state (Day {last['day']}, cutoff {last['cutoff']}) ===")
        print(f"  Return    : {last['return_pct']:+.2f}%")
        print(f"  Sharpe    : {last['sharpe']:.2f}")
        print(f"  maxDD     : {last['max_drawdown']:+.2f}%")
        print(f"  WinRate   : {last['win_rate']:.1f}%")
        print(f"  Trades    : {last['trades']}")
        print(f"  Final eq  : ₩{last['final_equity']:,.0f}")

        # 매주 (5거래일) sample
        print(f"\n=== Weekly snapshots (every 5 days) ===")
        print(f"{'day':>3} {'cutoff':<10} {'ret%':>7} {'sh':>5} {'mdd%':>7} {'eq':>11}")
        for r in results[::5]:
            print(f"{r['day']:>3} {r['cutoff']:<10} {r['return_pct']:>+7.2f} "
                  f"{r['sharpe']:>5.2f} {r['max_drawdown']:>+7.2f} {r['final_equity']:>11,.0f}")

        # 통계
        rets = [r["return_pct"] for r in results]
        max_ret = max(rets)
        min_ret = min(rets)
        end_ret = rets[-1]
        print(f"\n=== Trajectory stats ===")
        print(f"  peak return  : {max_ret:+.2f}%  (day {[r['day'] for r in results if r['return_pct']==max_ret][0]})")
        print(f"  trough return: {min_ret:+.2f}%  (day {[r['day'] for r in results if r['return_pct']==min_ret][0]})")
        print(f"  end return   : {end_ret:+.2f}%")
        print(f"  swing range  : {max_ret-min_ret:.2f}pp")

        # selector 안정성 (있을 경우)
        if args.include_selector:
            sel_seq = [r.get("selected") for r in results if r.get("selected")]
            from collections import Counter
            sel_counter = Counter(sel_seq)
            print(f"\n=== Selector stability (over {len(sel_seq)} days) ===")
            for name, count in sel_counter.most_common():
                pct = count / len(sel_seq) * 100
                print(f"  {name:<24} {count:>3} days ({pct:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
