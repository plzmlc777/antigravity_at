
from backend.app.core.live_aggregator import CandleRealAggregator
from datetime import datetime, timedelta

def verify_aggregator():
    print("--- Verifying Candle Real Aggregator ---")
    
    ag = CandleRealAggregator("TEST", interval_minutes=1)
    
    # Tick 1: 10:00:05, Price 100, Vol 10
    t1 = datetime(2023, 1, 1, 10, 0, 5)
    closed, snap = ag.add_tick(100.0, 10, t1)
    
    assert closed is None
    assert snap['open'] == 100
    assert snap['high'] == 100
    assert snap['volume'] == 10
    print("Tick 1: Correctly started bucket.")
    
    # Tick 2: 10:00:30, Price 105, Vol 5
    t2 = datetime(2023, 1, 1, 10, 0, 30)
    closed, snap = ag.add_tick(105.0, 5, t2)
    
    assert closed is None
    assert snap['high'] == 105
    assert snap['low'] == 100
    assert snap['volume'] == 15
    print("Tick 2: Correctly updated stats.")
    
    # Tick 3: 10:01:05 (NEXT MINUTE), Price 102, Vol 5
    t3 = datetime(2023, 1, 1, 10, 1, 5)
    closed, snap = ag.add_tick(102.0, 5, t3)
    
    # Expectation: 
    # 1. 'closed' should be the 10:00 candle [100, 105, 100, 105, vol 15]
    # 2. 'snap' should be the start of 10:01 candle [102, 102, 102, 102, vol 5]
    
    assert closed is not None, "Should have closed previous candle"
    assert closed['open'] == 100
    assert closed['high'] == 105
    assert closed['close'] == 105
    assert closed['volume'] == 15
    print("Tick 3: Correctly closed previous candle.")
    
    assert snap['open'] == 102
    assert snap['timestamp'] == "2023-01-01T10:01:00"
    print("Tick 3: Correctly started new candle.")
    
    print("AGGREGATOR VERIFICATION PASSED")

if __name__ == "__main__":
    verify_aggregator()
