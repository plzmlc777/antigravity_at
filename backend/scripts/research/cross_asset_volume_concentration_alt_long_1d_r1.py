"""R-1 PoC — cross_asset_volume_concentration_alt_long_1d.

Hypothesis (single sentence)
----------------------------
BTC daily USD-volume share (= BTC_vol_usd / sum(26-sym vol_usd)) 30d rolling
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
Both report; B mirror serves as falsification null.

Output
------
backend/runs/research_track/cross_asset_volume_concentration_alt_long_1d/r1_metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("xavc_r1")

PARADIGM = "cross_asset_volume_concentration_alt_long_1d"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_PATH = OUT_DIR / "r1_metrics.json"

BTC = "BTCUSDT"
# 13 alts (paradigm 69 validated set) — LONG direction
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
# 12 보강 (volume-share denominator only, not traded)
EXTRA = [
    "AXSUSDT", "HBARUSDT", "LDOUSDT", "COMPUSDT", "UNIUSDT", "PYTHUSDT",
    "TONUSDT", "ETCUSDT", "ICPUSDT", "JUPUSDT", "WLDUSDT", "1000LUNCUSDT",
]
UNIVERSE = [BTC] + ALTS + EXTRA  # 26 syms

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


def load_1m_close_vol(db, sym: str) -> pd.DataFrame:
    rows = db.execute(
        text(
            "SELECT timestamp, close, volume FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
        ),
        {"s": sym},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df[~df.index.duplicated(keep="first")]
    return df


def resample_to_daily(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1m -> 1d UTC. Returns daily close (last) + vol_usd (sum of close*volume)."""
    if df_1m.empty:
        return pd.DataFrame()
    df = df_1m.copy()
    df["vol_usd"] = df["close"] * df["volume"]  # 1m USD-volume proxy
    daily = pd.DataFrame({
        "close": df["close"].resample("1D").last(),
        "open": df["close"].resample("1D").first(),
        "vol_usd": df["vol_usd"].resample("1D").sum(),
        "bar_count": df["close"].resample("1D").count(),
    })
    # drop incomplete days (< 1200 bars = roughly 80% of 1440)
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


# ---------- trade simulation (daily close-to-close) ----------


def compute_alt_forward_returns(daily_df: pd.DataFrame, hold_days: int = HOLD_DAYS) -> pd.Series:
    """Per-day forward gross return: enter at next day's open, exit hold_days later at close.

    Returns Series indexed by trigger_date (= signal day). Value = exit_close/entry_open - 1.
    """
    open_next = daily_df["open"].shift(-1)
    close_exit = daily_df["close"].shift(-hold_days)
    fwd = close_exit / open_next - 1.0
    return fwd


def evaluate_cell(triggers_dates, alts_forward_returns, fee_rt: float = FEE_RT):
    """For each trigger date, take forward return on each alt, net of fee."""
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
    """Pool of non-trigger forward gross returns across the panel."""
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


# ---------- main ----------


