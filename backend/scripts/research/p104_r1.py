"""R-1 PoC: cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h.

Paradigm 104 (path #3 family-distinct from paradigm 103 graveyard 'ed7e9ccb').

Hypothesis
----------
Cross-exchange OI LEVEL differential = (Binance USDS-M perp OI - Bybit linear
perp OI), both normalized by per-exchange 30d median to remove cross-exchange
scale difference (Binance OI is typically 3-10x Bybit). z-score on rolling
30d window on 1h frame. When |z_diff| >= threshold, the venue with higher
relative OI is accumulating leverage faster — we test continuation
(LONG when z_diff>0 → Binance accumulating relative → continuation long,
 SHORT when z_diff<0 → Bybit accumulating relative → continuation short)
and the fade mirrors.

Mechanism distinction from paradigm 103 (fee-floor falsified):
  - OI is a STOCK variable (not flow). Venue arb cannot directly equalize
    OI between exchanges the way it equalizes funding rates.
  - OI differential reflects WHERE traders position, not WHAT rate they pay.
  - Fee dynamics: OI differential is the TRIGGER, not the outcome. The
    16bp round-trip fee compares to forward return magnitude, not to the
    differential itself. This bypasses paradigm 103's fee-floor compression.

5-axis novelty (3/5 NOVEL):
  - data source: NOVEL (cross-exchange OI paired feed; Bybit V5 OI endpoint
    untested in 103 prior paradigms)
  - statistic: known (z on differential)
  - time scale: known (1h frame, 240m hold)
  - universe: NOVEL (dual-exchange cross-sectional OI pairing)
  - mechanism: NOVEL (venue-positioning stock-variable imbalance)

Universe (deep-7, 2024-01-01 to 2026-05-19, ~870d, 1.0 data_window_ratio):
  AVAXUSDT, BCHUSDT, BNBUSDT, DOGEUSDT, LINKUSDT, SOLUSDT, XRPUSDT

R-1 protocol artifacts (paradigm-architect spec + Q3 lessons §6.2 + lesson #34 candidate):
  - Substrate verification (lesson #28)
  - Lesson #34 candidate prescreen — empirical |z_diff| p50/p90/p99
    distribution BEFORE threshold sweep commit (paradigm 103 dogfood)
  - Sample density per quadrant per quarter (lesson #11 prescreen)
  - 4-quadrant Symmetric Negative Test (lesson #19) single batch
  - 3-gate (signal_t_excess + ci_lower + perm_p)
  - Concentration Gate (lesson #16) per-quarter t + per-symbol bootstrap
  - Quadrant pair signature (lesson #8 symmetric LONG bias amendment candidate)
  - Hold sweep diagnostic (60m / 240m / 480m / 1440m) compare to p103 asymmetric drift
  - Cross-paradigm 103 comparison: OI differential vs rate differential strength
  - Lesson #20 narrow-scope 4-cond fallback
  - Lesson #30 data window ratio (=1.0 within aligned window)
  - Lesson #32 universe-baseline-coherent A_focus trap pre-check
  - Lesson #33 magnitude-conditioning trap NOT applicable (signed trigger)
  - Verdict tree (incl. NARROW_SCOPE_LIFE_CHANGING_FAIL paradigm 95/99 dogfood)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p104_r1")

# ------------------------- Config -------------------------
PARADIGM_NAME = "cross_exchange_oi_level_differential_binance_bybit_alt_directional_4h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME / "r1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]
BINANCE_OI_CACHE = ROOT / "runs" / "ohlcv_cache" / "binance_oi"
BYBIT_OI_CACHE = ROOT / "runs" / "ohlcv_cache" / "bybit_oi"

FEE_PER_TRADE = 0.0016  # 16 bp round-trip
HOLD_PRIMARY_MIN = 240
HOLD_SWEEP = [60, 240, 480, 1440]

# z-score on rolling 30d window on 1h frame (=720 bars)
Z_WINDOW_BARS = 720  # 30d * 24h
Z_THRESHOLDS = [1.5, 2.0, 2.5]

# Normalization rolling median window (Lesson #34 — scale-free, paradigm 104 spec)
NORM_WINDOW_BARS = 720  # 30d per-exchange

# Cell-size minimum (Lesson #11)
MIN_PER_CELL = 30
# Three-gate thresholds
SIG_T_EXCESS_PASS = 2.0
PERM_P_PASS = 0.10
CI_LOWER_PASS_BP = 0.0

# Concentration Gate
CONCENT_QUARTER_T_RATIO = 0.5
CONCENT_SYMBOL_CI_POS_RATIO = 0.30
CONCENT_MIN_SYMS_CI_POS = 3

N_PERMS = 1000
BOOTSTRAP_N = 2000

# Reference window for Lesson #30 data window ratio
REF_START = pd.Timestamp("2024-01-01")
REF_END = pd.Timestamp("2026-05-19")


# ------------------------- Data load -------------------------
def load_binance_oi_panel() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        path = BINANCE_OI_CACHE / f"{sym}_1h.joblib"
        if not path.exists():
            log.warning("[%s] binance OI cache missing", sym)
            continue
        df = joblib.load(path).copy()
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
        out[sym] = df
    return out


def load_bybit_oi_panel() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        path = BYBIT_OI_CACHE / f"{sym}_1h.joblib"
        if not path.exists():
            log.warning("[%s] bybit OI cache missing", sym)
            continue
        df = joblib.load(path).copy()
        df["ts"] = pd.to_datetime(df["ts"])
        df = df.sort_values("ts").drop_duplicates(subset=["ts"]).reset_index(drop=True)
        out[sym] = df
    return out


def load_ohlcv_panel() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        df = load_ohlcv_1m_cached(sym)
        if df.empty:
            log.warning("[%s] ohlcv empty", sym)
            continue
        out[sym] = df
    return out


# ------------------------- OI differential build -------------------------
def build_oi_diff_panel(
    bn: Dict[str, pd.DataFrame],
    bb: Dict[str, pd.DataFrame],
) -> Dict[str, pd.DataFrame]:
    """For each symbol, inner-join Binance + Bybit OI on hour timestamp.

    Each OI is normalized per-exchange-per-symbol by 30d rolling median:
        oi_norm_bn = oi_bn / oi_bn.rolling(720h).median()
        oi_norm_bb = oi_bb / oi_bb.rolling(720h).median()
        oi_diff = oi_norm_bn - oi_norm_bb     (centered around 0)
        z_diff = (oi_diff - mean_720h) / std_720h
    """
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        if sym not in bn or sym not in bb:
            continue
        a = bn[sym].rename(columns={"oi": "oi_bn"})[["ts", "oi_bn"]]
        b = bb[sym].rename(columns={"oi": "oi_bb"})[["ts", "oi_bb"]]
        merged = pd.merge(a, b, on="ts", how="inner")
        if merged.empty:
            log.warning("[%s] merge empty", sym)
            continue
        merged = merged.sort_values("ts").reset_index(drop=True)

        # Per-exchange 30d rolling median normalization (scale removal)
        merged["oi_bn_med30d"] = merged["oi_bn"].rolling(NORM_WINDOW_BARS, min_periods=240).median()
        merged["oi_bb_med30d"] = merged["oi_bb"].rolling(NORM_WINDOW_BARS, min_periods=240).median()
        merged["oi_bn_norm"] = merged["oi_bn"] / merged["oi_bn_med30d"]
        merged["oi_bb_norm"] = merged["oi_bb"] / merged["oi_bb_med30d"]
        merged["oi_diff"] = merged["oi_bn_norm"] - merged["oi_bb_norm"]

        # Rolling z-score of differential on 30d window
        merged["oi_diff_z"] = (
            (merged["oi_diff"] - merged["oi_diff"].rolling(Z_WINDOW_BARS, min_periods=240).mean())
            / merged["oi_diff"].rolling(Z_WINDOW_BARS, min_periods=240).std()
        )
        out[sym] = merged
    return out


def compute_forward_returns(
    oi_panel: Dict[str, pd.DataFrame],
    ohlcv: Dict[str, pd.DataFrame],
    hold_min: int,
) -> Dict[str, pd.DataFrame]:
    """Attach forward gross return at oi.ts to oi.ts+hold_min.

    1h frame closes are entry; +hold_min is exit. Use OHLCV 1m close at the
    nearest timestamp (tolerance 5min).
    """
    out: Dict[str, pd.DataFrame] = {}
    for sym, df in oi_panel.items():
        if sym not in ohlcv:
            continue
        ohl = ohlcv[sym]
        if ohl.empty:
            continue
        ohl_close = ohl["close"]
        # Ensure timezone-naive
        if ohl_close.index.tz is not None:
            ohl_close = ohl_close.copy()
            ohl_close.index = ohl_close.index.tz_localize(None)

        entry_ts = pd.DatetimeIndex(df["ts"].values)
        exit_ts = entry_ts + pd.Timedelta(minutes=hold_min)

        entry_close = ohl_close.reindex(entry_ts, method="nearest", tolerance=pd.Timedelta(minutes=5))
        exit_close = ohl_close.reindex(exit_ts, method="nearest", tolerance=pd.Timedelta(minutes=5))

        df_out = df.copy()
        df_out[f"entry_close_{hold_min}"] = entry_close.values
        df_out[f"exit_close_{hold_min}"] = exit_close.values
        with np.errstate(invalid="ignore", divide="ignore"):
            df_out[f"fwd_ret_{hold_min}"] = (exit_close.values / entry_close.values) - 1.0
        out[sym] = df_out
    return out


# ------------------------- Quadrant aggregation -------------------------
def collect_quadrant(
    panels: Dict[str, pd.DataFrame],
    threshold_val: float,
    direction_quadrant: str,
    hold_min: int,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Return (net_returns, gross_returns, df_trades_with_meta).

    Quadrants (single-sided z trigger; A is positive z, B is negative z):
      A_focus  : oi_diff_z > +threshold -> LONG  (Binance accumulating relative -> continuation long)
      A_mirror : oi_diff_z > +threshold -> SHORT (Binance accumulating relative -> fade short)
      B_focus  : oi_diff_z < -threshold -> SHORT (Bybit accumulating relative -> continuation short)
      B_mirror : oi_diff_z < -threshold -> LONG  (Bybit accumulating relative -> fade long)
    """
    nets: List[float] = []
    grosses: List[float] = []
    rows: List[dict] = []

    for sym, df in panels.items():
        up = df["oi_diff_z"] > threshold_val
        dn = df["oi_diff_z"] < -threshold_val

        fwd_col = f"fwd_ret_{hold_min}"
        if fwd_col not in df.columns:
            continue
        valid = df[fwd_col].notna()

        if direction_quadrant == "A_focus":
            mask = up & valid
            sign = +1.0
        elif direction_quadrant == "A_mirror":
            mask = up & valid
            sign = -1.0
        elif direction_quadrant == "B_focus":
            mask = dn & valid
            sign = -1.0
        elif direction_quadrant == "B_mirror":
            mask = dn & valid
            sign = +1.0
        else:
            raise ValueError(f"unknown quadrant {direction_quadrant}")

        sub = df.loc[mask].copy()
        if sub.empty:
            continue
        gross = sign * sub[fwd_col].values
        net = gross - FEE_PER_TRADE
        nets.extend(net.tolist())
        grosses.extend(gross.tolist())
        for i, idx in enumerate(sub.index):
            rows.append({
                "symbol": sym,
                "ts": sub.loc[idx, "ts"],
                "oi_diff_z": sub.loc[idx, "oi_diff_z"],
                "gross": gross[i],
                "net": net[i],
            })

    return np.asarray(nets), np.asarray(grosses), pd.DataFrame(rows)


