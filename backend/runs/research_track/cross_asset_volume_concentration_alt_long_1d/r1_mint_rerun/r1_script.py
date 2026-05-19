"""R-1 PoC — cross_asset_volume_concentration_alt_long_1d (Mint full-data re-run).

Hypothesis (single sentence)
----------------------------
BTC daily USD-volume share (= BTC_vol_usd / sum(14-sym vol_usd)) 30d rolling
z-score <= -1.5 (BTC share compression = alt rotation leading indicator)
  -> LONG 13 alts at next-day open, hold +1d (24h), exit at close.

Cross-proxy track (Lesson #29)
------------------------------
- obs proxy   = volume share fraction z-score (transform)
- fund proxy  = BTC absolute USD-volume 30d z-score (raw flow magnitude)
Both must independently three-gate PASS to satisfy Lesson #29.

Symmetric Negative Test (Lesson #19)
------------------------------------
- focus     : share_z <= -1.5 LONG  (concentration -> rotation)
- mirror    : share_z >= +1.5 LONG  (BTC dominance -> alt suppression hypothesis flipped)
Both report; mirror serves as falsification null.

Differences vs prior local R-1 (2026-05-18 23:07 KST)
-----------------------------------------------------
- Data source: Mint joblib ohlcv_cache (2024-01-02 ~ 2026-05-12, ~862 days)
  vs prior local DB intersection 72 days (2026-01-21 ~ 2026-04-02).
- Universe: 14 syms (BTC + 13 alts) — 12 EXTRA boost syms not in Mint joblib cache;
  load-from-DB cost prohibitive within R-1 wall-clock budget. Denominator universe
  matches paradigm 69 validated set, lesson #11 sample density restored via 12x window.

Output
------
backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_mint_rerun/r1_metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "research"))

from _ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from _perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("xavc_r1_mint")

PARADIGM = "cross_asset_volume_concentration_alt_long_1d"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM / "r1_mint_rerun"
OUT_PATH = OUT_DIR / "r1_metrics.json"

BTC = "BTCUSDT"
# 13 alts (paradigm 69 validated set) — LONG direction
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
# 12 EXTRA boost syms not available in Mint joblib cache — omitted for this R-1.
# Denominator universe = 14 syms (BTC + 13 alts) which matches paradigm 69
# validated cohort. Lesson #11 sample density is restored via 12x data window.
EXTRA = []
UNIVERSE = [BTC] + ALTS + EXTRA  # 14 syms

# config
Z_WINDOW = 30  # 30 days rolling
FOCUS_Z_CUTOFFS = [-1.5, -1.2, -1.0]  # primary then fallback
DEFAULT_FOCUS_CUTOFF = -1.5
DEFAULT_MIRROR_CUTOFF = +1.5
HOLD_DAYS = 1
FEE_RT = 0.0008
FEE_RT_STRESS = 0.0050

N_PERMS = 1000
N_BOOT = 2000
N_POOL_SAMPLES = 20000
SEED = 42


# ---------- data ----------


def resample_to_daily(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1m -> 1d UTC. Returns daily close (last) + vol_usd (sum of close*volume)."""
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


def _t_stat(arr: np.ndarray) -> float:
    n = len(arr)
    if n < 2:
        return 0.0
    sd = arr.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return 0.0
    return float(arr.mean() / sd * np.sqrt(n))


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


# ---------- trade simulation ----------


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
    # 2.4yr window: span 2024Q1 ~ 2026Q2 (10 quarters)
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
    for sym in alt_list:
        mask = syms == sym
        sub = nets[mask]
        if len(sub) < 2:
            out.append({"sym": sym, "n": int(len(sub)), "note": "insufficient"})
            continue
        n_measurable += 1
        sb = stats_block(sub)
        try:
            bs = bootstrap_ci(sub, n_boot=1000, block_size=1, rng_seed=SEED)
            ci_lo = bs["ci_lower"] * 1e4
            ci_pos = ci_lo > 0
        except Exception:
            ci_lo = None
            ci_pos = False
        if ci_pos:
            n_ci_pos += 1
        if sb["mean_bp"] > 0:
            n_pos += 1
        out.append({
            "sym": sym,
            "n": sb["n"],
            "mean_bp": sb["mean_bp"],
            "t": sb["t"],
            "win": sb["win"],
            "ci_lower_bp": ci_lo,
            "ci_pos": bool(ci_pos),
        })
    return out, n_pos, n_ci_pos, n_measurable


