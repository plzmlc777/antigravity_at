"""R-1 PoC: cross_exchange_funding_spread_binance_bybit_alt_directional_8h.

Hypothesis
----------
Cross-exchange funding spread = Binance USDS-M perp funding - Bybit linear perp
funding at the same 8h cycle boundary. When |spread_bp| >= threshold, the
venue with higher funding is paying premium for long exposure - we test
continuation (LONG when Binance > Bybit, SHORT when Binance < Bybit) and
the fade mirror (SHORT when Binance > Bybit, LONG when Binance < Bybit).

Family-distinct exception: cross-exchange spread (untested axis) vs single-
exchange funding (Tier 4 retired family: paradigm 73/79/96/97/98/99).

Universe (deep-7, OHLCV+funding from 2024-01-02 to 2026-05-12):
  AVAXUSDT, BCHUSDT, BNBUSDT, DOGEUSDT, LINKUSDT, SOLUSDT, XRPUSDT

R-1 protocol artifacts (paradigm-architect spec + Q3 lessons §6.2):
  - Substrate verification (lesson #28)
  - Sample density per quadrant per quarter (lesson #11 prescreen)
  - 4-quadrant Symmetric Negative Test (lesson #19) single batch
  - 3-gate (signal_t_excess + ci_lower + perm_p)
  - Concentration Gate (lesson #16) per-quarter t + per-symbol bootstrap
  - Quadrant pair signature (lesson #8 symmetric LONG bias amendment candidate)
  - Hold sweep diagnostic (60m / 240m / 480m / 1440m)
  - Lesson #20 narrow-scope 4-cond fallback
  - Lesson #30 data window ratio
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
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cross_exch_funding_r1")

# ------------------------- Config -------------------------
PARADIGM_NAME = "cross_exchange_funding_spread_binance_bybit_alt_directional_8h"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME / "r1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE = ["AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "LINKUSDT", "SOLUSDT", "XRPUSDT"]
BYBIT_CACHE_DIR = ROOT / "runs" / "ohlcv_cache" / "bybit_funding"

FEE_PER_TRADE = 0.0016  # 16 bp round-trip (Mint standard; paradigm-architect spec)
HOLD_PRIMARY_MIN = 240
HOLD_SWEEP = [60, 240, 480, 1440]

# Spread threshold sweep (bp)
SPREAD_BP_THRESHOLDS = [1.0, 2.0, 3.0, 5.0]
# z-score on rolling 90d (270 cycles)
Z_WINDOW_CYCLES = 270
Z_THRESHOLDS = [1.5, 2.0, 2.5]

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


# ------------------------- Data load -------------------------
def load_binance_funding_panel() -> Dict[str, pd.DataFrame]:
    """Load Binance funding from PostgreSQL."""
    db = SessionLocal()
    out: Dict[str, pd.DataFrame] = {}
    try:
        for sym in UNIVERSE:
            rows = db.execute(
                text(
                    "SELECT funding_time, funding_rate FROM binance_funding_rate "
                    "WHERE symbol=:s ORDER BY funding_time"
                ),
                {"s": sym},
            ).fetchall()
            if not rows:
                log.warning("[%s] binance no rows", sym)
                continue
            df = pd.DataFrame(rows, columns=["funding_time", "funding_rate"])
            df["funding_time"] = pd.to_datetime(df["funding_time"]).dt.tz_localize(None) \
                if df["funding_time"].dt.tz is not None else pd.to_datetime(df["funding_time"])
            # Round to nearest hour to align with 8h grid
            df["funding_time"] = df["funding_time"].dt.floor("h")
            df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
            df = df.dropna(subset=["funding_rate"]).drop_duplicates(subset=["funding_time"]).sort_values("funding_time").reset_index(drop=True)
            out[sym] = df
    finally:
        db.close()
    return out


def load_bybit_funding_panel() -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        path = BYBIT_CACHE_DIR / f"{sym}.joblib"
        if not path.exists():
            log.warning("[%s] bybit cache missing", sym)
            continue
        df = joblib.load(path)
        df = df.copy()
        df["funding_time"] = pd.to_datetime(df["funding_time"]).dt.floor("h")
        df = df.sort_values("funding_time").reset_index(drop=True)
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


# ------------------------- Spread + trigger build -------------------------
def build_spread_panel(
    bn: Dict[str, pd.DataFrame],
    bb: Dict[str, pd.DataFrame],
) -> Dict[str, pd.DataFrame]:
    """For each symbol, inner-join on funding_time, compute spread_bp."""
    out: Dict[str, pd.DataFrame] = {}
    for sym in UNIVERSE:
        if sym not in bn or sym not in bb:
            continue
        a = bn[sym].rename(columns={"funding_rate": "bn_rate"})
        b = bb[sym].rename(columns={"funding_rate": "bb_rate"})
        merged = pd.merge(a, b, on="funding_time", how="inner")
        if merged.empty:
            log.warning("[%s] merge empty", sym)
            continue
        # spread = bn - bb (decimal). spread_bp = spread * 10000
        merged["spread_bp"] = (merged["bn_rate"] - merged["bb_rate"]) * 10000.0
        # rolling z-score on spread (90d / 270 cycles)
        merged["spread_bp_z"] = (
            (merged["spread_bp"] - merged["spread_bp"].rolling(Z_WINDOW_CYCLES, min_periods=60).mean())
            / merged["spread_bp"].rolling(Z_WINDOW_CYCLES, min_periods=60).std()
        )
        merged = merged.sort_values("funding_time").reset_index(drop=True)
        out[sym] = merged
    return out


def compute_forward_returns(
    spread: Dict[str, pd.DataFrame],
    ohlcv: Dict[str, pd.DataFrame],
    hold_min: int,
) -> Dict[str, pd.DataFrame]:
    """Attach forward gross return at funding_time+1min to funding_time+hold_min.

    Funding_time is boundary close; entry is +1min after to avoid look-ahead.
    """
    out: Dict[str, pd.DataFrame] = {}
    for sym, df in spread.items():
        if sym not in ohlcv:
            continue
        ohl = ohlcv[sym]
        # Build entry close (at funding_time+1min) and exit close (at funding_time+1min+hold_min)
        funding_times = df["funding_time"].values  # numpy datetime64
        entry_ts = pd.DatetimeIndex(funding_times) + pd.Timedelta(minutes=1)
        exit_ts = entry_ts + pd.Timedelta(minutes=hold_min)

        # Locate close prices via reindex (forward-fill within 5min tolerance)
        ohl_close = ohl["close"]
        entry_close = ohl_close.reindex(entry_ts, method="nearest", tolerance=pd.Timedelta(minutes=5))
        exit_close = ohl_close.reindex(exit_ts, method="nearest", tolerance=pd.Timedelta(minutes=5))

        df_out = df.copy()
        df_out[f"entry_close_{hold_min}"] = entry_close.values
        df_out[f"exit_close_{hold_min}"] = exit_close.values
        df_out[f"fwd_ret_{hold_min}"] = (exit_close.values / entry_close.values) - 1.0
        out[sym] = df_out
    return out


# ------------------------- Quadrant aggregation -------------------------
def collect_quadrant(
    panels: Dict[str, pd.DataFrame],
    threshold_kind: str,  # "bp" or "z"
    threshold_val: float,
    direction_quadrant: str,  # "A_focus" "A_mirror" "B_focus" "B_mirror"
    hold_min: int,
) -> Tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Return (net_returns, gross_returns, df_trades_with_meta).

    Quadrants:
      A_focus  : spread > +threshold -> LONG  (binance > bybit -> continuation long)
      A_mirror : spread > +threshold -> SHORT (binance > bybit -> fade short)
      B_focus  : spread < -threshold -> SHORT (binance < bybit -> continuation short)
      B_mirror : spread < -threshold -> LONG  (binance < bybit -> fade long)
    """
    nets: List[float] = []
    grosses: List[float] = []
    rows: List[dict] = []

    for sym, df in panels.items():
        if threshold_kind == "bp":
            up = df["spread_bp"] > threshold_val
            dn = df["spread_bp"] < -threshold_val
        else:  # z
            up = df["spread_bp_z"] > threshold_val
            dn = df["spread_bp_z"] < -threshold_val

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
                "funding_time": sub.loc[idx, "funding_time"],
                "spread_bp": sub.loc[idx, "spread_bp"],
                "spread_bp_z": sub.loc[idx, "spread_bp_z"],
                "gross": gross[i],
                "net": net[i],
            })

    return np.asarray(nets), np.asarray(grosses), pd.DataFrame(rows)


