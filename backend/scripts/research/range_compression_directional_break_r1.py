"""R-1 PoC — paradigm 78: range_compression_directional_break_alt_30m_240m

Mechanism (path tortuosity = novel geometric DNA dimension)
-----------------------------------------------------------
For each alt, on rolling 24-bar (= 12-hour) windows of 30m bars:
1. `path_length_w = sum(|high_i - low_i|)` over the window (raw intra-bar excursion)
2. `net_move_w   = |close_window_end - close_window_start|`
3. `tortuosity_w = path_length_w / max(net_move_w, eps_floor)`
   eps_floor = 0.10 * median(|H-L|) over the SAME window — prevents div-by-zero
   without dominating in low-vol regimes.
4. `tortuosity_z_w = (tortuosity_w - rolling_30d_mean) / rolling_30d_std`
   30-day = 30 * 48 = 1440 bars rolling baseline.
5. **Compression trigger**: tortuosity_z_w >= +2.5 (top-decile path-heavy / coiled)
6. **Break trigger**: in next 30m bar, |return_30m| >= 2.0 * rolling_24bar_realized_vol
7. **Entry**: close of break bar, direction = sign(break_bar_return)
8. **Hold**: 240m (8 * 30m bars) fixed, exit at 240m close

DNA novelty vs existing graveyards
----------------------------------
- NOT cross-asset corr (74-77 retired family)
- NOT vol regime conditioner (paradigm 69 substantive)
- NOT skewness (65-66 graveyard)
- NOT taker family (23/60/72 retired)
- NOT premium/funding domain (saturated)
- NOT OI velocity (71 antipattern)
- Path tortuosity (geometric metric: intra-bar excursion / net move) is a
  brand new dimension. Combines coil (compression) + ignition (break) signature.

R-1 PASS gate (focus z>=+2.5 × hold=240m)
------------------------------------------
- aggregate signal_t_excess >= 2.0
- aggregate ci_lower > 0
- aggregate perm_p_two_sided <= 0.10
- per-alt diversity >= 7/13 alts directionally consistent (positive net_bp)
- Lesson #16 concentration: quarter_pos_t_ratio >= 0.5 AND
  symbol_ci_pos_ratio >= 0.30 AND n_symbols_ci_pos >= 3

Sign-conditional cells (Lesson #3, #8)
--------------------------------------
Also split UP-break (direction=+1, LONG) vs DOWN-break (direction=-1, SHORT)
cells separately. If aggregated direction-following PASSES but the two cells
have grossly different magnitudes (e.g., one strongly positive, one near zero
or negative), the paradigm becomes a candidate for mirror antipattern split
into two sub-paradigms.

Sample density prescreen (Lesson #11)
--------------------------------------
13 alts × ~870 days × 48 30m bars/day = ~543k bars total
Compression rate: top-decile z>=+2.5 ≈ 0.5-1% → ~3-5k events
Break rate (next-bar |ret|>=2*vol): ~10-20% → ~500-1000 total
Per-alt: ~38-77 events — above 30/cell floor.

Fee floor prescreen
-------------------
Mechanism predicts 50-100bp gross continuation 240m — well above 16bp fee floor.

11 lessons explicit avoidance
-----------------------------
- #1 _perm_utils.fee_aware_perm_test + bootstrap_ci (null_mean_t emitted)
- #2 Three-gate strict
- #3 Sign-conditional H5 sub-split (UP vs DOWN break)
- #5 OHLCV joblib cache
- #6 Mint host explicit + BTC 1m count verify (1,241,280)
- #8 Mirror antipattern check (UP-LONG vs DOWN-SHORT sub-cells)
- #10 Pure OHLCV — no taker family
- #11 Sample-density prescreen above
- #15 Non-focus PASS — N/A (single z=+2.5 focus, hold sweep included)
- #16 Concentration diagnostics auto-emit per-quarter + per-symbol bootstrap

Output
------
backend/runs/research_track/range_compression_directional_break_alt_30m_240m/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import (  # noqa: E402
    bootstrap_ci,
    fee_aware_perm_test,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p78_r1")

PARADIGM_NAME = "range_compression_directional_break_alt_30m_240m"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM_NAME
OUT_PATH = OUT_DIR / "r1__metrics.json"

# 13 alts (BTC excluded — BTC is regime context only)
ALT_SYMS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]

# 30m bars
BAR_MINUTES = 30
COMPRESSION_WINDOW_BARS = 24            # 12h = 24 * 30m
ZSCORE_LOOKBACK_BARS = 30 * 48          # 30d = 1440 (48 30m bars/day)
REALIZED_VOL_WINDOW_BARS = 24           # 12h realized vol for break threshold

# Focus thresholds
FOCUS_TORTUOSITY_Z = 2.5
FOCUS_BREAK_K = 2.0                      # |ret_30m| >= K * rolling_24bar_vol
FOCUS_HOLD_MIN = 240

# Hold sweep at focus (z=+2.5, K=2.0)
HOLD_SWEEP_MIN = [60, 120, 240, 480]

# Trigger spacing — min gap = focus hold to avoid overlapping trades
TRIGGER_MIN_GAP_BARS = FOCUS_HOLD_MIN // BAR_MINUTES  # 8 bars

FEE_PER_TRADE = 0.0008  # 8 bp one-way = 16 bp round-trip (lesson Q3 fee floor)
DIVERSITY_MIN_POSITIVE_ALTS = 7         # 13 alts

# Lesson #16 concentration gates
CONCENTRATION_QUARTER_POS_T_MIN = 0.5
CONCENTRATION_SYMBOL_CI_POS_RATIO_MIN = 0.30
CONCENTRATION_SYMBOL_CI_POS_FLOOR = 3


def resample_to_30m(df_1m: pd.DataFrame) -> pd.DataFrame:
    """1m OHLCV → 30m OHLCV (standard agg)."""
    out = pd.DataFrame({
        "open": df_1m["open"].resample("30min").first(),
        "high": df_1m["high"].resample("30min").max(),
        "low": df_1m["low"].resample("30min").min(),
        "close": df_1m["close"].resample("30min").last(),
        "volume": df_1m["volume"].resample("30min").sum(),
    }).dropna(subset=["open", "high", "low", "close"])
    return out


def compute_tortuosity_z(df_30m: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling tortuosity and its 30d z-score per alt.

    Adds columns:
      - bar_hl_abs: |high - low| each bar (raw intra-bar excursion)
      - path_length: rolling 24-bar sum of bar_hl_abs
      - net_move: |close_t - close_(t-24)|
      - eps_floor: 0.10 * rolling 24-bar median bar_hl_abs (prevents div-by-zero)
      - tortuosity: path_length / max(net_move, eps_floor)
      - tortuosity_z: 30d z-score of tortuosity
      - ret_30m: log return of close
      - rv_24bar: 24-bar rolling std of ret_30m (the break vol scale)
    """
    w = COMPRESSION_WINDOW_BARS
    df = df_30m.copy()
    df["bar_hl_abs"] = (df["high"] - df["low"]).abs()
    df["path_length"] = df["bar_hl_abs"].rolling(w).sum()
    df["net_move"] = (df["close"] - df["close"].shift(w)).abs()
    df["eps_floor"] = 0.10 * df["bar_hl_abs"].rolling(w).median()
    denom = df[["net_move", "eps_floor"]].max(axis=1)
    df["tortuosity"] = df["path_length"] / denom
    df["tortuosity_z"] = (
        (df["tortuosity"] - df["tortuosity"].rolling(ZSCORE_LOOKBACK_BARS).mean())
        / df["tortuosity"].rolling(ZSCORE_LOOKBACK_BARS).std()
    )
    df["ret_30m"] = np.log(df["close"] / df["close"].shift(1))
    df["rv_24bar"] = df["ret_30m"].rolling(REALIZED_VOL_WINDOW_BARS).std()
    return df


