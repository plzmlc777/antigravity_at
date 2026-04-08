#!/usr/bin/env python3
"""
Parameter Optimizer - Grid Search + Walk-Forward + Weighted Scoring.

기능:
  1. Grid Search: 백엔드 heavy-optimize와 동일한 파라미터 조합 탐색
  2. Walk-Forward: Train/Test 분할로 과적합 검증 (백엔드에 없는 신규 기능)
  3. Weighted Scoring: 백엔드 recalculate-scores와 동일한 가중 점수

Usage:
    # 기본 최적화
    python optimize.py --strategy dip_martingale --symbol BTCUSDT --interval 1h --days 90

    # 파라미터 범위 지정
    python optimize.py -s dip_martingale --symbol BTCUSDT -i 1h -d 90 \
        --param "trailing_start_percent=1.0,2.0,3.0" \
        --param "trailing_stop_percent=0.5,1.0,1.5"

    # 바이낸스 선물 최적화
    python optimize.py -s dip_martingale --symbol ETHUSDT -i 4h -d 180 \
        --exchange BinanceFutures --leverage 5

    # Walk-Forward 검증
    python optimize.py -s rsi_martingale --symbol SOLUSDT -i 1m -d 60 \
        --exchange BinanceFutures --leverage 5 --walk-forward --folds 3

    # 가중 점수 적용
    python optimize.py -s dip_martingale --symbol BTCUSDT -i 1h -d 90 \
        --scoring weighted --weights '{"return_weight":1.0,"mdd_weight":2.0}'
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


# 전략별 기본 최적화 파라미터 범위 (PARAMETER_SCHEMA defaultOptRange 기반)
DEFAULT_PARAM_GRIDS = {
    "rsi_martingale": {
        "rsi_period": [7, 14, 21],
        "trigger_level": [20, 25, 30, 35],
        "reset_level": [40, 50, 60, 70],
        "short_trigger_level": [65, 70, 75, 80],
        "short_reset_level": [30, 40, 50, 60],
    },
    "dip_martingale": {
        "dip_percent": [0.5, 1.0, 1.5, 2.0],
        "level_gap_percent": [1.0, 2.0, 3.0],
        "trailing_start_percent": [1.0, 2.0, 3.0, 5.0],
        "trailing_stop_percent": [0.5, 1.0, 1.5, 2.0],
        "max_buy_count": [2, 3, 4],
    },
    "ema_momentum": {
        "fast_period": [5, 9, 12],
        "slow_period": [21, 26, 50],
        "signal_period": [5, 9],
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

# 백엔드 호환 가중 점수 기본값 (recalculate-scores 동일)
DEFAULT_WEIGHTS = {
    "return_weight": 1.0,
    "sharpe_weight": 1.2,
    "stability_weight": 1.0,
    "mdd_weight": 1.5,
    "avg_pnl_weight": 1.0,
    "win_rate_weight": 0.0,
    "profit_factor_weight": 0.0,
    "trades_weight": 0.0,
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


def _parse_num(v) -> float:
    """Parse numeric from various formats."""
    if v is None or v == "-" or v == "":
        return 0.0
    s = str(v).replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _weighted_score_result(result: BacktestResult, weights: Dict = None) -> float:
    """Backend _calculate_weighted_score() compatible.
    Score = (Return^w * Sharpe^w * Stability^w * AvgPnL^w * ...) / MDD^w
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    ret = result.total_return
    sharpe = result.sharpe_ratio
    stability = result.stability_score
    mdd = abs(result.max_drawdown)
    wr = result.win_rate
    pf = result.profit_factor
    avg_pnl = getattr(result, "avg_pnl", 0.0)
    trades = result.total_cycles

    if ret <= 0:
        return 0.0
    if mdd == 0:
        mdd = 0.01
    if sharpe <= 0:
        sharpe = 0.01
    if stability <= 0:
        stability = 0.01

    numerator = 1.0
    if w["return_weight"] > 0:
        numerator *= pow(max(min(ret / 100.0, 10.0), 0.01), w["return_weight"])
    if w["sharpe_weight"] > 0:
        numerator *= pow(max(min(sharpe, 5.0), 0.01), w["sharpe_weight"])
    if w["stability_weight"] > 0:
        numerator *= pow(max(stability, 0.01), w["stability_weight"])
    if w["avg_pnl_weight"] > 0:
        numerator *= pow(max(1.0 + avg_pnl, 0.01), w["avg_pnl_weight"])
    if w["win_rate_weight"] > 0:
        numerator *= pow(max(wr / 100.0, 0.01), w["win_rate_weight"])
    if w["profit_factor_weight"] > 0:
        numerator *= pow(max(min(pf, 10.0), 0.01), w["profit_factor_weight"])
    if w["trades_weight"] > 0:
        numerator *= pow(max(min(trades / 50.0, 5.0), 0.01), w["trades_weight"])

    denominator = 1.0
    if w["mdd_weight"] > 0:
        denominator *= pow(max(mdd / 100.0, 0.01), w["mdd_weight"])

    return numerator / denominator if denominator > 0 else 0.0


