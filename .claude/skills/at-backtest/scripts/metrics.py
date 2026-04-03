#!/usr/bin/env python3
"""
Performance Metrics Calculator (Standalone)
기존 BacktestEngine의 _analyze_trades, _calc_mdd, calc_stability_stats와 동일한 공식.

Usage:
    from metrics import calculate_metrics
    result = calculate_metrics(trades, equity_curve, initial_capital)
"""

import statistics
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import numpy as np
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


@dataclass
class BacktestResult:
    """백테스트 결과 구조체. API 응답과 동일한 필드."""
    strategy_id: str = ""
    total_return: float = 0.0
    win_rate: float = 0.0
    recent_10_win_rate: float = 0.0
    max_drawdown: float = 0.0
    total_cycles: int = 0
    avg_pnl: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    activity_rate: float = 0.0
    total_days: int = 0
    avg_holding_time: int = 0       # minutes
    max_holding_time: str = "0m"
    min_holding_time: str = "0m"
    stability_score: float = 0.0
    acceleration_score: float = 0.0
    chart_data: List[Dict] = None
    bucket_stats: List[Dict] = None
    decile_stats: List[Dict] = None


def calc_total_return(equity_curve: List[Dict]) -> float:
    """총 수익률 (%). 기존 BacktestEngine과 동일."""
    if len(equity_curve) < 2:
        return 0.0
    initial = equity_curve[0]["equity"]
    final = equity_curve[-1]["equity"]
    if initial == 0:
        return 0.0
    return (final - initial) / initial * 100


def calc_max_drawdown(equity_curve: List[Dict]) -> float:
    """
    최대 낙폭 (%). 기존 _calc_mdd와 동일.
    Returns: 음수 값 (e.g., -12.50)
    """
    if not equity_curve:
        return 0.0

    peak = equity_curve[0]["equity"]
    max_dd = 0.0

    for point in equity_curve:
        val = point["equity"]
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            if dd > max_dd:
                max_dd = dd

    return -max_dd * 100


def calc_activity_rate(trades, data_feed_timestamps: List) -> tuple:
    """
    활동률 (%). 기존과 동일.
    Returns: (activity_rate, total_days)
    """
    data_dates = set()
    for ts in data_feed_timestamps:
        try:
            if hasattr(ts, 'date'):
                data_dates.add(ts.date())
            else:
                from datetime import datetime
                data_dates.add(datetime.fromisoformat(str(ts)).date())
        except Exception:
            pass

    traded_dates = set()
    for t in trades:
        try:
            entry_time = t.entry_time
            if hasattr(entry_time, 'date'):
                traded_dates.add(entry_time.date())
            exit_time = t.exit_time
            if hasattr(exit_time, 'date'):
                traded_dates.add(exit_time.date())
        except Exception:
            pass

    total_days = len(data_dates)
    traded_count = len(traded_dates)
    rate = (traded_count / total_days * 100) if total_days > 0 else 0
    return rate, total_days