def build_candidate_pool(panels: Dict[str, pd.DataFrame], hold_min: int) -> np.ndarray:
    """Pool = all (symbol, ts) GROSS returns (no direction-filter, no trigger)."""
    pool: List[float] = []
    fwd_col = f"fwd_ret_{hold_min}"
    for sym, df in panels.items():
        if fwd_col in df.columns:
            v = df[fwd_col].dropna().values
            pool.extend(v.tolist())
    return np.asarray(pool)


def per_symbol_bootstrap(trades_df: pd.DataFrame) -> dict:
    out = {}
    if trades_df.empty:
        return out
    for sym, sub in trades_df.groupby("symbol"):
        if len(sub) < 20:
            out[sym] = {"n": int(len(sub)), "ci_lower_bp": None, "ci_pos": False, "skipped": True}
            continue
        ci = bootstrap_ci(sub["net"].values, n_boot=BOOTSTRAP_N, block_size=1)
        out[sym] = {
            "n": int(len(sub)),
            "mean_bp": float(np.mean(sub["net"].values) * 10000),
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_pos": bool(ci["ci_lower"] > 0),
            "skipped": False,
        }
    return out


def per_quarter_t(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {}
    df = trades_df.copy()
    df["q"] = pd.to_datetime(df["ts"]).dt.to_period("Q").astype(str)
    out = {}
    for q, sub in df.groupby("q"):
        n = len(sub)
        if n < 10:
            out[q] = {"n": int(n), "t": None, "skipped": True}
            continue
        v = sub["net"].values
        sd = v.std(ddof=1)
        t = float(v.mean() / sd * np.sqrt(n)) if sd > 0 else 0.0
        out[q] = {"n": int(n), "mean_bp": float(np.mean(v) * 10000), "t": t,
                  "pos_t": bool(t > 0), "skipped": False}
    return out


# ------------------------- Eval single setting -------------------------
def evaluate_setting(
    panels_with_ret: Dict[str, pd.DataFrame],
    threshold_val: float,
    hold_min: int,
    label: str,
) -> dict:
    pool = build_candidate_pool(panels_with_ret, hold_min)
    result = {
        "label": label,
        "threshold_z": threshold_val,
        "hold_min": hold_min,
        "fee_per_trade": FEE_PER_TRADE,
        "n_pool": int(len(pool)),
        "quadrants": {},
    }
    for quad in ["A_focus", "A_mirror", "B_focus", "B_mirror"]:
        nets, grosses, trades = collect_quadrant(panels_with_ret, threshold_val, quad, hold_min)
        n = int(len(nets))
        if n < 2:
            result["quadrants"][quad] = {
                "n": n, "mean_net_bp": None, "mean_gross_bp": None,
                "sig_t_excess": None, "perm_p_two": None,
                "ci_lower_bp": None, "ci_upper_bp": None,
                "three_gate_pass": False, "skipped": True,
            }
            continue
        perm = fee_aware_perm_test(
            observed_net_returns=nets,
            candidate_pool_returns=pool,
            fee_per_trade=FEE_PER_TRADE,
            n_perms=N_PERMS,
            rng_seed=42,
        )
        ci = bootstrap_ci(nets, n_boot=BOOTSTRAP_N, block_size=1)
        sym_boot = per_symbol_bootstrap(trades)
        q_t = per_quarter_t(trades)

        n_ci_pos = sum(1 for v in sym_boot.values() if v.get("ci_pos") and not v.get("skipped"))
        n_sym_meas = sum(1 for v in sym_boot.values() if not v.get("skipped"))
        n_q_pos = sum(1 for v in q_t.values() if v.get("pos_t") and not v.get("skipped"))
        n_q_meas = sum(1 for v in q_t.values() if not v.get("skipped"))

        sig_t_excess = perm.get("signal_t_excess")
        perm_p = perm.get("perm_p_two_sided")
        ci_lower_bp = ci["ci_lower"] * 10000 if ci["ci_lower"] == ci["ci_lower"] else float("nan")
        ci_upper_bp = ci["ci_upper"] * 10000 if ci["ci_upper"] == ci["ci_upper"] else float("nan")

        three_gate_pass = (
            (sig_t_excess is not None and sig_t_excess == sig_t_excess and sig_t_excess >= SIG_T_EXCESS_PASS)
            and (ci_lower_bp == ci_lower_bp and ci_lower_bp > CI_LOWER_PASS_BP)
            and (perm_p is not None and perm_p == perm_p and perm_p <= PERM_P_PASS)
        )

        concentration_pass = (
            n_q_meas > 0
            and (n_q_pos / n_q_meas) >= CONCENT_QUARTER_T_RATIO
            and n_sym_meas > 0
            and (n_ci_pos / n_sym_meas) >= CONCENT_SYMBOL_CI_POS_RATIO
            and n_ci_pos >= CONCENT_MIN_SYMS_CI_POS
        )

        result["quadrants"][quad] = {
            "n": n,
            "mean_net_bp": float(np.mean(nets) * 10000),
            "mean_gross_bp": float(np.mean(grosses) * 10000),
            "obs_t": perm.get("obs_t"),
            "null_mean_t": perm.get("null_mean_t"),
            "sig_t_excess": sig_t_excess,
            "perm_p_two": perm_p,
            "perm_p_one_above": perm.get("perm_p_one_sided_above"),
            "perm_p_one_below": perm.get("perm_p_one_sided_below"),
            "ci_lower_bp": ci_lower_bp,
            "ci_upper_bp": ci_upper_bp,
            "ci_prob_pos": ci.get("prob_positive"),
            "three_gate_pass": bool(three_gate_pass),
            "concentration": {
                "n_symbols_total": int(n_sym_meas),
                "n_symbols_ci_pos": int(n_ci_pos),
                "symbol_ci_pos_ratio": float(n_ci_pos / n_sym_meas) if n_sym_meas else None,
                "n_quarters_total": int(n_q_meas),
                "n_quarters_pos_t": int(n_q_pos),
                "quarter_pos_t_ratio": float(n_q_pos / n_q_meas) if n_q_meas else None,
                "concentration_pass": bool(concentration_pass),
                "per_symbol": sym_boot,
                "per_quarter": q_t,
            },
            "skipped": False,
        }
    return result


# ------------------------- Main pipeline -------------------------
def main() -> int:
    t_start = time.time()
    log.info("=== R-1 PoC: %s ===", PARADIGM_NAME)
    log.info("Universe (deep-7): %s", UNIVERSE)
    log.info("Fee/trade: %.4f (16bp round-trip)", FEE_PER_TRADE)

    log.info("Loading Binance OI (cache)...")
    bn = load_binance_oi_panel()
    log.info("Loading Bybit OI (cache)...")
    bb = load_bybit_oi_panel()
    log.info("Loading OHLCV 1m (cache)...")
    ohl = load_ohlcv_panel()

    substrate = {}
    for sym in UNIVERSE:
        substrate[sym] = {
            "binance_n": len(bn.get(sym, [])),
            "binance_min": str(bn[sym]["ts"].min()) if sym in bn else None,
            "binance_max": str(bn[sym]["ts"].max()) if sym in bn else None,
            "bybit_n": len(bb.get(sym, [])),
            "bybit_min": str(bb[sym]["ts"].min()) if sym in bb else None,
            "bybit_max": str(bb[sym]["ts"].max()) if sym in bb else None,
            "ohlcv_n": len(ohl.get(sym, [])),
            "ohlcv_min": str(ohl[sym].index.min()) if sym in ohl else None,
            "ohlcv_max": str(ohl[sym].index.max()) if sym in ohl else None,
        }

    log.info("Building OI differential panel (binance_norm - bybit_norm, then z on 30d)...")
    oi_panel = build_oi_diff_panel(bn, bb)
    log.info("Panel built for %d/%d symbols", len(oi_panel), len(UNIVERSE))

    # ------- Lesson #34 candidate: empirical |z_diff| distribution BEFORE threshold sweep -------
    log.info("=== Lesson #34 candidate: empirical z_diff distribution prescreen ===")
    all_z = []
    for sym, df in oi_panel.items():
        z = df["oi_diff_z"].dropna().values
        all_z.append(z)
    all_z = np.concatenate(all_z) if all_z else np.array([])
    abs_z = np.abs(all_z)
    z_dist = {
        "n": int(len(all_z)),
        "median_abs_z": float(np.quantile(abs_z, 0.5)) if len(abs_z) else None,
        "p90_abs_z": float(np.quantile(abs_z, 0.9)) if len(abs_z) else None,
        "p95_abs_z": float(np.quantile(abs_z, 0.95)) if len(abs_z) else None,
        "p99_abs_z": float(np.quantile(abs_z, 0.99)) if len(abs_z) else None,
        "max_abs_z": float(np.max(abs_z)) if len(abs_z) else None,
        "frac_ge_1p5": float((abs_z >= 1.5).mean()) if len(abs_z) else None,
        "frac_ge_2p0": float((abs_z >= 2.0).mean()) if len(abs_z) else None,
        "frac_ge_2p5": float((abs_z >= 2.5).mean()) if len(abs_z) else None,
        "frac_signed_pos": float((all_z > 0).mean()) if len(all_z) else None,
        "frac_signed_neg": float((all_z < 0).mean()) if len(all_z) else None,
    }
    log.info("z_diff distribution: median=%.3f p90=%.3f p95=%.3f p99=%.3f max=%.3f frac|z|>=2.0=%.4f",
             z_dist.get("median_abs_z") or 0, z_dist.get("p90_abs_z") or 0,
             z_dist.get("p95_abs_z") or 0, z_dist.get("p99_abs_z") or 0,
             z_dist.get("max_abs_z") or 0, z_dist.get("frac_ge_2p0") or 0)
    # Verify chosen thresholds have non-zero trigger mass
    if (z_dist.get("frac_ge_2p0") or 0) < 0.005:
        log.warning("Lesson #34 candidate: |z|>=2.0 trigger frac %.4f < 0.5%% — threshold recalibration recommended",
                    z_dist.get("frac_ge_2p0") or 0)

    # ------- Compute forward returns for all hold horizons -------
    log.info("Computing forward returns for holds %s...", HOLD_SWEEP)
    panels_full = {sym: df.copy() for sym, df in oi_panel.items()}
    for h in HOLD_SWEEP:
        for_h = compute_forward_returns(oi_panel, ohl, h)
        for sym in panels_full:
            col_entry = f"entry_close_{h}"
            col_exit = f"exit_close_{h}"
            col_ret = f"fwd_ret_{h}"
            if sym in for_h:
                df_h = for_h[sym]
                for c in (col_entry, col_exit, col_ret):
                    if c in df_h.columns:
                        panels_full[sym][c] = df_h[c].values
                    else:
                        panels_full[sym][c] = np.nan
            else:
                panels_full[sym][col_ret] = np.nan

    # Universe-wide window
    all_ts = pd.concat([df["ts"] for df in panels_full.values()])
    window_min = str(all_ts.min())
    window_max = str(all_ts.max())
    n_pairs_total = sum(len(df) for df in panels_full.values())
    log.info("Window: %s .. %s, total paired rows = %d", window_min, window_max, n_pairs_total)

    # ------- Lesson #11 sample-density prescreen -------
    log.info("=== Lesson #11 sample-density prescreen ===")
    prescreen = {}
    for tv in Z_THRESHOLDS:
        label = f"z_{tv}"
        counts = {}
        for quad in ["A_focus", "B_focus"]:
            nets, _, trades = collect_quadrant(panels_full, tv, quad, HOLD_PRIMARY_MIN)
            counts[quad] = int(len(nets))
            if not trades.empty:
                by_q = trades.assign(q=pd.to_datetime(trades["ts"]).dt.to_period("Q").astype(str))
                per_q = by_q.groupby("q").size().to_dict()
                counts[f"{quad}_per_q"] = {str(k): int(v) for k, v in per_q.items()}
        prescreen[label] = counts
        log.info("[prescreen z=%.1f] A=%d B=%d", tv, counts.get("A_focus", 0), counts.get("B_focus", 0))

    # Pick FOCUS threshold: largest |z| where BOTH A_focus and B_focus per-quarter >= 30
    chosen_z = None
    # walk from highest z down to lowest (prefer narrower band if it satisfies density)
    for tv in sorted(Z_THRESHOLDS, reverse=True):
        label = f"z_{tv}"
        pre = prescreen.get(label, {})
        af_q = pre.get("A_focus_per_q", {})
        bf_q = pre.get("B_focus_per_q", {})
        af_pass_q = sum(1 for v in af_q.values() if v >= MIN_PER_CELL)
        bf_pass_q = sum(1 for v in bf_q.values() if v >= MIN_PER_CELL)
        # Need >=4 quarters with >=30 in each direction (Lesson #11 + Lesson #26 amendment)
        if af_pass_q >= 4 and bf_pass_q >= 4:
            chosen_z = tv
            break

    if chosen_z is None:
        # fallback to smallest z which may still skip cells
        chosen_z = min(Z_THRESHOLDS)
        log.warning("No threshold passes per-quarter density >=30 in both A/B — fallback z=%s", chosen_z)

    log.info("=== Focus threshold chosen: z=%s ===", chosen_z)

    # ------- Threshold sweep (full 4-quadrant) at primary hold -------
    sweep_results = {}
    for tv in Z_THRESHOLDS:
        label = f"z_{tv}_hold{HOLD_PRIMARY_MIN}"
        log.info("Evaluating sweep cell %s ...", label)
        sweep_results[label] = evaluate_setting(panels_full, tv, HOLD_PRIMARY_MIN, label)

    # ------- Hold sweep at chosen focus threshold -------
    hold_sweep = {}
    for h in HOLD_SWEEP:
        label = f"focus_z{chosen_z}_hold{h}"
        log.info("Evaluating hold sweep %s ...", label)
        hold_sweep[label] = evaluate_setting(panels_full, chosen_z, h, label)

    # ------- Verdict computation on FOCUS setting -------
    focus_label = f"z_{chosen_z}_hold{HOLD_PRIMARY_MIN}"
    focus = sweep_results[focus_label]
    quads = focus["quadrants"]

    def _sign_of(v) -> str:
        if v is None or v != v:
            return "NA"
        return "+" if v > 0 else ("-" if v < 0 else "0")

    pair_signature = [
        _sign_of(quads.get("A_focus", {}).get("mean_net_bp")),
        _sign_of(quads.get("A_mirror", {}).get("mean_net_bp")),
        _sign_of(quads.get("B_focus", {}).get("mean_net_bp")),
        _sign_of(quads.get("B_mirror", {}).get("mean_net_bp")),
    ]

    # Lesson #8 amendment candidate: A_focus + B_mirror both positive (general LONG upward bias)
    a_f_v = quads.get("A_focus", {}).get("mean_net_bp")
    b_m_v = quads.get("B_mirror", {}).get("mean_net_bp")
    upward_bias_flag = (
        a_f_v is not None and b_m_v is not None and a_f_v == a_f_v and b_m_v == b_m_v
        and a_f_v > 0 and b_m_v > 0
        and (a_f_v + b_m_v) > 2 * abs(min(0.0, quads.get("A_mirror", {}).get("mean_net_bp") or 0))
    )

    a_focus_pass = bool(quads.get("A_focus", {}).get("three_gate_pass"))
    a_focus_conc_pass = bool(quads.get("A_focus", {}).get("concentration", {}).get("concentration_pass"))
    b_focus_pass = bool(quads.get("B_focus", {}).get("three_gate_pass"))
    b_focus_conc_pass = bool(quads.get("B_focus", {}).get("concentration", {}).get("concentration_pass"))
    a_mirror_pass = bool(quads.get("A_mirror", {}).get("three_gate_pass"))
    b_mirror_pass = bool(quads.get("B_mirror", {}).get("three_gate_pass"))

    # ===== Verdict tree =====
    verdict = None
    verdict_rationale = []

    if not (a_focus_pass or b_focus_pass):
        # Check broad falsification + fee floor pattern
        net_vals = [quads[q].get("mean_net_bp") for q in ["A_focus", "A_mirror", "B_focus", "B_mirror"]]
        gross_focus = [abs(quads[q].get("mean_gross_bp") or 0) for q in ["A_focus", "B_focus"]]
        all_neg = all(v is not None and v == v and v < 0 for v in net_vals)
        focus_under_fee = all(g < FEE_PER_TRADE * 10000 for g in gross_focus)
        if all_neg and focus_under_fee:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            verdict_rationale.append("All 4 quadrants net < 0; focus gross |bp| < 16bp fee floor.")
        elif all_neg:
            verdict = "BROAD_FALSIFIED"
            verdict_rationale.append("All 4 quadrants net < 0; mirrors also fail.")
        else:
            verdict = "BROAD_FALSIFIED"
            verdict_rationale.append("Neither focus quadrant (A or B) passes three-gate.")

    elif (a_focus_pass and a_focus_conc_pass) or (b_focus_pass and b_focus_conc_pass):
        verdict = "PASS_R1"
        if a_focus_pass and a_focus_conc_pass:
            verdict_rationale.append("A_focus three-gate + Concentration PASS.")
        if b_focus_pass and b_focus_conc_pass:
            verdict_rationale.append("B_focus three-gate + Concentration PASS.")

    else:
        verdict = "CONCENTRATED_R1_PASS"
        verdict_rationale.append("Focus three-gate PASS but Concentration FAIL (narrow scope risk).")

    # ------- Life-changing 4-dim (if PASS_R1 or CONCENTRATED_R1_PASS) -------
    life_changing = None
    if verdict in ("PASS_R1", "CONCENTRATED_R1_PASS"):
        focus_quad = "A_focus" if a_focus_pass else "B_focus"
        q = quads[focus_quad]
        n_trades = q["n"]
        win_start = pd.to_datetime(window_min)
        win_end = pd.to_datetime(window_max)
        win_years = (win_end - win_start).total_seconds() / (365.25 * 24 * 3600)
        trades_per_yr = n_trades / max(win_years, 0.01)
        edge_bp = q.get("mean_net_bp") or 0.0
        time_in_trade_min = n_trades * HOLD_PRIMARY_MIN
        total_min = win_years * 365.25 * 24 * 60
        util = time_in_trade_min / total_min if total_min > 0 else 0.0
        nets_q, _, _ = collect_quadrant(panels_full, chosen_z, focus_quad, HOLD_PRIMARY_MIN)
        if len(nets_q) >= 2 and nets_q.std(ddof=1) > 0:
            sharpe = float(nets_q.mean() / nets_q.std(ddof=1) * np.sqrt(trades_per_yr))
        else:
            sharpe = 0.0
        life_changing = {
            "focus_quadrant": focus_quad,
            "trades_per_yr": float(trades_per_yr),
            "edge_bp_per_trade": float(edge_bp),
            "edge_pct_per_trade": float(edge_bp / 100),
            "capital_util": float(util),
            "sharpe_proxy": sharpe,
            "trades_per_yr_pass": bool(trades_per_yr >= 12),
            "edge_pass": bool(edge_bp / 100 >= 2.0),
            "util_pass": bool(util >= 0.30),
            "sharpe_pass": bool(sharpe >= 3.0),
            "all_pass": bool(trades_per_yr >= 12 and (edge_bp / 100) >= 2.0 and util >= 0.30 and sharpe >= 3.0),
        }
        if verdict == "CONCENTRATED_R1_PASS" and not life_changing["all_pass"]:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_rationale.append(
                f"Lesson #20 narrow-scope: three-gate PASS + Concentration FAIL + life-changing 4-dim FAIL "
                f"(trades/yr={trades_per_yr:.1f} edge={edge_bp/100:.2f}%/trade util={util:.2%} sharpe={sharpe:.2f})."
            )

    # ------- Lesson #30 data window ratio -------
    actual_start = pd.to_datetime(window_min)
    actual_end = pd.to_datetime(window_max)
    actual_days = (actual_end - actual_start).days
    ref_days = (REF_END - REF_START).days
    data_window_ratio = actual_days / ref_days if ref_days > 0 else 1.0

    # ------- Lesson #32 universe-baseline -------
    baseline_per_sym = {}
    for sym, df in panels_full.items():
        fwd = df["fwd_ret_240"].dropna()
        if len(fwd) >= 20:
            baseline_per_sym[sym] = float(fwd.mean() * 10000)
        else:
            baseline_per_sym[sym] = None
    vals = [v for v in baseline_per_sym.values() if v is not None]
    baseline_mean_bp = float(np.mean(vals)) if vals else None

    # ------- Cross-paradigm 103 comparison -------
    # paradigm 103 best gross at focus quadrant + 240m hold was ~14bp (from graveyard)
    a_focus_gross = quads.get("A_focus", {}).get("mean_gross_bp")
    b_focus_gross = quads.get("B_focus", {}).get("mean_gross_bp")
    p103_ceiling_bp = 14.0  # reference from paradigm 103 graveyard
    cross_p103 = {
        "p103_focus_gross_ceiling_bp": p103_ceiling_bp,
        "p104_a_focus_gross_bp": a_focus_gross,
        "p104_b_focus_gross_bp": b_focus_gross,
        "p104_max_focus_abs_gross_bp": max(abs(a_focus_gross or 0), abs(b_focus_gross or 0)),
        "oi_diff_stronger_than_p103_rate_diff": bool(
            max(abs(a_focus_gross or 0), abs(b_focus_gross or 0)) > p103_ceiling_bp
        ),
    }

    # ------- Assemble final metrics -------
    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "paradigm_seq": 104,
        "verdict": verdict,
        "verdict_rationale": verdict_rationale,
        "universe": UNIVERSE,
        "n_universe": len(UNIVERSE),
        "fee_per_trade": FEE_PER_TRADE,
        "fee_per_trade_bp": FEE_PER_TRADE * 10000,
        "window": {"min": window_min, "max": window_max, "days": actual_days},
        "data_window_ratio_lesson30": float(data_window_ratio),
        "substrate_lesson28": substrate,
        "z_diff_distribution_lesson34_candidate": z_dist,
        "sample_density_prescreen_lesson11": prescreen,
        "focus_threshold_z": chosen_z,
        "focus_setting_evaluation": focus,
        "all_threshold_sweep_at_primary_hold": sweep_results,
        "hold_sweep_at_focus_threshold": hold_sweep,
        "quadrant_pair_signature_lesson8": pair_signature,
        "lesson8_upward_bias_artifact_flag": bool(upward_bias_flag),
        "lesson32_baseline_check": {
            "baseline_per_sym_mean_bp": baseline_per_sym,
            "baseline_universe_mean_bp": baseline_mean_bp,
        },
        "lesson33_magnitude_conditioning_applicable": False,
        "lesson33_rationale": "Trigger statistic = signed oi_diff_z; outcome = signed fwd_ret. No |trigger|->|outcome| coupling.",
        "cross_paradigm_103_comparison": cross_p103,
        "life_changing_4dim": life_changing,
        "n_perms": N_PERMS,
        "bootstrap_n": BOOTSTRAP_N,
        "novelty_5axis": {
            "data_source": "NOVEL (cross-exchange OI paired feed; Bybit V5 OI endpoint untested in 103 paradigms)",
            "statistic": "known (z on normalized differential)",
            "time_scale": "known (1h frame, 240m hold)",
            "universe": "NOVEL (dual-exchange cross-sectional OI pairing)",
            "mechanism": "NOVEL (venue-positioning stock-variable imbalance)",
            "n_novel": 3,
        },
        "family_distinct_rationale": (
            "5m_microstructure_single_domain_alpha_family advisory caution borderline — different time "
            "scale (1h not 5m), dual-domain (Binance+Bybit not single), simple differential z transform "
            "(not multi-feature k-means as paradigm 83). Lesson #21 axis stacking check PASS — single "
            "composite statistic. funding_single_signal_sub_class Tier 4 not applicable (OI not funding). "
            "funding_oi_joint_squeeze_family (73+79) not applicable (single OI variable not funding×OI joint). "
            "Family-distinct path #3 from paradigm 103 graveyard verdict markdown rationale."
        ),
        "wall_clock_s": round(time.time() - t_start, 1),
    }

    out_metrics = OUT_DIR / "r1__metrics.json"
    with open(out_metrics, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    log.info("Wrote metrics -> %s", out_metrics)
    log.info("=== VERDICT: %s ===", verdict)
    log.info("Rationale: %s", "; ".join(verdict_rationale))
    log.info("Quadrant pair signature: %s", pair_signature)
    log.info("Wall-clock: %.1fs", time.time() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
