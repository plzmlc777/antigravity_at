from datetime import datetime, timedelta

def _aggregate_candles(base_candles, target_interval):
    print(f"\n--- Simulating Aggregation to {target_interval} ---")
    if not base_candles: return []
    
    # Ensure data is sorted by timestamp to prevent aggregation logic errors
    base_candles.sort(key=lambda x: x['timestamp'])
    
    minutes = 0
    hours = 0
    
    # Parse Target Interval
    if target_interval.endswith("m"):
        minutes = int(target_interval[:-1])
    elif target_interval.endswith("h"):
        hours = int(target_interval[:-1])
    
    agg = []
    current_bucket = None
    bucket_end_time = None
    
    for c in base_candles:
        dt = datetime.strptime(c['timestamp'], "%Y-%m-%d %H:%M:%S")
        
        # Determine Bucket Start (Align to grid)
        bucket_start = None
        if minutes > 0:
             # Logic from market_data.py
             m_block = (dt.minute // minutes) * minutes
             bucket_start = dt.replace(minute=m_block, second=0)
        elif hours > 0:
             h_block = (dt.hour // hours) * hours
             bucket_start = dt.replace(hour=h_block, minute=0, second=0)
        
        print(f"Candle: {dt} -> Bucket Start: {bucket_start}")

        bucket_duration = timedelta(minutes=minutes) if minutes > 0 else timedelta(hours=hours)
        bucket_end = bucket_start + bucket_duration
        
        # Check Alignment
        if current_bucket is None or dt >= bucket_end_time:
            if current_bucket: 
                agg.append(current_bucket)
            
            current_bucket = {
                "timestamp": bucket_start.strftime("%Y-%m-%d %H:%M:%S"),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"]
            }
            bucket_end_time = bucket_end
        else:
            current_bucket["high"] = max(current_bucket["high"], c["high"])
            current_bucket["low"] = min(current_bucket["low"], c["low"])
            current_bucket["close"] = c["close"]
            current_bucket["volume"] += c["volume"]
            
    if current_bucket: agg.append(current_bucket)
    return agg

# Test Cases
def run_simulation():
    # 1. Standard 09:00 case
    test_data_1 = [
        {"timestamp": "2025-01-08 09:00:00", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 10},
        {"timestamp": "2025-01-08 09:01:00", "open": 105, "high": 115, "low": 100, "close": 110, "volume": 20},
    ]
    
    # 2. Borderline 08:59 case (Pre-market)
    test_data_2 = [
        {"timestamp": "2025-01-08 08:59:00", "open": 90, "high": 95, "low": 85, "close": 90, "volume": 5},
        {"timestamp": "2025-01-08 09:00:00", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 10},
    ]

    result_1 = _aggregate_candles(test_data_1, "15m")
    print("Result 1 (09:00 Start):")
    for r in result_1: print(r)

    result_2 = _aggregate_candles(test_data_2, "15m")
    print("\nResult 2 (08:59 Start):")
    for r in result_2: print(r)

if __name__ == "__main__":
    run_simulation()