def run_quadrant(name: str, triggers_dates, alts_fwd, pool, fee_rt: float, n_perms: int) -> dict:
    """Run a single trigger quadrant: stats + perm + bootstrap CI."""
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
        "phase": "R-1",
        "dispatch_mode": "ad_hoc_user_explicit",
        "dispatch_date": "2026-05-18",
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
            "data_source": "local DB ohlcv 1m -> 1d resample",
        },
        "lesson_grid_applied": {
            "11_sample_density": "per-cell ≥30 floor + cutoff fallback chain -1.5/-1.2/-1.0",
            "16_concentration_gate": "per-quarter t + per-symbol bootstrap CI emitted",
            "19_symmetric_negative": "2-quadrant (focus z<=-1.5 LONG, mirror z>=+1.5 LONG)",
            "21_axis_stacking": "single statistic (volume share z) ✓ N/A",
            "22_stateful_detector": "rolling z is not stateful ✓ N/A",
            "24_boundary_horizon": "level crossing instantaneous ✓ N/A",
            "27_28_entry_substrate": "internal market structure ✓ N/A",
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

    db = SessionLocal()
    try:
        log.info("Loading 1m close+volume for %d syms ...", len(UNIVERSE))
        raw_data = {}
        for sym in UNIVERSE:
            t0 = time.time()
            df1m = load_1m_close_vol(db, sym)
            if df1m.empty:
                log.warning("[%s] empty", sym)
                continue
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

        # ---------- volume share computation ----------
        # Universe-level intersection of dates
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

        # Build panel of vol_usd
        vol_panel = pd.DataFrame({
            sym: raw_data[sym].loc[common_dates, "vol_usd"]
            for sym in raw_data
        })
        # share = btc_vol / total
        total_vol = vol_panel.sum(axis=1)
        btc_share = vol_panel[BTC] / total_vol
        # rolling 30d z
        share_mu = btc_share.rolling(Z_WINDOW, min_periods=Z_WINDOW).mean()
        share_sd = btc_share.rolling(Z_WINDOW, min_periods=Z_WINDOW).std()
        share_z = ((btc_share - share_mu) / share_sd).dropna()

        # fund proxy: absolute BTC vol_usd 30d z
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

        # ---------- forward returns ----------
        log.info("Computing per-alt forward 1d returns ...")
        alts_fwd = {}
        for sym in ALTS:
            if sym not in raw_data:
                continue
            alts_fwd[sym] = compute_alt_forward_returns(raw_data[sym], hold_days=HOLD_DAYS)
        out["alts_with_fwd"] = list(alts_fwd.keys())

        # =====================================================
        # OBS PROXY TRACK (volume share fraction z)
        # =====================================================
        log.info("=" * 60)
        log.info("OBS PROXY TRACK: volume share fraction z")
        log.info("=" * 60)

        # Try cutoffs progressively
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

        # Focus + mirror trigger dates
        obs_focus_dates = share_z[share_z <= chosen_focus_cutoff].index
        obs_mirror_dates = share_z[share_z >= DEFAULT_MIRROR_CUTOFF].index

        # Build candidate pool excluding all extreme |z|>1 events
        obs_exclude = set(share_z[share_z.abs() >= 1.0].index)
        obs_pool = build_candidate_pool(alts_fwd, obs_exclude, n_samples=N_POOL_SAMPLES, seed=SEED)
        log.info("OBS candidate pool size=%d", len(obs_pool))

        # Run focus + mirror quadrants @ 8bp
        obs_focus_8bp = run_quadrant("obs_focus_8bp", obs_focus_dates, alts_fwd, obs_pool,
                                       fee_rt=FEE_RT, n_perms=N_PERMS)
        obs_mirror_8bp = run_quadrant("obs_mirror_8bp", obs_mirror_dates, alts_fwd, obs_pool,
                                        fee_rt=FEE_RT, n_perms=N_PERMS)
        # Stress @ 50bp
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

        # Concentration breakdowns on obs focus
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
        }

        # =====================================================
        # FUND PROXY TRACK (BTC absolute USD-volume z)
        # =====================================================
        log.info("=" * 60)
        log.info("FUND PROXY TRACK: BTC absolute vol_usd z")
        log.info("=" * 60)
        # For fund: high BTC absolute volume = capital flow, low BTC abs volume = idle
        # Use SAME directional logic: low z (concentration of inflow elsewhere?) vs high z
        # Fund focus = btc_vol_z <= -1.5 (low BTC volume regime, alt-only flow?)
        # Fund mirror = btc_vol_z >= +1.5

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

            # cross-proxy correlation: do obs and fund trigger on same dates?
            obs_focus_set = set(obs_focus_dates)
            fund_focus_set = set(fund_focus_dates)
            both = obs_focus_set & fund_focus_set
            jaccard = (len(both) / len(obs_focus_set | fund_focus_set)) if (obs_focus_set | fund_focus_set) else 0
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
        # 3-GATE VERDICT — OBS proxy primary
        # =====================================================
        sigex = out["obs"]["focus_8bp"].get("signal_t_excess")
        ci_lo = out["obs"]["focus_8bp"].get("bootstrap_ci_lower_bp")
        perm_p = out["obs"]["focus_8bp"].get("perm_p_one_sided_above")
        net_mean_bp = out["obs"]["focus_8bp"].get("net_mean_bp")
        gross_mean_bp = out["obs"]["focus_8bp"].get("gross_mean_bp")

        criteria = {
            "obs_sigex_ge_2": sigex is not None and not (isinstance(sigex, float) and np.isnan(sigex)) and sigex >= 2.0,
            "obs_ci_lower_pos": ci_lo is not None and not (isinstance(ci_lo, float) and np.isnan(ci_lo)) and ci_lo > 0,
            "obs_perm_p_le_0p10": perm_p is not None and not (isinstance(perm_p, float) and np.isnan(perm_p)) and perm_p <= 0.10,
            "obs_concentration_pass": out["obs"]["concentration"]["gate_pass"],
            "obs_focus_50bp_signal_t_excess_ge_2": (
                out["obs"]["focus_50bp"].get("signal_t_excess") is not None
                and not (isinstance(out["obs"]["focus_50bp"].get("signal_t_excess"), float)
                         and np.isnan(out["obs"]["focus_50bp"].get("signal_t_excess")))
                and out["obs"]["focus_50bp"].get("signal_t_excess") >= 2.0
            ),
            "gross_above_fee_floor": gross_mean_bp is not None and not (isinstance(gross_mean_bp, float) and np.isnan(gross_mean_bp)) and gross_mean_bp >= 16.0,
            "obs_mirror_fails_or_inverted": (
                out["obs"]["mirror_8bp"].get("signal_t_excess") is None
                or (isinstance(out["obs"]["mirror_8bp"].get("signal_t_excess"), float)
                    and np.isnan(out["obs"]["mirror_8bp"].get("signal_t_excess")))
                or out["obs"]["mirror_8bp"].get("signal_t_excess", 0) < 2.0
            ),
        }

        # Fund track three-gate
        fund_three_gate = False
        if "focus_8bp" in out.get("fund", {}):
            fund_sigex = out["fund"]["focus_8bp"].get("signal_t_excess")
            fund_ci_lo = out["fund"]["focus_8bp"].get("bootstrap_ci_lower_bp")
            fund_perm_p = out["fund"]["focus_8bp"].get("perm_p_one_sided_above")
            fund_three_gate = (
                fund_sigex is not None and not (isinstance(fund_sigex, float) and np.isnan(fund_sigex)) and fund_sigex >= 2.0
                and fund_ci_lo is not None and not (isinstance(fund_ci_lo, float) and np.isnan(fund_ci_lo)) and fund_ci_lo > 0
                and fund_perm_p is not None and not (isinstance(fund_perm_p, float) and np.isnan(fund_perm_p)) and fund_perm_p <= 0.10
            )
        criteria["fund_three_gate_pass"] = fund_three_gate
        out["criteria"] = criteria

        # Verdict logic
        obs_three_gate = criteria["obs_sigex_ge_2"] and criteria["obs_ci_lower_pos"] and criteria["obs_perm_p_le_0p10"]
        obs_mirror_pass = not criteria["obs_mirror_fails_or_inverted"]

        if not criteria["gross_above_fee_floor"]:
            # Hard floor: gross < 16bp = fee floor not cleared
            # But check if BOTH quadrants fail (broad falsified) or just below floor
            mirror_gross = (out["obs"]["mirror_8bp"].get("net_mean_bp", 0) or 0) + FEE_RT * 1e4
            focus_gross = gross_mean_bp if gross_mean_bp is not None else float("-inf")
            both_below_floor = (
                focus_gross < 16.0 and mirror_gross < 16.0
            )
            if both_below_floor:
                verdict = "BROAD_FALSIFIED_FEE_FLOOR"
                reason = f"both focus({focus_gross:.2f}bp) and mirror({mirror_gross:.2f}bp) gross < 16bp fee floor"
            else:
                verdict = "BROAD_FALSIFIED_FEE_FLOOR"
                reason = f"focus gross {focus_gross:.2f}bp < 16bp fee floor"
        elif obs_three_gate and obs_mirror_pass:
            # Both quadrants strong = mirror invalidates focus directionality
            verdict = "BROAD_FALSIFIED"
            reason = "both focus and mirror show signal_t_excess>=2.0 — direction not isolated"
        elif obs_three_gate:
            # Focus passes, mirror fails — directional isolation OK
            if not criteria["obs_concentration_pass"]:
                verdict = "CONCENTRATED_R1_PASS"
                reason = f"3-gate OBS PASS but Concentration FAIL (q_pos_t_ratio={out['obs']['concentration'].get('q_pos_t_ratio')}, sym_ci_pos_ratio={out['obs']['concentration'].get('sym_ci_pos_ratio')}, n_sym_ci_pos={out['obs']['concentration'].get('sym_ci_pos')})"
            elif not fund_three_gate:
                # cross-proxy fail
                verdict = "SINGLE_PROXY_TRAP_OBS_ONLY"
                reason = "obs proxy 3-gate PASS but fund proxy 3-gate FAIL (Lesson #29)"
            else:
                # check redundancy
                jacc = out.get("fund", {}).get("cross_proxy_overlap", {}).get("jaccard", 0)
                if jacc >= 0.7:
                    verdict = "SINGLE_PROXY_TRAP_REDUNDANT"
                    reason = f"obs and fund proxies essentially redundant (jaccard={jacc:.2f} >= 0.7)"
                else:
                    verdict = "PASS_R1_CROSS_PROXY_PROMOTE_R2"
                    reason = "obs+fund 3-gate PASS + Concentration PASS + cross-proxy non-redundant"
        else:
            # focus fails three-gate
            mirror_three_gate = (
                out["obs"]["mirror_8bp"].get("signal_t_excess", 0) is not None
                and (out["obs"]["mirror_8bp"].get("signal_t_excess", 0) or 0) >= 2.0
            )
            if mirror_three_gate:
                verdict = "BROAD_FALSIFIED_DIRECTION_INVERTED"
                reason = "focus FAIL but mirror PASS — direction hypothesis inverted, falsifies"
            else:
                verdict = "FAIL_THREE_GATE"
                reason = (
                    f"focus 3-gate FAIL: sigex={sigex}, ci_lower_bp={ci_lo}, perm_p_above={perm_p}; "
                    f"mirror sigex={out['obs']['mirror_8bp'].get('signal_t_excess')}"
                )

        out["verdict"] = verdict
        out["verdict_reason"] = reason
        out["three_gate_pass"] = obs_three_gate
        out["concentration_gate_pass"] = criteria["obs_concentration_pass"]
        out["fund_three_gate_pass"] = fund_three_gate

        out["wall_clock_min"] = round((time.time() - t_start) / 60, 2)
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("R-1 verdict=%s reason=%s", verdict, reason)
        log.info("wall-clock=%.2f min, output=%s", out["wall_clock_min"], OUT_PATH)
    finally:
        db.close()


if __name__ == "__main__":
    main()
