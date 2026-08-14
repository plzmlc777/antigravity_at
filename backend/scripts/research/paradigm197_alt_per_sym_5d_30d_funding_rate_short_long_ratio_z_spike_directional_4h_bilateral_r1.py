"""Paradigm 197 R-1 — per-sym 5d/30d funding rate short/long ratio z-spike,
bilateral 4-quadrant SNT.

3rd-substrate transplant of paradigm 195 (RV ratio) + paradigm 196 (OI ratio)
formulation onto FUNDING RATE axis. PRIMARY GOAL: universe-level concentration
limit 3-substrate cross-verify (RV → OI → funding).

Hypothesis
----------
Per-sym 8h funding rate (binance_funding_rate DB). Compute:
    short_mean = mean funding rate over last 5d (5d × 3 funding events = 15)
    long_mean  = mean funding rate over last 30d (90 funding events)
    ratio      = short_mean / long_mean
    z_ratio    = 90d rolling z-score of ratio  (270 funding events window)
z_ratio >= +2 = "5d funding regime is elevated vs 30d baseline" = funding
regime shift (perpetual demand or short squeeze building). z_ratio aligned to
4h grid forward, then split by concurrent 4h bar direction:
    A_focus  : z>=+2 × bar UP   × LONG  (funding climbing + price climbing → continuation)
    A_mirror : z>=+2 × bar UP   × SHORT (funding climbing + price climbing → reversal)
    B_same   : z>=+2 × bar DOWN × SHORT (funding climbing + price falling → cascade)
    B_mirror : z>=+2 × bar DOWN × LONG  (funding climbing + price falling → MR;
                                          Lesson #42 9th dogfood)

Substrate
---------
- binance_funding_rate DB: 20 syms with 2.25yr (2466 records each, 8h cadence)
- 4h OHLCV joblib cache (backend/runs/ohlcv_cache_12col) — 14 syms intersected
- ZERO backfill required for the 14-sym cohort (paradigm 195/196 parity)

Universe decision (4h OHLCV cache constraint)
---------------------------------------------
Spec requested 20-sym (10 deep + 10 mid-cap). 4h OHLCV cache covers 14 syms.
Spec's PRIMARY GOAL is "3rd substrate cross-verify universe-level concentration
limit". The cleanest test of that hypothesis is UNIVERSE-IDENTICAL with
paradigm 195/196 (same 14-cohort). Expanding to 20 would confound cross-verify
with universe expansion. We run paradigm 197 on the SAME 14-cohort as 195/196.

Lesson refs
-----------
#11 sample density: 14 syms × 2.25yr × 8h cycle = ~3 funding events/day × 365 ×
    2.25 = ~2,500 per sym × 14 = ~35,000 funding events; |z|>=2 raw ~5% → ~1,750
    triggers panel-wide. 4 quadrants × 9 quarters = 36 cells → ~49/cell PASS.
#19 4-quadrant SNT bilateral mandatory (unary z>=+2 split by bar dir).
#21 single derived statistic (funding ratio z), no axis stacking.
#30 data window ratio: 2.25yr / 2.25yr = 100% (full-window applies).
#34 empirical distribution prescreen done below (logged at runtime).
#40 structural threshold — funding ratio CAN go z<=-2 (negative regimes);
    spec mandated z>=+2 only for cross-substrate parity (RV/OI).
#42 9th dogfood (capitulation MR universal cross-class verify, funding substrate)
#61 slug grep audit clean (no funding_ratio / funding_rate_ratio /
    funding_5d_30d / funding_short_long term match).
#62 5/5 family-distinct STRICT vs paradigm 22 (funding_carry R-5 LIVE):
    - statistic class: 8h single z-score MR vs 5d/30d window-ratio z → distinct
    - mechanism: sparse z mean-reversion vs ratio regime transition → distinct
    - direction class: single-direction MR vs 4-quadrant bilateral → distinct
    - hold class: 8h fixed vs 4h primary + sweep → distinct
    - universe: same 14-alt cohort (acceptable per Lesson #62 statistic-distinct path)
#62 vs funding family Tier 4 retire (73/79/96/97/98/99/132): all use
    8h single z-score or velocity or cross-sym dispersion. paradigm 197
    statistic = window-ratio z, which is NEW class within funding axis.
#67 ESCAPE per-sym funding idiosyncratic (each sym funding independent).
#68 ESCAPE continuous rolling 5d/30d window (NOT 8h cycle boundary anchor).
#69 5-item summary.
#70 corollary scope decision: paradigm 22 = sparse single-z MR. paradigm 197 =
    window-ratio z bilateral. CLASS SHIFT (statistic + direction + hold all
    different) → (b) PROCEED per paradigm 182/184 precedent (corollary applies
    only to spec-adaptive expansion of SAME class).
#71 sparse-strict mode (per-trade edge >= 2% target).

CRITICAL CROSS-SUBSTRATE COMPARISON (paradigm 195+196 finding direct)
---------------------------------------------------------------------
- paradigm 195 (RV ratio):   best A_focus_h12h sigex=+3.42 3-gate PASS, n_syms_ci_pos data NOT populated in artifact (per-sym dict empty)
- paradigm 196 (OI ratio):   best A_focus_h4h sigex=+2.29 3-gate FAIL, 1/14 syms ci_pos = 7.1% Conc FAIL → HYPOTHESIS_1_UNIVERSE_LEVEL_LIMIT_UNIVERSAL_14SYM_RETIRE_CANDIDATE
- paradigm 197 (funding):    TBD

Decision criteria (paradigm 197 best cell)
------------------------------------------
- syms_ci_pos_ratio >= 30% (≥5/14) → HYPOTHESIS 2 (funding axis alpha-bearing dispersion)
- syms_ci_pos_ratio <  14% (<2/14) → HYPOTHESIS 1 CONFIRMED (universe-level limit universal across momentum-like axes; 14-sym cohort sparse-trigger 4h-hold paradigm class Tier 4 retire formal)
- 14% <= syms_ci_pos_ratio < 30% → MARGINAL (partial universe limit, funding-specific)

NB on Lesson #42 9th dogfood
----------------------------
Previous chain paradigm 117/158/162/179/193/194/195/196 all confirmed
"capitulation MR" pattern: bar-DOWN × LONG (B_mirror) outperforms bar-DOWN ×
SHORT (B_same) at extreme triggers. paradigm 197 tests cross-substrate funding.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("paradigm197_r1")

PARADIGM = "alt_per_sym_5d_30d_funding_rate_short_long_ratio_z_spike_directional_4h_bilateral"
COUNTER = 197

PRICE_CACHE_DIR = REPO_ROOT / "runs" / "ohlcv_cache_12col"
OUT_DIR = REPO_ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 14-sym cohort, IDENTICAL to paradigm 195/196 for direct cross-substrate verify.
SYMS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX",
        "LINK", "LTC", "BCH", "NEAR", "FIL", "WIF"]

# Funding-event windows (3 events/day = 8h cycle)
FUND_PER_DAY = 3
WIN_SHORT_FE = 5 * FUND_PER_DAY    # 15 events (5d)
WIN_LONG_FE = 30 * FUND_PER_DAY    # 90 events (30d)
WIN_Z_FE = 90 * FUND_PER_DAY       # 270 events (90d z-window)

# 4h bar settings
DEBOUNCE_BARS_4H = 6   # 24h debounce
Z_THRESH = 2.0
HOLD_BARS = {"4h": 1, "8h": 2, "12h": 3, "24h": 6}
PRIMARY_HOLD = "4h"
FEE_RT = 0.0008

# Effective universe years (BTC=2.25, all others=2.25 — funding DB full window
# is 2024-02-19..2026-05-21; 4h OHLCV cache has same or longer span). Mean = 2.25
N_YEARS_UNIVERSE = 2.25

DB_URL = "postgresql+psycopg2://antigravity_user:antigravity_password@localhost/antigravity_db"


def load_funding_rate(sym: str) -> pd.Series:
    """Load 8h funding_rate Series indexed by funding_time (UTC, no tz)."""
    eng = create_engine(DB_URL)
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT funding_time, funding_rate FROM binance_funding_rate "
                 "WHERE symbol=:s ORDER BY funding_time"),
            {"s": f"{sym}USDT"},
        ).fetchall()
    if not rows:
        return pd.Series(dtype=float)
    ts = pd.to_datetime([r[0] for r in rows])
    if hasattr(ts, "tz") and ts.tz is not None:
        ts = ts.tz_convert(None)
    s = pd.Series([float(r[1]) for r in rows], index=ts, name=f"{sym}_fr").sort_index()
    s = s[~s.index.duplicated(keep="first")]
    return s


def compute_signal(funding_8h: pd.Series, close_4h: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series, pd.DatetimeIndex]:
    """Compute z_ratio of 5d/30d funding-rate window means, aligned to 4h grid.

    Steps:
      1. 8h funding series → 5d/30d rolling means → ratio → 90d z (all on 8h grid)
      2. forward-fill onto 4h grid (each 4h bar inherits most-recent 8h-cycle z)
      3. Compute 4h bar_ret from close_4h
    """
    short_mean = funding_8h.rolling(WIN_SHORT_FE, min_periods=WIN_SHORT_FE).mean()
    long_mean = funding_8h.rolling(WIN_LONG_FE, min_periods=WIN_LONG_FE).mean()
    # Guard zero/near-zero long_mean (funding can be ~0). Mask sign-flip pathology
    # by treating near-zero (|mean|<1e-6) as NaN.
    long_mean_safe = long_mean.where(long_mean.abs() > 1e-6)
    ratio = short_mean / long_mean_safe
    mu = ratio.rolling(WIN_Z_FE, min_periods=WIN_Z_FE).mean()
    sd = ratio.rolling(WIN_Z_FE, min_periods=WIN_Z_FE).std()
    z_8h = (ratio - mu) / sd
    z_8h = z_8h.replace([np.inf, -np.inf], np.nan)

    # Forward-fill 8h funding z onto 4h close index
    # close_4h index is RangeIndex of timestamps; we align by reindex + ffill.
    combined = pd.concat([z_8h.rename("z"), close_4h.rename("close")], axis=1).sort_index()
    combined["z"] = combined["z"].ffill()
    # Keep rows where close exists (4h bars), drop rows that are only funding ticks
    df = combined[combined["close"].notna()].copy()
    df["bar_ret"] = df["close"] / df["close"].shift(1) - 1.0
    valid = df["z"].notna() & df["bar_ret"].notna() & np.isfinite(df["z"]) & np.isfinite(df["bar_ret"])
    return df["z"], df["bar_ret"], valid, df.index


def debounce(trig: np.ndarray, gap: int) -> np.ndarray:
    out = np.zeros_like(trig, dtype=bool)
    last = -gap - 1
    for i in range(len(trig)):
        if trig[i] and (i - last) >= gap:
            out[i] = True
            last = i
    return out


def forward_return(close: np.ndarray, i: int, hold: int) -> float:
    j = i + hold
    if j >= len(close):
        return np.nan
    return float(close[j] / close[i] - 1.0)


def t_stat(arr: np.ndarray) -> float:
    arr = np.asarray(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return float("nan")
    sd = arr.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(arr.mean() / sd * np.sqrt(len(arr)))


def collect_per_sym() -> dict:
    out = {}
    z_dist_pool = []
    for sym in SYMS:
        px_path = PRICE_CACHE_DIR / f"{sym}USDT_4h.joblib"
        if not px_path.exists():
            log.warning("missing 4h price %s", sym)
            continue
        funding_8h = load_funding_rate(sym)
        if funding_8h.empty:
            log.warning("missing funding %s", sym)
            continue
        px_df = joblib.load(px_path).sort_index()
        close_4h = px_df["close"].astype(float)
        # Strip tz if present (DB returns naive; cache may be tz-aware)
        if close_4h.index.tz is not None:
            close_4h.index = close_4h.index.tz_convert(None)
        z, bar_ret, valid, idx = compute_signal(funding_8h, close_4h)
        close_aligned = close_4h.reindex(idx).values
        out[sym] = dict(
            close=close_aligned,
            z=z.values,
            bar_ret=bar_ret.values,
            valid=valid.values,
            index=idx,
        )
        n_pos2 = int(((z >= Z_THRESH) & valid).sum())
        n_neg2 = int(((z <= -Z_THRESH) & valid).sum())
        z_valid = z.values[valid.values]
        z_dist_pool.append(z_valid)
        log.info(
            "%s: 4h_rows=%d valid=%d pos2=%d neg2=%d window=%s..%s "
            "z_p50=%.2f p90=%.2f p99=%.2f min=%.2f max=%.2f",
            sym, len(idx), int(valid.sum()), n_pos2, n_neg2,
            idx[0], idx[-1],
            float(np.nanpercentile(z_valid, 50)) if len(z_valid) else float("nan"),
            float(np.nanpercentile(z_valid, 90)) if len(z_valid) else float("nan"),
            float(np.nanpercentile(z_valid, 99)) if len(z_valid) else float("nan"),
            float(np.nanmin(z_valid)) if len(z_valid) else float("nan"),
            float(np.nanmax(z_valid)) if len(z_valid) else float("nan"),
        )
    # Empirical distribution prescreen (Lesson #34)
    if z_dist_pool:
        all_z = np.concatenate(z_dist_pool)
        log.info(
            "PANEL z dist: n=%d p50=%.2f p90=%.2f p99=%.2f min=%.2f max=%.2f "
            "frac_ge_2=%.3f frac_le_neg2=%.3f",
            len(all_z),
            float(np.percentile(all_z, 50)), float(np.percentile(all_z, 90)),
            float(np.percentile(all_z, 99)), float(np.min(all_z)), float(np.max(all_z)),
            float((all_z >= Z_THRESH).mean()), float((all_z <= -Z_THRESH).mean()),
        )
    return out


def evaluate_quadrant(per_sym: dict, quadrant: str, hold_bars: int) -> dict:
    trades_gross, trades_net, trades_meta, pool_gross = [], [], [], []
    direction_long = quadrant in ("A_focus", "B_mirror")
    bar_dir_up = quadrant in ("A_focus", "A_mirror")

    for sym, d in per_sym.items():
        close = d["close"]
        z = d["z"]
        bar_ret = d["bar_ret"]
        valid = d["valid"]
        idx_arr = d["index"]

        trig_raw = (z >= Z_THRESH) & valid
        if bar_dir_up:
            trig_raw = trig_raw & (bar_ret > 0)
        else:
            trig_raw = trig_raw & (bar_ret < 0)
        trig = debounce(trig_raw, DEBOUNCE_BARS_4H)
        trig_idxs = np.where(trig)[0]

        for i in trig_idxs:
            r = forward_return(close, i, hold_bars)
            if np.isnan(r):
                continue
            if not direction_long:
                r = -r
            gross = r
            net = gross - FEE_RT
            trades_gross.append(gross)
            trades_net.append(net)
            trades_meta.append((sym, idx_arr[i], gross))

        for i in range(len(close) - hold_bars):
            if not valid[i]:
                continue
            r = forward_return(close, i, hold_bars)
            if np.isnan(r):
                continue
            if not direction_long:
                r = -r
            pool_gross.append(r)

    trades_gross = np.array(trades_gross, dtype=float)
    trades_net = np.array(trades_net, dtype=float)
    if len(trades_net) == 0:
        return dict(n_trades=0)

    obs_mean_gross_bp = float(trades_gross.mean() * 1e4)
    obs_mean_net_bp = float(trades_net.mean() * 1e4)
    obs_t = t_stat(trades_net)

    perm = fee_aware_perm_test(
        observed_net_returns=trades_net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=1000,
        rng_seed=42,
    )
    boot = bootstrap_ci(trades_net, n_boot=2000, block_size=1, alpha=0.05, rng_seed=42)
    ci_lower_bp = boot["ci_lower"] * 1e4
    ci_upper_bp = boot["ci_upper"] * 1e4
    prob_pos = boot.get("prob_positive", float("nan"))

    df_meta = pd.DataFrame(trades_meta, columns=["sym", "ts", "gross"])
    df_meta["net"] = df_meta["gross"] - FEE_RT
    df_meta["quarter"] = df_meta["ts"].dt.to_period("Q").astype(str)
    quarter_stats = []
    for q, sub in df_meta.groupby("quarter"):
        if len(sub) < 5:
            quarter_stats.append(dict(quarter=q, n=len(sub), t=float("nan"),
                                       mean_bp=float(sub["net"].mean() * 1e4), measurable=False))
            continue
        quarter_stats.append(dict(quarter=q, n=len(sub),
                                   t=t_stat(sub["net"].values),
                                   mean_bp=float(sub["net"].mean() * 1e4), measurable=True))
    n_q_measurable = sum(1 for q in quarter_stats if q["measurable"])
    n_q_pos_t = sum(1 for q in quarter_stats if q["measurable"] and q["t"] > 0)
    quarter_pos_t_ratio = n_q_pos_t / max(n_q_measurable, 1)

    syms_stats = []
    n_syms_ci_pos = 0
    n_syms_measurable = 0
    for sym in sorted(df_meta["sym"].unique()):
        sub = df_meta[df_meta["sym"] == sym]
        if len(sub) < 5:
            syms_stats.append(dict(sym=sym, n=int(len(sub)),
                                    mean_bp=float(sub["net"].mean() * 1e4) if len(sub) else 0.0,
                                    ci_lower_bp=float("nan"), ci_pos=False, measurable=False))
            continue
        n_syms_measurable += 1
        b = bootstrap_ci(sub["net"].values, n_boot=1000, block_size=1, alpha=0.05, rng_seed=42)
        ci_lo = b["ci_lower"] * 1e4
        ci_pos = ci_lo > 0
        if ci_pos:
            n_syms_ci_pos += 1
        syms_stats.append(dict(sym=sym, n=int(len(sub)),
                                mean_bp=float(sub["net"].mean() * 1e4),
                                ci_lower_bp=float(ci_lo), ci_pos=bool(ci_pos), measurable=True))
    syms_ci_pos_ratio = n_syms_ci_pos / max(n_syms_measurable, 1)

    signal_t_excess = perm.get("signal_t_excess", float("nan"))
    perm_p_one_above = perm.get("perm_p_one_sided_above", float("nan"))
    gate1 = (not np.isnan(signal_t_excess)) and signal_t_excess >= 2.0
    gate2 = (not np.isnan(ci_lower_bp)) and ci_lower_bp > 0
    gate3 = (not np.isnan(perm_p_one_above)) and perm_p_one_above <= 0.10
    three_gate_pass = bool(gate1 and gate2 and gate3)
    conc_pass = (quarter_pos_t_ratio >= 0.5 and syms_ci_pos_ratio >= 0.30
                 and n_syms_ci_pos >= 3)

    n = len(trades_net)
    trades_per_year = n / N_YEARS_UNIVERSE
    per_trade_edge_pct = float(trades_net.mean() * 100)
    hold_hours = hold_bars * 4
    util = trades_per_year * hold_hours / (365 * 24) * 100
    sharpe_ann = (trades_net.mean() / trades_net.std(ddof=1)) * np.sqrt(trades_per_year) if trades_net.std(ddof=1) > 0 else float("nan")
    lc4 = dict(
        trades_per_year=trades_per_year,
        per_trade_edge_pct=per_trade_edge_pct,
        capital_util_pct=util,
        sharpe_ann=sharpe_ann,
        passes=(trades_per_year >= 12 and per_trade_edge_pct >= 2.0
                and util >= 30 and sharpe_ann >= 1.5),
    )

    return dict(
        n_trades=n,
        obs_mean_gross_bp=obs_mean_gross_bp,
        obs_mean_net_bp=obs_mean_net_bp,
        obs_t=obs_t,
        signal_t_excess=signal_t_excess,
        null_mean_t=perm.get("null_mean_t"),
        perm_p_two_sided=perm.get("perm_p_two_sided"),
        perm_p_one_sided_above=perm_p_one_above,
        perm_p_one_sided_below=perm.get("perm_p_one_sided_below"),
        ci_lower_bp=float(ci_lower_bp),
        ci_upper_bp=float(ci_upper_bp),
        prob_positive=float(prob_pos),
        three_gate_pass=three_gate_pass,
        gate1_sigex_ge_2=bool(gate1),
        gate2_ci_lower_pos=bool(gate2),
        gate3_perm_p_le_010=bool(gate3),
        quarter_pos_t_ratio=quarter_pos_t_ratio,
        n_quarters_measurable=n_q_measurable,
        n_quarters_pos_t=n_q_pos_t,
        per_quarter=quarter_stats,
        syms_ci_pos_ratio=syms_ci_pos_ratio,
        n_syms_ci_pos=n_syms_ci_pos,
        n_syms_measurable=n_syms_measurable,
        per_sym=syms_stats,
        concentration_gate_pass=bool(conc_pass),
        life_changing_4dim=lc4,
        n_candidate_pool=len(pool_gross),
    )


def main() -> None:
    log.info("paradigm %s R-1 start", PARADIGM)
    t0 = time.time()
    log.info("collecting per-sym signals (funding 5d/30d ratio z)...")
    per_sym = collect_per_sym()
    log.info("collected %d syms", len(per_sym))

    results = {
        "paradigm": PARADIGM,
        "counter": COUNTER,
        "host": "hcp_local",
        "fee_rt": FEE_RT,
        "z_threshold": Z_THRESH,
        "win_short_funding_events": WIN_SHORT_FE,
        "win_long_funding_events": WIN_LONG_FE,
        "win_z_funding_events": WIN_Z_FE,
        "debounce_bars_4h": DEBOUNCE_BARS_4H,
        "syms_universe": SYMS,
        "universe_decision_note": (
            "14-sym IDENTICAL to paradigm 195/196 (4h OHLCV cache constraint + "
            "cleanest 3-substrate cross-verify of universe-level concentration "
            "limit; 20-sym spec deferred to avoid confounding universe expansion)."
        ),
        "primary_hold": PRIMARY_HOLD,
        "holds": list(HOLD_BARS.keys()),
        "n_years_universe": N_YEARS_UNIVERSE,
        "substrate_paths": {
            "funding": "binance_funding_rate (Postgres DB)",
            "price": str(PRICE_CACHE_DIR),
        },
        "lesson_70_corollary_scope_verdict": "PROCEED_b_class_shift_statistic_direction_hold_all_different_from_paradigm22_R5_LIVE",
    }

    quadrants = ["A_focus", "A_mirror", "B_same", "B_mirror"]
    cells = {}
    for hold_name, hold_bars in HOLD_BARS.items():
        log.info("hold=%s (%d bars)", hold_name, hold_bars)
        for q in quadrants:
            log.info("  quadrant %s ...", q)
            cell = evaluate_quadrant(per_sym, q, hold_bars)
            cells[f"{q}_h{hold_name}"] = cell
            n = cell.get("n_trades", 0)
            if n > 0:
                log.info(
                    "    n=%d gross=%.2fbp net=%.2fbp obs_t=%.2f sigex=%.2f "
                    "perm_p_above=%s ci_lower=%.2fbp three_gate=%s conc=%s "
                    "syms_ci_pos=%d/%d (%.1f%%) lc4=%s",
                    n, cell["obs_mean_gross_bp"], cell["obs_mean_net_bp"], cell["obs_t"],
                    cell["signal_t_excess"],
                    f"{cell['perm_p_one_sided_above']:.3f}" if cell['perm_p_one_sided_above'] is not None else "NA",
                    cell["ci_lower_bp"], cell["three_gate_pass"], cell["concentration_gate_pass"],
                    cell["n_syms_ci_pos"], cell["n_syms_measurable"], cell["syms_ci_pos_ratio"] * 100,
                    cell["life_changing_4dim"]["passes"],
                )
            else:
                log.info("    n=0 (empty cell)")
    results["cells"] = cells

    pass_cells_3gate = [k for k, c in cells.items() if c.get("three_gate_pass")]
    pass_cells_conc = [k for k, c in cells.items() if c.get("three_gate_pass") and c.get("concentration_gate_pass")]
    pass_cells_lc4 = [k for k, c in cells.items()
                      if c.get("three_gate_pass") and c.get("concentration_gate_pass")
                      and c.get("life_changing_4dim", {}).get("passes")]
    results["sweep_summary"] = {
        "n_cells_total": len(cells),
        "n_three_gate_pass": len(pass_cells_3gate),
        "cells_three_gate_pass": pass_cells_3gate,
        "n_concentration_pass": len(pass_cells_conc),
        "cells_concentration_pass": pass_cells_conc,
        "n_life_changing_pass": len(pass_cells_lc4),
        "cells_life_changing_pass": pass_cells_lc4,
    }

    best = None
    for k, c in cells.items():
        if c.get("n_trades", 0) < 30:
            continue
        sigex = c.get("signal_t_excess", float("nan"))
        if np.isnan(sigex):
            continue
        if best is None or sigex > best[1]:
            best = (k, sigex, c)
    results["best_cell"] = dict(
        key=best[0],
        signal_t_excess=best[1],
        n_trades=best[2]["n_trades"],
        gross_bp=best[2]["obs_mean_gross_bp"],
        net_bp=best[2]["obs_mean_net_bp"],
        ci_lower_bp=best[2]["ci_lower_bp"],
        three_gate_pass=best[2]["three_gate_pass"],
        concentration_gate_pass=best[2]["concentration_gate_pass"],
        syms_ci_pos_ratio=best[2]["syms_ci_pos_ratio"],
        n_syms_ci_pos=best[2]["n_syms_ci_pos"],
        n_syms_measurable=best[2]["n_syms_measurable"],
        life_changing_4dim=best[2]["life_changing_4dim"],
    ) if best else None

    # Lesson #42 9th dogfood
    l42 = {}
    for hold_name in HOLD_BARS:
        b_mirror = cells.get(f"B_mirror_h{hold_name}", {})
        b_same = cells.get(f"B_same_h{hold_name}", {})
        if b_mirror.get("n_trades", 0) > 0 and b_same.get("n_trades", 0) > 0:
            l42[hold_name] = dict(
                B_mirror_net_bp=b_mirror.get("obs_mean_net_bp"),
                B_mirror_sigex=b_mirror.get("signal_t_excess"),
                B_mirror_three_gate=b_mirror.get("three_gate_pass"),
                B_mirror_conc_gate=b_mirror.get("concentration_gate_pass"),
                B_same_net_bp=b_same.get("obs_mean_net_bp"),
                B_same_sigex=b_same.get("signal_t_excess"),
                B_mirror_minus_B_same_net_bp=(
                    b_mirror.get("obs_mean_net_bp") - b_same.get("obs_mean_net_bp")
                ),
            )
    results["lesson_42_9th_dogfood"] = l42

    # 3-substrate direct comparison
    p195_cmp = {}
    for hold_name in HOLD_BARS:
        cell = cells.get(f"A_focus_h{hold_name}", {})
        if cell.get("n_trades", 0) > 0:
            p195_cmp[hold_name] = dict(
                p197_funding_sigex=cell.get("signal_t_excess"),
                p197_funding_three_gate=cell.get("three_gate_pass"),
                p197_funding_conc_gate=cell.get("concentration_gate_pass"),
                p197_funding_syms_ci_pos_ratio=cell.get("syms_ci_pos_ratio"),
                p197_funding_n_syms_ci_pos=cell.get("n_syms_ci_pos"),
                p197_funding_n_syms_measurable=cell.get("n_syms_measurable"),
                p197_funding_net_bp=cell.get("obs_mean_net_bp"),
                p197_funding_n_trades=cell.get("n_trades"),
            )

    if best is not None:
        bsyms_ratio = best[2].get("syms_ci_pos_ratio", 0.0)
        n_meas = best[2].get("n_syms_measurable", 0)
        if bsyms_ratio >= 0.30:
            uni_verdict = "HYPOTHESIS_2_FUNDING_SUBSTRATE_ALPHA_BEARING_DISPERSION"
        elif bsyms_ratio < 0.14:
            uni_verdict = "HYPOTHESIS_1_UNIVERSE_LEVEL_LIMIT_CONFIRMED_3_SUBSTRATE_14SYM_4H_HOLD_PARADIGM_CLASS_TIER4_RETIRE_FORMAL"
        else:
            uni_verdict = "MARGINAL_PARTIAL_UNIVERSE_LIMIT_FUNDING_SPECIFIC"
    else:
        uni_verdict = "UNDETERMINED_NO_BEST_CELL"

    results["three_substrate_cross_verify"] = {
        "p195_axis": "per-sym 5d/30d realized variance ratio z (vol term structure)",
        "p196_axis": "per-sym 5d/30d open interest ratio z (OI term structure)",
        "p197_axis": "per-sym 5d/30d funding rate ratio z (funding term structure)",
        "p195_best": "A_focus_h12h sigex=+3.42 3-gate PASS Conc FAIL (per-sym dict not populated in artifact)",
        "p196_best": "A_focus_h4h sigex=+2.29 3-gate FAIL Conc FAIL 1/14 syms ci_pos (7.1%) → HYP1 candidate",
        "p197_a_focus_cells": p195_cmp,
        "p197_best_overall_cell": best[0] if best else None,
        "p197_best_sigex": best[1] if best else None,
        "p197_best_syms_ci_pos_ratio": best[2].get("syms_ci_pos_ratio") if best else None,
        "p197_best_n_syms_ci_pos": best[2].get("n_syms_ci_pos") if best else None,
        "universe_level_concentration_limit_verdict": uni_verdict,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    log.info("wrote %s (elapsed %.1fs)", out_path, time.time() - t0)
    log.info("universe-level concentration limit verdict: %s", uni_verdict)


if __name__ == "__main__":
    main()
