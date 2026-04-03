#!/usr/bin/env python3
"""
Analyze candles from a live session and generate signal recommendations.

Usage:
    python analyze_candles.py --session-id <ID> [--api-url http://localhost:8001] [--limit 100]

Output:
    JSON with indicator values and signal recommendation.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

# Add parent for indicators import
sys.path.insert(0, str(Path(__file__).parent))
from indicators import rsi, ema, macd, bollinger_bands, atr


def fetch_candles(api_url: str, session_id: str, limit: int = 100) -> dict:
    """Fetch candle data from session API."""
    url = f"{api_url}/api/v1/live/session/{session_id}/candles?limit={limit}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def analyze(data: dict) -> dict:
    """Analyze candles and produce indicator values + signal recommendation."""
    candles = data.get("candles", [])
    if len(candles) < 30:
        return {"error": "Not enough candles for analysis", "candle_count": len(candles)}

    closes = [c["close"] for c in candles]
    current_price = data.get("current_price", closes[-1])
    symbol = data.get("symbol", "?")
    holdings = data.get("holdings", {})

    # Calculate indicators
    rsi_values = rsi(closes, 14)
    ema_short = ema(closes, 9)
    ema_long = ema(closes, 21)
    macd_data = macd(closes, 12, 26, 9)
    bb = bollinger_bands(closes, 20, 2.0)
    atr_values = atr(candles, 14)

    current_rsi = rsi_values[-1] if rsi_values[-1] is not None else 50
    current_ema9 = ema_short[-1]
    current_ema21 = ema_long[-1]
    current_macd = macd_data["macd"][-1]
    current_signal = macd_data["signal"][-1]
    current_histogram = macd_data["histogram"][-1]
    current_bb_upper = bb["upper"][-1]
    current_bb_lower = bb["lower"][-1]
    current_atr = atr_values[-1] if atr_values[-1] is not None else 0

    # Signal generation logic
    signals = []
    score = 0  # -100 (strong sell) to +100 (strong buy)

    # RSI
    if current_rsi < 30:
        signals.append(f"RSI oversold ({current_rsi:.1f})")
        score += 30
    elif current_rsi > 70:
        signals.append(f"RSI overbought ({current_rsi:.1f})")
        score -= 30
    elif current_rsi < 40:
        signals.append(f"RSI low ({current_rsi:.1f})")
        score += 10

    # EMA crossover
    if current_ema9 is not None and current_ema21 is not None:
        if current_ema9 > current_ema21:
            signals.append("EMA9 > EMA21 (bullish)")
            score += 20
        else:
            signals.append("EMA9 < EMA21 (bearish)")
            score -= 20

    # MACD
    if current_histogram is not None:
        if current_histogram > 0 and current_macd > current_signal:
            signals.append("MACD bullish")
            score += 15
        elif current_histogram < 0 and current_macd < current_signal:
            signals.append("MACD bearish")
            score -= 15

    # Bollinger Bands
    if current_bb_lower is not None:
        if current_price < current_bb_lower:
            signals.append("Price below BB lower (oversold)")
            score += 20
        elif current_price > current_bb_upper:
            signals.append("Price above BB upper (overbought)")
            score -= 20

    # Determine recommendation
    has_position = symbol in holdings and holdings[symbol] > 0

    if score >= 40:
        recommendation = "STRONG_BUY" if not has_position else "HOLD"
    elif score >= 20:
        recommendation = "BUY" if not has_position else "HOLD"
    elif score <= -40:
        recommendation = "STRONG_SELL" if has_position else "AVOID"
    elif score <= -20:
        recommendation = "SELL" if has_position else "AVOID"
    else:
        recommendation = "NEUTRAL"

    return {
        "symbol": symbol,
        "current_price": current_price,
        "candle_count": len(candles),
        "holdings": holdings,
        "indicators": {
            "rsi_14": round(current_rsi, 2),
            "ema_9": round(current_ema9, 6) if current_ema9 else None,
            "ema_21": round(current_ema21, 6) if current_ema21 else None,
            "macd": round(current_macd, 6) if current_macd else None,
            "macd_signal": round(current_signal, 6) if current_signal else None,
            "macd_histogram": round(current_histogram, 6) if current_histogram else None,
            "bb_upper": round(current_bb_upper, 6) if current_bb_upper else None,
            "bb_lower": round(current_bb_lower, 6) if current_bb_lower else None,
            "atr_14": round(current_atr, 6) if current_atr else None,
        },
        "signals": signals,
        "score": score,
        "recommendation": recommendation,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze live session candles")
    parser.add_argument("--session-id", required=True, help="Live session ID")
    parser.add_argument("--api-url", default="http://localhost:8001", help="Backend API URL")
    parser.add_argument("--limit", type=int, default=100, help="Number of candles to fetch")
    args = parser.parse_args()

    try:
        data = fetch_candles(args.api_url, args.session_id, args.limit)
        result = analyze(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}: {e.reason}"}, indent=2))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": str(e)}), indent=2)
        sys.exit(1)


if __name__ == "__main__":
    main()