def find_triggers(
    df_feat: pd.DataFrame,
    tortuosity_z_thresh: float,
    break_k: float,
) -> Tuple[List[int], List[float]]:
    """Two-stage trigger:
    1. Compression bar at position p: tortuosity_z[p] >= tortuosity_z_thresh
    2. Break bar at position p+1: |ret_30m[p+1]| >= break_k * rv_24bar[p]

    Returns:
      entry_positions  — list of break-bar positions p+1 (entry at break close)
      directions       — sign(ret_30m at break bar): +1 (LONG) or -1 (SHORT)

    Enforces TRIGGER_MIN_GAP_BARS between consecutive entries (no overlap with
    focus 240m hold).
    """
    z = df_feat["tortuosity_z"].values
    ret = df_feat["ret_30m"].values
    rv = df_feat["rv_24bar"].values

    n = len(df_feat)
    entry_positions: List[int] = []
    directions: List[float] = []
    last_entry = -10**9
    for p in range(n - 1):
        if not np.isfinite(z[p]) or z[p] < tortuosity_z_thresh:
            continue
        b = p + 1
        if not np.isfinite(ret[b]) or not np.isfinite(rv[p]) or rv[p] <= 0:
            continue
        if abs(ret[b]) < break_k * rv[p]:
            continue
        if b - last_entry < TRIGGER_MIN_GAP_BARS:
            continue
        entry_positions.append(int(b))
        directions.append(float(np.sign(ret[b])))
        last_entry = b
    return entry_positions, directions