def run_walk_forward(
    strategy_name: str,
    symbol: str,
    interval: str = "1m",
    total_days: int = 60,
    folds: int = 3,
    train_ratio: float = 0.7,
    initial_capital: float = 500,
    base_config: Dict = None,
    param_grid: Dict[str, List] = None,
    weights: Dict = None,
) -> Dict:
    """Walk-Forward Validation.

    총 기간을 N개 fold로 나누고, 각 fold에서:
    1. Train (70%): grid search로 최적 파라미터 찾기
    2. Test (30%): 최적 파라미터로 out-of-sample 테스트

    과적합 판별: train_return vs test_return 비교.
    """
    from datetime import datetime, timedelta

    fold_days = total_days // folds
    train_days = max(int(fold_days * train_ratio), 1)
    test_days = fold_days - train_days

    if test_days < 1:
        return {"error": "Test period too short. Increase total_days or decrease folds."}

    grid = param_grid or DEFAULT_PARAM_GRIDS.get(strategy_name, {})
    if not grid:
        return {"error": f"No parameter grid for '{strategy_name}'"}

    base = base_config or {}
    combinations = generate_param_combinations(strategy_name, grid)
    scoring = _weighted_score_result if weights else _score_result

    print(f"[Walk-Forward] {folds} folds x ({train_days}d train + {test_days}d test)")
    print(f"[Walk-Forward] {len(combinations)} param combinations per fold")

    end_date = datetime.utcnow()
    fold_results = []

    for fold_idx in range(folds):
        fold_end = end_date - timedelta(days=fold_idx * fold_days)
        fold_start = fold_end - timedelta(days=fold_days)
        train_end = fold_start + timedelta(days=train_days)

        train_from = fold_start.strftime("%Y-%m-%d")
        train_to = train_end.strftime("%Y-%m-%d")
        test_from = train_to
        test_to = fold_end.strftime("%Y-%m-%d")

        print(f"\n[Fold {fold_idx+1}/{folds}] Train: {train_from}~{train_to}, Test: {test_from}~{test_to}")

        best_score = -float("inf")
        best_config = None
        best_train_result = None

        for combo in combinations:
            merged = {**base, **combo}
            try:
                result = run_backtest(
                    strategy_name=strategy_name,
                    symbol=symbol,
                    interval=interval,
                    days=train_days,
                    initial_capital=initial_capital,
                    config=merged,
                    from_date=train_from,
                    to_date=train_to,
                )
                score = scoring(result, weights) if weights else scoring(result)
                if score > best_score:
                    best_score = score
                    best_config = combo
                    best_train_result = result
            except Exception:
                continue

        if not best_config:
            fold_results.append({
                "fold": fold_idx + 1,
                "train_period": f"{train_from}~{train_to}",
                "test_period": f"{test_from}~{test_to}",
                "error": "No valid train results",
            })
            continue

        # Test with best config
        test_merged = {**base, **best_config}
        try:
            test_result = run_backtest(
                strategy_name=strategy_name,
                symbol=symbol,
                interval=interval,
                days=test_days,
                initial_capital=initial_capital,
                config=test_merged,
                from_date=test_from,
                to_date=test_to,
            )
            test_return = test_result.total_return
            test_return_compound = test_result.monthly_return_compound
            test_cycles = test_result.total_cycles
            test_error = None
        except Exception as e:
            test_return = 0.0
            test_return_compound = 0.0
            test_cycles = 0
            test_error = str(e)

        fold_results.append({
            "fold": fold_idx + 1,
            "train_period": f"{train_from}~{train_to}",
            "test_period": f"{test_from}~{test_to}",
            "best_config": best_config,
            "train_score": round(best_score, 4),
            "train_return": best_train_result.total_return,
            "train_return_monthly_compound": best_train_result.monthly_return_compound,
            "train_cycles": best_train_result.total_cycles,
            "test_return": test_return,
            "test_return_monthly_compound": test_return_compound,
            "test_cycles": test_cycles,
            "test_error": test_error,
        })

    # Summary
    valid_folds = [f for f in fold_results if "error" not in f]
    if not valid_folds:
        return {"folds": fold_results, "summary": {"error": "No valid folds"}}

    avg_train = sum(f["train_return"] for f in valid_folds) / len(valid_folds)
    avg_test = sum(f["test_return"] for f in valid_folds) / len(valid_folds)
    avg_train_compound = sum(f.get("train_return_monthly_compound", 0.0) for f in valid_folds) / len(valid_folds)
    avg_test_compound = sum(f.get("test_return_monthly_compound", 0.0) for f in valid_folds) / len(valid_folds)

    # Overfit ratio computed on compound (KPI metric), not arithmetic period total
    if avg_train_compound > 0:
        overfit_ratio = 1.0 - (avg_test_compound / avg_train_compound)
    elif avg_train > 0:
        overfit_ratio = 1.0 - (avg_test / avg_train)
    else:
        overfit_ratio = 0.0

    if overfit_ratio < 0.2:
        verdict = "GOOD - low overfit risk"
    elif overfit_ratio < 0.5:
        verdict = "WARNING - moderate overfit"
    else:
        verdict = "OVERFIT - severe, simplify parameters"

    return {
        "mode": "walk_forward",
        "strategy": strategy_name,
        "symbol": symbol,
        "total_days": total_days,
        "folds": fold_results,
        "summary": {
            "valid_folds": len(valid_folds),
            "avg_train_return": round(avg_train, 2),
            "avg_test_return": round(avg_test, 2),
            "avg_train_monthly_compound": round(avg_train_compound, 4),
            "avg_test_monthly_compound": round(avg_test_compound, 4),
            "kpi_gap_pp_test": round(12.0 - avg_test_compound, 4),
            "overfit_ratio": round(overfit_ratio, 3),
            "verdict": verdict,
        },
    }


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
    parser.add_argument("--walk-forward", action="store_true", help="Walk-Forward validation mode")
    parser.add_argument("--folds", type=int, default=3, help="Walk-Forward fold count (default: 3)")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="Train ratio (default: 0.7)")
    parser.add_argument("--scoring", choices=["simple", "weighted"], default="simple",
                        help="Scoring mode: simple (default) or weighted (backend-compatible)")
    parser.add_argument("--weights", default=None, help="Score weights JSON (for weighted scoring)")

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
    weights = json.loads(args.weights) if args.weights else None

    # Walk-Forward mode
    if args.walk_forward:
        wf_result = run_walk_forward(
            strategy_name=args.strategy,
            symbol=args.symbol,
            interval=args.interval,
            total_days=args.days,
            folds=args.folds,
            train_ratio=args.train_ratio,
            initial_capital=args.capital,
            base_config=base_config,
            param_grid=param_grid,
            weights=weights,
        )

        if args.json:
            print(json.dumps(wf_result, indent=2, ensure_ascii=False, default=str))
        else:
            s = wf_result.get("summary", {})
            sep = "=" * 70
            print(f"\n{sep}")
            print(f"  WALK-FORWARD Results - {args.strategy} / {args.symbol}")
            print(sep)
            print(f"  Folds: {s.get('valid_folds', 0)}")
            print(f"  Avg Train Return: {s.get('avg_train_return', 0):.2f}%")
            print(f"  Avg Test Return:  {s.get('avg_test_return', 0):.2f}%")
            print(f"  Overfit Ratio:    {s.get('overfit_ratio', 0):.3f}")
            print(f"  Verdict:          {s.get('verdict', '-')}")
            print()
            for f in wf_result.get("folds", []):
                st = "ERROR" if "error" in f else "OK"
                print(f"  Fold {f.get('fold')}: Train={f.get('train_return', '-')}% -> Test={f.get('test_return', '-')}% [{st}]")
                if f.get("best_config"):
                    print(f"    Config: {f['best_config']}")
            print(f"\n{sep}")
        return

    # Standard Grid Search
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

    # Apply weighted scoring if requested
    if args.scoring == "weighted":
        for r in results:
            r["score"] = round(_weighted_score_result(r["result"], weights), 6)
        results.sort(key=lambda x: x["score"], reverse=True)

    if args.json:
        output = []
        for r in results:
            output.append({
                "rank": len(output) + 1,
                "score": r["score"],
                "config": r["config"],
                "total_return": r["result"].total_return,
                "monthly_return_compound": r["result"].monthly_return_compound,
                "monthly_return_arithmetic": r["result"].monthly_return_arithmetic,
                "kpi_gap_pp": r["result"].kpi_gap_pp,
                "volatility_drag_warning": r["result"].volatility_drag_warning,
                "total_days": r["result"].total_days,
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
