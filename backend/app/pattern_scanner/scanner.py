"""PatternScanner — runs all registered detectors across a set of timeframes.

Output: a flat DataFrame ("Signal Tensor") with one row per signal emission.
Columns: symbol, timeframe, pattern_name, timestamp, direction, confidence,
         horizon_bars, suggested_target, suggested_stop, metadata.

Usage:
    df_1m = load_ohlcv_for_symbol("005930", days=365)
    scanner = PatternScanner()
    tensor = scanner.scan(df_1m, symbol="005930")
    # tensor: pd.DataFrame, ready for analytics or composer consumption
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from app.patterns import PatternRegistry
from app.patterns.base import PatternDetector

from .resample import resample_ohlcv
from .types import (
    SUPPORTED_TIMEFRAMES,
    ScannedSignal,
    signal_tensor_columns,
)

logger = logging.getLogger(__name__)


@dataclass
class ScanStats:
    """Per-scan diagnostics."""
    symbol: str
    n_input_bars: int
    timeframes_scanned: list[str]
    detectors_run: int
    total_signals: int
    signals_by_tf: dict[str, int]
    signals_by_pattern: dict[str, int]
    duration_sec: float

    def summary(self) -> str:
        lines = [
            f"PatternScanner stats — {self.symbol}",
            f"  input 1m bars         : {self.n_input_bars}",
            f"  timeframes scanned    : {self.timeframes_scanned}",
            f"  detectors run         : {self.detectors_run}",
            f"  total signals         : {self.total_signals}",
            f"  duration              : {self.duration_sec:.2f}s",
            f"  signals_by_tf         : {self.signals_by_tf}",
        ]
        return "\n".join(lines)


class PatternScanner:
    """Multi-timeframe pattern scanner.

    Idempotent and stateless across scans. Detector instances are created once
    and reused across timeframes — they hold no per-scan state.
    """

    def __init__(
        self,
        timeframes: Iterable[str] = SUPPORTED_TIMEFRAMES,
        detectors: list[PatternDetector] | None = None,
    ) -> None:
        for tf in timeframes:
            if tf not in SUPPORTED_TIMEFRAMES:
                raise ValueError(
                    f"Unsupported timeframe: {tf}. Supported: {SUPPORTED_TIMEFRAMES}"
                )
        self.timeframes: list[str] = list(timeframes)
        if detectors is not None:
            self.detectors = detectors
        else:
            self.detectors = PatternRegistry.instantiate_all()

    def scan(self, df_1m: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
        """Scan all (TF × detector) combinations and return Signal Tensor.

        df_1m: 1m OHLCV with DatetimeIndex and columns open/high/low/close/volume.
        symbol: free-form identifier stored on each row.
        """
        tensor, _ = self.scan_with_stats(df_1m, symbol=symbol)
        return tensor

    def scan_with_stats(
        self, df_1m: pd.DataFrame, *, symbol: str
    ) -> tuple[pd.DataFrame, ScanStats]:
        if not isinstance(df_1m.index, pd.DatetimeIndex):
            raise ValueError("df_1m must have DatetimeIndex")
        for col in ("open", "high", "low", "close", "volume"):
            if col not in df_1m.columns:
                raise ValueError(f"df_1m missing column: {col}")

        t0 = time.perf_counter()
        rows: list[dict] = []
        signals_by_tf: dict[str, int] = {}
        signals_by_pattern: dict[str, int] = {}

        for tf in self.timeframes:
            df_tf = resample_ohlcv(df_1m, tf)
            if len(df_tf) == 0:
                logger.warning("%s/%s: empty after resample", symbol, tf)
                signals_by_tf[tf] = 0
                continue
            tf_count = 0
            for det in self.detectors:
                # respect detector's applicable_timeframes if declared.
                applicable = getattr(det.__class__, "applicable_timeframes", None)
                if applicable is not None and tf not in applicable:
                    continue
                try:
                    sigs = det.detect(df_tf)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "detector %s on %s/%s raised: %s",
                        det.name, symbol, tf, exc,
                    )
                    continue
                for s in sigs:
                    scanned = ScannedSignal.from_pattern_signal(
                        s, symbol=symbol, timeframe=tf
                    )
                    rows.append(scanned.to_row())
                    signals_by_pattern[s.pattern_name] = (
                        signals_by_pattern.get(s.pattern_name, 0) + 1
                    )
                    tf_count += 1
            signals_by_tf[tf] = tf_count

        if rows:
            tensor = pd.DataFrame(rows, columns=signal_tensor_columns())
        else:
            tensor = pd.DataFrame(columns=signal_tensor_columns())

        # ensure timestamp dtype for downstream analytics
        if len(tensor):
            tensor["timestamp"] = pd.to_datetime(tensor["timestamp"])

        elapsed = time.perf_counter() - t0
        stats = ScanStats(
            symbol=symbol,
            n_input_bars=len(df_1m),
            timeframes_scanned=self.timeframes,
            detectors_run=len(self.detectors),
            total_signals=len(tensor),
            signals_by_tf=signals_by_tf,
            signals_by_pattern=signals_by_pattern,
            duration_sec=elapsed,
        )
        return tensor, stats
