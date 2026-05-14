"""Permutation / bootstrap utilities for Research Track R-1 PoCs.

Motivation
----------
Five R-1 PoCs in a row (2026-05-14) graveyarded with a recurring pattern:
- event-study + 8 bp round-trip fee + post-trigger mean reversion
- random anchor shuffle produced perm-null t-stat means of -5 to -8 σ
- observed t-stat indistinguishable from null → perm_p > 0.3
- ROOT CAUSE: the perm null also pays fees and exhibits the same drift,
  so the test cannot tell whether the observed t reflects signal or fee drag.

These helpers fix the design so future PoCs can distinguish signal from artifact:

1. `block_permutation_test` — preserves intra-symbol autocorrelation by
   shuffling contiguous time blocks within each symbol rather than re-anchoring
   triggers to arbitrary timestamps. Removes the global "all triggers fall in
   a high-fee-drift epoch" coincidence.

2. `fee_aware_perm_test` — computes the perm null with the SAME fee applied
   to each synthetic trade as the observed pool, then reports `signal_t_excess`
   = observed_t − null_mean_t. A positive excess of ≥ 2σ above the null mean
   means the observation is genuinely above the fee floor.

3. `bootstrap_ci` — block bootstrap on observed trades for a model-free
   confidence interval on the mean return. CI lower bound > 0 (after fee) is
   the cleanest pass signal; complements perm null but is not vulnerable to
   the same drift bias.

Usage in R-1 script
-------------------
```python
from scripts.research._perm_utils import (
    block_permutation_test,
    fee_aware_perm_test,
    bootstrap_ci,
)

# observed = pandas Series of per-trade NET returns (post-fee)
obs_t = observed.mean() / observed.std(ddof=1) * np.sqrt(len(observed))

# Block-perm shuffle within each symbol's own time series
block_result = block_permutation_test(
    per_sym_returns_by_time,        # dict: sym -> pd.Series indexed by entry timestamp
    trigger_mask_by_sym,            # dict: sym -> bool Series, True at trigger times
    hold_returns_by_sym,            # dict: sym -> pd.Series of hold-window returns aligned to trigger candidates
    fee_per_trade=0.0008,
    n_perms=1000,
    block_minutes=240,              # 4-hour blocks preserve session-scale autocorr
    direction_fn=lambda trigger_value: -np.sign(trigger_value),  # paradigm-specific
)
# returns dict {obs_t, null_t_mean, null_t_std, signal_t_excess, perm_p, n_signals}

# Fee-aware perm comparison (simpler, recommended for first pass)
fee_result = fee_aware_perm_test(
    observed_net_returns=observed,
    candidate_pool_size=len(all_potential_trade_windows),
    fee_per_trade=0.0008,
    n_perms=1000,
)

# Bootstrap CI on observed
ci_result = bootstrap_ci(observed, n_boot=2000, block_size=20)
# returns {mean, ci_lower, ci_upper, prob_positive}
```

Pass criteria — REPLACE the old "perm_p ≤ 0.05" gate
-----------------------------------------------------
For event-study PoCs (5m–4h hold windows):
- `signal_t_excess >= 2.0` (observed t-stat is ≥ 2σ above the fee-drift null mean)
- `bootstrap_ci.ci_lower > 0` (95% CI on observed net mean excludes 0)
- `block_perm.perm_p <= 0.10` (after block-shuffle the observation is still rare)

A paradigm that passes ALL three has cleared the fee drag trap.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, Optional, Sequence

import numpy as np
import pandas as pd

log = logging.getLogger("perm_utils")


def _t_stat(arr: np.ndarray) -> float:
    """Two-sided one-sample t against mean=0. Returns 0 if n<2 or std=0."""
    n = len(arr)
    if n < 2:
        return 0.0
    sd = arr.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(arr.mean() / sd * np.sqrt(n))


def fee_aware_perm_test(
    observed_net_returns: Sequence[float],
    candidate_pool_returns: Sequence[float],
    fee_per_trade: float = 0.0008,
    n_perms: int = 1000,
    rng_seed: Optional[int] = 42,
) -> Dict[str, float]:
    """Compare observed t-stat to null distribution where the SAME fee is applied
    to random subsets of candidate trades.

    Parameters
    ----------
    observed_net_returns : net (post-fee) per-trade returns at actual triggers
    candidate_pool_returns : per-trade GROSS returns over ALL candidate hold-windows
                              (not yet filtered by trigger). These are random non-trigger
                              outcomes that share the same fee structure.
                              For a 4-hour hold paradigm: every possible 4-hour window
                              return across the panel, NOT just the triggered ones.
    fee_per_trade : round-trip fee to subtract from each null draw
    n_perms : null draws
    rng_seed : reproducibility

    Returns
    -------
    dict with:
        obs_mean, obs_t,
        null_mean_t, null_std_t,    (the fee-drift baseline)
        signal_t_excess              = obs_t - null_mean_t
        perm_p_two_sided             P(|null t| >= |obs_t|)
        perm_p_one_sided_below       P(null t <= obs_t)  -- use for short/MR hypotheses
        perm_p_one_sided_above       P(null t >= obs_t)  -- use for long/momentum hypotheses
        n_observed
        n_candidate
    """
    rng = np.random.default_rng(rng_seed)
    obs = np.asarray(list(observed_net_returns), dtype=float)
    pool = np.asarray(list(candidate_pool_returns), dtype=float)
    n_obs = len(obs)
    n_pool = len(pool)
    if n_obs < 2 or n_pool < n_obs * 2:
        return {
            "obs_mean": float(obs.mean()) if n_obs else 0.0,
            "obs_t": _t_stat(obs),
            "null_mean_t": float("nan"),
            "null_std_t": float("nan"),
            "signal_t_excess": float("nan"),
            "perm_p_two_sided": float("nan"),
            "perm_p_one_sided_below": float("nan"),
            "perm_p_one_sided_above": float("nan"),
            "n_observed": n_obs,
            "n_candidate": n_pool,
            "error": "n_obs<2 or n_pool<2*n_obs",
        }

    obs_t = _t_stat(obs)
    pool_net = pool - fee_per_trade  # apply same fee
    null_t = np.empty(n_perms)
    for i in range(n_perms):
        idx = rng.choice(n_pool, size=n_obs, replace=False)
        sample = pool_net[idx]
        null_t[i] = _t_stat(sample)

    null_mean = float(null_t.mean())
    null_std = float(null_t.std(ddof=1))
    perm_p_two = float((np.abs(null_t) >= abs(obs_t)).mean())
    perm_p_below = float((null_t <= obs_t).mean())
    perm_p_above = float((null_t >= obs_t).mean())

    return {
        "obs_mean": float(obs.mean()),
        "obs_t": obs_t,
        "null_mean_t": null_mean,
        "null_std_t": null_std,
        "signal_t_excess": obs_t - null_mean,
        "perm_p_two_sided": perm_p_two,
        "perm_p_one_sided_below": perm_p_below,
        "perm_p_one_sided_above": perm_p_above,
        "n_observed": n_obs,
        "n_candidate": n_pool,
    }


def block_permutation_test(
    per_sym_signal: Dict[str, pd.Series],
    per_sym_forward_return: Dict[str, pd.Series],
    *,
    threshold_fn: Callable[[pd.Series], pd.Series],
    direction_fn: Callable[[pd.Series], pd.Series],
    fee_per_trade: float = 0.0008,
    n_perms: int = 1000,
    block_size: int = 240,
    rng_seed: Optional[int] = 42,
) -> Dict[str, float]:
    """Block-shuffle the signal series within each symbol independently,
    then re-run trigger+direction selection on the shuffled signals.

    This preserves:
    - per-symbol return distribution
    - per-symbol forward-return autocorrelation (within block)
    - fee structure

    It disrupts:
    - the temporal alignment between signal extremum and forward return

    Parameters
    ----------
    per_sym_signal : sym -> signal series (e.g., skew z-score) indexed by entry time
    per_sym_forward_return : sym -> forward GROSS return for each candidate entry time
    threshold_fn : function (signal_series) -> bool series, True at trigger
    direction_fn : function (signal_series) -> int series in {-1, 0, +1}, trade direction
    fee_per_trade : round-trip fee
    n_perms : block-shuffle iterations
    block_size : number of consecutive bars per shuffle block (keep ≥ horizon)
    rng_seed : reproducibility

    Returns dict with obs_t, null_mean_t, null_std_t, signal_t_excess, perm_p_two_sided.
    """
    rng = np.random.default_rng(rng_seed)

    def _trades_for(signal_by_sym: Dict[str, pd.Series]) -> np.ndarray:
        rows = []
        for sym, sig in signal_by_sym.items():
            fwd = per_sym_forward_return.get(sym)
            if fwd is None or sig is None or len(sig) == 0 or len(fwd) == 0:
                continue
            aligned = pd.DataFrame({"sig": sig, "fwd": fwd}).dropna()
            if aligned.empty:
                continue
            mask = threshold_fn(aligned["sig"])
            direction = direction_fn(aligned["sig"])
            entries = aligned.loc[mask]
            if entries.empty:
                continue
            d = direction.loc[entries.index].astype(float).values
            r = entries["fwd"].astype(float).values
            net = d * r - fee_per_trade
            rows.append(net)
        if not rows:
            return np.array([])
        return np.concatenate(rows)

    observed = _trades_for(per_sym_signal)
    if len(observed) < 2:
        return {
            "obs_t": 0.0,
            "null_mean_t": float("nan"),
            "null_std_t": float("nan"),
            "signal_t_excess": float("nan"),
            "perm_p_two_sided": float("nan"),
            "n_observed": int(len(observed)),
            "error": "observed n<2",
        }
    obs_t = _t_stat(observed)

    def _block_shuffle(series: pd.Series) -> pd.Series:
        n = len(series)
        if n <= block_size:
            shuffled_vals = rng.permutation(series.values)
            return pd.Series(shuffled_vals, index=series.index, name=series.name)
        n_blocks = (n + block_size - 1) // block_size
        block_indices = np.arange(n_blocks)
        rng.shuffle(block_indices)
        out_vals = np.empty(n, dtype=series.values.dtype)
        write = 0
        for bidx in block_indices:
            start = bidx * block_size
            end = min(start + block_size, n)
            chunk = series.values[start:end]
            out_vals[write : write + len(chunk)] = chunk
            write += len(chunk)
        return pd.Series(out_vals, index=series.index, name=series.name)

    null_t = np.empty(n_perms)
    for i in range(n_perms):
        shuffled = {sym: _block_shuffle(sig) for sym, sig in per_sym_signal.items()}
        null_arr = _trades_for(shuffled)
        null_t[i] = _t_stat(null_arr) if len(null_arr) >= 2 else 0.0

    null_mean = float(null_t.mean())
    null_std = float(null_t.std(ddof=1))
    perm_p_two = float((np.abs(null_t) >= abs(obs_t)).mean())

    return {
        "obs_t": obs_t,
        "null_mean_t": null_mean,
        "null_std_t": null_std,
        "signal_t_excess": obs_t - null_mean,
        "perm_p_two_sided": perm_p_two,
        "n_observed": int(len(observed)),
        "n_perms": int(n_perms),
        "block_size": int(block_size),
    }


def bootstrap_ci(
    observed_net_returns: Sequence[float],
    *,
    n_boot: int = 2000,
    block_size: int = 1,
    alpha: float = 0.05,
    rng_seed: Optional[int] = 42,
) -> Dict[str, float]:
    """Block bootstrap CI for the mean of per-trade net returns.

    `block_size=1` is i.i.d. bootstrap (suitable when trades are widely spaced
    and independent). For overlapping trades, use block_size ≥ hold/entry-stride.
    """
    rng = np.random.default_rng(rng_seed)
    arr = np.asarray(list(observed_net_returns), dtype=float)
    n = len(arr)
    if n < 2:
        return {
            "mean": float(arr.mean()) if n else 0.0,
            "ci_lower": float("nan"),
            "ci_upper": float("nan"),
            "prob_positive": float("nan"),
            "n": int(n),
            "error": "n<2",
        }
    means = np.empty(n_boot)
    if block_size <= 1:
        for i in range(n_boot):
            idx = rng.integers(0, n, size=n)
            means[i] = arr[idx].mean()
    else:
        n_blocks = (n + block_size - 1) // block_size
        for i in range(n_boot):
            sampled = []
            for _ in range(n_blocks):
                start = rng.integers(0, max(1, n - block_size + 1))
                sampled.append(arr[start : start + block_size])
            cat = np.concatenate(sampled)[:n]
            means[i] = cat.mean()
    lower = float(np.quantile(means, alpha / 2))
    upper = float(np.quantile(means, 1 - alpha / 2))
    return {
        "mean": float(arr.mean()),
        "ci_lower": lower,
        "ci_upper": upper,
        "prob_positive": float((means > 0).mean()),
        "n": int(n),
        "n_boot": int(n_boot),
        "block_size": int(block_size),
    }


__all__ = [
    "fee_aware_perm_test",
    "block_permutation_test",
    "bootstrap_ci",
]
