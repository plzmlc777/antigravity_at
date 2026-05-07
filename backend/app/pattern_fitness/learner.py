"""FitnessLearner — the core Phase 4 component.

Pipeline:
  1. Load Signal Tensor (from PatternScanner)
  2. Compute forward returns per signal
  3. Join each signal with its regime (regime DF per TF)
  4. Group by (pattern, tf, cell_id, direction) → aggregate stats
  5. Apply Benjamini-Hochberg FDR across all cells with n >= min_samples
  6. Emit FitnessTensor

Storage / persistence is via joblib (single file).
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from scipy import stats

from .forward_returns import attach_forward_returns
from .types import FitnessCell, FitnessCellKey, FitnessTensor, FitnessTensorMeta

logger = logging.getLogger(__name__)


def benjamini_hochberg_mask(pvalues: np.ndarray, alpha: float) -> np.ndarray:
    """Return boolean mask: which p-values pass BH-FDR at level alpha.

    Standard BH: rank p-values ascending; cell at rank i (1-indexed) passes
    iff p_i <= alpha * i / n. The largest i where this holds gives the
    threshold; all p_j <= threshold pass."""
    n = len(pvalues)
    if n == 0:
        return np.zeros(0, dtype=bool)
    sorted_idx = np.argsort(pvalues)
    sorted_p = pvalues[sorted_idx]
    critical = alpha * np.arange(1, n + 1) / n
    passes_sorted = sorted_p <= critical
    if not passes_sorted.any():
        return np.zeros(n, dtype=bool)
    k = int(np.where(passes_sorted)[0].max())
    threshold = sorted_p[k]
    return pvalues <= threshold


def _bootstrap_ci(returns: np.ndarray, n_boot: int = 500, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean."""
    if len(returns) < 2:
        m = float(returns.mean()) if len(returns) else 0.0
        return m, m
    rng = np.random.default_rng(42)
    means = rng.choice(returns, size=(n_boot, len(returns)), replace=True).mean(axis=1)
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1 - alpha / 2))
    return lo, hi