def build_candidate_pool(
    panels: Dict[str, pd.DataFrame],
    hold_min: int,
) -> np.ndarray:
    """Pool = all (symbol, funding_time) GROSS returns (no direction-filter, no trigger)."""
    pool: List[float] = []
    fwd_col = f"fwd_ret_{hold_min}"
    for sym, df in panels.items():
        if fwd_col in df.columns:
            v = df[fwd_col].dropna().values
            pool.extend(v.tolist())
    return np.asarray(pool)


def per_symbol_bootstrap(trades_df: pd.DataFrame) -> dict:
    """For each symbol with >=20 trades, compute bootstrap CI lower."""
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
    """Per-calendar-quarter t-stat on net returns."""
    if trades_df.empty:
        return {}
    df = trades_df.copy()
    df["q"] = pd.to_datetime(df["funding_time"]).dt.to_period("Q").astype(str)
    out = {}
    for q, sub in df.groupby("q"):
        n = len(sub)
        if n < 10:
            out[q] = {"n": int(n), "t": None, "skipped": True}
            continue
        v = sub["net"].values
        sd = v.std(ddof=1)
        t = float(v.mean() / sd * np.sqrt(n)) if sd > 0 else 0.0
        out[q] = {"n": int(n), "mean_bp": float(np.mean(v) * 10000), "t": t, "pos_t": bool(t > 0), "skipped": False}
    return out