def calc_trade_stats(trades) -> Dict[str, Any]:
    """
    매매 통계. 기존 _analyze_trades와 동일한 공식.

    Returns: {
        total_cycles, win_rate, avg_pnl, max_profit, max_loss,
        profit_factor, sharpe_ratio, avg_holding_time,
        max_holding_time, min_holding_time, recent_10_win_rate
    }
    """
    if not trades:
        return {
            "total_cycles": 0, "win_rate": 0, "avg_pnl": 0,
            "max_profit": 0, "max_loss": 0, "profit_factor": 0,
            "sharpe_ratio": 0, "avg_holding_time": 0,
            "max_holding_time": "0m", "min_holding_time": "0m",
            "recent_10_win_rate": 0,
        }

    total = len(trades)
    pnl_pcts = [t.pnl_pct for t in trades]
    pnl_abs = [t.pnl for t in trades]

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]

    # Win rate
    win_rate = len(wins) / total * 100

    # Recent 10 win rate
    recent = trades[-10:] if len(trades) >= 10 else trades
    recent_wins = sum(1 for t in recent if t.pnl > 0)
    recent_10_wr = recent_wins / len(recent) * 100

    # Avg PnL (%)
    avg_pnl = sum(pnl_pcts) / total * 100

    # Max profit / loss (%)
    max_profit = max(pnl_pcts) * 100
    max_loss = min(pnl_pcts) * 100

    # Profit factor
    gross_profit = sum(t.pnl for t in wins) if wins else 0
    gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99

    # Sharpe ratio: (mean / stdev) * sqrt(N)
    sharpe = 0.0
    if len(pnl_pcts) > 1:
        stdev = statistics.stdev(pnl_pcts)
        if stdev > 0:
            sharpe = (statistics.mean(pnl_pcts) / stdev) * (len(pnl_pcts) ** 0.5)

    # Holding times
    hold_secs = [t.holding_seconds for t in trades]
    avg_hold_min = int(sum(hold_secs) / total / 60) if total > 0 else 0
    max_hold_min = int(max(hold_secs) / 60) if hold_secs else 0
    min_hold_min = int(min(hold_secs) / 60) if hold_secs else 0

    return {
        "total_cycles": total,
        "win_rate": win_rate,
        "recent_10_win_rate": recent_10_wr,
        "avg_pnl": avg_pnl,
        "max_profit": max_profit,
        "max_loss": max_loss,
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe, 4),
        "avg_holding_time": avg_hold_min,
        "max_holding_time": f"{max_hold_min}m" if max_hold_min < 1440 else f"{max_hold_min // 60}h",
        "min_holding_time": f"{min_hold_min}m" if min_hold_min < 1440 else f"{min_hold_min // 60}h",
    }


def calc_stability_stats(trades, n_buckets: int = 12) -> Dict[str, Any]:
    """
    안정성/가속도 점수. 기존 calc_stability_stats와 동일.

    Returns: {stability_score, acceleration_score, bucket_stats}
    """
    if not trades or len(trades) < 3:
        return {"stability_score": 0.0, "acceleration_score": 0.0, "bucket_stats": []}

    total = len(trades)
    actual_buckets = min(n_buckets, total)
    if actual_buckets < 2:
        return {"stability_score": 0.0, "acceleration_score": 0.0, "bucket_stats": []}

    bucket_size = total // actual_buckets
    remainder = total % actual_buckets

    bucket_stats = []
    idx = 0
    for i in range(actual_buckets):
        size = bucket_size + (1 if i < remainder else 0)
        chunk = trades[idx:idx + size]
        idx += size

        pnls = [t.pnl_pct * 100 for t in chunk]
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / len(chunk) if chunk else 0
        win_count = sum(1 for p in pnls if p > 0)
        wr = win_count / len(chunk) * 100 if chunk else 0

        bucket_stats.append({
            "block": i + 1,
            "total_pnl": round(total_pnl, 4),
            "avg_pnl": round(avg_pnl, 4),
            "win_rate": round(wr, 1),
            "count": len(chunk),
        })

    # Stability = R² of cumulative PnL
    pnl_values = [s["total_pnl"] for s in bucket_stats]

    if not HAS_SCIPY:
        # Fallback without scipy
        return {
            "stability_score": 0.0,
            "acceleration_score": 1.0,
            "bucket_stats": bucket_stats,
        }

    cumulative = np.cumsum(pnl_values)
    x = np.arange(len(cumulative))

    if len(cumulative) < 2:
        return {
            "stability_score": 0.0,
            "acceleration_score": 1.0,
            "bucket_stats": bucket_stats,
        }

    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, cumulative)
    stability_score = r_value ** 2

    # Acceleration = recent slope / overall slope
    acceleration_score = 1.0
    n_recent = max(3, int(len(cumulative) * 0.25))

    if len(cumulative) >= 6:
        recent_cum = cumulative[-n_recent:]
        x_recent = np.arange(len(recent_cum))
        slope_recent, _, _, _, _ = scipy_stats.linregress(x_recent, recent_cum)

        if abs(slope) > 0.0001:
            acceleration_score = slope_recent / slope
        else:
            acceleration_score = 0.0

    return {
        "stability_score": round(stability_score, 4),
        "acceleration_score": round(acceleration_score, 4),
        "bucket_stats": bucket_stats,
    }


