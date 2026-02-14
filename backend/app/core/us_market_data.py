"""
US Market Data Provider (via yfinance)

Provides US market index data for strategies and analysis.
Cached to avoid redundant API calls within the same trading day.

Usage:
    from app.core.us_market_data import us_market

    # Get previous day's change
    change = us_market.get_change("^GSPC")  # S&P 500: +1.23 (%)

    # Get multiple indices at once
    data = us_market.get_summary()
    # {'sp500': {'close': 6836.17, 'change_pct': 0.05, ...}, 'nasdaq': {...}, ...}

    # Get historical data
    hist = us_market.get_history("^GSPC", days=30)
"""
import logging
from datetime import datetime, date
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Well-known US index tickers
US_INDICES = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "sox": "^SOX",        # Philadelphia Semiconductor
}


class USMarketData:
    """Singleton US market data provider with daily cache."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}       # {ticker: {date: str, data: DataFrame}}
        return cls._instance

    def _fetch(self, ticker: str, period: str = "5d"):
        """Fetch data from yfinance with daily caching."""
        today = date.today().isoformat()
        cache_key = f"{ticker}:{period}"

        if cache_key in self._cache and self._cache[cache_key]["date"] == today:
            return self._cache[cache_key]["data"]

        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist = t.history(period=period)
            if hist.empty:
                logger.warning(f"No data returned for {ticker}")
                return None

            self._cache[cache_key] = {"date": today, "data": hist}
            return hist
        except Exception as e:
            logger.error(f"Failed to fetch {ticker}: {e}")
            return None

    def get_change(self, ticker: str = "^GSPC") -> Optional[float]:
        """Get previous day's close-to-close change percentage.

        Args:
            ticker: Yahoo Finance ticker (default: S&P 500)

        Returns:
            Change percentage (e.g., 1.23 for +1.23%), or None on error.
        """
        hist = self._fetch(ticker)
        if hist is None or len(hist) < 2:
            return None

        prev_close = hist["Close"].iloc[-2]
        last_close = hist["Close"].iloc[-1]
        return (last_close - prev_close) / prev_close * 100

    def get_latest(self, ticker: str = "^GSPC") -> Optional[Dict]:
        """Get latest trading day's data.

        Returns:
            {'open': float, 'high': float, 'low': float, 'close': float,
             'volume': int, 'change_pct': float, 'date': str}
        """
        hist = self._fetch(ticker)
        if hist is None or len(hist) < 2:
            return None

        last = hist.iloc[-1]
        prev_close = hist["Close"].iloc[-2]
        change_pct = (last["Close"] - prev_close) / prev_close * 100

        return {
            "open": round(float(last["Open"]), 2),
            "high": round(float(last["High"]), 2),
            "low": round(float(last["Low"]), 2),
            "close": round(float(last["Close"]), 2),
            "volume": int(last["Volume"]),
            "change_pct": round(change_pct, 4),
            "date": str(hist.index[-1].date()),
        }

    def get_summary(self) -> Dict[str, Optional[Dict]]:
        """Get summary of all major US indices.

        Returns:
            {'sp500': {...}, 'nasdaq': {...}, 'dow': {...}, 'sox': {...}}
        """
        result = {}
        for name, ticker in US_INDICES.items():
            result[name] = self.get_latest(ticker)
        return result

    def get_history(self, ticker: str = "^GSPC", days: int = 30) -> Optional[list]:
        """Get historical daily data.

        Args:
            ticker: Yahoo Finance ticker
            days: Number of days (5, 30, 90, 365, etc.)

        Returns:
            List of {'date': str, 'open': float, 'close': float, 'change_pct': float, ...}
        """
        period_map = {5: "5d", 30: "1mo", 90: "3mo", 180: "6mo", 365: "1y"}
        period = period_map.get(days, f"{days}d")

        hist = self._fetch(ticker, period=period)
        if hist is None or len(hist) < 2:
            return None

        records = []
        for i in range(1, len(hist)):
            prev_close = hist["Close"].iloc[i - 1]
            row = hist.iloc[i]
            change_pct = (row["Close"] - prev_close) / prev_close * 100
            records.append({
                "date": str(hist.index[i].date()),
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "change_pct": round(change_pct, 4),
            })
        return records

    def get_change_map(self, ticker: str = "^GSPC", days: int = 365) -> Dict[str, float]:
        """Get a date→change_pct mapping for backtest use.

        Maps Korean trading dates to the most recent US market close change.
        Korean Mon 09:00 → uses US Fri close vs Thu close.

        Args:
            ticker: Yahoo Finance ticker
            days: How many days of history

        Returns:
            {'2025-06-15': 1.23, '2025-06-16': -0.45, ...}
            Key = US trading date (the day the change was recorded).
            Strategy should look up using the previous US trading day
            relative to the Korean date.
        """
        history = self.get_history(ticker, days=days)
        if not history:
            return {}

        # Build date→change map from US trading dates
        us_changes = {row["date"]: row["change_pct"] for row in history}

        # Also build a Korean date → US change mapping
        # Korean date D at 09:00 → US market closed at D 06:00 KST (= D-1 US date)
        # So for Korean date, we need the latest US close BEFORE that date
        import bisect
        us_dates = sorted(us_changes.keys())

        result = {}
        # For each US date, the change is available to Korean market on the NEXT calendar day
        for us_date in us_dates:
            result[us_date] = us_changes[us_date]

        return result

    def get_change_for_date(self, korean_date: str, change_map: Dict[str, float]) -> float:
        """Look up US market change for a given Korean trading date.

        Args:
            korean_date: Korean date string 'YYYY-MM-DD'
            change_map: Result from get_change_map()

        Returns:
            US market change % that was known at Korean market open, or 0.0
        """
        # Korean date D → US market last closed on D-1 (or earlier if weekend)
        from datetime import timedelta
        d = datetime.strptime(korean_date, "%Y-%m-%d").date()

        # Look back up to 4 days (covers weekends + holidays)
        for offset in range(1, 5):
            us_date = str(d - timedelta(days=offset))
            if us_date in change_map:
                return change_map[us_date]
        return 0.0

    def clear_cache(self):
        """Clear all cached data."""
        self._cache.clear()


# Singleton instance
us_market = USMarketData()