# ------------------------- Eval single setting (one threshold, one hold) -------------------------
def evaluate_setting(
    panels_with_ret: Dict[str, pd.DataFrame],
    threshold_kind: str,
    threshold_val: float,
    hold_min: int,
    label: str,
) -> dict:
    """Run full 4-quadrant evaluation for one threshold × hold setting."""
    pool = build_candidate_pool(panels_with_ret, hold_min)
    result = {
        "label": label,
        "threshold_kind": threshold_kind,
        "threshold_val": threshold_val,
        "hold_min": hold_min,
        "fee_per_trade": FEE_PER_TRADE,
        "n_pool": int(len(pool)),
        "quadrants": {},
    }
    for quad in ["A_focus", "A_mirror", "B_focus", "B_mirror"]:
        nets, grosses, trades = collect_quadrant(panels_with_ret, threshold_kind, threshold_val, quad, hold_min)
        n = int(len(nets))
        if n < 2:
            result["quadrants"][quad] = {
                "n": n,
                "mean_net_bp": None,
                "mean_gross_bp": None,
                "sig_t_excess": None,
                "perm_p_two": None,
                "ci_lower_bp": None,
                "ci_upper_bp": None,
                "three_gate_pass": False,
                "skipped": True,
            }
            continue
        # fee-aware perm
        perm = fee_aware_perm_test(
            observed_net_returns=nets,
            candidate_pool_returns=pool,
            fee_per_trade=FEE_PER_TRADE,
            n_perms=N_PERMS,
            rng_seed=42,
        )
        ci = bootstrap_ci(nets, n_boot=BOOTSTRAP_N, block_size=1)
        # Per-symbol bootstrap
        sym_boot = per_symbol_bootstrap(trades)
        # Per-quarter t
        q_t = per_quarter_t(trades)

        n_ci_pos = sum(1 for v in sym_boot.values() if v.get("ci_pos") and not v.get("skipped"))
        n_sym_meas = sum(1 for v in sym_boot.values() if not v.get("skipped"))
        n_q_pos = sum(1 for v in q_t.values() if v.get("pos_t") and not v.get("skipped"))
        n_q_meas = sum(1 for v in q_t.values() if not v.get("skipped"))

        sig_t_excess = perm.get("signal_t_excess")
        # For LONG/momentum quadrants (A_focus, B_mirror, etc) use one_sided_above
        # but our "continuation" hypothesis is direction-agnostic; we use two-sided perm_p
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

    # --- Load substrate ---
    log.info("Loading Binance funding (DB)...")
    bn = load_binance_funding_panel()
    log.info("Loading Bybit funding (cache)...")
    bb = load_bybit_funding_panel()
    log.info("Loading OHLCV (cache)...")
    ohl = load_ohlcv_panel()

    substrate = {}
    for sym in UNIVERSE:
        substrate[sym] = {
            "binance_n": len(bn.get(sym, [])),
            "binance_min": str(bn[sym]["funding_time"].min()) if sym in bn else None,
            "binance_max": str(bn[sym]["funding_time"].max()) if sym in bn else None,
            "bybit_n": len(bb.get(sym, [])),
            "bybit_min": str(bb[sym]["funding_time"].min()) if sym in bb else None,
            "bybit_max": str(bb[sym]["funding_time"].max()) if sym in bb else None,
            "ohlcv_n": len(ohl.get(sym, [])),
            "ohlcv_min": str(ohl[sym].index.min()) if sym in ohl else None,
            "ohlcv_max": str(ohl[sym].index.max()) if sym in ohl else None,
        }

    # --- Build spread panel ---
    log.info("Building spread panel (binance - bybit)...")
    spread = build_spread_panel(bn, bb)

    # --- Compute forward returns for all hold horizons ---
    log.info("Computing forward returns for holds %s...", HOLD_SWEEP)
    panels_full = {sym: df.copy() for sym, df in spread.items()}
    for h in HOLD_SWEEP:
        for_h = compute_forward_returns(spread, ohl, h)
        for sym in panels_full:
            col_entry = f"entry_close_{h}"
            col_exit = f"exit_close_{h}"
            col_ret = f"fwd_ret_{h}"
            if sym in for_h:
                df_h = for_h[sym]
                # merge only the new hold-specific columns (do not overwrite df)
                for c in (col_entry, col_exit, col_ret):
                    if c in df_h.columns:
                        panels_full[sym][c] = df_h[c].values
                    else:
                        panels_full[sym][c] = np.nan
            else:
                panels_full[sym][col_ret] = np.nan

    # Universe-wide window
    all_funding_times = pd.concat([df["funding_time"] for df in panels_full.values()])
    window_min = str(all_funding_times.min())
    window_max = str(all_funding_times.max())
    n_pairs_total = sum(len(df) for df in panels_full.values())

    log.info("Window: %s .. %s, total paired rows = %d", window_min, window_max, n_pairs_total)

    # --- Lesson #11 sample-density prescreen ---
    log.info("=== Lesson #11 sample-density prescreen ===")
    prescreen = {}
    for tk, tv_list in [("bp", SPREAD_BP_THRESHOLDS), ("z", Z_THRESHOLDS)]:
        for tv in tv_list:
            label = f"{tk}_{tv}"
            counts = {}
            for quad in ["A_focus", "B_focus"]:
                # use 240m for prescreen
                nets, _, trades = collect_quadrant(panels_full, tk, tv, quad, HOLD_PRIMARY_MIN)
                counts[quad] = int(len(nets))
                if not trades.empty:
                    by_q = trades.assign(q=pd.to_datetime(trades["funding_time"]).dt.to_period("Q").astype(str))
                    per_q = by_q.groupby("q").size().to_dict()
                    counts[f"{quad}_per_q"] = {str(k): int(v) for k, v in per_q.items()}
            prescreen[label] = counts
            log.info("[prescreen %s=%s] A=%d B=%d", tk, tv, counts.get("A_focus", 0), counts.get("B_focus", 0))

    # Pick FOCUS threshold: smallest |bp| that gives BOTH A_focus and B_focus per-cell (quarter) >=30
    chosen_kind, chosen_val = None, None
    for tk, tv_list in [("bp", SPREAD_BP_THRESHOLDS), ("z", Z_THRESHOLDS)]:
        for tv in tv_list:
            label = f"{tk}_{tv}"
            pre = prescreen.get(label, {})
            af_q = pre.get("A_focus_per_q", {})
            bf_q = pre.get("B_focus_per_q", {})
            # require >=4 quarters with >=30 each direction
            af_pass_q = sum(1 for v in af_q.values() if v >= MIN_PER_CELL)
            bf_pass_q = sum(1 for v in bf_q.values() if v >= MIN_PER_CELL)
            if af_pass_q >= 4 and bf_pass_q >= 4:
                chosen_kind, chosen_val = tk, tv
                break
        if chosen_kind:
            break

    if chosen_kind is None:
        # fallback: pick smallest threshold (bp=30)
        chosen_kind, chosen_val = "bp", 30
        log.warning("No threshold passes per-quarter density >=30 in both A/B — fallback %s=%s", chosen_kind, chosen_val)

    log.info("=== Focus threshold chosen: %s=%s ===", chosen_kind, chosen_val)

    # --- Threshold sweep (full 4-quadrant) at primary hold ---
    sweep_results = {}
    for tk, tv_list in [("bp", SPREAD_BP_THRESHOLDS), ("z", Z_THRESHOLDS)]:
        for tv in tv_list:
            label = f"{tk}_{tv}_hold{HOLD_PRIMARY_MIN}"
            log.info("Evaluating sweep cell %s ...", label)
            sweep_results[label] = evaluate_setting(panels_full, tk, tv, HOLD_PRIMARY_MIN, label)

    # --- Hold sweep at chosen focus threshold ---
    hold_sweep = {}
    for h in HOLD_SWEEP:
        label = f"focus_{chosen_kind}_{chosen_val}_hold{h}"
        log.info("Evaluating hold sweep %s ...", label)
        hold_sweep[label] = evaluate_setting(panels_full, chosen_kind, chosen_val, h, label)

    # --- Verdict computation on FOCUS setting ---
    focus_label = f"{chosen_kind}_{chosen_val}_hold{HOLD_PRIMARY_MIN}"
    focus = sweep_results[focus_label]
    quads = focus["quadrants"]

    # Quadrant pair signature [A_focus_sign, A_mirror_sign, B_focus_sign, B_mirror_sign]
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

    # Lesson #8 amendment candidate flag: A_focus + B_mirror both positive (general upward bias)
    upward_bias_flag = (
        pair_signature[0] == "+" and pair_signature[3] == "+"
        and pair_signature[1] == "-" and pair_signature[2] == "-"
    )

    a_focus_pass = bool(quads.get("A_focus", {}).get("three_gate_pass"))
    a_focus_conc_pass = bool(quads.get("A_focus", {}).get("concentration", {}).get("concentration_pass"))
    b_focus_pass = bool(quads.get("B_focus", {}).get("three_gate_pass"))
    b_focus_conc_pass = bool(quads.get("B_focus", {}).get("concentration", {}).get("concentration_pass"))
    a_mirror_pass = bool(quads.get("A_mirror", {}).get("three_gate_pass"))
    b_mirror_pass = bool(quads.get("B_mirror", {}).get("three_gate_pass"))

    # Verdict tree
    verdict = None
    verdict_rationale = []

    # Both focus quadrants fail three-gate
    if not (a_focus_pass or b_focus_pass):
        # Check if all 4 quadrants have negative mean (broad-falsified)
        all_neg = all(
            (quads[q].get("mean_net_bp") is not None and quads[q].get("mean_net_bp") < 0)
            for q in ["A_focus", "A_mirror", "B_focus", "B_mirror"]
        )
        # Check if fee floor is dominant (gross >= 16bp but net < 0)
        gross_under_fee = all(
            (quads[q].get("mean_gross_bp") is not None and abs(quads[q].get("mean_gross_bp")) < FEE_PER_TRADE * 10000)
            for q in ["A_focus", "B_focus"]
        )
        if all_neg and gross_under_fee:
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
        # three-gate PASS but Concentration FAIL → Lesson #20 narrow-scope check + life-changing 4-dim
        verdict = "CONCENTRATED_R1_PASS"
        verdict_rationale.append("Focus three-gate PASS but Concentration FAIL (narrow scope risk).")

    # Build life-changing 4-dim only if PASS_R1 or CONCENTRATED_R1_PASS
    life_changing = None
    if verdict in ("PASS_R1", "CONCENTRATED_R1_PASS"):
        # use whichever focus quad passed
        focus_quad = "A_focus" if a_focus_pass else "B_focus"
        q = quads[focus_quad]
        n_trades = q["n"]
        # window in years
        win_start = pd.to_datetime(window_min)
        win_end = pd.to_datetime(window_max)
        win_years = (win_end - win_start).total_seconds() / (365.25 * 24 * 3600)
        trades_per_yr = n_trades / max(win_years, 0.01)
        edge_bp = q.get("mean_net_bp") or 0.0
        # capital util: fraction of time in trade
        time_in_trade_min = n_trades * HOLD_PRIMARY_MIN
        total_min = win_years * 365.25 * 24 * 60
        util = time_in_trade_min / total_min if total_min > 0 else 0.0
        # rough sharpe from per-trade
        # net std needs raw nets — recover from quadrant
        nets_q, _, _ = collect_quadrant(panels_full, chosen_kind, chosen_val, focus_quad, HOLD_PRIMARY_MIN)
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
            "edge_pass": bool(edge_bp / 100 >= 2.0),  # >= +2%/trade
            "util_pass": bool(util >= 0.30),
            "sharpe_pass": bool(sharpe >= 3.0),
            "all_pass": bool(trades_per_yr >= 12 and (edge_bp / 100) >= 2.0 and util >= 0.30 and sharpe >= 3.0),
        }
        # If CONCENTRATED + life-changing FAIL → NARROW_SCOPE_LIFE_CHANGING_FAIL
        if verdict == "CONCENTRATED_R1_PASS" and not life_changing["all_pass"]:
            # also need Lesson #20 4-cond ALL PASS check (focus three-gate + ALL pass at full + sweep mono)
            # We approximate: 4-cond = three-gate + concentration + life-changing + symmetric (mirror negative)
            # If life-changing FAIL → narrow scope fail
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_rationale.append(
                f"Lesson #20 narrow-scope: three-gate PASS + Concentration FAIL + life-changing 4-dim FAIL "
                f"(trades/yr={trades_per_yr:.1f} edge={edge_bp/100:.2f}%/trade util={util:.2%} sharpe={sharpe:.2f})."
            )

    # --- Lesson #30 data window ratio ---
    # Reference window: Binance funding earliest 2023-11-15 → today 2026-05-19 = 916 days
    ref_start = pd.Timestamp("2023-11-15")
    ref_end = pd.Timestamp("2026-05-19")
    ref_days = (ref_end - ref_start).days
    actual_start = pd.to_datetime(window_min)
    actual_end = pd.to_datetime(window_max)
    actual_days = (actual_end - actual_start).days
    data_window_ratio = actual_days / ref_days if ref_days > 0 else 1.0

    # --- Lesson #32 universe-baseline-coherent A_focus pre-check ---
    # Baseline = mean fwd_ret_240m over ALL paired rows (no trigger) per symbol
    baseline_per_sym = {}
    for sym, df in panels_full.items():
        fwd = df["fwd_ret_240"].dropna()
        if len(fwd) >= 20:
            baseline_per_sym[sym] = float(fwd.mean() * 10000)
        else:
            baseline_per_sym[sym] = None
    baseline_mean_bp = float(np.mean([v for v in baseline_per_sym.values() if v is not None]))

    # ============= Assemble final metrics ============
    metrics = {
        "paradigm_name": PARADIGM_NAME,
        "verdict": verdict,
        "verdict_rationale": verdict_rationale,
        "universe": UNIVERSE,
        "n_universe": len(UNIVERSE),
        "fee_per_trade": FEE_PER_TRADE,
        "fee_per_trade_bp": FEE_PER_TRADE * 10000,
        "window": {"min": window_min, "max": window_max, "days": actual_days},
        "data_window_ratio_lesson30": float(data_window_ratio),
        "substrate_lesson28": substrate,
        "sample_density_prescreen_lesson11": prescreen,
        "focus_threshold": {"kind": chosen_kind, "val": chosen_val},
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
        "lesson33_rationale": "Trigger statistic = signed spread_bp; outcome = signed fwd_ret. No |trigger|->|outcome| coupling.",
        "life_changing_4dim": life_changing,
        "n_perms": N_PERMS,
        "bootstrap_n": BOOTSTRAP_N,
        "novelty_5axis": {
            "data_source": "NOVEL (cross-exchange paired feed)",
            "statistic": "known (spread + rolling z)",
            "time_scale": "known (8h funding cycle)",
            "universe": "NOVEL (dual-exchange cross-sectional pairing)",
            "mechanism": "NOVEL (exchange arbitrage / venue-positioning imbalance)",
            "n_novel": 3,
        },
        "family_distinct_rationale": "funding_single_signal_sub_class Tier 4 (paradigm 73/79/96/97/98/99) — explicit exception: cross-exchange spread is a NEW axis per memory snapshot §3 family retire row.",
        "wall_clock_s": round(time.time() - t_start, 1),
    }

    out_metrics = OUT_DIR / "r1__metrics.json"
    with open(out_metrics, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    log.info("Wrote metrics → %s", out_metrics)
    log.info("=== VERDICT: %s ===", verdict)
    log.info("Rationale: %s", "; ".join(verdict_rationale))
    log.info("Quadrant pair signature: %s", pair_signature)
    log.info("Wall-clock: %.1fs", time.time() - t_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