def main():
    t_start = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "paradigm": PARADIGM,
        "phase": "R-1_mint_rerun",
        "dispatch_mode": "ad_hoc_user_explicit_mint_full_data",
        "dispatch_date": "2026-05-19",
        "prior_run_reference": "r1_metrics.json (local 72d, verdict=BROAD_FALSIFIED_FEE_FLOOR)",
        "hypothesis": (
            "BTC daily USD-volume share z(30d) <= -1.5 -> LONG 13 alts entry next-day open, "
            "hold 1d (24h), exit close. Compression of BTC volume share = alt rotation leading indicator."
        ),
        "config": {
            "btc_symbol": BTC,
            "alts": ALTS,
            "extras_volume_denominator_only": EXTRA,
            "universe_size": len(UNIVERSE),
            "z_window_days": Z_WINDOW,
            "focus_cutoffs_tried": FOCUS_Z_CUTOFFS,
            "default_focus_cutoff": DEFAULT_FOCUS_CUTOFF,
            "default_mirror_cutoff": DEFAULT_MIRROR_CUTOFF,
            "hold_days": HOLD_DAYS,
            "fee_round_trip": FEE_RT,
            "fee_round_trip_stress": FEE_RT_STRESS,
            "n_perms": N_PERMS,
            "n_boot": N_BOOT,
            "data_source": "mint joblib ohlcv_cache 1m -> 1d resample",
        },
        "lesson_grid_applied": {
            "11_sample_density": "per-cell >=30 floor + cutoff fallback chain -1.5/-1.2/-1.0; restored via 12x window vs local",
            "16_concentration_gate": "per-quarter t + per-symbol bootstrap CI emitted",
            "19_symmetric_negative": "2-quadrant (focus z<=-1.5 LONG, mirror z>=+1.5 LONG)",
            "21_axis_stacking": "single statistic (volume share z) N/A",
            "22_stateful_detector": "rolling z is not stateful N/A",
            "24_boundary_horizon": "level crossing instantaneous N/A",
            "27_28_entry_substrate": "internal market structure N/A",
            "29_cross_proxy": "obs=share_z + fund=abs_btc_vol_z both measured",
        },
        "family_distinct_check": {
            "5m_microstructure_single_domain": "different (daily aggregation)",
            "kr_equity_post_earnings": "different (crypto perp)",
            "geometric_path_metrics": "different (volume share, not path)",
            "funding_oi_joint_squeeze": "different (volume only)",
            "btc_eth_5m_corr_breakdown": "different (daily, no corr)",
            "verdict": "family_distinct_new_transform_class",
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
        # ensure close+volume numeric
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

    # universe-level intersection of dates
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

    log.info("Computing per-alt forward 1d returns ...")
    alts_fwd = {}
    for sym in ALTS:
        if sym not in raw_data:
            continue
        alts_fwd[sym] = compute_alt_forward_returns(raw_data[sym], hold_days=HOLD_DAYS)
    out["alts_with_fwd"] = list(alts_fwd.keys())

    # =====================================================
    # OBS PROXY TRACK
    # =====================================================
    log.info("=" * 60)
    log.info("OBS PROXY TRACK: volume share fraction z")
    log.info("=" * 60)

    obs_focus_results = {}
    chosen_focus_cutoff = None
    for cutoff in FOCUS_Z_CUTOFFS:
        trig_dates = share_z[share_z <= cutoff].index
        n_trig = len(trig_dates)
        log.info("OBS focus cutoff z<=%.2f -> %d trigger days", cutoff, n_trig)
        obs_focus_results[f"cutoff_{cutoff}"] = {"n_triggers": int(n_trig),
                                                   "first": str(trig_dates[0].date()) if n_trig else None,
                                                   "last": str(trig_dates[-1].date()) if n_trig else None}
        if n_trig * len(alts_fwd) >= 30 and chosen_focus_cutoff is None:
            chosen_focus_cutoff = cutoff

    out["obs_focus_cutoff_sweep"] = obs_focus_results

    if chosen_focus_cutoff is None:
        log.warning("OBS sample insufficient at all cutoffs")
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = "all focus cutoffs (-1.5, -1.2, -1.0) yield <30 trades"
        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        return

    out["obs_chosen_focus_cutoff"] = chosen_focus_cutoff

    obs_focus_dates = share_z[share_z <= chosen_focus_cutoff].index
    obs_mirror_dates = share_z[share_z >= DEFAULT_MIRROR_CUTOFF].index

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
    obs_per_sym, obs_pos, obs_ci_pos, obs_measurable = per_symbol_breakdown(
        nets, syms, ALTS, obs_pool, FEE_RT
    )
    q_measurable = sum(1 for q in obs_quarters if "mean_bp" in q)
    q_pos_t = sum(1 for q in obs_quarters if q.get("t", 0) > 0)
    q_pos_t_ratio = q_pos_t / q_measurable if q_measurable > 0 else None
    sym_ci_pos_ratio = obs_ci_pos / obs_measurable if obs_measurable > 0 else None
    n_sym_ci_pos = obs_ci_pos

    # mirror per-symbol + per-quarter (for diagnosis)
    mirror_nets = np.array(obs_mirror_8bp.get("_nets", []))
    mirror_syms = np.array(obs_mirror_8bp.get("_syms", []))
    mirror_dates = np.array(obs_mirror_8bp.get("_dates", []))
    mirror_quarters = per_quarter_breakdown(mirror_nets, mirror_syms, mirror_dates) if len(mirror_nets) else []
    mirror_per_sym, mirror_pos, mirror_ci_pos, mirror_measurable = per_symbol_breakdown(
        mirror_nets, mirror_syms, ALTS, obs_pool, FEE_RT
    ) if len(mirror_nets) else ([], 0, 0, 0)
    mq_measurable = sum(1 for q in mirror_quarters if "mean_bp" in q)
    mq_pos_t = sum(1 for q in mirror_quarters if q.get("t", 0) > 0)
    mq_pos_t_ratio = mq_pos_t / mq_measurable if mq_measurable > 0 else None
    msym_ci_pos_ratio = mirror_ci_pos / mirror_measurable if mirror_measurable > 0 else None
    n_msym_ci_pos = mirror_ci_pos

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
            "sym_ci_pos": n_msym_ci_pos,
            "sym_ci_pos_ratio": msym_ci_pos_ratio,
            "gate_pass": (
                mq_pos_t_ratio is not None and mq_pos_t_ratio >= 0.5
                and msym_ci_pos_ratio is not None and msym_ci_pos_ratio >= 0.30
                and n_msym_ci_pos >= 3
            ),
        },
    }

    # =====================================================
    # FUND PROXY TRACK
    # =====================================================
    log.info("=" * 60)
    log.info("FUND PROXY TRACK: BTC absolute vol_usd z")
    log.info("=" * 60)

    fund_focus_results = {}
    chosen_fund_cutoff = None
    for cutoff in FOCUS_Z_CUTOFFS:
        trig_dates = btc_vol_z[btc_vol_z <= cutoff].index
        n_trig = len(trig_dates)
        log.info("FUND focus cutoff z<=%.2f -> %d trigger days", cutoff, n_trig)
        fund_focus_results[f"cutoff_{cutoff}"] = {"n_triggers": int(n_trig)}
        if n_trig * len(alts_fwd) >= 30 and chosen_fund_cutoff is None:
            chosen_fund_cutoff = cutoff

    out["fund_focus_cutoff_sweep"] = fund_focus_results

    if chosen_fund_cutoff is None:
        log.warning("FUND sample insufficient at all cutoffs")
        out["fund"] = {"sample_status": "SAMPLE_INSUFFICIENT_FUND",
                       "note": "fund track unable to test cross-proxy"}
    else:
        out["fund_chosen_focus_cutoff"] = chosen_fund_cutoff
        fund_focus_dates = btc_vol_z[btc_vol_z <= chosen_fund_cutoff].index
        fund_mirror_dates = btc_vol_z[btc_vol_z >= DEFAULT_MIRROR_CUTOFF].index
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
    # 3-GATE VERDICT
    # =====================================================
    sigex = out["obs"]["focus_8bp"].get("signal_t_excess")
    ci_lo = out["obs"]["focus_8bp"].get("bootstrap_ci_lower_bp")
    perm_p = out["obs"]["focus_8bp"].get("perm_p_one_sided_above")
    net_mean_bp = out["obs"]["focus_8bp"].get("net_mean_bp")
    gross_mean_bp = out["obs"]["focus_8bp"].get("gross_mean_bp")

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
            _has(out["obs"]["focus_50bp"].get("signal_t_excess"))
            and out["obs"]["focus_50bp"].get("signal_t_excess") >= 2.0
        ),
        "gross_above_fee_floor": _has(gross_mean_bp) and gross_mean_bp >= 16.0,
        "obs_mirror_fails_or_inverted": (
            not _has(out["obs"]["mirror_8bp"].get("signal_t_excess"))
            or (out["obs"]["mirror_8bp"].get("signal_t_excess") or 0) < 2.0
        ),
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

    # Mirror three-gate (for diagnosis)
    mirror_sigex = out["obs"]["mirror_8bp"].get("signal_t_excess")
    mirror_ci_lo = out["obs"]["mirror_8bp"].get("bootstrap_ci_lower_bp")
    mirror_perm_p = out["obs"]["mirror_8bp"].get("perm_p_one_sided_above")
    mirror_gross_bp = out["obs"]["mirror_8bp"].get("gross_mean_bp")
    mirror_three_gate = (
        _has(mirror_sigex) and mirror_sigex >= 2.0
        and _has(mirror_ci_lo) and mirror_ci_lo > 0
        and _has(mirror_perm_p) and mirror_perm_p <= 0.10
    )
    mirror_above_fee_floor = _has(mirror_gross_bp) and mirror_gross_bp >= 16.0
    mirror_concentration = out["obs"]["mirror_concentration"]["gate_pass"]
    criteria["mirror_three_gate_pass"] = mirror_three_gate
    criteria["mirror_above_fee_floor"] = mirror_above_fee_floor
    criteria["mirror_concentration_pass"] = mirror_concentration
    out["criteria"] = criteria

    obs_three_gate = criteria["obs_sigex_ge_2"] and criteria["obs_ci_lower_pos"] and criteria["obs_perm_p_le_0p10"]
    obs_mirror_pass_strict = not criteria["obs_mirror_fails_or_inverted"]

    if not criteria["gross_above_fee_floor"]:
        mirror_gross_eff = mirror_gross_bp if _has(mirror_gross_bp) else float("-inf")
        focus_gross = gross_mean_bp if _has(gross_mean_bp) else float("-inf")
        both_below_floor = (focus_gross < 16.0 and mirror_gross_eff < 16.0)
        # Direction-inverted check: focus FAIL fee floor BUT mirror PASS robust
        if mirror_three_gate and mirror_above_fee_floor and mirror_concentration and (out["obs"]["mirror_8bp"].get("n_trades", 0) >= 30):
            verdict = "DIRECTION_INVERTED_MIRROR_PASS"
            reason = (
                f"focus gross {focus_gross:.2f}bp < 16bp fee floor BUT mirror three-gate PASS "
                f"+ mirror gross {mirror_gross_eff:.2f}bp >= 16bp + Concentration PASS + n_mirror>=30 — "
                f"hypothesis is inverted; mirror direction (BTC dominance HIGH -> alt LONG) candidate for separate R-1"
            )
        elif mirror_three_gate and mirror_above_fee_floor and (out["obs"]["mirror_8bp"].get("n_trades", 0) < 30):
            verdict = "DIRECTION_INVERTED_MIRROR_PASS_SPARSE"
            reason = (
                f"focus gross {focus_gross:.2f}bp < 16bp fee floor; mirror three-gate PASS but sparse "
                f"(n={out['obs']['mirror_8bp'].get('n_trades')}); inverted candidate but underpowered"
            )
        elif both_below_floor:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            reason = f"both focus({focus_gross:.2f}bp) and mirror({mirror_gross_eff:.2f}bp) gross < 16bp fee floor"
        else:
            verdict = "BROAD_FALSIFIED_FEE_FLOOR"
            reason = f"focus gross {focus_gross:.2f}bp < 16bp fee floor (mirror gross {mirror_gross_eff:.2f}bp)"
    elif obs_three_gate and not criteria["obs_mirror_fails_or_inverted"]:
        verdict = "BROAD_FALSIFIED"
        reason = "both focus and mirror show signal_t_excess>=2.0 — direction not isolated"
    elif obs_three_gate:
        if not criteria["obs_concentration_pass"]:
            verdict = "CONCENTRATED_R1_PASS"
            reason = (
                f"3-gate OBS PASS but Concentration FAIL "
                f"(q_pos_t_ratio={out['obs']['concentration'].get('q_pos_t_ratio')}, "
                f"sym_ci_pos_ratio={out['obs']['concentration'].get('sym_ci_pos_ratio')}, "
                f"n_sym_ci_pos={out['obs']['concentration'].get('sym_ci_pos')})"
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
        if mirror_three_gate and mirror_above_fee_floor and mirror_concentration:
            verdict = "DIRECTION_INVERTED_MIRROR_PASS"
            reason = "focus 3-gate FAIL but mirror three-gate PASS robust — hypothesis inverted"
        elif mirror_three_gate:
            verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
            reason = "focus FAIL but mirror PASS — direction hypothesis inverted, falsifies"
        else:
            verdict = "FAIL_THREE_GATE"
            reason = (
                f"focus 3-gate FAIL: sigex={sigex}, ci_lower_bp={ci_lo}, perm_p_above={perm_p}; "
                f"mirror sigex={mirror_sigex}"
            )

    out["verdict"] = verdict
    out["verdict_reason"] = reason
    out["three_gate_pass"] = obs_three_gate
    out["concentration_gate_pass"] = criteria["obs_concentration_pass"]
    out["fund_three_gate_pass"] = fund_three_gate
    out["mirror_three_gate_pass"] = mirror_three_gate

    out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    log.info("R-1 verdict=%s reason=%s", verdict, reason)
    log.info("wall-clock=%.2f min, output=%s", out["wall_clock_min"], OUT_PATH)


if __name__ == "__main__":
    main()
