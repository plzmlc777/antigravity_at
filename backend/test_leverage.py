"""Quick test: Verify leverage affects backtest results on BinanceFutures"""
import asyncio
import httpx

async def test():
    base = "http://localhost:8001/api/v1/strategies/dip_martingale/backtest"
    common = {
        "symbol": "AVAXUSDT",
        "interval": "1h",
        "days": 90,
        "initial_capital": 100,
        "exchange_name": "BinanceFutures",
    }

    for lev in [1, 5, 10]:
        cfg = {
            "leverage": lev,
            "dip_percent": 3,
            "trailing_start_percent": 2,
            "trailing_callback_percent": 1,
            "max_buy_count": 5,
            "qty_mode": "fixed",
            "base_quantity": 5,
            "lot_size_multiplier": 2,
        }
        payload = {**common, "config": cfg}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(base, json=payload)
            d = resp.json()
            tr = d.get("total_return")
            tc = d.get("total_cycles")
            mdd = d.get("max_drawdown")
            wr = d.get("win_rate")
            pf = d.get("profit_factor")
            trades = d.get("trades", [])
            buys = [t for t in trades if t.get("type") == "buy"]
            sells = [t for t in trades if t.get("type") == "sell"]
            if buys:
                qty_sum = sum(t["quantity"] for t in buys)
                avg_qty = qty_sum / len(buys)
            else:
                qty_sum = avg_qty = 0
            chart = d.get("chart_data", [])
            eq0 = chart[0]["equity"] if chart else 0
            eq_end = chart[-1]["equity"] if chart else 0
            logs = d.get("logs", [])
            cap_logs = [l for l in logs if "Capital for qty" in l or "CASH GUARD" in l or "Cycle Plan" in l]
            print(f"Leverage={lev:>2}: return={tr}, cycles={tc}, buy_count={len(buys)}, avg_qty={avg_qty:.4f}, eq={eq0}→{eq_end}")
            for cl in cap_logs[:3]:
                print(f"  LOG: {cl}")

asyncio.run(test())
