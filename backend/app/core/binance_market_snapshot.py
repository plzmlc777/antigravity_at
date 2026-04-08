"""
binance_market_snapshot.py - SINGLE SOURCE OF TRUTH for Binance market snapshot transformation

Pure functions used by both:
- backend AISymbolSelectionService._fetch_binance_market_data (live AI symbol selection,
  with HttpClientManager + volume_spike caching)
- skill at-symbol-select/scripts/fetch_market_data.py (CLI for ad-hoc inspection)

Both paths must produce identical (stock_data, ranking_data) for the same input ticker
list. Differences in I/O (async httpx vs sync urllib) and stateful caching (volume_spike)
remain at the call site; only the pure transformation logic lives here.

Algorithm constants:
- DEFAULT_MIN_VOLUME = 100,000 USD (24h quote volume)
- volume_top: top 50 by quoteVolume
- change_top / change_bottom: top/bottom 30 by priceChangePercent
- volatility_top: top 30 by (high - low) / low
- D-012 blacklist filter applied before any ranking
"""

import json
import os
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

DEFAULT_MIN_VOLUME = 100_000
VOLUME_TOP_N = 50
CHANGE_TOP_N = 30
VOLATILITY_TOP_N = 30


def project_blacklist_path() -> str:
    """Return absolute path to the canonical D-012 symbol blacklist file."""
    # backend/app/core/binance_market_snapshot.py → project root is 4 levels up
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    return os.path.join(
        project_root, ".claude", "skills", "at-symbol-select", "references", "symbol_blacklist.json"
    )


def load_blacklist(path: Optional[str] = None) -> Set[str]:
    """Load D-012 symbol blacklist. Returns an empty set on any failure so absence
    never breaks symbol selection."""
    if path is None:
        path = project_blacklist_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            str(entry["symbol"]).strip().upper()
            for entry in data.get("blacklist", [])
            if entry.get("symbol")
        }
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def filter_usdt_tickers(
    tickers: Iterable[Dict[str, Any]],
    min_volume: float = DEFAULT_MIN_VOLUME,
    blacklist: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter raw Binance ticker list to USDT pairs above min_volume, excluding blacklist."""
    bl = blacklist or set()
    return [
        t
        for t in tickers
        if t.get("symbol", "").endswith("USDT")
        and float(t.get("quoteVolume", 0)) > min_volume
        and t.get("symbol", "").strip().upper() not in bl
    ]


def _ticker_to_rank(t: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a Binance ticker dict into a compact ranking entry."""
    pct = float(t.get("priceChangePercent", 0))
    return {
        "code": t["symbol"],
        "name": t["symbol"].replace("USDT", ""),
        "lastPrice": t.get("lastPrice", "0"),
        "priceChangePercent": f"{pct:+.2f}%",
        "quoteVolume": t.get("quoteVolume", "0"),
    }


def build_stock_data(
    usdt_tickers: List[Dict[str, Any]], is_futures: bool = False
) -> List[Dict[str, Any]]:
    """Convert filtered USDT tickers to stock_data list (Kiwoom-compatible format)."""
    stock_data = []
    for t in usdt_tickers:
        symbol = t["symbol"]
        pct = float(t.get("priceChangePercent", 0))
        stock_data.append(
            {
                "code": symbol,
                "name": symbol.replace("USDT", ""),
                "lastPrice": t.get("lastPrice", "0"),
                "priceChangePercent": f"{pct:+.2f}%",
                "quoteVolume": t.get("quoteVolume", "0"),
                "highPrice": t.get("highPrice", "0"),
                "lowPrice": t.get("lowPrice", "0"),
                "marketName": "Futures" if is_futures else "Spot",
            }
        )
    return stock_data


def build_volume_top(usdt_tickers: List[Dict[str, Any]], n: int = VOLUME_TOP_N) -> List[Dict[str, Any]]:
    sorted_tickers = sorted(
        usdt_tickers, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True
    )
    return [_ticker_to_rank(t) for t in sorted_tickers[:n]]


def build_change_rankings(
    usdt_tickers: List[Dict[str, Any]], n: int = CHANGE_TOP_N
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (change_top, change_bottom) sorted by priceChangePercent."""
    sorted_tickers = sorted(
        usdt_tickers, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True
    )
    return (
        [_ticker_to_rank(t) for t in sorted_tickers[:n]],
        [_ticker_to_rank(t) for t in sorted_tickers[-n:]],
    )


def build_volatility_top(
    usdt_tickers: List[Dict[str, Any]], n: int = VOLATILITY_TOP_N
) -> List[Dict[str, Any]]:
    """Sort by 24h volatility = (high - low) / low. Skip tickers with low <= 0."""
    items: List[Tuple[Dict[str, Any], float]] = []
    for t in usdt_tickers:
        high = float(t.get("highPrice", 0))
        low = float(t.get("lowPrice", 0))
        if low > 0:
            vol_pct = ((high - low) / low) * 100
            entry = _ticker_to_rank(t)
            entry["volatility"] = f"{vol_pct:.1f}%"
            items.append((entry, vol_pct))
    items.sort(key=lambda x: x[1], reverse=True)
    return [d[0] for d in items[:n]]


def build_market_data(
    tickers: Iterable[Dict[str, Any]],
    is_futures: bool = False,
    min_volume: float = DEFAULT_MIN_VOLUME,
    blacklist: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Top-level pure transformation: raw tickers → (stock_data, ranking_data).

    The caller is responsible for fetching tickers (HTTP) and any caching like
    volume_spike. ranking_data here contains volume_top, change_top, change_bottom,
    volatility_top — volume_spike is computed by the caller when prior cache exists.
    """
    if blacklist is None:
        blacklist = load_blacklist()
    usdt_tickers = filter_usdt_tickers(tickers, min_volume=min_volume, blacklist=blacklist)
    stock_data = build_stock_data(usdt_tickers, is_futures=is_futures)
    change_top, change_bottom = build_change_rankings(usdt_tickers)
    ranking_data = {
        "volume_top": build_volume_top(usdt_tickers),
        "change_top": change_top,
        "change_bottom": change_bottom,
        "volatility_top": build_volatility_top(usdt_tickers),
    }
    return stock_data, ranking_data


def compute_volume_spike(
    usdt_tickers: List[Dict[str, Any]],
    prev_volume_cache: Dict[str, float],
    threshold_pct: float = 5.0,
    min_prev_volume: float = 100_000,
    top_n: int = 50,
) -> List[Dict[str, Any]]:
    """Compare current 24h volume vs prior cached volumes; return top spikes.

    Returns an empty list when prev_volume_cache is empty (first run).
    """
    if not prev_volume_cache:
        return []
    spikes: List[Tuple[Dict[str, Any], float]] = []
    for t in usdt_tickers:
        sym = t["symbol"]
        cur_vol = float(t.get("quoteVolume", 0))
        prev_vol = prev_volume_cache.get(sym)
        if prev_vol and prev_vol > min_prev_volume:
            spike_pct = ((cur_vol - prev_vol) / prev_vol) * 100
            if spike_pct > threshold_pct:
                entry = _ticker_to_rank(t)
                entry["spike_pct"] = f"+{spike_pct:.1f}%"
                spikes.append((entry, spike_pct))
    spikes.sort(key=lambda x: x[1], reverse=True)
    return [d[0] for d in spikes[:top_n]]
