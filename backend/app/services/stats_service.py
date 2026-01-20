import math
import statistics
from datetime import datetime
from typing import List, Dict, Any, Optional
import numpy as np
from scipy import stats as scipy_stats

class StatsService:
    @staticmethod
    def calculate_detailed_stats(
        trades: List[Any], 
        equity_curve: List[Any], # Kept for signature compatibility, but we'll use virtual one
        start_time: Optional[datetime] = None,
        initial_capital: float = 10000000
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive performance statistics matching the Backtest Report.
        
        Args:
            trades: List of LiveRealizedTrade objects or dicts
            equity_curve: List of LiveEquitySnapshot objects or dicts
            start_time: Session start time
        """
        
        # 1. Basic Counts
        total_trades = len(trades)
        if total_trades == 0:
            return _get_empty_stats()
            
        # 2. Key Trade Metrics
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        
        win_rate = (len(wins) / total_trades) * 100
        
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 99.99
        
        total_pnl = sum(t.pnl for t in trades)
        
        # PnL Percentages (avg, max, min)
        pnl_percents = [t.pnl_percent * 100 for t in trades]
        avg_pnl = statistics.mean(pnl_percents) if pnl_percents else 0
        max_profit = max(pnl_percents) if pnl_percents else 0
        max_loss = min(pnl_percents) if pnl_percents else 0
        
        # 3. Holding Time
        holding_times = [t.holding_seconds for t in trades if t.holding_seconds is not None]
        avg_holding_sec = statistics.mean(holding_times) if holding_times else 0
        avg_holding_min = int(avg_holding_sec / 60)
        
        # 4. Generate Virtual Equity Curve (Trade-based)
        # We start at initial_capital and add PnL of each trade sequentially.
        # This isolations this strategy's performance from other account activities.
        current_v_equity = initial_capital
        equity_values = [current_v_equity]
        
        # Sort trades by exit time to build chronological curve
        sorted_trades = sorted(trades, key=lambda x: x.exit_time if hasattr(x, 'exit_time') else x['exit_time'])
        
        max_dd = 0
        peak = initial_capital
        
        for t in sorted_trades:
            pnl = t.pnl if hasattr(t, 'pnl') else t['pnl']
            current_v_equity += pnl
            equity_values.append(current_v_equity)
            
            if current_v_equity > peak:
                peak = current_v_equity
            
            dd = (peak - current_v_equity) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        final_equity = equity_values[-1]
        total_return = ((final_equity - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0

        # 5. Sharpe Ratio (Trade-based Proxy)
        # Using trade returns distribution
        if len(pnl_percents) > 1:
            stdev = statistics.stdev(pnl_percents)
            # Annualized factor approximation: sqrt(Trades per Year)
            # For live session, we can just give a raw score or normalize by trade frequency?
            # Backtest engine uses: (mean / stdev) * sqrt(count) 
            # This is "Trade Sharpe", distinguishable from Daily Sharpe.
            sharpe = (avg_pnl / stdev * (total_trades ** 0.5)) if stdev > 0 else 0
        else:
            sharpe = 0
            
        # 6. Stability & Acceleration (Regression on Equity)
        stability_score = 0.0
        acceleration_score = 0.0
        
        try:
            if len(equity_values) >= 2: # Lowered threshold to provide feedback earlier
                # Stability = R-squared of equity curve
                x = np.arange(len(equity_values))
                slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(x, equity_values)
                stability_score = r_value ** 2
                
                # Acceleration = Recent Slope / Overall Slope
                n_recent = max(5, int(len(equity_values) * 0.25))
                recent_vals = equity_values[-n_recent:]
                x_recent = np.arange(len(recent_vals))
                slope_recent, _, _, _, _ = scipy_stats.linregress(x_recent, recent_vals)
                
                if abs(slope) > 1e-6:
                    acceleration_score = slope_recent / slope
                else:
                    acceleration_score = 0
        except Exception as e:
            print(f"Stats Error: {e}")

        # 7. Activity Rate
        # Distinct days traded / Total days open
        # We need start_time to now
        activity_rate = 0
        if start_time:
            now = datetime.now()
            total_days = (now - start_time).days + 1
            # Count unique trade dates
            unique_dates = set()
            for t in trades:
                d = t.entry_time.date() if isinstance(t.entry_time, datetime) else datetime.fromisoformat(str(t.entry_time)).date()
                unique_dates.add(d)
            
            activity_rate = (len(unique_dates) / total_days) * 100 if total_days > 0 else 0


        return {
            "total_return": f"{total_return:.2f}%",
            "profit_factor": f"{profit_factor:.2f}",
            "win_rate": f"{win_rate:.1f}%",
            "sharpe_ratio": f"{sharpe:.2f}",
            "total_trades": total_trades,
            "stability": f"{stability_score:.2f}",
            "profit_accel": f"{acceleration_score:.2f}x",
            "activity_rate": f"{activity_rate:.1f}%",
            "avg_pnl": f"{avg_pnl:.2f}%",
            "avg_holding": f"{avg_holding_min}m",
            "max_profit": f"{max_profit:.2f}%",
            "max_loss": f"{max_loss:.2f}%",
            "max_drawdown": f"-{max_dd * 100:.2f}%"
        }

def _get_empty_stats():
    return {
        "total_return": "0.00%",
        "profit_factor": "0.00",
        "win_rate": "0.0%",
        "sharpe_ratio": "0.00",
        "total_trades": 0,
        "stability": "0.00",
        "profit_accel": "0.00x",
        "activity_rate": "0.0%",
        "avg_pnl": "0.00%",
        "avg_holding": "0m",
        "max_profit": "0.00%",
        "max_loss": "0.00%",
        "max_drawdown": "0.00%"
    }