@dataclass
class FifoTrade:
    """FIFO 매칭된 개별 매매. Trade와 동일한 인터페이스."""
    entry_time: Any
    exit_time: Any
    exit_price: float = 0
    total_quantity: float = 0
    average_price: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    holding_seconds: float = 0


def fifo_match_trades(raw_trades: List[Dict]) -> List:
    """
    API BacktestEngine._analyze_trades()와 동일한 FIFO 매칭.
    raw_trades: [{"type": "buy"/"sell", "price": float, "quantity": float, "time": str}, ...]
    Returns: FifoTrade 리스트 (pnl, pnl_pct, holding_seconds 포함)
    """
    from datetime import datetime as dt

    buy_queue = []
    completed = []

    for t in raw_trades:
        if t['type'] == 'buy':
            buy_queue.append({
                'price': t['price'],
                'quantity': t['quantity'],
                'time': t['time']
            })
        elif t['type'] == 'sell':
            # API 동일: 백테스트 종료 시 강제 청산은 통계에서 제외
            if t.get('force_liquidated'):
                buy_queue.clear()
                continue
            qty_to_sell = t['quantity']
            sell_price = t['price']
            sell_time = dt.fromisoformat(t['time'])

            while qty_to_sell > 0 and buy_queue:
                buy_order = buy_queue[0]
                matched_qty = min(qty_to_sell, buy_order['quantity'])

                profit = matched_qty * (sell_price - buy_order['price'])
                profit_percent = (sell_price - buy_order['price']) / buy_order['price']

                buy_time = dt.fromisoformat(buy_order['time'])
                holding_seconds = (sell_time - buy_time).total_seconds()

                completed.append(FifoTrade(
                    entry_time=buy_time,
                    exit_time=sell_time,
                    exit_price=sell_price,
                    total_quantity=matched_qty,
                    average_price=buy_order['price'],
                    pnl=profit,
                    pnl_pct=profit_percent,
                    holding_seconds=holding_seconds,
                ))

                qty_to_sell -= matched_qty
                buy_order['quantity'] -= matched_qty
                if buy_order['quantity'] <= 0:
                    buy_queue.pop(0)

    return completed


def aggregate_fifo_to_cycles(fifo_trades: List, raw_trades: List[Dict] = None) -> List:
    """
    FIFO 매칭된 개별 매매를 사이클 단위로 집계 (API _compute_stats_from_completed와 동일).
    같은 exit_time을 가진 FIFO 트레이드들은 같은 사이클 (L1+L2→exit).
    API 동일: cycle_start_equity 기반 pnl_pct (equity-based return).
    """
    if not fifo_trades:
        return []

    # Build sell metadata lookup (exit_time → cycle_start_equity)
    sell_equity = {}
    if raw_trades:
        from datetime import datetime as dt
        for t in raw_trades:
            if t['type'] == 'sell' and t.get('cycle_start_equity'):
                sell_time = dt.fromisoformat(t['time'])
                sell_equity[sell_time] = t['cycle_start_equity']

    from collections import OrderedDict
    cycles = OrderedDict()

    for ft in fifo_trades:
        key = ft.exit_time
        if key not in cycles:
            cycles[key] = {
                "pnl": 0.0,
                "total_cost": 0.0,
                "holding_seconds": 0.0,
                "entry_time": ft.entry_time,
                "exit_time": ft.exit_time,
                "exit_price": ft.exit_price,
                "cycle_start_equity": sell_equity.get(ft.exit_time),
            }
        c = cycles[key]
        c["pnl"] += ft.pnl
        c["total_cost"] += ft.average_price * ft.total_quantity
        if ft.holding_seconds > c["holding_seconds"]:
            c["holding_seconds"] = ft.holding_seconds
        if ft.entry_time < c["entry_time"]:
            c["entry_time"] = ft.entry_time

    result = []
    for c in cycles.values():
        # API 동일: cycle_start_equity가 있으면 equity-based, 없으면 investment-based
        cse = c.get("cycle_start_equity")
        if cse and cse > 0:
            pnl_pct = c["pnl"] / cse
        else:
            pnl_pct = c["pnl"] / c["total_cost"] if c["total_cost"] > 0 else 0
        result.append(FifoTrade(
            entry_time=c["entry_time"],
            exit_time=c["exit_time"],
            exit_price=c["exit_price"],
            total_quantity=0,
            average_price=0,
            pnl=c["pnl"],
            pnl_pct=pnl_pct,
            holding_seconds=c["holding_seconds"],
        ))
    return result


