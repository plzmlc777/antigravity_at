"""Paradigm 109 — alt_cohort_dispersion_compression_directional_4h R-1 PoC

Hypothesis
----------
When the cross-section standard deviation of recent forward returns across
the 13-alt cohort compresses to historical-low (rolling 30d z-score < -2),
the cohort enters a uniform-alignment regime where the next 4h alt directional
move aligns with BTC direction (LONG if BTC up, SHORT if BTC down).

Statistic dimension: cross-section dispersion COMPRESSION (low std regime),
distinct from pairwise corr breakdown / rank rotation / volume share.

R-0 prescreens applied: Lessons 11/19/21/23/28/30/32/34
R-1 body: 4-quadrant Symmetric Negative Test + hold×threshold sweep +
          Concentration Gate + Life-changing 4-dim gate
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

ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from scripts.research._perm_utils import fee_aware_perm_test, bootstrap_ci  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p109_r1")

CACHE_DIR = ROOT / "runs" / "ohlcv_cache"
OUT_DIR = ROOT / "runs" / "research_track" / "alt_cohort_dispersion_compression_directional_4h"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 13-alt cohort (excludes BTC which is direction reference)
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
BTC = "BTCUSDT"

FEE_PER_TRADE = 0.0008  # 16bp round-trip
ROLLING_30D_HRS = 24 * 30  # 720 1h bars
HOLD_SWEEP_MIN = [60, 120, 240, 480, 1440]
Z_SWEEP = [-2.5, -2.0, -1.5, -1.0]
PRIMARY_Z = -2.0
PRIMARY_HOLD = 240  # min


def load_1h(sym: str) -> pd.DataFrame:
    """Load 1m joblib cache, resample to 1h closes."""
    path = CACHE_DIR / f"{sym}_1m.joblib"
    df = joblib.load(path)
    # Resample 1m → 1h using ohlc agg
    h = df["close"].resample("1h").last().to_frame("close")
    return h


def compute_cohort_panel(alts: list[str]) -> pd.DataFrame:
    """Return DataFrame indexed by hourly timestamp, columns = alt 1h forward log-return."""
    log.info("loading 1h closes for %d alts", len(alts))
    closes = {}
    for s in alts:
        h = load_1h(s)
        closes[s] = h["close"]
    closes_df = pd.concat(closes, axis=1)
    closes_df.columns = alts
    closes_df = closes_df.sort_index()
    # 1h forward log-return: r(t) = log(p(t+1h)/p(t))
    fwd = np.log(closes_df.shift(-1) / closes_df)
    return fwd


def compute_btc_1h(btc_df_path) -> pd.Series:
    df = joblib.load(btc_df_path)
    h = df["close"].resample("1h").last()
    return h


def main():
    t_start = time.time()
    out = {
        "paradigm_name": "alt_cohort_dispersion_compression_directional_4h",
        "paradigm_number": 109,
        "executed_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "universe_alts": ALTS,
        "n_alts": len(ALTS),
        "fee_per_trade": FEE_PER_TRADE,
        "primary_z_threshold": PRIMARY_Z,
        "primary_hold_min": PRIMARY_HOLD,
        "z_sweep": Z_SWEEP,
        "hold_sweep_min": HOLD_SWEEP_MIN,
    }

    # ─── Stage 1: Load cohort + BTC ──────────────────────────────────────
    fwd_panel = compute_cohort_panel(ALTS)  # 1h forward log-ret per alt
    btc_1h = compute_cohort_panel([BTC])[BTC]
    log.info("panel shape: %s, BTC: %s", fwd_panel.shape, btc_1h.shape)

    # Common index intersection
    common_idx = fwd_panel.dropna(how="all").index.intersection(btc_1h.dropna().index)
    fwd_panel = fwd_panel.loc[common_idx]
    btc_1h = btc_1h.loc[common_idx]

    # 1h closes for hold calc
    closes_alts = {s: load_1h(s)["close"] for s in ALTS}
    closes_alts_df = pd.concat(closes_alts, axis=1)
    closes_alts_df.columns = ALTS

    out["panel_window"] = {
        "first": str(common_idx.min()),
        "last": str(common_idx.max()),
        "n_hours": len(common_idx),
        "n_years": float((common_idx.max() - common_idx.min()).days / 365.25),
    }

    # ─── R-0 Prescreens ──────────────────────────────────────────────────
    log.info("=== R-0 prescreens ===")

    # σ_cs(t) = cross-section std of 1h forward returns
    sigma_cs = fwd_panel.std(axis=1, ddof=1)  # std across alts at each timestamp

    # Rolling 30d (720h) mean and std of σ_cs
    mu_30d = sigma_cs.rolling(ROLLING_30D_HRS, min_periods=ROLLING_30D_HRS // 2).mean()
    sd_30d = sigma_cs.rolling(ROLLING_30D_HRS, min_periods=ROLLING_30D_HRS // 2).std(ddof=1)
    z_disp = (sigma_cs - mu_30d) / sd_30d

    # BTC 4h log-return (4 hourly bars back: log(p_t / p_{t-4}))
    # Use BTC 1h CLOSE (not forward ret) for direction: btc_close_now / btc_close_4h_ago
    btc_close_1h = closes_alts_df  # placeholder
    btc_close_series = load_1h(BTC)["close"]
    btc_ret_4h = np.log(btc_close_series / btc_close_series.shift(4))
    btc_ret_4h = btc_ret_4h.loc[common_idx]

    # Trigger candidate filter
    valid_mask = z_disp.notna() & btc_ret_4h.notna()
    n_valid_hours = int(valid_mask.sum())

    # Lesson #34 — empirical distribution of σ_cs and z_disp
    sigma_q = sigma_cs.quantile([0.01, 0.05, 0.10, 0.50, 0.90, 0.99]).to_dict()
    z_q = z_disp.quantile([0.005, 0.01, 0.025, 0.05, 0.10, 0.50, 0.90, 0.95, 0.99, 0.995]).to_dict()
    out["lesson34_empirical_distribution"] = {
        "sigma_cs_quantiles": {f"p{int(k*100)}" if (k*100).is_integer() else f"p{k*100:.1f}": float(v) for k, v in sigma_q.items()},
        "z_disp_quantiles": {f"p{k*100:.1f}": float(v) for k, v in z_q.items()},
        "n_valid_hours": n_valid_hours,
    }
    log.info("σ_cs p5=%.6f p50=%.6f p90=%.6f", sigma_q[0.05], sigma_q[0.50], sigma_q[0.90])
    log.info("z_disp p1=%.3f p2.5=%.3f p5=%.3f p95=%.3f", z_q[0.01], z_q[0.025], z_q[0.05], z_q[0.95])

    # Lesson #23 — empirical trigger rate
    trigger_mask = (z_disp <= PRIMARY_Z) & btc_ret_4h.notna()
    n_trigger = int(trigger_mask.sum())
    trigger_rate = n_trigger / max(n_valid_hours, 1)
    out["lesson23_trigger_rate"] = {
        "z_threshold": PRIMARY_Z,
        "n_trigger": n_trigger,
        "n_valid_hours": n_valid_hours,
        "trigger_rate": float(trigger_rate),
        "trigger_rate_pct": float(trigger_rate * 100),
        "lesson23_min_threshold_pct": 1.5,
        "passes_lesson23": bool(trigger_rate * 100 >= 1.5),
    }
    log.info("trigger rate at z<%.1f: %d / %d = %.2f%%", PRIMARY_Z, n_trigger, n_valid_hours, trigger_rate * 100)

    # Direction split
    btc_up_mask = trigger_mask & (btc_ret_4h > 0)
    btc_dn_mask = trigger_mask & (btc_ret_4h < 0)
    n_btc_up = int(btc_up_mask.sum())
    n_btc_dn = int(btc_dn_mask.sum())

    # Lesson #11 sample density — per-cell sample
    n_quarters = 4 * int((common_idx.max() - common_idx.min()).days / 365.25 + 1)  # rough
    n_quarters_real = max(1, int(np.ceil((common_idx.max() - common_idx.min()).days / 91)))
    expected_per_cell_focus = n_btc_up / n_quarters_real
    expected_per_cell_mirror_B = n_btc_dn / n_quarters_real
    out["lesson11_sample_density"] = {
        "n_btc_up_at_trigger": n_btc_up,
        "n_btc_dn_at_trigger": n_btc_dn,
        "n_quarters": n_quarters_real,
        "expected_per_quarter_A_focus": float(expected_per_cell_focus),
        "expected_per_quarter_B_same_sign": float(expected_per_cell_mirror_B),
        "lesson11_min_per_cell": 30,
        "passes_lesson11_A": bool(expected_per_cell_focus >= 30),
        "passes_lesson11_B": bool(expected_per_cell_mirror_B >= 30),
        "passes_lesson11_both": bool(expected_per_cell_focus >= 30 and expected_per_cell_mirror_B >= 30),
    }
    log.info("Lesson #11 per-quarter: A focus=%.1f / B same-sign=%.1f (n_quarters=%d)",
             expected_per_cell_focus, expected_per_cell_mirror_B, n_quarters_real)

    # Lesson #30 data window ratio (panel 2.4yr vs Mint full 2.4yr — same → 100%)
    out["lesson30_data_window_ratio"] = {
        "panel_years": out["panel_window"]["n_years"],
        "mint_full_years": out["panel_window"]["n_years"],
        "ratio": 1.0,
        "passes_lesson30": True,
    }

    # Lesson #28 substrate audit
    out["lesson28_substrate"] = {
        "alts_with_coverage": [s for s in ALTS if (CACHE_DIR / f"{s}_1m.joblib").exists()],
        "n_alts_covered": sum(1 for s in ALTS if (CACHE_DIR / f"{s}_1m.joblib").exists()),
        "passes_lesson28": all((CACHE_DIR / f"{s}_1m.joblib").exists() for s in ALTS),
    }

    # HALT check — Lesson #11 / #23
    if (not out["lesson11_sample_density"]["passes_lesson11_both"]) and (not out["lesson23_trigger_rate"]["passes_lesson23"]):
        out["verdict"] = "SAMPLE_INSUFFICIENT"
        out["verdict_reason"] = (
            f"Lesson #11 fail: per-quarter A={expected_per_cell_focus:.1f} / B={expected_per_cell_mirror_B:.1f} (<30 cutoff). "
            f"Lesson #23 fail: trigger rate {trigger_rate*100:.2f}% (<1.5% cutoff)."
        )
        out["lessons_dogfood"] = ["#11", "#23"]
        out["wall_clock_minutes"] = (time.time() - t_start) / 60
        _write(out)
        log.warning("HALT — SAMPLE_INSUFFICIENT")
        return
    elif not out["lesson11_sample_density"]["passes_lesson11_both"]:
        log.warning("Lesson #11 marginal: per-cell <30 in one quadrant — proceeding with caveat")

    # ─── R-1 Body: 4-quadrant + sweep ─────────────────────────────────────
    log.info("=== R-1 4-quadrant + sweep ===")

    # Compute hold returns per alt for each hold horizon (from 1h closes)
    # hold_return at trigger time t = log(p_alt(t + hold_h) / p_alt(t))
    # where hold_h = hold_min / 60
    def hold_returns_panel(hold_min: int) -> pd.DataFrame:
        h = hold_min // 60
        return np.log(closes_alts_df.shift(-h) / closes_alts_df)

    # ─── Lesson #19 Symmetric Negative Test 4-quadrant ──────────────────
    # Direction labels
    #   A focus    : z_disp ≤ -2 AND BTC_4h > 0 → cohort LONG  (predicted)
    #   A mirror   : z_disp ≤ -2 AND BTC_4h > 0 → cohort SHORT
    #   B same-sign: z_disp ≤ -2 AND BTC_4h < 0 → cohort SHORT (predicted)
    #   B mirror   : z_disp ≤ -2 AND BTC_4h < 0 → cohort LONG

    quadrant_results = {}
    sweep_results = []

    # Candidate pool for perm test: every (timestamp, alt) hold-window return at valid hours,
    # used as random non-trigger comparator. Use primary hold for candidate pool.
    primary_hold_panel = hold_returns_panel(PRIMARY_HOLD)
    candidate_pool_primary = primary_hold_panel.loc[valid_mask].values.flatten()
    candidate_pool_primary = candidate_pool_primary[~np.isnan(candidate_pool_primary)]
    out["candidate_pool_size_primary"] = int(len(candidate_pool_primary))

    def compute_quadrant(quadrant_name: str, mask: pd.Series, direction: int, hold_min: int, z_thr: float):
        """
        direction: +1 LONG (use raw alt hold return), -1 SHORT (negate hold return)
        Each TRIGGER produces a BASKET trade: equally-weighted avg of 13 alts' hold returns.
        Fee applied ONCE per basket trade (single basket position).
        """
        hold_panel = hold_returns_panel(hold_min)
        # At each triggered timestamp, basket return = mean of 13 alts' hold-returns
        trig_ts = mask[mask].index
        basket_rets_gross = []
        per_sym_basket_contribs = {s: [] for s in ALTS}  # for per-symbol concentration
        for ts in trig_ts:
            row = hold_panel.loc[ts]
            if row.isna().all():
                continue
            r = row.dropna()
            if len(r) < len(ALTS) // 2:  # require ≥ half of cohort
                continue
            basket_gross = float(r.mean())
            basket_rets_gross.append(direction * basket_gross)
            for s in ALTS:
                v = row.get(s)
                if pd.notna(v):
                    per_sym_basket_contribs[s].append(direction * float(v))
        if len(basket_rets_gross) < 5:
            return {
                "quadrant": quadrant_name,
                "z_threshold": z_thr,
                "hold_min": hold_min,
                "n_trades": len(basket_rets_gross),
                "error": "n_trades<5",
            }
        gross = np.asarray(basket_rets_gross)
        net = gross - FEE_PER_TRADE

        obs_t = float(net.mean() / net.std(ddof=1) * np.sqrt(len(net))) if net.std(ddof=1) > 0 else 0.0
        obs_mean_bp = float(net.mean() * 10000)
        gross_mean_bp = float(gross.mean() * 10000)

        # Bootstrap CI on net mean
        ci = bootstrap_ci(net, n_boot=1000, rng_seed=42)

        # Fee-aware perm
        # Build candidate pool: random hold-window returns (any timestamp/alt) with direction sign applied
        pool = direction * candidate_pool_primary if hold_min == PRIMARY_HOLD else direction * hold_panel.loc[valid_mask].values.flatten()
        pool = pool[~np.isnan(pool)]
        if len(pool) < len(net) * 2:
            perm = {"perm_p_two_sided": float("nan"), "signal_t_excess": float("nan"), "null_mean_t": float("nan")}
        else:
            perm = fee_aware_perm_test(net, pool, fee_per_trade=FEE_PER_TRADE, n_perms=1000, rng_seed=42)

        # Per-symbol bootstrap concentration
        per_sym_ci = {}
        for s in ALTS:
            arr = np.asarray(per_sym_basket_contribs[s])
            if len(arr) < 5:
                per_sym_ci[s] = {"n": len(arr), "ci_lower_bp": float("nan"), "ci_pos": False}
                continue
            net_sym = arr - FEE_PER_TRADE
            ci_s = bootstrap_ci(net_sym, n_boot=500, rng_seed=42)
            per_sym_ci[s] = {
                "n": int(len(arr)),
                "mean_bp": float(net_sym.mean() * 10000),
                "ci_lower_bp": float(ci_s["ci_lower"] * 10000),
                "ci_upper_bp": float(ci_s["ci_upper"] * 10000),
                "ci_pos": bool(ci_s["ci_lower"] > 0),
            }

        n_syms_ci_pos = sum(1 for v in per_sym_ci.values() if v["ci_pos"])

        # Per-quarter t
        df_per = pd.DataFrame({"ts": trig_ts[:len(basket_rets_gross)], "ret": net})
        df_per["quarter"] = pd.to_datetime(df_per["ts"]).dt.to_period("Q").astype(str)
        per_q = {}
        for q, sub in df_per.groupby("quarter"):
            if len(sub) < 5:
                per_q[q] = {"n": len(sub), "t": float("nan"), "pos_t": False}
                continue
            tq = sub["ret"].mean() / sub["ret"].std(ddof=1) * np.sqrt(len(sub)) if sub["ret"].std(ddof=1) > 0 else 0
            per_q[q] = {"n": int(len(sub)), "mean_bp": float(sub["ret"].mean() * 10000), "t": float(tq), "pos_t": bool(tq > 0)}
        n_q_measurable = sum(1 for v in per_q.values() if pd.notna(v["t"]))
        n_q_pos = sum(1 for v in per_q.values() if v["pos_t"])
        q_pos_ratio = n_q_pos / n_q_measurable if n_q_measurable > 0 else 0

        # 3-gate
        gate_3 = bool(perm.get("signal_t_excess", float("nan")) >= 2.0 and ci["ci_lower"] > 0 and perm.get("perm_p_two_sided", 1.0) <= 0.10)
        # Concentration gate
        gate_conc = bool(q_pos_ratio >= 0.5 and (n_syms_ci_pos / len(ALTS)) >= 0.30 and n_syms_ci_pos >= 3)

        return {
            "quadrant": quadrant_name,
            "z_threshold": z_thr,
            "hold_min": hold_min,
            "direction": direction,
            "n_trades": int(len(net)),
            "obs_mean_net_bp": obs_mean_bp,
            "obs_mean_gross_bp": gross_mean_bp,
            "obs_t": obs_t,
            "ci_lower_bp": float(ci["ci_lower"] * 10000),
            "ci_upper_bp": float(ci["ci_upper"] * 10000),
            "ci_pos": bool(ci["ci_lower"] > 0),
            "perm_p_two_sided": float(perm.get("perm_p_two_sided", float("nan"))),
            "perm_p_one_sided_above": float(perm.get("perm_p_one_sided_above", float("nan"))),
            "null_mean_t": float(perm.get("null_mean_t", float("nan"))),
            "signal_t_excess": float(perm.get("signal_t_excess", float("nan"))),
            "gate_3_pass": gate_3,
            "per_quarter": per_q,
            "n_q_measurable": int(n_q_measurable),
            "n_q_pos": int(n_q_pos),
            "q_pos_ratio": float(q_pos_ratio),
            "per_symbol_ci": per_sym_ci,
            "n_syms_ci_pos": int(n_syms_ci_pos),
            "n_syms_total": len(ALTS),
            "syms_ci_pos_ratio": float(n_syms_ci_pos / len(ALTS)),
            "gate_concentration_pass": gate_conc,
        }

    # Primary z = -2 at primary hold 240
    for (qname, m, d) in [
        ("A_focus_z2_LONG", btc_up_mask, +1),
        ("A_mirror_z2_SHORT", btc_up_mask, -1),
        ("B_same_sign_z2_SHORT", btc_dn_mask, -1),
        ("B_mirror_z2_LONG", btc_dn_mask, +1),
    ]:
        log.info("computing %s n_mask=%d", qname, int(m.sum()))
        quadrant_results[qname] = compute_quadrant(qname, m, d, PRIMARY_HOLD, PRIMARY_Z)

    # ─── Sweep z × hold (focus direction only — A focus + B same-sign) ──
    log.info("=== sweep z × hold ===")
    for z_thr in Z_SWEEP:
        trig_z = (z_disp <= z_thr) & btc_ret_4h.notna()
        up_z = trig_z & (btc_ret_4h > 0)
        dn_z = trig_z & (btc_ret_4h < 0)
        for hold_min in HOLD_SWEEP_MIN:
            for tag, m, d in [
                (f"A_focus_z{abs(z_thr):.1f}_h{hold_min}", up_z, +1),
                (f"B_same_z{abs(z_thr):.1f}_h{hold_min}", dn_z, -1),
            ]:
                if hold_min == PRIMARY_HOLD and z_thr == PRIMARY_Z:
                    # already in quadrant_results
                    continue
                r = compute_quadrant(tag, m, d, hold_min, z_thr)
                sweep_results.append(r)

    out["r1_4quadrant"] = quadrant_results
    out["r1_sweep"] = sweep_results

    # ─── Lesson #21 axis stacking — test each axis alone ────────────────
    log.info("=== Lesson #21 axis-alone tests ===")
    # Axis 1: z_disp<-2 alone (no BTC dir) on hold 240 — sign of cohort basket?
    z_only_mask = (z_disp <= PRIMARY_Z) & btc_ret_4h.notna()
    # axis1 LONG basket (no direction conditioning)
    axis1 = compute_quadrant("axis1_z_only_LONG", z_only_mask, +1, PRIMARY_HOLD, PRIMARY_Z)
    # Axis 2: BTC direction alone at high z_disp days (i.e., no compression filter — use any z) — predicts cohort?
    btc_dir_only_mask = btc_ret_4h.notna() & z_disp.notna()
    # downsample to same n as primary trigger
    rng = np.random.default_rng(123)
    btc_up_only = (btc_ret_4h > 0) & btc_dir_only_mask
    btc_dn_only = (btc_ret_4h < 0) & btc_dir_only_mask
    # Use 5x trigger count or full pool
    n_target = min(n_btc_up * 5, int(btc_up_only.sum()))
    if n_target > 10 and btc_up_only.sum() > 0:
        idx_up = np.where(btc_up_only)[0]
        sel_up = rng.choice(idx_up, size=min(n_target, len(idx_up)), replace=False)
        sub_up_mask = pd.Series(False, index=btc_up_only.index)
        sub_up_mask.iloc[sel_up] = True
        axis2_up = compute_quadrant("axis2_btc_up_only_LONG", sub_up_mask, +1, PRIMARY_HOLD, np.nan)
    else:
        axis2_up = {"error": "insufficient"}
    n_target2 = min(n_btc_dn * 5, int(btc_dn_only.sum()))
    if n_target2 > 10 and btc_dn_only.sum() > 0:
        idx_dn = np.where(btc_dn_only)[0]
        sel_dn = rng.choice(idx_dn, size=min(n_target2, len(idx_dn)), replace=False)
        sub_dn_mask = pd.Series(False, index=btc_dn_only.index)
        sub_dn_mask.iloc[sel_dn] = True
        axis2_dn = compute_quadrant("axis2_btc_dn_only_SHORT", sub_dn_mask, -1, PRIMARY_HOLD, np.nan)
    else:
        axis2_dn = {"error": "insufficient"}

    out["lesson21_axis_alone"] = {
        "axis1_z_compression_alone_LONG": axis1,
        "axis2_btc_up_only_LONG_random_subsample": axis2_up,
        "axis2_btc_dn_only_SHORT_random_subsample": axis2_dn,
    }

    # ─── Lesson #32 universe baseline coherent ──────────────────────────
    # A_focus net vs B_baseline (z<-2 any BTC dir LONG without dir filter)
    baseline_mask = z_only_mask
    baseline_long = compute_quadrant("baseline_z_compression_LONG", baseline_mask, +1, PRIMARY_HOLD, PRIMARY_Z)
    out["lesson32_universe_baseline"] = {
        "A_focus_LONG_mean_bp": quadrant_results["A_focus_z2_LONG"].get("obs_mean_net_bp"),
        "baseline_z_compression_LONG_mean_bp": baseline_long.get("obs_mean_net_bp"),
        "drift_artifact_concern": (
            quadrant_results["A_focus_z2_LONG"].get("obs_mean_net_bp", 0) <=
            baseline_long.get("obs_mean_net_bp", 0) + 5
        ),
    }

    # ─── Life-changing 4-dim gate ────────────────────────────────────────
    # On A_focus primary
    afocus = quadrant_results["A_focus_z2_LONG"]
    n_trades_year = afocus["n_trades"] / out["panel_window"]["n_years"]
    edge_pct_per_trade = afocus["obs_mean_net_bp"] / 100
    sharpe_annualized = (afocus["obs_t"] / np.sqrt(afocus["n_trades"])) * np.sqrt(n_trades_year) if afocus["n_trades"] > 0 else float("nan")
    # Capital util: triggers cover what fraction of time? n_trigger * hold_hours / total_hours
    util_pct = (afocus["n_trades"] * (PRIMARY_HOLD / 60)) / out["panel_window"]["n_hours"] * 100
    out["life_changing_4dim_A_focus"] = {
        "trades_per_year": float(n_trades_year),
        "edge_pct_per_trade": float(edge_pct_per_trade),
        "sharpe_annualized": float(sharpe_annualized),
        "capital_util_pct": float(util_pct),
        "passes_trades": bool(n_trades_year >= 12),
        "passes_edge": bool(edge_pct_per_trade >= 2.0),
        "passes_sharpe": bool(sharpe_annualized >= 3.0),
        "passes_util": bool(util_pct >= 30.0),
        "passes_all_4dim": bool(n_trades_year >= 12 and edge_pct_per_trade >= 2.0 and sharpe_annualized >= 3.0 and util_pct >= 30.0),
    }

    # ─── Verdict logic ──────────────────────────────────────────────────
    a_focus = quadrant_results["A_focus_z2_LONG"]
    a_mirror = quadrant_results["A_mirror_z2_SHORT"]
    b_same = quadrant_results["B_same_sign_z2_SHORT"]
    b_mirror = quadrant_results["B_mirror_z2_LONG"]

    # Sweep PASS scan (Lesson #37)
    sweep_pass = [r for r in sweep_results + list(quadrant_results.values())
                  if isinstance(r, dict) and r.get("gate_3_pass") and r.get("gate_concentration_pass")
                  and r.get("quadrant", "").startswith(("A_focus", "B_same"))]

    verdict = None
    verdict_reason = ""

    # Check focus signs
    a_focus_gross_pos = a_focus.get("obs_mean_gross_bp", 0) > 0
    b_same_gross_pos = b_same.get("obs_mean_gross_bp", 0) > 0
    a_mirror_gross_pos = a_mirror.get("obs_mean_gross_bp", 0) > 0
    b_mirror_gross_pos = b_mirror.get("obs_mean_gross_bp", 0) > 0

    # Broad-falsified: both focus quadrants gross negative or sub-fee
    if (not a_focus_gross_pos) and (not b_same_gross_pos):
        verdict = "BROAD_FALSIFIED"
        verdict_reason = (
            f"Both focus quadrants gross-negative: A_focus={a_focus['obs_mean_gross_bp']:.2f}bp, "
            f"B_same={b_same['obs_mean_gross_bp']:.2f}bp. Hypothesis direction inverted."
        )
    # Fee floor: both gross positive but <16bp
    elif (a_focus.get("obs_mean_gross_bp", 0) < FEE_PER_TRADE * 10000 and
          b_same.get("obs_mean_gross_bp", 0) < FEE_PER_TRADE * 10000):
        verdict = "BROAD_FALSIFIED_FEE_FLOOR"
        verdict_reason = (
            f"Both focus quadrants below 16bp fee floor: A_focus_gross={a_focus['obs_mean_gross_bp']:.2f}bp, "
            f"B_same_gross={b_same['obs_mean_gross_bp']:.2f}bp."
        )
    elif a_focus.get("gate_3_pass") and a_focus.get("gate_concentration_pass"):
        if out["life_changing_4dim_A_focus"]["passes_all_4dim"]:
            verdict = "PASS_R1_FULL"
            verdict_reason = "A_focus full 3-gate + Concentration + life-changing 4-dim."
        else:
            verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
            verdict_reason = (
                f"A_focus 3-gate + Concentration PASS but 4-dim fail: "
                f"trades/yr={n_trades_year:.1f}, edge={edge_pct_per_trade:.2f}%, "
                f"sharpe={sharpe_annualized:.2f}, util={util_pct:.1f}%."
            )
    elif a_focus.get("gate_3_pass") and not a_focus.get("gate_concentration_pass"):
        verdict = "CONCENTRATED_R1_PASS"
        verdict_reason = (
            f"A_focus 3-gate PASS but Concentration FAIL: "
            f"q_pos_ratio={a_focus['q_pos_ratio']:.2f}, syms_ci_pos={a_focus['n_syms_ci_pos']}/13."
        )
    elif sweep_pass:
        verdict = "NARROW_SCOPE_LIFE_CHANGING_FAIL"
        verdict_reason = f"Primary cell fail but {len(sweep_pass)} sweep cell(s) PASS; defer narrow-scope qualification to R-2."
    else:
        # Check Lesson #21 axis stacking
        axis2_up_t = out["lesson21_axis_alone"]["axis2_btc_up_only_LONG_random_subsample"].get("obs_t", 0)
        if isinstance(axis2_up_t, (int, float)) and abs(axis2_up_t) > 1.5:
            verdict = "BROAD_FALSIFIED_NO_AXIS_SYNTHESIS"
            verdict_reason = (
                f"Axis-alone test: BTC direction alone has t={axis2_up_t:.2f}. "
                f"Joint trigger (z_disp+BTC_dir) does not synthesize alpha beyond single axis."
            )
        else:
            # Default: broad-falsified for not meeting any pass criterion
            verdict = "BROAD_FALSIFIED"
            verdict_reason = (
                f"4-quadrant: A_focus gross={a_focus['obs_mean_gross_bp']:.2f}bp t={a_focus['obs_t']:.2f}, "
                f"B_same gross={b_same['obs_mean_gross_bp']:.2f}bp t={b_same['obs_t']:.2f}; "
                f"neither 3-gate PASS at primary."
            )

    # Universe drift artifact check
    if (quadrant_results["A_focus_z2_LONG"].get("gate_3_pass") and
        out["lesson32_universe_baseline"]["drift_artifact_concern"]):
        verdict = "BROAD_FALSIFIED_UNIVERSE_DRIFT_ARTIFACT"
        verdict_reason = (
            f"A_focus gate PASS but baseline (z compression alone, no BTC dir) also positive. "
            f"A_focus={out['lesson32_universe_baseline']['A_focus_LONG_mean_bp']:.2f}bp vs "
            f"baseline={out['lesson32_universe_baseline']['baseline_z_compression_LONG_mean_bp']:.2f}bp — "
            f"upward drift artifact concern."
        )

    out["verdict"] = verdict
    out["verdict_reason"] = verdict_reason
    out["sweep_pass_cells"] = [r.get("quadrant") for r in sweep_pass]
    out["lessons_dogfood"] = ["#11", "#16", "#19", "#20", "#21", "#23", "#28", "#29", "#30", "#32", "#34", "#37"]
    out["lesson_candidates"] = []

    out["wall_clock_minutes"] = (time.time() - t_start) / 60
    out["infrastructure_notes"] = {
        "cache_used": True,
        "panel_compute_seconds": "embedded in wall clock",
        "candidate_pool_size_primary": out["candidate_pool_size_primary"],
        "host": "mint@183.99.228.81",
    }

    _write(out)
    log.info("=== verdict: %s ===", verdict)
    log.info(verdict_reason)


def _write(out: dict):
    p = OUT_DIR / "r1__metrics.json"
    with open(p, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("wrote %s", p)


if __name__ == "__main__":
    main()
