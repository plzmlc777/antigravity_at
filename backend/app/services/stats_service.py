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
        equity_curve: List[Any], 
        start_time: Optional[datetime] = None
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
        
        # 4. Total Return & MDD (Equity Based)
        if equity_curve and len(equity_curve) > 1:
            initial_equity = equity_curve[0].equity if hasattr(equity_curve[0], 'equity') else equity_curve[0]['equity']
            final_equity = equity_curve[-1].equity if hasattr(equity_curve[-1], 'equity') else equity_curve[-1]['equity']
            
            # If initial is 0 (bug?), avoid div zero
            if initial_equity == 0: initial_equity = final_equity 
            
            total_return = ((final_equity - initial_equity) / initial_equity) * 100 if initial_equity > 0 else 0
            
            # MDD Calculation
            peak = initial_equity
            max_dd = 0
            equity_values = []
            for point in equity_curve:
                val = point.equity if hasattr(point, 'equity') else point['equity']
                equity_values.append(val)
                if val > peak: peak = val
                dd = (peak - val) / peak
                if dd > max_dd: max_dd = dd
        else:
            total_return = 0
            max_dd = 0
            equity_values = []

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
            if len(equity_values) > 10:
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