def calculate_metrics(
    trades,
    equity_curve: List[Dict],
    data_timestamps: List,
    initial_capital: float,
    strategy_id: str = "",
    raw_trades: List[Dict] = None,
) -> BacktestResult:
    """
    전체 성과지표를 계산하여 BacktestResult로 반환.
    raw_trades 제공 시 API 동일 FIFO 매칭 + 사이클 집계로 통계 산출.
    """
    total_return = calc_total_return(equity_curve)
    max_drawdown = calc_max_drawdown(equity_curve)

    # FIFO 매칭 모드: API _analyze_trades + _compute_stats_from_completed와 동일
    if raw_trades:
        fifo_trades = fifo_match_trades(raw_trades)
        # 사이클 집계: 같은 exit_time의 FIFO 매치들을 하나의 사이클로 (API cycle_id 동일)
        cycle_trades = aggregate_fifo_to_cycles(fifo_trades, raw_trades)
        activity_rate, total_days = calc_activity_rate(cycle_trades, data_timestamps)
        trade_stats = calc_trade_stats(cycle_trades)
        # API 동일: stability/acceleration은 raw FIFO 트레이드 기준 (사이클 집계 전)
        stability = calc_stability_stats(fifo_trades)
    else:
        fifo_trades = trades
        activity_rate, total_days = calc_activity_rate(trades, data_timestamps)
        trade_stats = calc_trade_stats(trades)
        stability = calc_stability_stats(trades)

    return BacktestResult(
        strategy_id=strategy_id,
        total_return=round(total_return, 4),
        win_rate=round(trade_stats["win_rate"], 4),
        recent_10_win_rate=round(trade_stats["recent_10_win_rate"], 4),
        max_drawdown=round(max_drawdown, 4),
        total_cycles=trade_stats["total_cycles"],
        avg_pnl=round(trade_stats["avg_pnl"], 4),
        max_profit=round(trade_stats["max_profit"], 4),
        max_loss=round(trade_stats["max_loss"], 4),
        profit_factor=trade_stats["profit_factor"],
        sharpe_ratio=trade_stats["sharpe_ratio"],
        activity_rate=round(activity_rate, 4),
        total_days=total_days,
        avg_holding_time=trade_stats["avg_holding_time"],
        max_holding_time=trade_stats["max_holding_time"],
        min_holding_time=trade_stats["min_holding_time"],
        stability_score=stability["stability_score"],
        acceleration_score=stability["acceleration_score"],
        chart_data=equity_curve,
        bucket_stats=stability["bucket_stats"],
    )


def format_results(result: BacktestResult) -> str:
    """결과를 텍스트 테이블로 포맷."""
    lines = [
        f"{'='*50}",
        f"  Strategy: {result.strategy_id}",
        f"{'='*50}",
        f"  Total Return:     {result.total_return:>10.2f}%",
        f"  Max Drawdown:     {result.max_drawdown:>10.2f}%",
        f"  Sharpe Ratio:     {result.sharpe_ratio:>10.4f}",
        f"  Win Rate:         {result.win_rate:>10.1f}%",
        f"  Profit Factor:    {result.profit_factor:>10.2f}",
        f"  Total Cycles:     {result.total_cycles:>10d}",
        f"  Avg PnL:          {result.avg_pnl:>10.2f}%",
        f"  Max Profit:       {result.max_profit:>10.2f}%",
        f"  Max Loss:         {result.max_loss:>10.2f}%",
        f"  Activity Rate:    {result.activity_rate:>10.1f}%",
        f"  Total Days:       {result.total_days:>10d}",
        f"  Avg Hold Time:    {result.avg_holding_time:>10d}m",
        f"  Stability:        {result.stability_score:>10.4f}",
        f"  Acceleration:     {result.acceleration_score:>10.4f}",
        f"{'='*50}",
    ]
    return "\n".join(lines)
