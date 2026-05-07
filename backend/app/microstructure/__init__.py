"""
Microstructure module — Binance futures order-flow / positioning data.

Sources:
  - REST API:
      - Funding rate (full history, 8h frequency)
      - Open interest (last 30d, hourly)
      - L/S ratios (last 30d, hourly)
      - Taker buy/sell ratio (last 30d, hourly)
  - data.binance.vision daily archives:
      - metrics CSV: OI + top trader L/S + account L/S + taker L/S ratio
                     at 5-minute frequency, going back to contract listing
      - aggTrades: every individual trade (large files)

Why this matters: OHLCV-only pattern signals showed no OOS forward-predictive
power on liquid crypto (correlation -0.05 with forward returns). Microstructure
adds POSITIONING information (who's leveraged long/short, who's pressing the
market with market orders) which is qualitatively different from price/volume
patterns. The hypothesis is that positioning extremes precede price moves
because of mechanical liquidations / forced unwinds.
"""
from .archive_downloader import download_metrics_range, parse_metrics_csv
from .features import aggregate_to_eval_bars, attach_to_feature_matrix

__all__ = [
    "download_metrics_range",
    "parse_metrics_csv",
    "aggregate_to_eval_bars",
    "attach_to_feature_matrix",
]
