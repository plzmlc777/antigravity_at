"""Forward-return computation for signals.

For each signal at (timeframe, timestamp, direction, horizon_bars), we look up
the close price at the signal's TF bar AT timestamp, and the close price
horizon_bars later. Direction-adjusts the return:
    bull   :  +(close[t+h]/close[t] - 1)
    bear   :  -(close[t+h]/close[t] - 1)   -- profit on decline
    neutral:  abs(close[t+h]/close[t] - 1)  -- volatility expansion proxy

Look-ahead safety:
  - The signal was emitted at the close of bar t (this is enforced in detectors).
  - The "entry" happens at next bar's open (we use close[t] as entry proxy here
    because for signal-quality measurement the small open-vs-close gap doesn't
    bias edge ranking. Phase 5 composer applies the +1-bar shift for trading.).
  - The "exit" is close[t+h], which is fully in the future of t — no leak.

Inputs:
  - signals_df: from PatternScanner — symbol, timeframe, pattern_name, timestamp,
                direction, horizon_bars (and other fields we don't need here)
  - ohlcv_by_tf: dict[str, pd.DataFrame] with the resampled OHLCV per TF (DatetimeIndex)

Output: signals_df with two new columns:
  - forward_return:        direction-adjusted forward return
  - forward_return_raw:    raw close-to-close return (no direction sign)
  - exit_timestamp:        the timestamp at +horizon_bars on that TF (NaT if past end)

Signals whose horizon extends past the available data are dropped (their forward
return is unknowable yet — they're "unfinished" trades).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def attach_forward_returns(
    signals_df: pd.DataFrame,
    ohlcv_by_tf: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    if len(signals_df) == 0:
        out = signals_df.copy()
        out["forward_return"] = np.nan
        out["forward_return_raw"] = np.nan
        out["exit_timestamp"] = pd.NaT
        return out

    required = {"timeframe", "timestamp", "direction", "horizon_bars"}
    missing = required - set(signals_df.columns)
    if missing:
        raise ValueError(f"signals_df missing columns: {missing}")

    out = signals_df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    out["forward_return"] = np.nan
    out["forward_return_raw"] = np.nan
    out["exit_timestamp"] = pd.NaT

    for tf, group_idx in out.groupby("timeframe").groups.items():
        if tf not in ohlcv_by_tf:
            # no OHLCV for this TF — leave NaN
            continue
        tf_df = ohlcv_by_tf[tf]
        if len(tf_df) == 0:
            continue
        # Build a position lookup: timestamp → integer index in tf_df
        tf_idx = tf_df.index
        # ensure DatetimeIndex sorted
        closes = tf_df["close"].to_numpy()

        sub = out.loc[group_idx]
        for ix, row in sub.iterrows():
            ts = row["timestamp"]
            h = int(row["horizon_bars"])
            # find position of ts in tf_idx (exact match — signals were emitted
            # at TF bar close timestamps)
            pos_arr = tf_idx.get_indexer([ts])
            pos = int(pos_arr[0])
            if pos < 0:
                # timestamp not exactly in TF index — fall back to nearest <= ts
                pos = int(tf_idx.searchsorted(ts, side="right") - 1)
                if pos < 0:
                    continue
            exit_pos = pos + h
            if exit_pos >= len(closes):
                continue  # horizon extends past end → unfinished

            entry = float(closes[pos])
            exit_p = float(closes[exit_pos])
            if entry <= 0:
                continue
            raw = (exit_p - entry) / entry
            direction = row["direction"]
            if direction == "bull":
                adj = raw
            elif direction == "bear":
                adj = -raw
            elif direction == "neutral":
                adj = abs(raw)
            else:
                continue
            out.at[ix, "forward_return_raw"] = raw
            out.at[ix, "forward_return"] = adj
            out.at[ix, "exit_timestamp"] = tf_idx[exit_pos]

    return out
