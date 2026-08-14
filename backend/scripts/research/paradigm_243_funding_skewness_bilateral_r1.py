"""Paradigm 243 — alt_funding_rate_30d_rolling_skewness_bilateral_1d_to_4d — R-1 PoC.

Hypothesis
----------
Per-symbol Binance Futures perpetual 8h funding rate 30d rolling skewness
(shape of the leverage distribution) at extremes predicts directional alpha:
- A_focus: skew >= +T  → SHORT (fragile bullish leverage buildup reverts)
- B_focus: skew <= -T  → LONG  (fragile bearish leverage buildup reverts)
- A_mirror: skew >= +T → LONG  (continuation baseline / long-drift control)
- B_mirror: skew <= -T → SHORT (continuation baseline)

Substrate
---------
- binance_funding_rate DB (2023-11-15 → 2026-08, 8h cadence, 14 syms deep)
- ohlcv_cache 1m joblib for forward-return computation (14 syms available)

Design
------
* Compute per-symbol rolling skewness over 90 funding periods (~30 days at 8h).
* Take last skew per UTC day as the daily signal.
* Forward return: log-close-to-log-close over {1, 3, 4} days.
* Bilateral SNT: 4 quadrants × 3 thresholds × 3 holds = 36 cells.
* Fee: 8 bp round-trip (0.0008), applied via fee_aware_perm_test.
* Gates: signal_t_excess >= 2.0 AND ci_lower > 0 AND perm_p_two_sided <= 0.10.
* Concentration: symbol_ci_pos_ratio >= 0.30 AND quarter_pos_t_ratio >= 0.50.

Output
------
runs/research_track/paradigm_243_funding_skewness_bilateral/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import psycopg2
from scipy import stats as sstats

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("paradigm_243_r1")

PARADIGM = "paradigm_243_funding_skewness_bilateral"
OUT_DIR = Path("runs/research_track") / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

FEE_ROUND_TRIP = 0.0008
SKEW_WINDOW = 90  # funding periods (~30 days of 8h funding)
THRESHOLDS = [0.5, 1.0, 1.5]
HOLDS_DAYS = [1, 3, 4]
PRIMARY_HOLD = 1
PRIMARY_T = 1.0
N_PERMS = 1000
N_BOOT = 2000

UNIVERSE = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT",
    "XRPUSDT", "BNBUSDT", "BCHUSDT", "LTCUSDT", "LINKUSDT",
    "AVAXUSDT", "FILUSDT", "NEARUSDT", "WIFUSDT",
]

DB = dict(host="localhost", dbname="antigravity_db",
          user="antigravity_user", password="antigravity_password")


def load_daily_signals(sym: str) -> pd.DataFrame:
    """Return DataFrame indexed by UTC date with columns:
    skew, close, fwd_1d, fwd_3d, fwd_4d (all log-returns for consistency)."""
    conn = psycopg2.connect(**DB)
    try:
        df = pd.read_sql(
            "SELECT funding_time, funding_rate FROM binance_funding_rate "
            f"WHERE symbol='{sym}' ORDER BY funding_time",
            conn,
        )
    finally:
        conn.close()
    if df.empty:
        return pd.DataFrame()
    df["funding_time"] = pd.to_datetime(df["funding_time"])
    df["funding_rate"] = pd.to_numeric(df["funding_rate"])
    df = df.set_index("funding_time").sort_index()
    df["skew_90"] = df["funding_rate"].rolling(SKEW_WINDOW).apply(
        lambda x: sstats.skew(x), raw=True
    )
    df["day"] = df.index.floor("D")
    daily_skew = df.dropna(subset=["skew_90"]).groupby("day")["skew_90"].last()

    ohlcv_path = Path("runs/ohlcv_cache") / f"{sym}_1m.joblib"
    if not ohlcv_path.exists():
        log.warning("no ohlcv cache for %s", sym)
        return pd.DataFrame()
    o = joblib.load(ohlcv_path)
    close_d = o["close"].resample("D").last().dropna()

    out = pd.DataFrame({"skew": daily_skew, "close": close_d}).dropna()
    for h in HOLDS_DAYS:
        fwd_close = out["close"].shift(-h)
        out[f"fwd_{h}d"] = np.log(fwd_close / out["close"])
    out = out.dropna()
    return out


def per_symbol_data() -> Dict[str, pd.DataFrame]:
    data: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        d = load_daily_signals(sym)
        if len(d) < 200:
            log.warning("insufficient rows for %s (n=%d) — skip", sym, len(d))
            continue
        data[sym] = d
        log.info("%s loaded n=%d date_range=%s->%s",
                 sym, len(d), d.index.min().date(), d.index.max().date())
    return data


def apply_direction(fwd: np.ndarray, side: str) -> np.ndarray:
    """side='long' → fwd; side='short' → -fwd; then subtract fee."""
    signed = fwd if side == "long" else -fwd
    return signed - FEE_ROUND_TRIP


def evaluate_cell(
    data: Dict[str, pd.DataFrame],
    quadrant: str,
    T: float,
    h: int,
) -> Dict:
    """quadrant ∈ {A_focus, B_focus, A_mirror, B_mirror}
    A: skew >= +T (positive-skew trigger); side=short (focus) or long (mirror)
    B: skew <= -T (negative-skew trigger); side=long (focus) or short (mirror)"""
    if quadrant.startswith("A"):
        mask_fn = lambda skew: skew >= T
        side = "short" if quadrant.endswith("focus") else "long"
    else:
        mask_fn = lambda skew: skew <= -T
        side = "long" if quadrant.endswith("focus") else "short"

    obs_net: List[float] = []
    pool_gross: List[float] = []  # candidate pool = ALL windows (non-trigger baseline)
    per_sym_obs_net: Dict[str, List[float]] = {}
    per_quarter_obs_net: Dict[str, List[float]] = {}

    for sym, d in data.items():
        fwd_col = f"fwd_{h}d"
        skew = d["skew"].values
        fwd = d[fwd_col].values
        # candidate pool = all forward returns (used for perm null)
        pool_signed_all = apply_direction(fwd, side)
        pool_gross.extend(pool_signed_all + FEE_ROUND_TRIP)  # feed GROSS to perm utility

        mask = mask_fn(skew)
        if mask.sum() == 0:
            continue
        obs = apply_direction(fwd[mask], side)
        obs_net.extend(obs.tolist())
        per_sym_obs_net.setdefault(sym, []).extend(obs.tolist())
        # quarter labels
        for ts, val in zip(d.index[mask], obs):
            q = f"{ts.year}Q{((ts.month - 1) // 3) + 1}"
            per_quarter_obs_net.setdefault(q, []).append(float(val))

    if len(obs_net) < 20:
        return dict(
            quadrant=quadrant, T=T, h=h, n_events=len(obs_net),
            insufficient=True,
        )

    perm = fee_aware_perm_test(
        observed_net_returns=obs_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=N_PERMS,
        rng_seed=42,
    )
    boot = bootstrap_ci(
        observed_net_returns=obs_net,
        n_boot=N_BOOT,
        block_size=1,
        rng_seed=42,
    )

    # Concentration diagnostics
    per_sym_summary = {}
    n_sym_ci_pos = 0
    n_sym_measurable = 0
    for sym, arr in per_sym_obs_net.items():
        if len(arr) < 20:
            per_sym_summary[sym] = dict(n=len(arr), insufficient=True)
            continue
        n_sym_measurable += 1
        b = bootstrap_ci(observed_net_returns=arr, n_boot=1000, rng_seed=43)
        per_sym_summary[sym] = dict(
            n=len(arr),
            mean_bp=float(np.mean(arr) * 10000),
            ci_lower_bp=float(b["ci_lower"] * 10000),
            ci_pos=bool(b["ci_lower"] > 0),
        )
        if b["ci_lower"] > 0:
            n_sym_ci_pos += 1

    per_quarter_summary = {}
    n_q_measurable = 0
    n_q_pos_t = 0
    for q, arr in per_quarter_obs_net.items():
        if len(arr) < 10:
            per_quarter_summary[q] = dict(n=len(arr), insufficient=True)
            continue
        n_q_measurable += 1
        a = np.asarray(arr)
        t = float(a.mean() / a.std(ddof=1) * np.sqrt(len(a))) if a.std(ddof=1) > 0 else 0.0
        per_quarter_summary[q] = dict(n=len(arr), mean_bp=float(a.mean() * 10000), t=t)
        if t > 0:
            n_q_pos_t += 1

    return dict(
        quadrant=quadrant, T=T, h=h,
        n_events=len(obs_net),
        obs_mean_bp=float(np.mean(obs_net) * 10000),
        obs_t=perm["obs_t"],
        null_mean_t=perm["null_mean_t"],
        signal_t_excess=perm["signal_t_excess"],
        perm_p_two_sided=perm["perm_p_two_sided"],
        ci_lower_bp=float(boot["ci_lower"] * 10000),
        ci_upper_bp=float(boot["ci_upper"] * 10000),
        prob_positive=boot["prob_positive"],
        n_symbols=len(per_sym_summary),
        n_symbols_measurable=n_sym_measurable,
        n_symbols_ci_pos=n_sym_ci_pos,
        symbol_ci_pos_ratio=(n_sym_ci_pos / n_sym_measurable) if n_sym_measurable else 0.0,
        n_quarters_measurable=n_q_measurable,
        n_quarters_pos_t=n_q_pos_t,
        quarter_pos_t_ratio=(n_q_pos_t / n_q_measurable) if n_q_measurable else 0.0,
        per_sym=per_sym_summary,
        per_quarter=per_quarter_summary,
        three_gate_pass=bool(
            perm["signal_t_excess"] >= 2.0
            and boot["ci_lower"] > 0
            and perm["perm_p_two_sided"] <= 0.10
        ),
        concentration_gate_pass=bool(
            (n_sym_ci_pos / max(n_sym_measurable, 1)) >= 0.30
            and (n_q_pos_t / max(n_q_measurable, 1)) >= 0.50
        ),
    )


def main() -> None:
    log.info("PARADIGM 243 R-1 START — funding skewness bilateral SNT")
    data = per_symbol_data()
    log.info("universe intersection: %d syms → %s", len(data), sorted(data.keys()))
    if len(data) < 5:
        raise RuntimeError("insufficient universe intersection (<5)")

    results: List[Dict] = []
    for T in THRESHOLDS:
        for h in HOLDS_DAYS:
            for quad in ("A_focus", "B_focus", "A_mirror", "B_mirror"):
                r = evaluate_cell(data, quad, T, h)
                results.append(r)
                if r.get("insufficient"):
                    log.info("  %s T=%.1f h=%dd n=%d INSUFFICIENT",
                             quad, T, h, r["n_events"])
                else:
                    log.info(
                        "  %s T=%.1f h=%dd n=%d mean=%+.1fbp t_ex=%+.2f ci_lo=%+.1fbp p=%.3f | conc_sym=%d/%d q_pos=%d/%d",
                        quad, T, h, r["n_events"], r["obs_mean_bp"], r["signal_t_excess"],
                        r["ci_lower_bp"], r["perm_p_two_sided"],
                        r["n_symbols_ci_pos"], r["n_symbols_measurable"],
                        r["n_quarters_pos_t"], r["n_quarters_measurable"],
                    )

    # Best-cell scan (all cells, all quadrants)
    scored = [
        r for r in results
        if not r.get("insufficient") and np.isfinite(r.get("signal_t_excess", np.nan))
    ]
    best_three_gate = [r for r in scored if r["three_gate_pass"]]
    best_full_gate = [r for r in scored if r["three_gate_pass"] and r["concentration_gate_pass"]]

    verdict = {
        "n_cells_total": len(results),
        "n_cells_measurable": len(scored),
        "n_cells_three_gate_pass": len(best_three_gate),
        "n_cells_full_gate_pass": len(best_full_gate),
        "primary_cell_T": PRIMARY_T,
        "primary_cell_h": PRIMARY_HOLD,
    }

    # Sort by signal_t_excess for reporting
    scored_sorted = sorted(scored, key=lambda r: -r.get("signal_t_excess", -1e9))
    top10 = [
        dict(quadrant=r["quadrant"], T=r["T"], h=r["h"], n=r["n_events"],
             mean_bp=r["obs_mean_bp"], t_ex=r["signal_t_excess"],
             ci_lo_bp=r["ci_lower_bp"], perm_p=r["perm_p_two_sided"],
             sym_ci_pos_ratio=r["symbol_ci_pos_ratio"],
             q_pos_t_ratio=r["quarter_pos_t_ratio"],
             three_gate=r["three_gate_pass"], conc_gate=r["concentration_gate_pass"])
        for r in scored_sorted[:10]
    ]

    if best_full_gate:
        verdict["overall"] = "R1_PASS_FULL_GATE"
    elif best_three_gate:
        verdict["overall"] = "R1_PASS_THREE_GATE_CONCENTRATION_FAIL"
    else:
        verdict["overall"] = "R1_FAIL"

    payload = dict(
        paradigm=PARADIGM,
        paradigm_number=243,
        phase="R-1",
        universe=sorted(data.keys()),
        n_universe=len(data),
        fee_round_trip=FEE_ROUND_TRIP,
        thresholds=THRESHOLDS,
        holds_days=HOLDS_DAYS,
        skew_window_funding_periods=SKEW_WINDOW,
        n_perms=N_PERMS,
        n_boot=N_BOOT,
        cells=results,
        top10_by_t_excess=top10,
        verdict=verdict,
    )
    out = OUT_DIR / "r1__metrics.json"
    out.write_text(json.dumps(payload, indent=2, default=float))
    log.info("R-1 verdict=%s wrote %s", verdict["overall"], out)


if __name__ == "__main__":
    main()