def compute_forward_returns(
    df_feat: pd.DataFrame,
    entry_positions: List[int],
    directions: List[float],
    hold_bars: int,
) -> Tuple[pd.Series, np.ndarray, np.ndarray]:
    """For each entry b, compute log return from close[b] to close[b+hold_bars],
    multiplied by direction. Returns:
      - net_series indexed by entry timestamp
      - direction_array (signed +1 / -1)
      - gross_return_array (direction * raw log return)
    """
    close = df_feat["close"].values
    n = len(df_feat)
    out_idx: List[pd.Timestamp] = []
    out_net: List[float] = []
    out_dir: List[float] = []
    out_gross: List[float] = []
    for b, d in zip(entry_positions, directions):
        if b + hold_bars >= n:
            continue
        c0 = close[b]
        cT = close[b + hold_bars]
        if c0 <= 0 or cT <= 0:
            continue
        gross = d * float(np.log(cT / c0))
        net = gross - FEE_PER_TRADE
        out_idx.append(df_feat.index[b])
        out_net.append(net)
        out_dir.append(d)
        out_gross.append(gross)
    return (
        pd.Series(out_net, index=out_idx, name=f"net_{hold_bars * BAR_MINUTES}m"),
        np.array(out_dir),
        np.array(out_gross),
    )


def build_candidate_pool(
    df_feat: pd.DataFrame,
    hold_bars: int,
    n_target: int = 30000,
) -> np.ndarray:
    """Random non-overlapping unsigned hold-window log returns (population pool).

    Since direction in the observed trades comes from break-bar sign, the pool
    must include BOTH +/- directions. We approximate by sampling unsigned
    returns and then signing them randomly (50/50). This produces a fair
    fee-aware null whose mean approaches 0 - fee (matches the observed
    direction-randomization counterfactual).
    """
    close = df_feat["close"].values
    n = len(df_feat)
    starts = np.arange(0, n - hold_bars, hold_bars)
    if len(starts) > n_target:
        rng = np.random.default_rng(42)
        starts = np.sort(rng.choice(starts, size=n_target, replace=False))
    raw = np.log(close[starts + hold_bars] / close[starts])
    raw = raw[np.isfinite(raw)]
    rng = np.random.default_rng(99)
    signs = rng.choice([-1.0, 1.0], size=len(raw))
    return raw * signs


