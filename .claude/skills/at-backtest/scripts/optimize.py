#!/usr/bin/env python3
"""
Parameter Optimizer - 전략 파라미터 그리드 서치 최적화.
기존 API optimize 엔드포인트와 동일한 방식으로 파라미터 조합을 탐색.

Usage:
    # 기본 최적화 (dip_martingale, BTCUSDT, 1h)
    python optimize.py --strategy dip_martingale --symbol BTCUSDT --interval 1h --days 90

    # 파라미터 범위 지정
    python optimize.py -s dip_martingale --symbol BTCUSDT -i 1h -d 90 \
        --param "trailing_start_percent=1.0,2.0,3.0" \
        --param "trailing_stop_percent=0.5,1.0,1.5" \
        --param "max_buy_count=2,3,4"

    # 바이낸스 선물 최적화
    python optimize.py -s dip_martingale --symbol ETHUSDT -i 4h -d 180 \
        --exchange BinanceFutures --leverage 5 \
        --param "dip_threshold=1.0,2.0,3.0"

    # 상위 N개 결과 출력
    python optimize.py -s dip_martingale --symbol BTCUSDT -i 1h -d 90 --top 5
"""

import argparse
import json
import sys
import time
from itertools import product
from pathlib import Path
from typing import Dict, Any, List, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from backtest import run_backtest
from metrics import BacktestResult


# 전략별 기본 최적화 파라미터 범위
DEFAULT_PARAM_GRIDS = {
    "dip_martingale": {
        "dip_threshold": [1.0, 1.5, 2.0, 2.5, 3.0],
        "trailing_start_percent": [1.0, 2.0, 3.0, 5.0],
        "trailing_stop_percent": [0.5, 1.0, 1.5, 2.0],
        "max_buy_count": [2, 3, 4],
    },
    "ema_momentum": {
        "ema_short_period": [5, 10, 15],
        "ema_long_period": [20, 30, 50],
        "trailing_start_percent": [1.0, 2.0, 3.0],
        "trailing_stop_percent": [0.5, 1.0, 1.5],
    },
    "time_momentum": {
        "momentum_period": [5, 10, 20],
        "trailing_start_percent": [1.0, 2.0, 3.0],
        "trailing_stop_percent": [0.5, 1.0, 1.5],
        "max_buy_count": [2, 3, 4],
    },
    "chart_pattern": {
        "lookback_candles": [15, 20, 30, 50],
        "tolerance_percent": [1.0, 1.5, 2.0, 3.0],
        "min_pattern_depth": [2.0, 3.0, 5.0, 7.0],
        "cooldown_candles": [3, 5, 10],
    },
    "us_market_follow": {
        "us_change_threshold": [0.5, 1.0, 1.5, 2.0],
        "trailing_start_percent": [1.0, 2.0, 3.0, 5.0],
        "trailing_stop_percent": [0.5, 1.0, 1.5, 2.0],
        "max_loss_percent": [2.0, 3.0, 5.0],
        "cycle_max_hours": [2, 4, 6, 8],
    },
    "funding_rate_arb": {
        "entry_rate_threshold": [0.01, 0.03, 0.05, 0.1],
        "exit_rate_threshold": [0.001, 0.005, 0.01],
        "proxy_lookback": [4, 8, 12, 24],
    },
    "spot_futures_hedge": {
        "entry_rate_threshold": [0.03, 0.05, 0.1],
        "exit_rate_threshold": [0.005, 0.01, 0.02],
        "proxy_lookback": [4, 8, 12],
    },
}


def _score_result(result: BacktestResult) -> float:
    """
    백테스트 결과에 점수를 매긴다. API optimize와 동일한 가중치.
    높을수록 좋음.
    """
    if result.total_cycles < 3:
        return -999.0

    score = 0.0

    # 수익률 (가중치 30%)
    score += result.total_return * 0.3

    # 승률 (가중치 20%) - 50% 기준
    score += (result.win_rate - 50) * 0.2

    # 샤프 비율 (가중치 20%)
    score += result.sharpe_ratio * 0.2

    # MDD (가중치 15%) - 작을수록 좋음
    score += result.max_drawdown * 0.15  # max_drawdown은 이미 음수

    # 안정성 (가중치 10%)
    score += result.stability_score * 10 * 0.1

    # 활동률 (가중치 5%) - 적절한 활동
    score += min(result.activity_rate, 80) * 0.05

    return round(score, 4)


