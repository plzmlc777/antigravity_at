"""
PMT (Pattern Memory Trader) walk-forward 검증 스크립트.

워크플로:
  1. 1년치 1m feed 로드
  2. 처음 N일을 KNN reference (history)로 사용
  3. 그 다음 5일 단위 window를 walk-forward test
  4. 매 window마다 KNN을 expand (history += 직전 window 데이터)
  5. window별 수익률 + 누적 통계 출력

목적: PMT가 진짜 작동하는지 (월 평균 +양수 수익) 검증.
실패하면 폐기, 성공하면 풀 통합.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from app.db.session import engine
from app.meta_strategy_pool.pmt_engine import PMTEngine, PMTConfig


def fetch_feed(market: str, symbol: str, start: str, end: str) -> List[Dict]:
    if market == "kr":
        from app.kr_strategy_pool.data_utils import fetch_1m_feed
    else:
        from app.crypto_strategy_pool.data_utils import fetch_1m_feed
    return fetch_1m_feed(engine, symbol, start, end)


def calendar_days(feed: List[Dict]) -> List[str]:
    df = pd.DataFrame(feed)
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["d"] = df["ts"].dt.date.astype(str)
    return sorted(df["d"].unique().tolist())


def slice_by_days(feed: List[Dict], days: List[str]) -> List[Dict]:
    keep = set(days)
    return [c for c in feed if c["timestamp"][:10] in keep]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--market", required=True, choices=["kr", "crypto"])
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", required=True, help="full data start (e.g. 2025-05-01)")
    p.add_argument("--end", required=True, help="full data end (e.g. 2026-04-30)")
    p.add_argument("--history-days", type=int, default=120,
                   help="initial KNN reference days")
    p.add_argument("--window-days", type=int, default=5,
                   help="walk-forward test window size")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--fee-rate", type=float, default=None,
                   help="default: KR 0.0021 (round-trip), Crypto 0.0004 (taker)")
    # PMT hyperparams
    p.add_argument("--window-bars", type=int, default=60)
    p.add_argument("--horizon-bars", type=int, default=30)
    p.add_argument("--k-neighbors", type=int, default=20)
    p.add_argument("--hit-threshold", type=float, default=0.005)
    p.add_argument("--min-hit-rate", type=float, default=0.65)
    p.add_argument("--min-mean-return", type=float, default=0.003)
    p.add_argument("--tp-pct", type=float, default=0.005)
    p.add_argument("--sl-pct", type=float, default=0.003)
    p.add_argument("--max-hold-bars", type=int, default=30)
    p.add_argument("--decision-step", type=int, default=5)
    args = p.parse_args()

    fee = args.fee_rate
    if fee is None:
        fee = 0.0021 if args.market == "kr" else 0.0004

    cfg = PMTConfig(
        window_bars=args.window_bars,
        horizon_bars=args.horizon_bars,
        k_neighbors=args.k_neighbors,
        hit_threshold=args.hit_threshold,
        min_hit_rate=args.min_hit_rate,
        min_mean_return=args.min_mean_return,
        tp_pct=args.tp_pct,
        sl_pct=args.sl_pct,
        max_hold_bars=args.max_hold_bars,
        decision_step=args.decision_step,
    )

    print("=" * 80)
    print(f"PMT Walk-Forward: {args.market.upper()} {args.symbol}  fee={fee}")
    print(f"  data    : {args.start}..{args.end}")
    print(f"  history : {args.history_days}d initial → expanding")
    print(f"  window  : {args.window_days}d each test")
    print(f"  config  : W={cfg.window_bars} H={cfg.horizon_bars} K={cfg.k_neighbors} "
          f"hit_thr={cfg.hit_threshold} min_hr={cfg.min_hit_rate} "
          f"min_mr={cfg.min_mean_return}")
    print(f"  exit    : tp={cfg.tp_pct} sl={cfg.sl_pct} max_hold={cfg.max_hold_bars}")
    print("=" * 80)

    print(f"\nLoading feed...")
    t0 = time.time()
    feed = fetch_feed(args.market, args.symbol, args.start, args.end)
    print(f"  {len(feed)} bars in {time.time()-t0:.1f}s")

    days = calendar_days(feed)
    print(f"  {len(days)} unique days")

    if len(days) < args.history_days + args.window_days:
        raise SystemExit(f"Not enough days: {len(days)}")

    # Build window list
    windows = []
    i = args.history_days
    while i + args.window_days <= len(days):
        windows.append({
            "id": len(windows),
            "history_days": days[:i],
            "test_days": days[i : i + args.window_days],
        })
        i += args.window_days
    print(f"  {len(windows)} test windows")

    # Walk-forward
    out_dir = Path(__file__).resolve().parent / "runs" / "pmt" / args.symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"pmt_{args.symbol}_{int(time.time())}.jsonl"

    print(f"\n--- Walk-forward results ---")
    print(f"{'win':<5} {'test_range':<25} {'ret%':<8} {'trades':<7} {'winR':<7} {'sharpe':<8} {'maxDD%':<8}")
    print("-" * 80)

    win_returns = []
    win_trades = []
    win_winrate = []
    cum_equity = args.capital

    started = time.time()

    with open(log_path, "w") as logf:
        for w in windows:
            history_feed = slice_by_days(feed, w["history_days"])
            test_feed = slice_by_days(feed, w["test_days"])

            try:
                pmt = PMTEngine(cfg).fit(history_feed)
            except ValueError as e:
                print(f"win {w['id']:<3} SKIP: {e}")
                continue

            result = pmt.backtest(test_feed, initial_capital=args.capital, fee_rate=fee)
            ret = result["return_pct"]
            tr = result["trades_count"]
            wr = result["win_rate"]
            sh = result["sharpe"]
            mdd = result["max_drawdown"]

            win_returns.append(ret)
            win_trades.append(tr)
            win_winrate.append(wr)
            cum_equity *= (1 + ret / 100)

            test_range = f"{w['test_days'][0]}..{w['test_days'][-1]}"
            print(f"{w['id']:<5} {test_range:<25} {ret:>+6.2f}%  {tr:<7} {wr:>5.1f}%  {sh:>+5.2f}    {mdd:>+5.2f}%")

            log_row = {
                "window_id": w["id"],
                "history_days_count": len(w["history_days"]),
                "test_range": test_range,
                "ref_signatures": int(len(pmt._reference_signatures)),
                "return_pct": ret,
                "trades_count": tr,
                "win_rate": wr,
                "sharpe": sh,
                "max_drawdown": mdd,
            }
            logf.write(json.dumps(log_row) + "\n")
            logf.flush()

    elapsed = time.time() - started

    # Summary
    print("\n" + "=" * 80)
    print(f"=== SUMMARY ({len(win_returns)} windows, {elapsed:.0f}s) ===")
    print("=" * 80)
    if win_returns:
        total_days = sum(args.window_days for _ in win_returns)
        sum_ret = sum(win_returns)
        avg_per_window = sum_ret / len(win_returns)
        monthly_days = 22 if args.market == "kr" else 30
        monthly_ret = sum_ret / total_days * monthly_days

        print(f"  test days       : {total_days}")
        print(f"  total trades    : {sum(win_trades)}")
        print(f"  trades/window   : {np.mean(win_trades):.1f}")
        print(f"  windows w/ trade: {sum(1 for t in win_trades if t > 0)}/{len(win_trades)}")
        print(f"  avg win rate    : {np.mean(win_winrate):.1f}%")
        print(f"  ")
        print(f"  sum return      : {sum_ret:+.2f}%")
        print(f"  avg per window  : {avg_per_window:+.3f}% (5d)")
        print(f"  >>> monthly est : {monthly_ret:+.2f}% <<<")
        print(f"  cumulative      : ${cum_equity:,.2f} (start ${args.capital:,.0f}, "
              f"compound +{(cum_equity/args.capital - 1)*100:+.2f}%)")
        win_pos = sum(1 for r in win_returns if r > 0)
        print(f"  windows w/ +    : {win_pos}/{len(win_returns)} ({win_pos/len(win_returns)*100:.0f}%)")

    print(f"\n  log saved: {log_path}")


if __name__ == "__main__":
    main()
