"""CrossSymbolFitnessLearner — pool signals from many symbols into one tensor.

The fitness cell key remains (pattern, tf, cell_id, direction) but evidence
from ALL training symbols contributes to each cell. This dramatically increases
sample size per cell, which is the standard remedy for FDR-passing edges that
nevertheless fail OOS.

Hypothesis: pattern alpha is a structural property of patterns + regimes, not
symbol-specific. If true, pooling makes the fitness tensor more robust and
generalize across symbols. If false (alpha really IS symbol-specific), the
pooled fitness will average out — but at least it won't catastrophically
overfit one symbol's noise.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats

from .forward_returns import attach_forward_returns
from .learner import benjamini_hochberg_mask, _bootstrap_ci
from .types import FitnessCell, FitnessCellKey, FitnessTensor, FitnessTensorMeta

logger = logging.getLogger(__name__)


class CrossSymbolFitnessLearner:
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
        signals_by_symbol: dict[str, pd.DataFrame],
        ohlcv_by_symbol_tf: dict[str, dict[str, pd.DataFrame]],
        regime_by_symbol_tf: dict[str, dict[str, pd.DataFrame]],
    ) -> FitnessTensor:
        """Pool signals from many symbols, attach fwd returns + regime cells,
        aggregate by (pattern, tf, cell_id, direction)."""
        all_rows: list[pd.DataFrame] = []
        for sym, sigs in signals_by_symbol.items():
            if len(sigs) == 0:
                continue
            df = sigs.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            ohlcv_tf = ohlcv_by_symbol_tf.get(sym, {})
            regime_tf = regime_by_symbol_tf.get(sym, {})
            df = attach_forward_returns(df, ohlcv_tf)
            df = df.dropna(subset=["forward_return"])

            df["cell_id"] = pd.NA
            for tf, gidx in df.groupby("timeframe").groups.items():
                rdf = regime_tf.get(tf)
                if rdf is None:
                    continue
                sub = df.loc[gidx]
                mapped = rdf.reindex(sub["timestamp"].values)
                df.loc[sub.index, "cell_id"] = mapped["cell_id"].values
                if "is_warmup" in rdf.columns:
                    df.loc[sub.index, "is_warmup"] = mapped["is_warmup"].values

            df = df.dropna(subset=["cell_id"])
            if "is_warmup" in df.columns:
                warm = df["is_warmup"].astype("boolean").fillna(False).astype(bool)
                df = df[~warm]
            df["__symbol__"] = sym
            all_rows.append(df)

        if not all_rows:
            return self._empty(symbol_label="<empty>")

        df_all = pd.concat(all_rows, ignore_index=True)
        logger.info("CrossSymbol: %d total signals across %d symbols",
                    len(df_all), len(signals_by_symbol))

        # group ignoring __symbol__
        groups = df_all.groupby(["pattern_name", "timeframe", "cell_id", "direction"])
        records: list[dict] = []
        for (pat, tf, cell, dirn), sub in groups:
            n = len(sub)
            rets = sub["forward_return"].to_numpy()
            mean_edge = float(rets.mean()) if n > 0 else 0.0
            std = float(rets.std(ddof=1)) if n >= 2 else 0.0
            wr = float((rets > 0).mean()) if n > 0 else 0.0
            if n >= 2 and std > 0:
                _, pval = stats.ttest_1samp(rets, 0.0)
                pval = float(pval)
            else:
                pval = 1.0
            ci_lo, ci_hi = _bootstrap_ci(rets, n_boot=self.bootstrap_n) if n >= 2 else (mean_edge, mean_edge)
            records.append({
                "pattern": pat, "timeframe": tf, "cell_id": cell, "direction": dirn,
                "n": n, "edge_mean": mean_edge, "edge_std": std,
                "edge_ci_low": ci_lo, "edge_ci_high": ci_hi,
                "win_rate": wr, "p_value": pval,
            })

        rec_df = pd.DataFrame(records)
        n_total = len(rec_df)
        if n_total == 0:
            return self._empty(symbol_label="cross")

        eligible = rec_df["n"] >= self.min_samples
        rec_df["fdr_significant"] = False
        if eligible.any():
            mask = benjamini_hochberg_mask(
                rec_df.loc[eligible, "p_value"].to_numpy(), self.fdr_alpha
            )
            rec_df.loc[eligible, "fdr_significant"] = mask

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cells: dict[FitnessCellKey, FitnessCell] = {}
        for _, r in rec_df.iterrows():
            c = FitnessCell(
                pattern=str(r["pattern"]), timeframe=str(r["timeframe"]),
                cell_id=str(r["cell_id"]), direction=str(r["direction"]),
                n=int(r["n"]), edge_mean=float(r["edge_mean"]), edge_std=float(r["edge_std"]),
                edge_ci_low=float(r["edge_ci_low"]), edge_ci_high=float(r["edge_ci_high"]),
                win_rate=float(r["win_rate"]), p_value=float(r["p_value"]),
                fdr_significant=bool(r["fdr_significant"]), last_updated=now,
            )
            cells[c.key()] = c

        n_min = int(eligible.sum())
        n_active = int(rec_df["fdr_significant"].sum())
        meta = FitnessTensorMeta(
            symbol="cross_symbol(" + ",".join(sorted(signals_by_symbol.keys())) + ")",
            learned_at=now,
            train_window_start=df_all["timestamp"].min().to_pydatetime() if len(df_all) else now,
            train_window_end=df_all["timestamp"].max().to_pydatetime() if len(df_all) else now,
            min_samples=self.min_samples, fdr_alpha=self.fdr_alpha,
            n_cells_total=n_total, n_cells_with_min_samples=n_min,
            n_cells_active=n_active,
            forward_horizon_policy=f"cross-symbol pool (n={len(signals_by_symbol)} symbols)",
        )
        return FitnessTensor(meta=meta, cells=cells)

    def _empty(self, *, symbol_label: str) -> FitnessTensor:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return FitnessTensor(
            meta=FitnessTensorMeta(
                symbol=symbol_label, learned_at=now,
                train_window_start=now, train_window_end=now,
                min_samples=0, fdr_alpha=0.0,
                n_cells_total=0, n_cells_with_min_samples=0, n_cells_active=0,
                forward_horizon_policy="(empty)",
            ),
            cells={},
        )