def parse_param_args(param_args: List[str]) -> Dict[str, List]:
    """
    --param "key=v1,v2,v3" 형식의 인자를 파싱.
    """
    params = {}
    for arg in param_args:
        key, values_str = arg.split("=", 1)
        key = key.strip()
        values = []
        for v in values_str.split(","):
            v = v.strip()
            try:
                if "." in v:
                    values.append(float(v))
                else:
                    values.append(int(v))
            except ValueError:
                values.append(v)
        params[key] = values
    return params


def generate_param_combinations(
    strategy_name: str,
    user_params: Dict[str, List] = None,
) -> List[Dict[str, Any]]:
    """
    파라미터 조합 목록을 생성한다.
    user_params가 있으면 사용, 없으면 전략별 기본 그리드 사용.
    """
    if user_params:
        grid = user_params
    else:
        grid = DEFAULT_PARAM_GRIDS.get(strategy_name, {})

    if not grid:
        print(f"Warning: No parameter grid for '{strategy_name}'. Using default config only.")
        return [{}]

    keys = list(grid.keys())
    values = list(grid.values())

    combinations = []
    for combo in product(*values):
        config = dict(zip(keys, combo))
        combinations.append(config)

    return combinations


def _run_single(args: Tuple) -> Tuple[Dict, BacktestResult, float]:
    """단일 백테스트 실행 (멀티프로세싱용)."""
    strategy_name, symbol, interval, days, capital, config = args
    result = run_backtest(
        strategy_name=strategy_name,
        symbol=symbol,
        interval=interval,
        days=days,
        initial_capital=capital,
        config=config,
    )
    score = _score_result(result)
    return config, result, score


def run_optimization(
    strategy_name: str,
    symbol: str,
    interval: str = "1h",
    days: int = 90,
    initial_capital: float = 10_000_000,
    base_config: Dict[str, Any] = None,
    param_grid: Dict[str, List] = None,
    top_n: int = 10,
    workers: int = 1,
) -> List[Dict]:
    """
    파라미터 최적화 실행.

    Args:
        strategy_name: 전략 이름
        symbol: 종목 코드
        interval: 캔들 인터벌
        days: 데이터 기간
        initial_capital: 초기 자본
        base_config: 기본 설정 (exchange_name, leverage 등)
        param_grid: 탐색할 파라미터 범위
        top_n: 상위 N개 결과 반환
        workers: 병렬 워커 수

    Returns:
        상위 N개 결과 리스트 [{config, result, score}]
    """
    base = base_config or {}
    combinations = generate_param_combinations(strategy_name, param_grid)

    print(f"Optimization: {strategy_name} / {symbol} ({interval}, {days}d)")
    print(f"Parameter combinations: {len(combinations)}")
    print(f"Workers: {workers}")
    print()

    results = []
    start_time = time.time()

    if workers > 1:
        # 멀티프로세싱
        tasks = []
        for combo in combinations:
            merged = {**base, **combo}
            tasks.append((strategy_name, symbol, interval, days, initial_capital, merged))

        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run_single, task): task for task in tasks}
            done = 0
            for future in as_completed(futures):
                done += 1
                try:
                    config, result, score = future.result()
                    results.append({"config": config, "result": result, "score": score})
                except Exception as e:
                    print(f"  Error: {e}")

                if done % 10 == 0 or done == len(tasks):
                    elapsed = time.time() - start_time
                    print(f"  Progress: {done}/{len(tasks)} ({elapsed:.1f}s)")
    else:
        # 싱글 프로세스
        for i, combo in enumerate(combinations):
            merged = {**base, **combo}
            try:
                result = run_backtest(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    interval=interval,
                    days=days,
                    initial_capital=initial_capital,
                    config=merged,
                )
                score = _score_result(result)
                results.append({"config": combo, "result": result, "score": score})
            except Exception as e:
                print(f"  Error with {combo}: {e}")

            if (i + 1) % 10 == 0 or i + 1 == len(combinations):
                elapsed = time.time() - start_time
                print(f"  Progress: {i+1}/{len(combinations)} ({elapsed:.1f}s)")

    # 점수 기준 정렬
    results.sort(key=lambda x: x["score"], reverse=True)

    total_time = time.time() - start_time
    print(f"\nCompleted in {total_time:.1f}s")

    return results[:top_n]