def evaluate_one_sym(
    sym: str,
    df_30m: pd.DataFrame,
    tortuosity_z_thresh: float,
    break_k: float,
    hold_bars: int,
) -> Dict:
    """End-to-end per-symbol evaluation. Returns diag dict + per-trade arrays."""
    df_feat = compute_tortuosity_z(df_30m)
    entries, dirs = find_triggers(df_feat, tortuosity_z_thresh, break_k)
    if not entries:
        return {
            "n_triggers": 0,
            "skip": "no triggers found",
            "net_series": pd.Series(dtype=float),
            "direction_array": np.array([]),
            "gross_array": np.array([]),
            "pool": np.array([]),
        }
    net_series, dir_arr, gross_arr = compute_forward_returns(df_feat, entries, dirs, hold_bars)
    pool = build_candidate_pool(df_feat, hold_bars)
    diag = {
        "n_triggers": int(len(entries)),
        "n_with_forward": int(len(net_series)),
        "n_up_break": int((dir_arr > 0).sum()),
        "n_down_break": int((dir_arr < 0).sum()),
        "mean_gross_bp": float(gross_arr.mean() * 10000) if len(gross_arr) > 0 else 0.0,
        "mean_net_bp": float(net_series.values.mean() * 10000) if len(net_series) > 0 else 0.0,
        "n_pool": int(len(pool)),
    }
    if len(net_series) > 1 and net_series.std(ddof=1) > 0:
        diag["t_stat"] = float(
            net_series.mean() / net_series.std(ddof=1) * np.sqrt(len(net_series))
        )
    else:
        diag["t_stat"] = 0.0
    return {
        **diag,
        "net_series": net_series,
        "direction_array": dir_arr,
        "gross_array": gross_arr,
        "pool": pool,
        "df_feat": df_feat,
    }


def compute_concentration(
    obs_df: pd.DataFrame,
) -> Dict:
    """Lesson #16: per-quarter t-stat + per-symbol bootstrap CI.

    obs_df columns: ts (datetime), symbol (str), net_return (float),
                    direction (float)
    """
    if obs_df.empty:
        return {
            "per_quarter_t_stats": [],
            "n_quarters_measurable": 0,
            "n_quarters_pos_t": 0,
            "quarter_pos_t_ratio": float("nan"),
            "per_symbol_bootstrap": [],
            "n_symbols_measurable": 0,
            "n_symbols_ci_pos": 0,
            "symbol_ci_pos_ratio": float("nan"),
        }

    df = obs_df.copy()
    df["quarter"] = pd.to_datetime(df["ts"]).dt.to_period("Q").astype(str)

    def _t(s: pd.Series) -> float:
        if len(s) < 3:
            return float("nan")
        sd = s.std(ddof=1)
        if not np.isfinite(sd) or sd == 0:
            return float("nan")
        return float(s.mean() / sd * np.sqrt(len(s)))

    per_q = df.groupby("quarter").agg(
        n_trades=("net_return", "size"),
        mean_bp=("net_return", lambda s: float(s.mean() * 10000)),
        t_stat=("net_return", _t),
    ).reset_index()
    per_q_records = per_q.to_dict(orient="records")
    n_q_measurable = int((per_q["n_trades"] >= 10).sum())
    n_q_pos_t = int(((per_q["t_stat"] > 0) & (per_q["n_trades"] >= 10)).sum())

    per_sym_records = []
    for sym, sub in df.groupby("symbol"):
        if len(sub) < 10:
            per_sym_records.append({
                "symbol": sym, "n_trades": int(len(sub)), "skip": "n<10",
            })
            continue
        ci = bootstrap_ci(sub["net_return"].values, n_boot=2000, block_size=1)
        per_sym_records.append({
            "symbol": sym,
            "n_trades": int(len(sub)),
            "mean_bp": float(sub["net_return"].mean() * 10000),
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_lower_pos": bool(ci["ci_lower"] > 0),
        })
    n_sym_measurable = sum(1 for r in per_sym_records if r.get("skip") is None)
    n_sym_ci_pos = sum(1 for r in per_sym_records if r.get("ci_lower_pos") is True)

    return {
        "per_quarter_t_stats": per_q_records,
        "n_quarters_measurable": n_q_measurable,
        "n_quarters_pos_t": n_q_pos_t,
        "quarter_pos_t_ratio": (n_q_pos_t / n_q_measurable) if n_q_measurable else float("nan"),
        "per_symbol_bootstrap": per_sym_records,
        "n_symbols_measurable": n_sym_measurable,
        "n_symbols_ci_pos": n_sym_ci_pos,
        "symbol_ci_pos_ratio": (n_sym_ci_pos / n_sym_measurable) if n_sym_measurable else float("nan"),
    }


