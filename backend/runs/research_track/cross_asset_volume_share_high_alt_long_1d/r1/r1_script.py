"""R-1 PoC — cross_asset_volume_share_high_alt_long_1d (paradigm 95).

Hypothesis (single sentence)
----------------------------
BTC daily USD-volume share (= BTC_vol_usd / sum(14-sym vol_usd)) 30d rolling
z-score >= +1.5 (BTC volume share peak = BTC dominance momentum / bull regime
confirmation)
  -> LONG 13 alts at next-day open, hold +1d (24h), exit at close.

Independent re-test (Lesson #8 mirror antipattern)
--------------------------------------------------
This paradigm 95 is NOT paradigm 94's mirror metric reused. paradigm 94 R-1
(BTC share LOW = compression) was BROAD_FALSIFIED_DIRECTION_INVERTED — its
mirror produced strong evidence but the mirror cannot be auto-promoted per
Lesson #8 / paradigm 70 mirror antipattern catalog. paradigm 95 is dispatched
as an independent hypothesis with its own dedicated R-1 batch, separate
PARADIGM name + directory, separate candidate pool, separate codepath.

Cross-proxy track (Lesson #29)
------------------------------
- obs proxy   = volume share fraction z-score (transform)
- fund proxy  = BTC absolute USD-volume 30d z-score (raw flow magnitude)
Both must independently three-gate PASS to satisfy Lesson #29.

Symmetric Negative Test (Lesson #19)
------------------------------------
- focus     : share_z >= +1.5 LONG  (BTC dominance peak -> alt LONG)
- mirror    : share_z <= -1.5 LONG  (BTC share compression -> alt LONG;
                                       this is paradigm 94 focus, already
                                       BROAD_FALSIFIED_DIRECTION_INVERTED in
                                       paradigm 94 R-1, included here for
                                       within-batch falsification null)

Lesson #20 narrow-scope 4-cond (a/b/c/d)
----------------------------------------
paradigm 94 R-1 mirror evidence had sym_ci_pos_ratio = 3/13 = 0.231 marginal
(< 0.30 Concentration Gate threshold). Lesson #20 narrow-scope candidate path
measures 4 conditions in this batch:
  a. 4-gate PASS (sigex>=2 + ci_lo>0 + perm_p<=0.10 + 50bp stress sigex>=2)
  b. Held-out replication: split data into first-half / last-half by trigger
     date and require BOTH halves three-gate PASS independently
  c. Bonferroni-adjusted p-value: per-symbol min p multiplied by n_symbols,
     require p_adj <= 0.10
  d. Hold-sweep sign consistency: re-run at hold=1d/2d/3d and require all
     three nets > 0 with at least 2/3 three-gate PASS

If 3-gate PASS + Concentration FAIL + a/b/c/d ALL PASS -> NARROW_SCOPE_CANDIDATE
If 3-gate PASS + Concentration FAIL + a/b/c/d NOT all PASS -> CONCENTRATED_R1_PASS

Life-changing 4-dim gate (memory feedback_life_changing_strategy_criterion)
---------------------------------------------------------------------------
- trades/yr >= 12 (sparse-trigger antipattern check)
- per-trade edge (net of fees) >= +2.0% (50bp fee stress applied)
- capital utilization >= 30% (= n_trade_days / n_total_days * fraction of
                                universe in trades)
- sharpe >= 1.5 (annualized assuming daily returns sqrt(252) scaling)

Output
------
backend/runs/research_track/cross_asset_volume_share_high_alt_long_1d/r1/
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]  # backend/
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

from _ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from _perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p95_r1")

PARADIGM = "cross_asset_volume_share_high_alt_long_1d"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM / "r1"
OUT_PATH = OUT_DIR / "r1_metrics.json"

BTC = "BTCUSDT"
# 13 alts (paradigm 69 validated set) — LONG direction
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
# 12 EXTRA boost syms not available in Mint joblib cache — omitted.
EXTRA = []
UNIVERSE = [BTC] + ALTS + EXTRA  # 14 syms

# config — HIGH side focus
Z_WINDOW = 30
FOCUS_Z_CUTOFFS_HIGH = [+1.5, +1.2, +1.0]  # primary then fallback
DEFAULT_FOCUS_CUTOFF = +1.5
DEFAULT_MIRROR_CUTOFF = -1.5  # mirror = paradigm 94 focus
HOLD_DAYS = 1
HOLD_SWEEP = [1, 2, 3]  # Lesson #20 cond (d)
FEE_RT = 0.0008
FEE_RT_STRESS = 0.0050

N_PERMS = 1000
N_BOOT = 2000
N_POOL_SAMPLES = 20000
SEED = 42


# ---------- data ----------


def resample_to_daily(df_1m: pd.DataFrame) -> pd.DataFrame:
    if df_1m.empty:
        return pd.DataFrame()
    df = df_1m.copy()
    df["vol_usd"] = df["close"] * df["volume"]
    daily = pd.DataFrame({
        "close": df["close"].resample("1D").last(),
        "open": df["close"].resample("1D").first(),
        "vol_usd": df["vol_usd"].resample("1D").sum(),
        "bar_count": df["close"].resample("1D").count(),
    })
    daily = daily[daily["bar_count"] >= 1200]
    daily = daily.dropna(subset=["close", "vol_usd"])
    return daily


# ---------- stats ----------


def stats_block(arr: np.ndarray) -> dict:
    if len(arr) < 2:
        return {"n": int(len(arr)), "mean_bp": float("nan"), "t": float("nan"),
                "win": float("nan"), "sharpe": float("nan")}
    m = float(arr.mean())
    s = float(arr.std(ddof=1))
    t_s = m / s * np.sqrt(len(arr)) if s > 0 else 0.0
    return {
        "n": int(len(arr)),
        "mean_bp": m * 1e4,
        "t": t_s,
        "win": float((arr > 0).mean()),
        "sharpe": (m / s) if s > 0 else 0.0,
    }


# ---------- forward returns / cell evaluation ----------


def compute_alt_forward_returns(daily_df: pd.DataFrame, hold_days: int = HOLD_DAYS) -> pd.Series:
    open_next = daily_df["open"].shift(-1)
    close_exit = daily_df["close"].shift(-hold_days)
    fwd = close_exit / open_next - 1.0
    return fwd


def evaluate_cell(triggers_dates, alts_forward_returns, fee_rt: float = FEE_RT):
    nets = []
    sym_list = []
    date_list = []
    for sym, fwd_ser in alts_forward_returns.items():
        for d in triggers_dates:
            if d not in fwd_ser.index:
                continue
            g = fwd_ser.loc[d]
            if pd.isna(g):
                continue
            nets.append(float(g) - fee_rt)
            sym_list.append(sym)
            date_list.append(d)
    return np.array(nets), np.array(sym_list), np.array(date_list)


def build_candidate_pool(alts_forward_returns, exclude_dates_set, n_samples=N_POOL_SAMPLES, seed=SEED):
    rng = np.random.default_rng(seed)
    pool = []
    for sym, fwd_ser in alts_forward_returns.items():
        clean = fwd_ser.dropna()
        mask_nontrig = ~clean.index.isin(exclude_dates_set)
        cand = clean[mask_nontrig].values
        if len(cand) == 0:
            continue
        n = min(n_samples // max(len(alts_forward_returns), 1), len(cand))
        idx = rng.choice(len(cand), size=n, replace=(n > len(cand)))
        pool.extend(cand[idx].tolist())
    return np.array(pool, dtype=float)


def run_quadrant(name: str, triggers_dates, alts_fwd, pool, fee_rt: float, n_perms: int) -> dict:
    nets, syms, dates = evaluate_cell(triggers_dates, alts_fwd, fee_rt=fee_rt)
    if len(nets) < 2:
        return {"quadrant": name, "n_trades": int(len(nets)),
                "n_triggers": int(len(triggers_dates)), "note": "insufficient"}
    s = stats_block(nets)
    fe = fee_aware_perm_test(
        observed_net_returns=nets,
        candidate_pool_returns=pool,
        fee_per_trade=fee_rt,
        n_perms=n_perms,
        rng_seed=SEED,
    )
    bs = bootstrap_ci(nets, n_boot=N_BOOT, block_size=1, rng_seed=SEED)
    return {
        "quadrant": name,
        "n_triggers": int(len(triggers_dates)),
        "n_trades": int(len(nets)),
        "net_mean_bp": s["mean_bp"],
        "gross_mean_bp": s["mean_bp"] + fee_rt * 1e4,
        "t": s["t"],
        "win": s["win"],
        "sharpe": s["sharpe"],
        "obs_t": fe.get("obs_t"),
        "null_mean_t": fe.get("null_mean_t"),
        "null_std_t": fe.get("null_std_t"),
        "signal_t_excess": fe.get("signal_t_excess"),
        "perm_p_one_sided_above": fe.get("perm_p_one_sided_above"),
        "perm_p_two_sided": fe.get("perm_p_two_sided"),
        "n_candidate_pool": fe.get("n_candidate"),
        "bootstrap_mean_bp": bs["mean"] * 1e4,
        "bootstrap_ci_lower_bp": bs["ci_lower"] * 1e4,
        "bootstrap_ci_upper_bp": bs["ci_upper"] * 1e4,
        "bootstrap_prob_positive": bs["prob_positive"],
        "_nets": nets.tolist(),
        "_syms": syms.tolist(),
        "_dates": [str(d) for d in dates],
    }


def per_quarter_breakdown(nets, syms, dates):
    if len(nets) == 0:
        return []
    dates_dt = pd.to_datetime(dates)
    out = []
    edges = [
        ("2024Q1", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-04-01")),
        ("2024Q2", pd.Timestamp("2024-04-01"), pd.Timestamp("2024-07-01")),
        ("2024Q3", pd.Timestamp("2024-07-01"), pd.Timestamp("2024-10-01")),
        ("2024Q4", pd.Timestamp("2024-10-01"), pd.Timestamp("2025-01-01")),
        ("2025Q1", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-04-01")),
        ("2025Q2", pd.Timestamp("2025-04-01"), pd.Timestamp("2025-07-01")),
        ("2025Q3", pd.Timestamp("2025-07-01"), pd.Timestamp("2025-10-01")),
        ("2025Q4", pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")),
        ("2026Q1", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01")),
        ("2026Q2", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")),
    ]
    for qname, qs, qe in edges:
        mask = (dates_dt >= qs) & (dates_dt < qe)
        sub = nets[mask]
        if len(sub) < 2:
            out.append({"quarter": qname, "n": int(len(sub)), "note": "insufficient"})
            continue
        out.append({"quarter": qname, **stats_block(sub)})
    return out


def per_symbol_breakdown(nets, syms, alt_list, pool, fee_rt: float):
    out = []
    n_pos = 0
    n_ci_pos = 0
    n_measurable = 0
    per_sym_p_values = {}
    for sym in alt_list:
        mask = syms == sym
        sub = nets[mask]
        if len(sub) < 2:
            out.append({"sym": sym, "n": int(len(sub)), "note": "insufficient"})
            continue
        n_measurable += 1
        sb = stats_block(sub)
        # bootstrap CI
        try:
            bs = bootstrap_ci(sub, n_boot=1000, block_size=1, rng_seed=SEED)
            ci_lo = bs["ci_lower"] * 1e4
            ci_pos = ci_lo > 0
        except Exception:
            ci_lo = None
            ci_pos = False
        # per-sym perm p (for Bonferroni)
        try:
            sym_fe = fee_aware_perm_test(
                observed_net_returns=sub,
                candidate_pool_returns=pool,
                fee_per_trade=fee_rt,
                n_perms=500,
                rng_seed=SEED,
            )
            sym_p = sym_fe.get("perm_p_one_sided_above")
        except Exception:
            sym_p = None
        if ci_pos:
            n_ci_pos += 1
        if sb["mean_bp"] > 0:
            n_pos += 1
        per_sym_p_values[sym] = sym_p
        out.append({
            "sym": sym,
            "n": sb["n"],
            "mean_bp": sb["mean_bp"],
            "t": sb["t"],
            "win": sb["win"],
            "ci_lower_bp": ci_lo,
            "ci_pos": bool(ci_pos),
            "perm_p_one_sided_above": sym_p,
        })
    return out, n_pos, n_ci_pos, n_measurable, per_sym_p_values


# ---------- Lesson #20 narrow-scope 4-cond ----------


def lesson20_b_held_out_replication(share_z, alts_fwd_by_hold, cutoff, pool, fee_rt, n_perms):
    """Cond b: split focus triggers by date into first-half / last-half, both must three-gate PASS."""
    alts_fwd = alts_fwd_by_hold[HOLD_DAYS]
    trig_dates = sorted(share_z[share_z >= cutoff].index)
    if len(trig_dates) < 6:
        return {"status": "INSUFFICIENT", "n_triggers": len(trig_dates)}
    midpoint = trig_dates[len(trig_dates) // 2]
    first_half = [d for d in trig_dates if d < midpoint]
    last_half = [d for d in trig_dates if d >= midpoint]

    def _three_gate(triggers):
        if len(triggers) < 3:
            return None
        res = run_quadrant("split", pd.Index(triggers), alts_fwd, pool, fee_rt=fee_rt, n_perms=n_perms)
        sigex = res.get("signal_t_excess")
        ci_lo = res.get("bootstrap_ci_lower_bp")
        perm_p = res.get("perm_p_one_sided_above")
        if sigex is None or ci_lo is None or perm_p is None:
            return None
        pass_flag = (sigex >= 2.0) and (ci_lo > 0) and (perm_p <= 0.10)
        return {
            "n_triggers": len(triggers),
            "n_trades": res.get("n_trades"),
            "signal_t_excess": sigex,
            "bootstrap_ci_lower_bp": ci_lo,
            "perm_p_one_sided_above": perm_p,
            "three_gate_pass": pass_flag,
        }

    first_res = _three_gate(first_half)
    last_res = _three_gate(last_half)
    pass_b = (first_res is not None and first_res["three_gate_pass"]) and \
             (last_res is not None and last_res["three_gate_pass"])
    return {
        "status": "MEASURED",
        "midpoint": str(midpoint.date()),
        "first_half": first_res,
        "last_half": last_res,
        "pass": bool(pass_b),
    }


def lesson20_c_bonferroni(per_sym_p_values, alpha=0.10):
    """Cond c: per-symbol min p_value * n_symbols <= alpha."""
    p_vals = [p for p in per_sym_p_values.values() if p is not None and not np.isnan(p)]
    if not p_vals:
        return {"status": "INSUFFICIENT", "pass": False}
    n_sym = len(p_vals)
    min_p = min(p_vals)
    p_adj = min(min_p * n_sym, 1.0)
    return {
        "status": "MEASURED",
        "n_symbols": n_sym,
        "min_p": min_p,
        "p_adj_bonferroni": p_adj,
        "alpha": alpha,
        "pass": bool(p_adj <= alpha),
    }


def lesson20_d_hold_sweep(share_z, alts_fwd_by_hold, cutoff, pool, fee_rt, n_perms):
    """Cond d: re-run at hold = 1d/2d/3d; require all 3 nets > 0 AND >=2/3 three-gate PASS."""
    out = {}
    pos_count = 0
    pass_count = 0
    trig_idx = share_z[share_z >= cutoff].index
    for h in HOLD_SWEEP:
        alts_fwd = alts_fwd_by_hold[h]
        res = run_quadrant(f"hold_{h}d", trig_idx, alts_fwd, pool, fee_rt=fee_rt, n_perms=n_perms)
        sigex = res.get("signal_t_excess")
        ci_lo = res.get("bootstrap_ci_lower_bp")
        perm_p = res.get("perm_p_one_sided_above")
        net_bp = res.get("net_mean_bp")
        three_gate = (
            sigex is not None and sigex >= 2.0
            and ci_lo is not None and ci_lo > 0
            and perm_p is not None and perm_p <= 0.10
        )
        if net_bp is not None and net_bp > 0:
            pos_count += 1
        if three_gate:
            pass_count += 1
        out[f"hold_{h}d"] = {
            "n_trades": res.get("n_trades"),
            "net_mean_bp": net_bp,
            "gross_mean_bp": res.get("gross_mean_bp"),
            "signal_t_excess": sigex,
            "bootstrap_ci_lower_bp": ci_lo,
            "perm_p_one_sided_above": perm_p,
            "three_gate_pass": three_gate,
        }
    pass_d = (pos_count == len(HOLD_SWEEP)) and (pass_count >= 2)
    out["sign_pos_count"] = pos_count
    out["three_gate_pass_count"] = pass_count
    out["pass"] = bool(pass_d)
    return out


# ---------- life-changing 4-dim ----------


def life_changing_4dim(focus_8bp, focus_50bp, n_total_days, universe_size):
    """Measure trades/yr, edge/trade, capital util, sharpe."""
    n_trades = focus_8bp.get("n_trades", 0)
    n_triggers = focus_8bp.get("n_triggers", 0)
    years = n_total_days / 365.25 if n_total_days else 1
    trades_per_yr = n_trades / years if years > 0 else 0
    # per-trade edge — use 50bp stress net mean (life-changing fee model)
    edge_pct = (focus_50bp.get("net_mean_bp") or 0) / 100.0  # bp -> %
    # capital util — fraction of days × fraction of universe traded
    # avg cells per trigger day = n_trades / n_triggers
    cells_per_day = n_trades / n_triggers if n_triggers > 0 else 0
    trigger_day_frac = n_triggers / n_total_days if n_total_days > 0 else 0
    sym_alloc_frac = cells_per_day / universe_size if universe_size > 0 else 0
    capital_util_pct = trigger_day_frac * sym_alloc_frac * 100.0
    # sharpe — focus_8bp.sharpe is per-trade; annualize approx daily sqrt(252)
    per_trade_sharpe = focus_8bp.get("sharpe", 0)
    annual_sharpe = per_trade_sharpe * np.sqrt(252) if per_trade_sharpe else 0
    return {
        "trades_per_yr": trades_per_yr,
        "trades_per_yr_pass": trades_per_yr >= 12,
        "per_trade_edge_pct_at_50bp": edge_pct,
        "per_trade_edge_pass": edge_pct >= 2.0,
        "capital_util_pct": capital_util_pct,
        "capital_util_pass": capital_util_pct >= 30.0,
        "annualized_sharpe": annual_sharpe,
        "sharpe_pass": annual_sharpe >= 1.5,
        "gate_pass": (
            trades_per_yr >= 12
            and edge_pct >= 2.0
            and capital_util_pct >= 30.0
            and annual_sharpe >= 1.5
        ),
    }


# ---------- main ----------


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "paradigm_n": 95,
        "phase": "R-1",
        "dispatch_mode": "ad_hoc_user_explicit_mint_full_data",
        "dispatch_date": "2026-05-19",
        "prior_run_reference": (
            "paradigm 94 R-1 Mint full-data rerun (commit fc61755f, "
            "verdict=BROAD_FALSIFIED_DIRECTION_INVERTED). Mirror metric "
            "sigex=+6.86 / gross=+96.97bp / ci_lower=+59.77bp -> paradigm 95 "
            "independent re-test per Lesson #8 mirror antipattern."
        ),
        "hypothesis": (
            "BTC daily USD-volume share z(30d) >= +1.5 (BTC dominance peak) "
            "-> LONG 13 alts entry next-day open, hold 1d (24h), exit close. "
            "Mechanism: BTC volume share peak = BTC dominance momentum / "
            "bull regime confirmation / risk-on signal; alts catch up +1d "
            "rotation cascade."
        ),
        "config": {
            "btc_symbol": BTC,
            "alts": ALTS,
            "extras_volume_denominator_only": EXTRA,
            "universe_size": len(UNIVERSE),
            "z_window_days": Z_WINDOW,
            "focus_cutoffs_tried": FOCUS_Z_CUTOFFS_HIGH,
            "default_focus_cutoff": DEFAULT_FOCUS_CUTOFF,
            "default_mirror_cutoff": DEFAULT_MIRROR_CUTOFF,
            "hold_days": HOLD_DAYS,
            "hold_sweep": HOLD_SWEEP,
            "fee_round_trip": FEE_RT,
            "fee_round_trip_stress": FEE_RT_STRESS,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "data_source": "mint joblib ohlcv_cache 1m -> 1d resample",
        },
        "lesson_grid_applied": {
            "8_mirror_antipattern": (
                "paradigm 94 mirror evidence triggers independent re-test "
                "with separate codepath + new candidate pool"
            ),
            "11_sample_density": (
                "per-cell >=30 floor + cutoff fallback chain +1.5/+1.2/+1.0"
            ),
            "16_concentration_gate": "per-quarter t + per-symbol bootstrap CI",
            "19_symmetric_negative": (
                "2-quadrant (focus z>=+1.5 LONG, mirror z<=-1.5 LONG = "
                "paradigm 94 focus already broad-falsified)"
            ),
            "20_narrow_scope_4cond": (
                "a 4-gate / b held-out 50/50 split / c Bonferroni p_adj / "
                "d hold sweep 1d/2d/3d sign consistency"
            ),
            "21_axis_stacking": "single statistic (volume share z) N/A",
            "22_stateful_detector": "rolling z is not stateful N/A",
            "24_boundary_horizon": "level crossing instantaneous N/A",
            "27_28_entry_substrate": "internal market structure N/A",
            "29_cross_proxy": "obs=share_z + fund=abs_btc_vol_z both measured",
            "life_changing_4dim": "trades/yr + edge + capital util + sharpe",
        },
        "family_distinct_check": {
            "5m_microstructure_single_domain": "different (daily aggregation)",
            "kr_equity_post_earnings": "different (crypto perp)",
            "geometric_path_metrics": "different (volume share, not path)",
            "funding_oi_joint_squeeze": "different (volume only)",
            "btc_eth_5m_corr_breakdown": "different (daily, no corr)",
            "paradigm_94_low_share_compression": (
                "different direction class (HIGH vs LOW share); same statistic "
                "family but distinct mechanism (dominance peak vs compression "
                "rotation); paradigm 94 R-1 was BROAD_FALSIFIED_DIRECTION_INVERTED"
            ),
            "verdict": "family_distinct_inverted_direction_independent",
        },
    }

    log.info("Loading 1m close+volume for %d syms from Mint joblib cache ...", len(UNIVERSE))
    raw_data = {}
    for sym in UNIVERSE:
        t0 = time.time()
        df1m = load_ohlcv_1m_cached(sym)
        if df1m.empty:
            log.warning("[%s] empty", sym)
            continue
        df1m = df1m[["close", "volume"]].copy()
        df1m["close"] = pd.to_numeric(df1m["close"], errors="coerce")
        df1m["volume"] = pd.to_numeric(df1m["volume"], errors="coerce")
        daily = resample_to_daily(df1m)
        if daily.empty:
            log.warning("[%s] daily resample empty", sym)
            continue
        raw_data[sym] = daily
        log.info("[%s] 1m=%d -> 1d=%d days in %.1fs (range %s..%s)",
                 sym, len(df1m), len(daily), time.time() - t0,
                 daily.index[0].date(), daily.index[-1].date())

    if BTC not in raw_data:
        raise SystemExit("BTC missing — cannot compute signal")

    all_dates = None
    for sym, df in raw_data.items():
        if all_dates is None:
            all_dates = set(df.index)
        else:
            all_dates &= set(df.index)
    if not all_dates:
        raise SystemExit("no common dates across universe")
    common_dates = sorted(all_dates)
    log.info("common dates intersection: %d days (%s..%s)",
             len(common_dates), common_dates[0].date(), common_dates[-1].date())

    vol_panel = pd.DataFrame({
        sym: raw_data[sym].loc[common_dates, "vol_usd"]
        for sym in raw_data
    })
    total_vol = vol_panel.sum(axis=1)
    btc_share = vol_panel[BTC] / total_vol
    share_mu = btc_share.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    share_sd = btc_share.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    share_z = ((btc_share - share_mu) / share_sd).dropna()

    btc_vol = vol_panel[BTC]
    btc_vol_mu = btc_vol.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
    btc_vol_sd = btc_vol.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
    btc_vol_z = ((btc_vol - btc_vol_mu) / btc_vol_sd).dropna()

    out["data_window"] = {
        "common_dates_total": len(common_dates),
        "common_first": str(common_dates[0].date()),
        "common_last": str(common_dates[-1].date()),
        "usable_after_warmup": int(len(share_z)),
        "share_z_first": str(share_z.index[0].date()),
        "share_z_last": str(share_z.index[-1].date()),
        "btc_share_mean": float(btc_share.mean()),
        "btc_share_std": float(btc_share.std()),
    }
    log.info("share_z usable rows=%d range %s..%s", len(share_z),
             share_z.index[0].date(), share_z.index[-1].date())

    # forward returns for hold=1d (primary) AND hold sweep
    log.info("Computing per-alt forward returns for hold=%s ...", HOLD_SWEEP)
    alts_fwd_by_hold = {}
    for h in HOLD_SWEEP:
        alts_fwd_by_hold[h] = {}
        for sym in ALTS:
            if sym not in raw_data:
                continue
            alts_fwd_by_hold[h][sym] = compute_alt_forward_returns(raw_data[sym], hold_days=h)
    alts_fwd = alts_fwd_by_hold[HOLD_DAYS]
    out["alts_with_fwd"] = list(alts_fwd.keys())

    # =====================================================
    # OBS PROXY TRACK — HIGH side focus
    # =====================================================
    log.info("=" * 60)
    log.info("OBS PROXY TRACK: share_z >= +cutoff (BTC dominance peak)")
    log.info("=" * 60)

    obs_focus_results = {}
    chosen_focus_cutoff = None
    for cutoff in FOCUS_Z_CUTOFFS_HIGH:
        trig_dates = share_z[share_z >= cutoff].index
        n_trig = len(trig_dates)
        log.info("OBS focus cutoff z>=%.2f -> %d trigger days", cutoff, n_trig)
        obs_focus_results[f"cutoff_+{cutoff}"] = {
            "n_triggers": int(n_trig),
            "first": str(trig_dates[0].date()) if n_trig else None,
            "last": str(trig_dates[-1].date()) if n_trig else None,
        }
        if n_trig * len(alts_fwd) >= 30 and chosen_focus_cutoff is None:
            chosen_focus_cutoff = cutoff

    out["obs_focus_cutoff_sweep"] = obs_focus_results

    if chosen_focus_cutoff is None:
        log.warning("OBS sample insufficient at all cutoffs")
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = "all focus cutoffs (+1.5,+1.2,+1.0) yield <30 trades"
        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return

    out["obs_chosen_focus_cutoff"] = chosen_focus_cutoff

    obs_focus_dates = share_z[share_z >= chosen_focus_cutoff].index
    obs_mirror_dates = share_z[share_z <= DEFAULT_MIRROR_CUTOFF].index

    # Candidate pool: exclude all extreme |z|>1
    obs_exclude = set(share_z[share_z.abs() >= 1.0].index)
    obs_pool = build_candidate_pool(alts_fwd, obs_exclude, n_samples=N_POOL_SAMPLES, seed=SEED)
    log.info("OBS candidate pool size=%d", len(obs_pool))

    obs_focus_8bp = run_quadrant("obs_focus_8bp", obs_focus_dates, alts_fwd, obs_pool,
                                   fee_rt=FEE_RT, n_perms=N_PERMS)
    obs_mirror_8bp = run_quadrant("obs_mirror_8bp", obs_mirror_dates, alts_fwd, obs_pool,
                                    fee_rt=FEE_RT, n_perms=N_PERMS)
    obs_focus_50bp = run_quadrant("obs_focus_50bp", obs_focus_dates, alts_fwd, obs_pool,
                                    fee_rt=FEE_RT_STRESS, n_perms=N_PERMS)

    log.info("OBS focus @8bp: n=%s mean=%.2f bp sigex=%s ci_lo=%s perm_p=%s",
             obs_focus_8bp.get("n_trades"), obs_focus_8bp.get("net_mean_bp", float("nan")),
             obs_focus_8bp.get("signal_t_excess"), obs_focus_8bp.get("bootstrap_ci_lower_bp"),
             obs_focus_8bp.get("perm_p_one_sided_above"))
    log.info("OBS mirror @8bp: n=%s mean=%.2f bp sigex=%s",
             obs_mirror_8bp.get("n_trades"), obs_mirror_8bp.get("net_mean_bp", float("nan")),
             obs_mirror_8bp.get("signal_t_excess"))
    log.info("OBS focus @50bp: n=%s mean=%.2f bp sigex=%s",
             obs_focus_50bp.get("n_trades"), obs_focus_50bp.get("net_mean_bp", float("nan")),
             obs_focus_50bp.get("signal_t_excess"))

    nets = np.array(obs_focus_8bp.get("_nets", []))
    syms = np.array(obs_focus_8bp.get("_syms", []))
    dates_arr = np.array(obs_focus_8bp.get("_dates", []))
    obs_quarters = per_quarter_breakdown(nets, syms, dates_arr) if len(nets) else []
    obs_per_sym, obs_pos, obs_ci_pos, obs_measurable, obs_per_sym_p = per_symbol_breakdown(
        nets, syms, ALTS, obs_pool, FEE_RT
    )
    q_measurable = sum(1 for q in obs_quarters if "mean_bp" in q)
    q_pos_t = sum(1 for q in obs_quarters if q.get("t", 0) > 0)
    q_pos_t_ratio = q_pos_t / q_measurable if q_measurable > 0 else None
    sym_ci_pos_ratio = obs_ci_pos / obs_measurable if obs_measurable > 0 else None
    n_sym_ci_pos = obs_ci_pos

    # mirror diagnostics
    mirror_nets = np.array(obs_mirror_8bp.get("_nets", []))
    mirror_syms = np.array(obs_mirror_8bp.get("_syms", []))
    mirror_dates = np.array(obs_mirror_8bp.get("_dates", []))
    mirror_quarters = per_quarter_breakdown(mirror_nets, mirror_syms, mirror_dates) if len(mirror_nets) else []
    if len(mirror_nets):
        mirror_per_sym, _, mirror_ci_pos, mirror_measurable, _ = per_symbol_breakdown(
            mirror_nets, mirror_syms, ALTS, obs_pool, FEE_RT
        )
    else:
        mirror_per_sym, mirror_ci_pos, mirror_measurable = [], 0, 0
    mq_measurable = sum(1 for q in mirror_quarters if "mean_bp" in q)
    mq_pos_t = sum(1 for q in mirror_quarters if q.get("t", 0) > 0)
    mq_pos_t_ratio = mq_pos_t / mq_measurable if mq_measurable > 0 else None
    msym_ci_pos_ratio = mirror_ci_pos / mirror_measurable if mirror_measurable > 0 else None

    out["obs"] = {
        "focus_8bp": {k: v for k, v in obs_focus_8bp.items() if not k.startswith("_")},
        "mirror_8bp": {k: v for k, v in obs_mirror_8bp.items() if not k.startswith("_")},
        "focus_50bp": {k: v for k, v in obs_focus_50bp.items() if not k.startswith("_")},
        "concentration": {
            "per_quarter": obs_quarters,
            "per_symbol": obs_per_sym,
            "q_measurable": q_measurable,
            "q_pos_t": q_pos_t,
            "q_pos_t_ratio": q_pos_t_ratio,
            "sym_measurable": obs_measurable,
            "sym_ci_pos": n_sym_ci_pos,
            "sym_ci_pos_ratio": sym_ci_pos_ratio,
            "gate_pass": (
                q_pos_t_ratio is not None and q_pos_t_ratio >= 0.5
                and sym_ci_pos_ratio is not None and sym_ci_pos_ratio >= 0.30
                and n_sym_ci_pos >= 3
            ),
        },
        "mirror_concentration": {
            "per_quarter": mirror_quarters,
            "per_symbol": mirror_per_sym,
            "q_measurable": mq_measurable,
            "q_pos_t": mq_pos_t,
            "q_pos_t_ratio": mq_pos_t_ratio,
            "sym_measurable": mirror_measurable,
            "sym_ci_pos": mirror_ci_pos,
            "sym_ci_pos_ratio": msym_ci_pos_ratio,
            "gate_pass": (
                mq_pos_t_ratio is not None and mq_pos_t_ratio >= 0.5
                and msym_ci_pos_ratio is not None and msym_ci_pos_ratio >= 0.30
                and mirror_ci_pos >= 3
            ),
        },
    }

    # =====================================================
    # FUND PROXY TRACK — HIGH side
    # =====================================================
    log.info("=" * 60)
    log.info("FUND PROXY TRACK: btc_vol_z >= +cutoff (BTC absolute vol peak)")
    log.info("=" * 60)

    fund_focus_results = {}
    chosen_fund_cutoff = None
    for cutoff in FOCUS_Z_CUTOFFS_HIGH:
        trig_dates = btc_vol_z[btc_vol_z >= cutoff].index
        n_trig = len(trig_dates)
        log.info("FUND focus cutoff z>=%.2f -> %d trigger days", cutoff, n_trig)
        fund_focus_results[f"cutoff_+{cutoff}"] = {"n_triggers": int(n_trig)}
        if n_trig * len(alts_fwd) >= 30 and chosen_fund_cutoff is None:
            chosen_fund_cutoff = cutoff

    out["fund_focus_cutoff_sweep"] = fund_focus_results

    if chosen_fund_cutoff is None:
        log.warning("FUND sample insufficient at all cutoffs")
        out["fund"] = {"sample_status": "SAMPLE_INSUFFICIENT_FUND",
                       "note": "fund track unable to test cross-proxy"}
    else:
        out["fund_chosen_focus_cutoff"] = chosen_fund_cutoff
        fund_focus_dates = btc_vol_z[btc_vol_z >= chosen_fund_cutoff].index
        fund_mirror_dates = btc_vol_z[btc_vol_z <= DEFAULT_MIRROR_CUTOFF].index
        fund_exclude = set(btc_vol_z[btc_vol_z.abs() >= 1.0].index)
        fund_pool = build_candidate_pool(alts_fwd, fund_exclude, n_samples=N_POOL_SAMPLES, seed=SEED)
        fund_focus_8bp = run_quadrant("fund_focus_8bp", fund_focus_dates, alts_fwd, fund_pool,
                                        fee_rt=FEE_RT, n_perms=N_PERMS)
        fund_mirror_8bp = run_quadrant("fund_mirror_8bp", fund_mirror_dates, alts_fwd, fund_pool,
                                         fee_rt=FEE_RT, n_perms=N_PERMS)
        log.info("FUND focus @8bp: n=%s mean=%.2f bp sigex=%s",
                 fund_focus_8bp.get("n_trades"), fund_focus_8bp.get("net_mean_bp", float("nan")),
                 fund_focus_8bp.get("signal_t_excess"))
        log.info("FUND mirror @8bp: n=%s mean=%.2f bp sigex=%s",
                 fund_mirror_8bp.get("n_trades"), fund_mirror_8bp.get("net_mean_bp", float("nan")),
                 fund_mirror_8bp.get("signal_t_excess"))
        out["fund"] = {
            "focus_8bp": {k: v for k, v in fund_focus_8bp.items() if not k.startswith("_")},
            "mirror_8bp": {k: v for k, v in fund_mirror_8bp.items() if not k.startswith("_")},
        }

        obs_focus_set = set(obs_focus_dates)
        fund_focus_set = set(fund_focus_dates)
        both = obs_focus_set & fund_focus_set
        union = obs_focus_set | fund_focus_set
        jaccard = (len(both) / len(union)) if union else 0
        out["fund"]["cross_proxy_overlap"] = {
            "obs_n": len(obs_focus_set),
            "fund_n": len(fund_focus_set),
            "intersection": len(both),
            "jaccard": jaccard,
            "redundancy_warning": jaccard >= 0.7,
        }
        log.info("cross-proxy overlap: obs=%d fund=%d intersect=%d jaccard=%.3f",
                 len(obs_focus_set), len(fund_focus_set), len(both), jaccard)

    # =====================================================
    # LESSON #20 NARROW-SCOPE 4-COND
    # =====================================================
    log.info("=" * 60)
    log.info("LESSON #20 NARROW-SCOPE 4-COND a/b/c/d")
    log.info("=" * 60)

    # cond (a): 4-gate at default cutoff
    sigex_a = obs_focus_8bp.get("signal_t_excess")
    ci_lo_a = obs_focus_8bp.get("bootstrap_ci_lower_bp")
    perm_p_a = obs_focus_8bp.get("perm_p_one_sided_above")
    sigex_50bp = obs_focus_50bp.get("signal_t_excess")
    cond_a_pass = (
        sigex_a is not None and sigex_a >= 2.0
        and ci_lo_a is not None and ci_lo_a > 0
        and perm_p_a is not None and perm_p_a <= 0.10
        and sigex_50bp is not None and sigex_50bp >= 2.0
    )
    log.info("cond (a) 4-gate: sigex=%.2f ci=%.2f p=%.3f 50bp_sigex=%.2f -> %s",
             sigex_a or 0, ci_lo_a or 0, perm_p_a or 1, sigex_50bp or 0, cond_a_pass)

    # cond (b): held-out 50/50 replication
    cond_b = lesson20_b_held_out_replication(share_z, alts_fwd_by_hold, chosen_focus_cutoff,
                                                obs_pool, FEE_RT, N_PERMS)
    log.info("cond (b) held-out: %s", cond_b.get("pass"))

    # cond (c): Bonferroni
    cond_c = lesson20_c_bonferroni(obs_per_sym_p, alpha=0.10)
    log.info("cond (c) Bonferroni: min_p=%s n=%s p_adj=%s pass=%s",
             cond_c.get("min_p"), cond_c.get("n_symbols"),
             cond_c.get("p_adj_bonferroni"), cond_c.get("pass"))

    # cond (d): hold sweep
    cond_d = lesson20_d_hold_sweep(share_z, alts_fwd_by_hold, chosen_focus_cutoff,
                                      obs_pool, FEE_RT, N_PERMS)
    log.info("cond (d) hold sweep: sign_pos=%s/%s three_gate=%s/%s pass=%s",
             cond_d.get("sign_pos_count"), len(HOLD_SWEEP),
             cond_d.get("three_gate_pass_count"), len(HOLD_SWEEP), cond_d.get("pass"))

    narrow_scope_4cond_all_pass = (
        cond_a_pass
        and bool(cond_b.get("pass"))
        and bool(cond_c.get("pass"))
        and bool(cond_d.get("pass"))
    )

    out["lesson20_narrow_scope"] = {
        "cond_a_4_gate_pass": bool(cond_a_pass),
        "cond_b_held_out_replication": cond_b,
        "cond_c_bonferroni": cond_c,
        "cond_d_hold_sweep": cond_d,
        "all_4_cond_pass": narrow_scope_4cond_all_pass,
    }

    # =====================================================
    # LIFE-CHANGING 4-DIM
    # =====================================================
    n_total_days = len(common_dates)
    universe_size = len(ALTS)
    lc4 = life_changing_4dim(obs_focus_8bp, obs_focus_50bp, n_total_days, universe_size)
    out["life_changing_4dim"] = lc4
    log.info("life-changing 4-dim: trades/yr=%.1f edge=%.2f%% util=%.1f%% sharpe=%.2f -> gate=%s",
             lc4["trades_per_yr"], lc4["per_trade_edge_pct_at_50bp"],
             lc4["capital_util_pct"], lc4["annualized_sharpe"], lc4["gate_pass"])

    # =====================================================
    # 3-GATE VERDICT
    # =====================================================
    sigex = obs_focus_8bp.get("signal_t_excess")
    ci_lo = obs_focus_8bp.get("bootstrap_ci_lower_bp")
    perm_p = obs_focus_8bp.get("perm_p_one_sided_above")
    gross_mean_bp = obs_focus_8bp.get("gross_mean_bp")

    def _has(v):
        if v is None:
            return False
        if isinstance(v, float) and np.isnan(v):
            return False
        return True

    criteria = {
        "obs_sigex_ge_2": _has(sigex) and sigex >= 2.0,
        "obs_ci_lower_pos": _has(ci_lo) and ci_lo > 0,
        "obs_perm_p_le_0p10": _has(perm_p) and perm_p <= 0.10,
        "obs_concentration_pass": out["obs"]["concentration"]["gate_pass"],
        "obs_focus_50bp_signal_t_excess_ge_2": (
            _has(sigex_50bp) and sigex_50bp >= 2.0
        ),
        "gross_above_fee_floor": _has(gross_mean_bp) and gross_mean_bp >= 16.0,
        "obs_mirror_fails_or_inverted": (
            not _has(obs_mirror_8bp.get("signal_t_excess"))
            or (obs_mirror_8bp.get("signal_t_excess") or 0) < 2.0
        ),
        "narrow_scope_4cond_all_pass": narrow_scope_4cond_all_pass,
        "life_changing_4dim_pass": lc4["gate_pass"],
    }

    fund_three_gate = False
    if "focus_8bp" in out.get("fund", {}):
        fund_sigex = out["fund"]["focus_8bp"].get("signal_t_excess")
        fund_ci_lo = out["fund"]["focus_8bp"].get("bootstrap_ci_lower_bp")
        fund_perm_p = out["fund"]["focus_8bp"].get("perm_p_one_sided_above")
        fund_three_gate = (
            _has(fund_sigex) and fund_sigex >= 2.0
            and _has(fund_ci_lo) and fund_ci_lo > 0
            and _has(fund_perm_p) and fund_perm_p <= 0.10
        )
    criteria["fund_three_gate_pass"] = fund_three_gate
    out["criteria"] = criteria

    obs_three_gate = criteria["obs_sigex_ge_2"] and criteria["obs_ci_lower_pos"] and criteria["obs_perm_p_le_0p10"]

    # Verdict resolution tree
    if not criteria["gross_above_fee_floor"]:
        verdict = "BROAD_FALSIFIED_FEE_FLOOR"
        reason = f"focus gross {gross_mean_bp:.2f}bp < 16bp fee floor"
    elif obs_three_gate and not criteria["obs_mirror_fails_or_inverted"]:
        verdict = "BROAD_FALSIFIED"
        reason = "both focus and mirror show signal_t_excess>=2.0 — direction not isolated"
    elif obs_three_gate:
        if not criteria["obs_concentration_pass"]:
            # Lesson #20 path
            if narrow_scope_4cond_all_pass:
                verdict = "NARROW_SCOPE_CANDIDATE"
                reason = (
                    f"3-gate PASS + Concentration FAIL "
                    f"(sym_ci_pos_ratio={sym_ci_pos_ratio:.3f}) "
                    f"+ Lesson #20 a/b/c/d ALL PASS -> narrow-scope candidate"
                )
            else:
                verdict = "CONCENTRATED_R1_PASS"
                reason = (
                    f"3-gate PASS but Concentration FAIL "
                    f"(q_pos_t_ratio={q_pos_t_ratio}, "
                    f"sym_ci_pos_ratio={sym_ci_pos_ratio}, "
                    f"n_sym_ci_pos={n_sym_ci_pos}); "
                    f"Lesson #20 4-cond not all pass "
                    f"(a={cond_a_pass}, b={cond_b.get('pass')}, "
                    f"c={cond_c.get('pass')}, d={cond_d.get('pass')})"
                )
        elif not fund_three_gate:
            verdict = "SINGLE_PROXY_TRAP_OBS_ONLY"
            reason = "obs proxy 3-gate PASS but fund proxy 3-gate FAIL (Lesson #29)"
        else:
            jacc = out.get("fund", {}).get("cross_proxy_overlap", {}).get("jaccard", 0)
            if jacc >= 0.7:
                verdict = "SINGLE_PROXY_TRAP_REDUNDANT"
                reason = f"obs and fund proxies essentially redundant (jaccard={jacc:.2f} >= 0.7)"
            else:
                verdict = "PASS_R1_CROSS_PROXY_PROMOTE_R2"
                reason = "obs+fund 3-gate PASS + Concentration PASS + cross-proxy non-redundant"
    else:
        verdict = "FAIL_THREE_GATE"
        reason = (
            f"focus 3-gate FAIL: sigex={sigex}, ci_lower_bp={ci_lo}, perm_p_above={perm_p}"
        )

    out["verdict"] = verdict
    out["verdict_reason"] = reason
    out["three_gate_pass"] = obs_three_gate
    out["concentration_gate_pass"] = criteria["obs_concentration_pass"]
    out["fund_three_gate_pass"] = fund_three_gate
    out["lesson20_narrow_scope_all_pass"] = narrow_scope_4cond_all_pass
    out["life_changing_4dim_pass"] = lc4["gate_pass"]

    # paradigm 94 mirror evidence consistency check
    out["paradigm_94_mirror_consistency_check"] = {
        "paradigm_94_mirror_sigex": 6.86,
        "paradigm_94_mirror_gross_bp": 96.97,
        "paradigm_94_mirror_ci_lower_bp": 59.77,
        "paradigm_94_mirror_n_trades": 702,
        "paradigm_95_focus_sigex": sigex,
        "paradigm_95_focus_gross_bp": gross_mean_bp,
        "paradigm_95_focus_ci_lower_bp": ci_lo,
        "paradigm_95_focus_n_trades": obs_focus_8bp.get("n_trades"),
        "consistency_note": (
            "paradigm 94 mirror = paradigm 95 focus (same trigger, same direction). "
            "Differences may arise from independent candidate pool seeding and "
            "minor data window shifts."
        ),
    }

    out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 verdict=%s reason=%s", verdict, reason)
    log.info("wall-clock=%.2f min, output=%s", out["wall_clock_min"], OUT_PATH)


if __name__ == "__main__":
    main()
