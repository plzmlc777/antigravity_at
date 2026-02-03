
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.db.session import SessionLocal
from backend.app.models.strategy_result import StrategyAnalysisResult

def analyze_trades():
    db = SessionLocal()
    try:
        # Fetch the most recent backtest result
        # We assume result_type='backtest' and sort by updated_at descending
        latest_result = db.query(StrategyAnalysisResult)\
            .filter(StrategyAnalysisResult.result_type == 'backtest')\
            .order_by(StrategyAnalysisResult.updated_at.desc())\
            .first()

        if not latest_result:
            print("No backtest results found in database.")
            return

        data = latest_result.data
        if not data:
            print("Latest result has no data.")
            return
            
        # Handle potentially nested structure
        # Integrated returns dict with 'trades' key
        trades = data.get('trades', [])
        
        # If empty, check if it's inside 'result' key (common pattern)
        if not trades and 'result' in data:
            trades = data['result'].get('trades', [])

        if not trades:
            print("No trades found in the latest backtest result.")
            return

        print(f"Analyzing {len(trades)} trades from latest backtest ({latest_result.updated_at})...")

        # Group by Date (KST)
        daily_counts = defaultdict(int)
        
        kst = timezone(timedelta(hours=9))

        for t in trades:
            # t['time'] might be ISO string or timestamp
            raw_time = t.get('time')
            if not raw_time:
                continue
                
            if isinstance(raw_time, (int, float)):
                # Timestamp (ms or s)
                # Usually BacktestEngine returns ISO strings, but let's handle both
                # If > 3000000000, it's ms.
                if raw_time > 3000000000:
                    dt = datetime.fromtimestamp(raw_time / 1000, kst)
                else:
                    dt = datetime.fromtimestamp(raw_time, kst)
            else:
                # ISO String
                try:
                    dt = datetime.fromisoformat(str(raw_time).replace('Z', '+00:00'))
                    # Convert to KST
                    dt = dt.astimezone(kst)
                except:
                    # Fallback or error
                    print(f"Skipping invalid time: {raw_time}")
                    continue
            
            date_str = dt.strftime('%Y-%m-%d')
            daily_counts[date_str] += 1

        # Count days with >= 2 trades
        target_days = {date: count for date, count in daily_counts.items() if count >= 2}
        
        # Analyze Rank Distribution
        rank_counts = defaultdict(int)
        for t in trades:
            rank = t.get('strategy_rank', 'Unknown')
            rank_counts[rank] += 1
            
        print("\n[Analysis Result]")
        print(f"Total Trading Days: {len(daily_counts)}")
        print(f"Days with 2+ Trades: {len(target_days)}")
        
        print("\n[Rank Distribution]")
        for rank, count in sorted(rank_counts.items(), key=lambda x: str(x[0])):
             print(f"  Rank {rank}: {count} trades")
        
        if target_days:
            print("\nDetails (Top 10 Days by Frequency):")
            sorted_days = sorted(target_days.items(), key=lambda x: x[0], reverse=True)
            for d, c in sorted_days[:10]:
                print(f"  {d}: {c} trades")

    except Exception as e:
        print(f"Error analyzing trades: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    analyze_trades()