def aggregate_results(
    per_sym: Dict[str, Dict],
    hold_minutes: int,
) -> Dict:
    """Pool per-symbol nets into aggregate three-gate evaluation + sign-split."""
    pieces: List[pd.Series] = []
    pool_pieces: List[np.ndarray] = []
    per_sym_summary: Dict[str, Dict] = {}
    sym_to_records: List[Tuple[str, pd.Timestamp, float, float]] = []  # for concentration

    for sym, res in per_sym.items():
        if "skip" in res:
            per_sym_summary[sym] = {"skip": res.get("skip"), "n_triggers": res.get("n_triggers", 0)}
            continue
        ns = res["net_series"]
        gross = res["gross_array"]
        if len(ns) == 0:
            per_sym_summary[sym] = {"n_triggers": res.get("n_triggers", 0), "n_with_forward": 0}
            continue
        pieces.append(ns)
        # sample 5000 from pool per sym for aggregation (lesson #1 manageable)
        pool = res["pool"]
        if len(pool) > 5000:
            rng = np.random.default_rng(hash(sym) & 0xFFFFFFFF)
            pool = rng.choice(pool, size=5000, replace=False)
        pool_pieces.append(pool)
        per_sym_summary[sym] = {
            "n_triggers": res.get("n_triggers", 0),
            "n_with_forward": int(len(ns)),
            "n_up_break": int((res["direction_array"] > 0).sum()),
            "n_down_break": int((res["direction_array"] < 0).sum()),
            "mean_gross_bp": res.get("mean_gross_bp", 0.0),
            "mean_net_bp": res.get("mean_net_bp", 0.0),
            "t_stat": res.get("t_stat", 0.0),
        }
        for ts, val, d in zip(ns.index, ns.values, res["direction_array"]):
            sym_to_records.append((sym, ts, float(val), float(d)))

    if not pieces:
        return {
            "hold_minutes": hold_minutes,
            "n_aggregate": 0,
            "skip_reason": "no symbol produced trades",
            "per_sym": per_sym_summary,
        }

    agg_net = np.concatenate([p.values for p in pieces])
    agg_pool = np.concatenate(pool_pieces)
    n_agg = int(len(agg_net))

    if n_agg < 30:
        log.warning("hold=%dm aggregate n=%d < 30 (lesson #11 marginal)", hold_minutes, n_agg)

    gross_mean_bp = float((agg_net.mean() + FEE_PER_TRADE) * 10000)
    net_mean_bp = float(agg_net.mean() * 10000)
    if agg_net.std(ddof=1) > 0 and n_agg >= 2:
        obs_t = float(agg_net.mean() / agg_net.std(ddof=1) * np.sqrt(n_agg))
        sharpe_proxy = float(agg_net.mean() / agg_net.std(ddof=1) * np.sqrt(252 * (1440 / hold_minutes)))
    else:
        obs_t = 0.0
        sharpe_proxy = 0.0

    fee_res = fee_aware_perm_test(
        observed_net_returns=agg_net.tolist(),
        candidate_pool_returns=agg_pool.tolist(),
        fee_per_trade=FEE_PER_TRADE,
        n_perms=1000,
        rng_seed=42,
    )
    ci_res = bootstrap_ci(
        observed_net_returns=agg_net.tolist(),
        n_boot=2000,
        block_size=1,
        rng_seed=42,
    )

    diversity_positive = 0
    diversity_alts: List[str] = []
    for sym, summ in per_sym_summary.items():
        if summ.get("n_with_forward", 0) >= 5 and summ.get("mean_net_bp", 0.0) > 0:
            diversity_positive += 1
            diversity_alts.append(sym)

    sig_excess = fee_res.get("signal_t_excess", float("nan"))
    ci_lower = ci_res.get("ci_lower", float("nan"))
    perm_p = fee_res.get("perm_p_two_sided", float("nan"))
    gate_signal = bool(np.isfinite(sig_excess) and sig_excess >= 2.0)
    gate_ci = bool(np.isfinite(ci_lower) and ci_lower > 0)
    gate_perm = bool(np.isfinite(perm_p) and perm_p <= 0.10)
    gate_diversity = diversity_positive >= DIVERSITY_MIN_POSITIVE_ALTS
    three_gate = gate_signal and gate_ci and gate_perm
    full_pass = three_gate and gate_diversity

    # Lesson #16 concentration
    obs_df = pd.DataFrame(
        sym_to_records, columns=["symbol", "ts", "net_return", "direction"]
    )
    concentration = compute_concentration(obs_df)
    qpt_ratio = concentration["quarter_pos_t_ratio"]
    sci_ratio = concentration["symbol_ci_pos_ratio"]
    sci_pos = concentration["n_symbols_ci_pos"]
    gate_quarter = bool(np.isfinite(qpt_ratio) and qpt_ratio >= CONCENTRATION_QUARTER_POS_T_MIN)
    gate_symbol_ratio = bool(np.isfinite(sci_ratio) and sci_ratio >= CONCENTRATION_SYMBOL_CI_POS_RATIO_MIN)
    gate_symbol_floor = bool(sci_pos >= CONCENTRATION_SYMBOL_CI_POS_FLOOR)
    concentration_pass = gate_quarter and gate_symbol_ratio and gate_symbol_floor

    # Sign-split (UP-break LONG cell vs DOWN-break SHORT cell)
    up_mask = obs_df["direction"] > 0
    dn_mask = obs_df["direction"] < 0
    up_net = obs_df.loc[up_mask, "net_return"].values
    dn_net = obs_df.loc[dn_mask, "net_return"].values

    def _cell_summary(arr: np.ndarray, label: str) -> Dict:
        n = int(len(arr))
        if n < 2:
            return {"label": label, "n": n, "skip": "n<2"}
        mean_bp = float(arr.mean() * 10000)
        sd = arr.std(ddof=1)
        t = float(arr.mean() / sd * np.sqrt(n)) if sd > 0 else 0.0
        ci_split = bootstrap_ci(arr, n_boot=2000, block_size=1)
        return {
            "label": label,
            "n": n,
            "mean_net_bp": mean_bp,
            "mean_gross_bp": mean_bp + FEE_PER_TRADE * 10000,
            "t_stat": t,
            "ci_lower_bp": ci_split["ci_lower"] * 10000,
            "ci_upper_bp": ci_split["ci_upper"] * 10000,
        }

    sign_split = {
        "up_break_long_cell": _cell_summary(up_net, "UP-break LONG"),
        "down_break_short_cell": _cell_summary(dn_net, "DOWN-break SHORT"),
    }

    return {
        "hold_minutes": hold_minutes,
        "n_aggregate": n_agg,
        "aggregate": {
            "gross_bp": gross_mean_bp,
            "net_bp": net_mean_bp,
            "obs_t": obs_t,
            "sharpe_proxy_ann": sharpe_proxy,
            "fee_aware_perm": fee_res,
            "bootstrap_ci": ci_res,
            "three_gate": {
                "signal_t_excess_pass": gate_signal,
                "ci_lower_pass": gate_ci,
                "perm_p_pass": gate_perm,
                "PASS_ALL_3GATE": three_gate,
            },
            "diversity": {
                "positive_alt_count": diversity_positive,
                "min_required": DIVERSITY_MIN_POSITIVE_ALTS,
                "PASS_DIVERSITY": gate_diversity,
                "positive_alts": diversity_alts,
            },
            "FULL_PASS_4GATE": full_pass,
        },
        "concentration": concentration,
        "concentration_gate": {
            "quarter_pos_t_ratio": qpt_ratio,
            "quarter_pos_t_min": CONCENTRATION_QUARTER_POS_T_MIN,
            "PASS_QUARTER": gate_quarter,
            "symbol_ci_pos_ratio": sci_ratio,
            "symbol_ci_pos_ratio_min": CONCENTRATION_SYMBOL_CI_POS_RATIO_MIN,
            "n_symbols_ci_pos": sci_pos,
            "symbol_ci_pos_floor": CONCENTRATION_SYMBOL_CI_POS_FLOOR,
            "PASS_SYMBOL": gate_symbol_ratio and gate_symbol_floor,
            "PASS_CONCENTRATION": concentration_pass,
        },
        "sign_split": sign_split,
        "per_sym": per_sym_summary,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    log.info("=== paradigm 78 R-1: %s ===", PARADIGM_NAME)
    log.info("focus: tortuosity_z>=%.2f, break_k=%.2f, hold=%dm",
             FOCUS_TORTUOSITY_Z, FOCUS_BREAK_K, FOCUS_HOLD_MIN)
    log.info("hold sweep: %s minutes", HOLD_SWEEP_MIN)
    log.info("universe: %d alts (BTC excluded)", len(ALT_SYMS))

    # Sanity: verify BTC count (mandatory per Q3 lesson #6)
    btc_1m = load_ohlcv_1m_cached("BTCUSDT")
    log.info("BTC 1m count = %d (expected 1,241,280)", len(btc_1m))
    if len(btc_1m) != 1_241_280:
        log.warning("BTC count mismatch — continuing but flagging")

    # Load 30m panels for each alt
    alt_panels_30m: Dict[str, pd.DataFrame] = {}
    for sym in ALT_SYMS:
        df_1m = load_ohlcv_1m_cached(sym)
        df_30m = resample_to_30m(df_1m)
        alt_panels_30m[sym] = df_30m
        log.info("  %s: 1m=%d 30m=%d (%s → %s)",
                 sym, len(df_1m), len(df_30m),
                 df_30m.index.min(), df_30m.index.max())

    # ---- Sweep 1: focus z, focus break_k, sweep hold ----
    hold_sweep_results: Dict[str, Dict] = {}
    for h_min in HOLD_SWEEP_MIN:
        log.info("=== hold=%dm @ z>=%.2f, K=%.2f ===", h_min, FOCUS_TORTUOSITY_Z, FOCUS_BREAK_K)
        t0 = time.time()
        h_bars = h_min // BAR_MINUTES
        per_sym: Dict[str, Dict] = {}
        for sym, df_30m in alt_panels_30m.items():
            per_sym[sym] = evaluate_one_sym(
                sym, df_30m, FOCUS_TORTUOSITY_Z, FOCUS_BREAK_K, h_bars,
            )
        agg = aggregate_results(per_sym, h_min)
        if "aggregate" in agg:
            a = agg["aggregate"]
            log.info(
                "  n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f null_mean_t=%.2f sigex=%.2f ci_lower=%.2fbp perm_p=%.3f",
                agg["n_aggregate"], a["gross_bp"], a["net_bp"], a["obs_t"],
                a["fee_aware_perm"].get("null_mean_t", float("nan")),
                a["fee_aware_perm"].get("signal_t_excess", float("nan")),
                a["bootstrap_ci"].get("ci_lower", float("nan")) * 10000,
                a["fee_aware_perm"].get("perm_p_two_sided", float("nan")),
            )
            log.info(
                "  3gate=%s diversity=%s/%d FULL_4GATE=%s",
                a["three_gate"]["PASS_ALL_3GATE"],
                a["diversity"]["positive_alt_count"],
                DIVERSITY_MIN_POSITIVE_ALTS,
                a["FULL_PASS_4GATE"],
            )
            if "concentration_gate" in agg:
                cg = agg["concentration_gate"]
                log.info(
                    "  CONCENTRATION: q_pos_t_ratio=%.2f sym_ci_pos=%d/%d (ratio=%.2f) PASS=%s",
                    cg["quarter_pos_t_ratio"] if np.isfinite(cg["quarter_pos_t_ratio"]) else float("nan"),
                    cg["n_symbols_ci_pos"], agg["concentration"]["n_symbols_measurable"],
                    cg["symbol_ci_pos_ratio"] if np.isfinite(cg["symbol_ci_pos_ratio"]) else float("nan"),
                    cg["PASS_CONCENTRATION"],
                )
            if "sign_split" in agg:
                ss = agg["sign_split"]
                up = ss["up_break_long_cell"]
                dn = ss["down_break_short_cell"]
                log.info(
                    "  SIGN: UP-LONG n=%s net=%sbp t=%s | DN-SHORT n=%s net=%sbp t=%s",
                    up.get("n"),
                    f"{up.get('mean_net_bp', float('nan')):.2f}" if "mean_net_bp" in up else "—",
                    f"{up.get('t_stat', float('nan')):.2f}" if "t_stat" in up else "—",
                    dn.get("n"),
                    f"{dn.get('mean_net_bp', float('nan')):.2f}" if "mean_net_bp" in dn else "—",
                    f"{dn.get('t_stat', float('nan')):.2f}" if "t_stat" in dn else "—",
                )
        log.info("  hold=%dm elapsed=%.1fs", h_min, time.time() - t0)
        hold_sweep_results[f"hold_{h_min}m"] = agg

    # ---- Focus result + verdict ----
    focus_key = f"hold_{FOCUS_HOLD_MIN}m"
    focus_res = hold_sweep_results[focus_key]
    focus_full_pass = focus_res.get("aggregate", {}).get("FULL_PASS_4GATE", False)
    focus_three_gate = focus_res.get("aggregate", {}).get("three_gate", {}).get("PASS_ALL_3GATE", False)
    focus_concentration_pass = focus_res.get("concentration_gate", {}).get("PASS_CONCENTRATION", False)

    # Hold sign consistency: focus 240m direction sign vs other holds
    focus_net = focus_res.get("aggregate", {}).get("net_bp", 0.0)
    focus_sign = 1 if focus_net > 0 else -1 if focus_net < 0 else 0
    hold_sign_check = {}
    for h_min in HOLD_SWEEP_MIN:
        net_bp = hold_sweep_results[f"hold_{h_min}m"].get("aggregate", {}).get("net_bp", 0.0)
        sign = 1 if net_bp > 0 else -1 if net_bp < 0 else 0
        hold_sign_check[f"hold_{h_min}m"] = {
            "n_agg": hold_sweep_results[f"hold_{h_min}m"].get("n_aggregate", 0),
            "net_bp": net_bp,
            "sign_matches_focus": sign == focus_sign and focus_sign != 0,
        }
    holds_sign_consistent = all(v["sign_matches_focus"] for v in hold_sign_check.values())

    # Final verdict (Lesson #16 concentration gate REQUIRED for full PASS)
    if focus_full_pass and focus_concentration_pass:
        verdict = "R1_PASS"
    elif focus_full_pass and not focus_concentration_pass:
        verdict = "CONCENTRATED_R1_PASS"
    elif focus_three_gate and not focus_full_pass:
        verdict = "R1_FAIL_DIVERSITY"
    else:
        verdict = "R1_FAIL_GRAVEYARD"

    out = {
        "paradigm": PARADIGM_NAME,
        "phase": "R-1",
        "direction": "sign-conditional (entry direction = sign(break_bar_return))",
        "alts": ALT_SYMS,
        "n_alts": len(ALT_SYMS),
        "fee_per_trade": FEE_PER_TRADE,
        "bar_minutes": BAR_MINUTES,
        "compression_window_bars": COMPRESSION_WINDOW_BARS,
        "zscore_lookback_bars": ZSCORE_LOOKBACK_BARS,
        "realized_vol_window_bars": REALIZED_VOL_WINDOW_BARS,
        "focus_tortuosity_z": FOCUS_TORTUOSITY_Z,
        "focus_break_k": FOCUS_BREAK_K,
        "focus_hold_minutes": FOCUS_HOLD_MIN,
        "hold_sweep_minutes": HOLD_SWEEP_MIN,
        "trigger_min_gap_bars": TRIGGER_MIN_GAP_BARS,
        "diversity_min_positive_alts": DIVERSITY_MIN_POSITIVE_ALTS,
        "data_window": {
            "btc_min": str(btc_1m.index.min()),
            "btc_max": str(btc_1m.index.max()),
            "btc_n_1m": int(len(btc_1m)),
        },
        "hold_sweep": hold_sweep_results,
        "hold_sweep_sign_check": {
            "focus_net_bp": focus_net,
            "focus_sign": focus_sign,
            "by_hold": hold_sign_check,
            "all_consistent": holds_sign_consistent,
        },
        "verdict": {
            "focus_hold_minutes": FOCUS_HOLD_MIN,
            "focus_three_gate_pass": focus_three_gate,
            "focus_full_pass_4gate": focus_full_pass,
            "focus_concentration_pass": focus_concentration_pass,
            "hold_sweep_sign_consistent": holds_sign_consistent,
            "OVERALL_VERDICT": verdict,
        },
        "elapsed_s": round(time.time() - t_start, 1),
    }

    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("written %s", OUT_PATH)
    log.info("R1 VERDICT: %s focus_full_pass=%s concentration=%s",
             verdict, focus_full_pass, focus_concentration_pass)
    return 0


if __name__ == "__main__":
    sys.exit(main())