def format_optimization_results(results: List[Dict], strategy_name: str) -> str:
    """최적화 결과를 테이블로 포맷."""
    lines = [
        f"{'='*90}",
        f"  Optimization Results: {strategy_name}",
        f"{'='*90}",
        f"  {'Rank':>4s}  {'Score':>8s}  {'Return':>8s}  {'MDD':>8s}  {'WinRate':>7s}  {'Cycles':>6s}  {'Sharpe':>7s}  Config",
        f"  {'-'*86}",
    ]

    for i, r in enumerate(results):
        res = r["result"]
        cfg_str = ", ".join(f"{k}={v}" for k, v in r["config"].items())
        if len(cfg_str) > 35:
            cfg_str = cfg_str[:32] + "..."

        lines.append(
            f"  {i+1:>4d}  {r['score']:>8.2f}  {res.total_return:>7.2f}%  {res.max_drawdown:>7.2f}%  "
            f"{res.win_rate:>6.1f}%  {res.total_cycles:>6d}  {res.sharpe_ratio:>7.4f}  {cfg_str}"
        )

    lines.append(f"  {'-'*86}")

    if results:
        best = results[0]
        lines.append(f"\n  Best Config:")
        for k, v in best["config"].items():
            lines.append(f"    {k}: {v}")

    lines.append(f"{'='*90}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Strategy Parameter Optimizer"
    )
    parser.add_argument("--strategy", "-s", required=True, help="Strategy name")
    parser.add_argument("--symbol", required=True, help="Symbol (e.g., BTCUSDT)")
    parser.add_argument("--interval", "-i", default="1h", help="Interval (default: 1h)")
    parser.add_argument("--days", "-d", type=int, default=90, help="Days (default: 90)")
    parser.add_argument("--capital", "-c", type=float, default=10_000_000, help="Initial capital")
    parser.add_argument("--exchange", default=None, help="Exchange name (default: auto)")
    parser.add_argument("--leverage", type=int, default=1, help="Leverage (default: 1)")
    parser.add_argument("--param", action="append", default=[], help="Parameter range: key=v1,v2,v3")
    parser.add_argument("--top", type=int, default=10, help="Top N results (default: 10)")
    parser.add_argument("--workers", "-w", type=int, default=1, help="Parallel workers (default: 1)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--base-qty", type=float, default=None, help="Base quantity")
    parser.add_argument("--qty-mode", default=None, help="Qty mode: fixed or percent")

    args = parser.parse_args()

    # Base config
    exchange = args.exchange
    if exchange is None:
        exchange = "Kiwoom" if args.symbol.isdigit() else "BinanceFutures"

    base_config = {
        "exchange_name": exchange,
        "leverage": args.leverage,
    }
    if args.base_qty is not None:
        base_config["base_quantity"] = args.base_qty
    if args.qty_mode is not None:
        base_config["qty_mode"] = args.qty_mode

    # Parse param grid
    param_grid = parse_param_args(args.param) if args.param else None

    results = run_optimization(
        strategy_name=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
        initial_capital=args.capital,
        base_config=base_config,
        param_grid=param_grid,
        top_n=args.top,
        workers=args.workers,
    )

    if args.json:
        output = []
        for r in results:
            output.append({
                "rank": len(output) + 1,
                "score": r["score"],
                "config": r["config"],
                "total_return": r["result"].total_return,
                "max_drawdown": r["result"].max_drawdown,
                "win_rate": r["result"].win_rate,
                "total_cycles": r["result"].total_cycles,
                "sharpe_ratio": r["result"].sharpe_ratio,
                "profit_factor": r["result"].profit_factor,
                "stability_score": r["result"].stability_score,
            })
        print(json.dumps(output, indent=2))
    else:
        print(format_optimization_results(results, args.strategy))


if __name__ == "__main__":
    main()