class FitnessLearner:
    """Run the full fitness learning pipeline."""

    def __init__(
        self,
        *,
        min_samples: int = 30,
        fdr_alpha: float = 0.05,
        bootstrap_n: int = 500,
    ) -> None:
        self.min_samples = int(min_samples)
        self.fdr_alpha = float(fdr_alpha)
        self.bootstrap_n = int(bootstrap_n)

    def learn(
        self,
        *,
        symbol: str,
        signals_df: pd.DataFrame,
        ohlcv_by_tf: dict[str, pd.DataFrame],
        regime_by_tf: dict[str, pd.DataFrame],
        train_start: Optional[pd.Timestamp] = None,
        train_end: Optional[pd.Timestamp] = None,
    ) -> FitnessTensor:
        """Build a FitnessTensor from the inputs.

        regime_by_tf: dict mapping TF -> regime DataFrame (output of
        RegimeClassifier.classify) for that TF's resampled OHLCV. Must include
        the cell_id column.
        """
        if len(signals_df) == 0:
            logger.warning("Empty signals_df — returning empty tensor")
            return self._empty_tensor(symbol)

        df = signals_df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # --- 1) train window filter
        if train_start is not None:
            df = df[df["timestamp"] >= pd.Timestamp(train_start)]
        if train_end is not None:
            df = df[df["timestamp"] <= pd.Timestamp(train_end)]

        # --- 2) attach forward returns
        df = attach_forward_returns(df, ohlcv_by_tf)
        df = df.dropna(subset=["forward_return"])
        logger.info("After fwd return: %d signals (dropped unfinished/no-OHLCV)", len(df))

        # --- 3) join regimes per TF
        df["cell_id"] = pd.NA
        for tf, group_idx in df.groupby("timeframe").groups.items():
            if tf not in regime_by_tf:
                continue
            rdf = regime_by_tf[tf]
            if "cell_id" not in rdf.columns or "is_warmup" not in rdf.columns:
                continue
            sub = df.loc[group_idx]
            mapped = rdf.reindex(sub["timestamp"].values)
            df.loc[sub.index, "cell_id"] = mapped["cell_id"].values
            df.loc[sub.index, "is_warmup"] = mapped["is_warmup"].values
        df = df.dropna(subset=["cell_id"])
        if "is_warmup" in df.columns:
            warmup_bool = df["is_warmup"].astype("boolean").fillna(False).astype(bool)
            df = df[~warmup_bool]
        logger.info("After regime join + warmup drop: %d signals", len(df))

        # --- 4) groupby aggregate
        groups = df.groupby(["pattern_name", "timeframe", "cell_id", "direction"])
        records: list[dict] = []
        for (pat, tf, cell, dirn), sub in groups:
            n = len(sub)
            returns = sub["forward_return"].to_numpy()
            mean_edge = float(returns.mean()) if n > 0 else 0.0
            std = float(returns.std(ddof=1)) if n >= 2 else 0.0
            wr = float((returns > 0).mean()) if n > 0 else 0.0

            if n >= 2 and std > 0:
                # 1-sample t-test vs 0
                tstat, pval = stats.ttest_1samp(returns, 0.0)
                pval = float(pval)
            else:
                pval = 1.0  # not enough data to reject H0

            ci_lo, ci_hi = _bootstrap_ci(returns, n_boot=self.bootstrap_n, alpha=0.05) if n >= 2 else (mean_edge, mean_edge)

            records.append({
                "pattern": pat,
                "timeframe": tf,
                "cell_id": cell,
                "direction": dirn,
                "n": n,
                "edge_mean": mean_edge,
                "edge_std": std,
                "edge_ci_low": ci_lo,
                "edge_ci_high": ci_hi,
                "win_rate": wr,
                "p_value": pval,
            })

        rec_df = pd.DataFrame(records)
        n_total = len(rec_df)
        if n_total == 0:
            return self._empty_tensor(symbol)

        # --- 5) FDR — apply only to cells with n >= min_samples
        eligible = rec_df["n"] >= self.min_samples
        rec_df["fdr_significant"] = False
        if eligible.any():
            pvals = rec_df.loc[eligible, "p_value"].to_numpy()
            mask = benjamini_hochberg_mask(pvals, self.fdr_alpha)
            rec_df.loc[eligible, "fdr_significant"] = mask

        # --- 6) build tensor
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cells: dict[FitnessCellKey, FitnessCell] = {}
        for _, r in rec_df.iterrows():
            cell = FitnessCell(
                pattern=str(r["pattern"]),
                timeframe=str(r["timeframe"]),
                cell_id=str(r["cell_id"]),
                direction=str(r["direction"]),
                n=int(r["n"]),
                edge_mean=float(r["edge_mean"]),
                edge_std=float(r["edge_std"]),
                edge_ci_low=float(r["edge_ci_low"]),
                edge_ci_high=float(r["edge_ci_high"]),
                win_rate=float(r["win_rate"]),
                p_value=float(r["p_value"]),
                fdr_significant=bool(r["fdr_significant"]),
                last_updated=now,
            )
            cells[cell.key()] = cell

        n_min = int(eligible.sum())
        n_active = int(rec_df["fdr_significant"].sum())

        # train window (use df range we actually trained on)
        if len(df):
            tw_start = df["timestamp"].min().to_pydatetime()
            tw_end = df["timestamp"].max().to_pydatetime()
        else:
            tw_start = now
            tw_end = now

        meta = FitnessTensorMeta(
            symbol=symbol,
            learned_at=now,
            train_window_start=tw_start,
            train_window_end=tw_end,
            min_samples=self.min_samples,
            fdr_alpha=self.fdr_alpha,
            n_cells_total=n_total,
            n_cells_with_min_samples=n_min,
            n_cells_active=n_active,
            forward_horizon_policy="signal.horizon_bars on signal.timeframe (close-to-close)",
        )
        return FitnessTensor(meta=meta, cells=cells)

    @staticmethod
    def _empty_tensor(symbol: str) -> FitnessTensor:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return FitnessTensor(
            meta=FitnessTensorMeta(
                symbol=symbol,
                learned_at=now,
                train_window_start=now,
                train_window_end=now,
                min_samples=0,
                fdr_alpha=0.0,
                n_cells_total=0,
                n_cells_with_min_samples=0,
                n_cells_active=0,
                forward_horizon_policy="(empty)",
            ),
            cells={},
        )

    @staticmethod
    def save(tensor: FitnessTensor, path: Path | str) -> None:
        joblib.dump(tensor, Path(path), compress=3)

    @staticmethod
    def load(path: Path | str) -> FitnessTensor:
        return joblib.load(Path(path))
