"""SignalTensorCache — disk-backed cache for scan results.

Cache key is derived from (symbol, scan_window_start, scan_window_end,
detector_signature). The detector_signature is a hash of all currently
registered detector names + a manual version bump field, so when detector
logic changes you bump CACHE_VERSION to invalidate.

Storage format: joblib pickle (gzip-compressed). joblib is already a project
dependency (used for ML models) and handles pandas DataFrames + nested dict
metadata natively — no need to JSON-encode metadata.

Note: master plan calls for parquet long-term (analytics-friendly,
cross-language). Migrate when fitness-tensor analytics tooling is built
(P4). For Phase 2 cache, joblib avoids a new dependency.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import pandas as pd

from app.patterns import PatternRegistry

logger = logging.getLogger(__name__)


# Bump when detector logic changes in a way that invalidates prior caches.
CACHE_VERSION = "v1"


def _detector_signature(detector_names: Iterable[str] | None = None) -> str:
    if detector_names is None:
        detector_names = sorted(d.name for d in PatternRegistry.all())
    h = hashlib.sha256()
    h.update(CACHE_VERSION.encode())
    for name in sorted(detector_names):
        h.update(name.encode())
        h.update(b";")
    return h.hexdigest()[:16]


@dataclass(frozen=True)
class CacheKey:
    symbol: str
    start: pd.Timestamp
    end: pd.Timestamp
    detector_sig: str

    def filename(self) -> str:
        return (
            f"{self.symbol}__{self.start.strftime('%Y%m%d_%H%M')}"
            f"__{self.end.strftime('%Y%m%d_%H%M')}__{self.detector_sig}.joblib"
        )


class SignalTensorCache:
    """Parquet-backed cache for scan results."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(
        *,
        symbol: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
        detector_names: Iterable[str] | None = None,
    ) -> CacheKey:
        return CacheKey(
            symbol=symbol,
            start=pd.Timestamp(start),
            end=pd.Timestamp(end),
            detector_sig=_detector_signature(detector_names),
        )

    def path(self, key: CacheKey) -> Path:
        return self.root / key.filename()

    def has(self, key: CacheKey) -> bool:
        return self.path(key).exists()

    def get(self, key: CacheKey) -> pd.DataFrame | None:
        p = self.path(key)
        if not p.exists():
            return None
        try:
            df = joblib.load(p)
        except Exception:
            logger.warning("Failed to load cache at %s; treating as miss", p)
            return None
        if not isinstance(df, pd.DataFrame):
            return None
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def put(self, key: CacheKey, tensor: pd.DataFrame) -> None:
        joblib.dump(tensor, self.path(key), compress=3)

    def invalidate(self, key: CacheKey) -> None:
        p = self.path(key)
        if p.exists():
            p.unlink()
