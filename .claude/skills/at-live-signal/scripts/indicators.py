"""
Technical indicators for candle analysis.
Pure Python — no external dependencies required.
"""

from typing import List, Dict, Any, Optional


def ema(values: List[float], period: int) -> List[float]:
    """Exponential Moving Average."""
    if len(values) < period:
        return [None] * len(values)

    k = 2 / (period + 1)
    result = [None] * (period - 1)
    # SMA for first value
    sma = sum(values[:period]) / period
    result.append(sma)

    prev = sma
    for i in range(period, len(values)):
        val = values[i] * k + prev * (1 - k)
        result.append(val)
        prev = val

    return result


def sma(values: List[float], period: int) -> List[float]:
    """Simple Moving Average."""
    result = [None] * (period - 1)
    for i in range(period - 1, len(values)):
        result.append(sum(values[i - period + 1:i + 1]) / period)
    return result


def rsi(closes: List[float], period: int = 14) -> List[float]:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return [None] * len(closes)

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    result = [None] * period

    if avg_loss == 0:
        result.append(100.0)
    else:
        rs = avg_gain / avg_loss
        result.append(100 - (100 / (1 + rs)))

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            result.append(100.0)
        else:
            rs = avg_gain / avg_loss
            result.append(100 - (100 / (1 + rs)))

    return result


def macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[float]]:
    """MACD (Moving Average Convergence Divergence)."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    macd_line = []
    for f, s in zip(ema_fast, ema_slow):
        if f is not None and s is not None:
            macd_line.append(f - s)
        else:
            macd_line.append(None)

    # Signal line = EMA of MACD line
    valid_macd = [v for v in macd_line if v is not None]
    signal_line_values = ema(valid_macd, signal) if len(valid_macd) >= signal else []

    # Align signal line with macd_line
    signal_line = [None] * (len(macd_line) - len(signal_line_values)) + signal_line_values

    # Histogram
    histogram = []
    for m, s in zip(macd_line, signal_line):
        if m is not None and s is not None:
            histogram.append(m - s)
        else:
            histogram.append(None)

    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def bollinger_bands(closes: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, List[float]]:
    """Bollinger Bands."""
    middle = sma(closes, period)
    upper = []
    lower = []

    for i in range(len(closes)):
        if middle[i] is None:
            upper.append(None)
            lower.append(None)
        else:
            window = closes[i - period + 1:i + 1]
            mean = middle[i]
            variance = sum((x - mean) ** 2 for x in window) / period
            std = variance ** 0.5
            upper.append(mean + std_dev * std)
            lower.append(mean - std_dev * std)

    return {"upper": upper, "middle": middle, "lower": lower}


def atr(candles: List[Dict], period: int = 14) -> List[Optional[float]]:
    """Average True Range."""
    if len(candles) < 2:
        return [None] * len(candles)

    tr_list = [None]  # First candle has no previous
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)

    valid_tr = [v for v in tr_list if v is not None]
    if len(valid_tr) < period:
        return [None] * len(candles)

    result = [None] * period
    avg = sum(valid_tr[:period]) / period
    result.append(avg)

    for i in range(period, len(valid_tr)):
        avg = (avg * (period - 1) + valid_tr[i]) / period
        result.append(avg)

    # Align
    return [None] * (len(candles) - len(result)) + result
