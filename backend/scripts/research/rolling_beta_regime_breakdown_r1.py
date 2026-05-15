"""Paradigm 81 — rolling_beta_regime_breakdown R-1 PoC.

Hypothesis
----------
13 alts × BTCUSDT rolling 30d beta (regression slope of daily alt return on
BTC return). Beta z-score computed on 60d rolling window of the beta series.

4-cell symmetric sign-conditional design (Lesson #3 + #19 mandatory):
  Cell 1: beta_z > +Z × BTC up_1d   -> alt LONG   (amplification + momentum)
  Cell 2: beta_z > +Z × BTC down_1d -> alt SHORT  (amplification + reversal)
  Cell 3: beta_z < -Z × BTC up_1d   -> alt SHORT  (decoupling, alt undershoots)
  Cell 4: beta_z < -Z × BTC down_1d -> alt LONG   (decoupling, alt outperforms)

Focus: cell 1 (beta amplification + BTC up + LONG) at z=2.0, hold=5d.

Why beta paradigm is distinct from retired families:
- vs cross_asset_corr_breakdown_family (74-77): correlation rho is scale-free
  association strength [-1,1]; beta is regression slope (scale-dependent
  directional sensitivity). Different statistic.
- vs paradigm 80 oi_premium_5m_decoupling (broad-falsified): joint level
  z-event; beta is derived regression coefficient, sign-conditional trigger.
- vs paradigm 64 cross_sec_30d_mom (graveyard): cross-sectional rank rotation;
  beta paradigm is per-alt asynchronous pairwise event with BTC.
- vs paradigm 63 cross_sec_weekly_mr (graveyard): not ranking-based.

Sample density prescreen (Lesson #11):
  2.4yr * 13 alts * 1d granularity = ~11,310 daily obs
  |beta_z|>2.0 trigger rate ~4-5% gaussian tail
  BTC direction split 50/50
  Expected n per cell = 11,310 * 0.05 * 0.5 = ~283 trades
  -> 30 floor cleared by 10x

Data: ~/auto_trading/backend/runs/ohlcv_cache/{SYM}_1m.joblib (Mint).

Output: backend/runs/research_track/rolling_beta_regime_breakdown/r1__metrics.json
        + r1__per_symbol.csv + r1__hold_sweep.csv
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Tuple

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
log = logging.getLogger("paradigm_81_r1")

OUT_DIR = ROOT / "runs" / "research_track" / "rolling_beta_regime_breakdown"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BTC = "BTCUSDT"
ALTS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT",
    "XRPUSDT",
]

# Beta computation parameters
BETA_WINDOW = 30   # 30d rolling beta
BETA_Z_WINDOW = 60  # 60d rolling z-score on beta series
FOCUS_Z = 2.0
Z_SWEEP = [1.5, 2.0, 2.5]

# Hold horizons (in days)
HOLD_SWEEP_D = [1, 3, 5, 10, 20]
FOCUS_HOLD_D = 5

# Fee
FEE_RT = 0.0008  # 8 bp round-trip


def build_daily_panel() -> Tuple[pd.DataFrame, dict]:
    """Load 14 OHLCV 1m caches, resample to 1d close, return wide df + meta."""
    closes = {}
    meta = {}
    for sym in [BTC] + ALTS:
        df = load_ohlcv_1m_cached(sym)
        if df.empty:
            log.warning("[%s] no data", sym)
            continue
        # resample to daily close (last value of UTC day)
        daily_close = df["close"].resample("1D").last().dropna()
        closes[sym] = daily_close
        meta[sym] = {
            "n_1m_rows": int(len(df)),
            "n_daily": int(len(daily_close)),
            "min_ts": str(df.index.min()),
            "max_ts": str(df.index.max()),
        }
    panel = pd.concat(closes, axis=1).sort_index()
    return panel, meta


def compute_beta_and_z(panel: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """For each alt, compute rolling 30d beta vs BTC, then 60d z-score on beta.

    Returns
    -------
    beta_df : daily beta per alt (columns = alts, index = dates)
    beta_z_df : daily 60d z-score on beta series
    """
    rets = panel.pct_change()
    btc_ret = rets[BTC]
    beta_dict = {}
    bz_dict = {}
    for alt in ALTS:
        if alt not in rets.columns:
            continue
        alt_ret = rets[alt]
        # rolling beta = Cov(alt, btc) / Var(btc) over BETA_WINDOW
        # use pairwise rolling with min_periods to require full window
        roll_cov = alt_ret.rolling(BETA_WINDOW, min_periods=BETA_WINDOW).cov(btc_ret)
        roll_var = btc_ret.rolling(BETA_WINDOW, min_periods=BETA_WINDOW).var()
        beta = roll_cov / roll_var
        # z-score of beta over BETA_Z_WINDOW
        bz = (beta - beta.rolling(BETA_Z_WINDOW, min_periods=BETA_Z_WINDOW).mean()) / \
             beta.rolling(BETA_Z_WINDOW, min_periods=BETA_Z_WINDOW).std()
        beta_dict[alt] = beta
        bz_dict[alt] = bz
    return pd.DataFrame(beta_dict), pd.DataFrame(bz_dict)


def collect_triggers(panel: pd.DataFrame, beta_z_df: pd.DataFrame,
                     z_thresh: float, hold_d: int) -> pd.DataFrame:
    """For each (alt, day) where |beta_z|>=z_thresh and BTC direction known,
    compute hold-day forward return for the alt and tag the 4-cell membership.

    Returns long-format DataFrame:
        ts, symbol, beta_z, btc_dir (+1/-1/0),
        alt_ret_fwd (gross), cell ('1'/'2'/'3'/'4'/'skip'),
        signed_direction (+1 LONG / -1 SHORT / 0 skip),
        net_return (signed * alt_ret_fwd - fee)
    """
    btc_close = panel[BTC]
    btc_daily_ret = btc_close.pct_change()
    btc_dir = np.sign(btc_daily_ret).fillna(0).astype(int)

    rows = []
    for alt in ALTS:
        if alt not in panel.columns or alt not in beta_z_df.columns:
            continue
        alt_close = panel[alt]
        bz = beta_z_df[alt]
        # forward return over hold_d days from today's close to t+hold_d close
        fwd = alt_close.shift(-hold_d) / alt_close - 1.0
        df = pd.DataFrame({
            "ts": panel.index,
            "symbol": alt,
            "beta_z": bz.values,
            "btc_dir": btc_dir.values,
            "alt_ret_fwd": fwd.values,
        })
        # filter: |beta_z|>=z_thresh, btc_dir != 0, fwd not NaN
        mask = (df["beta_z"].abs() >= z_thresh) & (df["btc_dir"] != 0) & df["alt_ret_fwd"].notna()
        df = df.loc[mask].copy()
        if df.empty:
            continue

        # cell assignment
        def cell_of(r):
            if r["beta_z"] > 0 and r["btc_dir"] > 0:
                return "1", +1  # high beta + BTC up -> LONG
            if r["beta_z"] > 0 and r["btc_dir"] < 0:
                return "2", -1  # high beta + BTC dn -> SHORT
            if r["beta_z"] < 0 and r["btc_dir"] > 0:
                return "3", -1  # low beta + BTC up -> SHORT
            if r["beta_z"] < 0 and r["btc_dir"] < 0:
                return "4", +1  # low beta + BTC dn -> LONG
            return "skip", 0
        labels = df.apply(cell_of, axis=1, result_type="expand")
        df["cell"] = labels[0]
        df["signed_direction"] = labels[1]
        df["net_return"] = df["signed_direction"] * df["alt_ret_fwd"] - FEE_RT
        rows.append(df)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def collect_candidate_pool(panel: pd.DataFrame, hold_d: int) -> np.ndarray:
    """All possible (alt, day) hold-day forward GROSS returns for null pool.

    Used as candidate_pool_returns for fee_aware_perm_test.
    """
    pool = []
    for alt in ALTS:
        if alt not in panel.columns:
            continue
        alt_close = panel[alt]
        fwd = alt_close.shift(-hold_d) / alt_close - 1.0
        pool.append(fwd.dropna().values)
    if not pool:
        return np.array([])
    return np.concatenate(pool)


def evaluate_cell(triggers: pd.DataFrame, cell_id: str) -> dict:
    """Compute aggregate stats + per-symbol bootstrap + per-quarter t for a single cell."""
    sub = triggers.loc[triggers["cell"] == cell_id].copy()
    n = len(sub)
    if n < 10:
        return {
            "cell_id": cell_id,
            "n_trades": int(n),
            "skip": "n<10",
        }
    net = sub["net_return"].values
    mean_bp = float(net.mean() * 10000)

    # Per-quarter t-stat distribution
    sub["ts"] = pd.to_datetime(sub["ts"])
    sub["quarter"] = sub["ts"].dt.to_period("Q").astype(str)
    per_q = sub.groupby("quarter").agg(
        n_trades=("net_return", "size"),
        mean_bp=("net_return", lambda s: float(s.mean() * 10000)),
        t_stat=("net_return", lambda s: float(s.mean() / s.std(ddof=1) * (len(s) ** 0.5))
                if len(s) >= 3 and s.std(ddof=1) > 0 else float("nan")),
    ).reset_index()
    per_quarter_records = per_q.to_dict(orient="records")
    n_q_measurable = int((per_q["n_trades"] >= 10).sum())
    n_q_pos_t = int(((per_q["t_stat"] > 0) & (per_q["n_trades"] >= 10)).sum())

    # Per-symbol bootstrap CI
    per_sym_records = []
    for sym, g in sub.groupby("symbol"):
        if len(g) < 10:
            per_sym_records.append({"symbol": sym, "n_trades": int(len(g)), "skip": "n<10"})
            continue
        ci = bootstrap_ci(g["net_return"].values, n_boot=2000, block_size=1)
        per_sym_records.append({
            "symbol": sym,
            "n_trades": int(len(g)),
            "mean_bp": float(g["net_return"].mean() * 10000),
            "ci_lower_bp": ci["ci_lower"] * 10000,
            "ci_upper_bp": ci["ci_upper"] * 10000,
            "ci_lower_pos": bool(ci["ci_lower"] > 0),
        })
    n_sym_measurable = sum(1 for r in per_sym_records if r.get("skip") is None)
    n_sym_ci_pos = sum(1 for r in per_sym_records if r.get("ci_lower_pos") is True)

    return {
        "cell_id": cell_id,
        "n_trades": int(n),
        "mean_bp": mean_bp,
        "concentration": {
            "per_quarter_t_stats": per_quarter_records,
            "n_quarters_measurable": n_q_measurable,
            "n_quarters_pos_t": n_q_pos_t,
            "quarter_pos_t_ratio": (n_q_pos_t / n_q_measurable) if n_q_measurable else float("nan"),
            "per_symbol_bootstrap": per_sym_records,
            "n_symbols_measurable": n_sym_measurable,
            "n_symbols_ci_pos": n_sym_ci_pos,
            "symbol_ci_pos_ratio": (n_sym_ci_pos / n_sym_measurable) if n_sym_measurable else float("nan"),
        },
    }


def evaluate_focus_three_gate(triggers: pd.DataFrame, panel: pd.DataFrame,
                               hold_d: int) -> dict:
    """Focus = cell 1 (beta_z > +Z × BTC up × LONG). Run full 3-gate + concentration."""
    sub = triggers.loc[triggers["cell"] == "1"].copy()
    n = len(sub)
    if n < 10:
        return {"error": "focus cell 1 n<10", "n": int(n)}

    observed_net = sub["net_return"].values  # net (post-fee), already signed +1
    # For cell 1: signed_direction = +1, net = +alt_ret_fwd - fee = LONG net
    # Candidate pool: all possible gross daily forward returns across panel (LONG side)
    candidate_pool_gross = collect_candidate_pool(panel, hold_d)
    # For LONG: candidate gross direct returns
    fee_result = fee_aware_perm_test(
        observed_net_returns=observed_net,
        candidate_pool_returns=candidate_pool_gross,
        fee_per_trade=FEE_RT,
        n_perms=1000,
    )
    ci_result = bootstrap_ci(observed_net, n_boot=2000, block_size=hold_d)
    # 3-gate
    g_a = fee_result["signal_t_excess"] >= 2.0
    g_b = ci_result["ci_lower"] > 0
    g_c = fee_result["perm_p_two_sided"] <= 0.10
    return {
        "fee_aware_perm": fee_result,
        "bootstrap_ci": ci_result,
        "three_gate": {
            "A_signal_t_excess_ge_2": bool(g_a),
            "B_ci_lower_pos": bool(g_b),
            "C_perm_p_le_0p10": bool(g_c),
            "all_pass": bool(g_a and g_b and g_c),
        },
    }


def main() -> int:
    log.info("paradigm 81 R-1 — rolling_beta_regime_breakdown")
    log.info("loading 14-sym 1m cache, building daily panel...")
    panel, meta = build_daily_panel()
    log.info("daily panel: %d days × %d syms", len(panel), panel.shape[1])

    log.info("computing rolling 30d beta + 60d z-score...")
    beta_df, beta_z_df = compute_beta_and_z(panel)

    # Focus z=2.0, hold=5d, full 4-cell + 3-gate
    log.info("focus z=%.1f hold=%dd: 4-cell evaluation + three-gate on cell 1",
             FOCUS_Z, FOCUS_HOLD_D)
    focus_triggers = collect_triggers(panel, beta_z_df, FOCUS_Z, FOCUS_HOLD_D)
    log.info("focus total triggers: %d", len(focus_triggers))

    cell_breakdown = {}
    for cid in ["1", "2", "3", "4"]:
        cell_breakdown[cid] = evaluate_cell(focus_triggers, cid)
        n = cell_breakdown[cid].get("n_trades", 0)
        mean_bp = cell_breakdown[cid].get("mean_bp", float("nan"))
        log.info("  cell %s: n=%d mean_bp=%.2f", cid, n, mean_bp)

    focus_eval = evaluate_focus_three_gate(focus_triggers, panel, FOCUS_HOLD_D)
    log.info("focus cell 1 three-gate: %s", focus_eval.get("three_gate"))

    # Hold sweep (focus z=2.0, all 4 cells aggregate stats)
    log.info("hold sweep (z=%.1f, 1/3/5/10/20 d)...", FOCUS_Z)
    hold_sweep_records = []
    for hd in HOLD_SWEEP_D:
        trig = collect_triggers(panel, beta_z_df, FOCUS_Z, hd)
        for cid in ["1", "2", "3", "4"]:
            sub = trig.loc[trig["cell"] == cid]
            n = len(sub)
            if n < 5:
                hold_sweep_records.append({
                    "hold_d": hd, "cell": cid, "n": n, "mean_bp": float("nan"),
                    "t_stat": float("nan"),
                })
                continue
            net = sub["net_return"].values
            t = float(net.mean() / net.std(ddof=1) * (n ** 0.5)) if net.std(ddof=1) > 0 else float("nan")
            hold_sweep_records.append({
                "hold_d": hd, "cell": cid, "n": int(n),
                "mean_bp": float(net.mean() * 10000),
                "t_stat": t,
            })

    # Z threshold sweep at focus hold (3-gate eval per z)
    log.info("z threshold sweep (hold=%dd)...", FOCUS_HOLD_D)
    z_sweep_records = []
    for zt in Z_SWEEP:
        trig = collect_triggers(panel, beta_z_df, zt, FOCUS_HOLD_D)
        for cid in ["1", "2", "3", "4"]:
            sub = trig.loc[trig["cell"] == cid]
            n = len(sub)
            if n < 5:
                z_sweep_records.append({
                    "z": zt, "cell": cid, "n": n, "mean_bp": float("nan"),
                })
                continue
            z_sweep_records.append({
                "z": zt, "cell": cid, "n": int(n),
                "mean_bp": float(sub["net_return"].mean() * 10000),
            })

    # Build symmetric_variants block (Lesson #19)
    symmetric_variants = {
        "cell_1_high_beta_btc_up_LONG": cell_breakdown["1"],
        "cell_2_high_beta_btc_dn_SHORT": cell_breakdown["2"],
        "cell_3_low_beta_btc_up_SHORT": cell_breakdown["3"],
        "cell_4_low_beta_btc_dn_LONG": cell_breakdown["4"],
    }

    # Final metrics dict
    out = {
        "paradigm_name": "rolling_beta_regime_breakdown",
        "phase": "R-1",
        "hypothesis_summary": "13 alts × BTC rolling 30d beta breakdown, sign-conditional 4-cell, focus cell 1 high-beta-amp + BTC up + alt LONG, hold 5d",
        "data": {
            "syms": [BTC] + ALTS,
            "per_sym_meta": meta,
            "beta_window_d": BETA_WINDOW,
            "beta_z_window_d": BETA_Z_WINDOW,
            "focus_z": FOCUS_Z,
            "focus_hold_d": FOCUS_HOLD_D,
            "fee_round_trip": FEE_RT,
        },
        "focus_three_gate": focus_eval,
        "symmetric_variants": symmetric_variants,
        "hold_sweep_records": hold_sweep_records,
        "z_sweep_records": z_sweep_records,
    }

    # Final R-1 verdict
    tg = focus_eval.get("three_gate", {})
    all_pass = tg.get("all_pass", False)
    cell1 = cell_breakdown.get("1", {}).get("concentration", {})
    conc_q = cell1.get("quarter_pos_t_ratio")
    conc_s_ratio = cell1.get("symbol_ci_pos_ratio")
    n_sym_pos = cell1.get("n_symbols_ci_pos", 0)
    conc_gate = False
    if conc_q is not None and conc_s_ratio is not None:
        conc_gate = (conc_q >= 0.5) and (conc_s_ratio >= 0.30) and (n_sym_pos >= 3)

    # All cells negative test (broad-falsified detection, Lesson #19)
    all_cells_neg = True
    for cid in ["1", "2", "3", "4"]:
        c = cell_breakdown.get(cid, {})
        mb = c.get("mean_bp")
        if mb is not None and mb > 0:
            all_cells_neg = False
            break

    if all_pass and conc_gate:
        verdict = "R1_PASS"
    elif all_pass and not conc_gate:
        verdict = "CONCENTRATED_R1_PASS"
    elif all_cells_neg:
        verdict = "BROAD_FALSIFIED_R1_FAIL"
    else:
        verdict = "R1_FAIL"

    out["verdict"] = verdict
    out["concentration_gate"] = {
        "quarter_pos_t_ratio": conc_q,
        "symbol_ci_pos_ratio": conc_s_ratio,
        "n_symbols_ci_pos": n_sym_pos,
        "passes": bool(conc_gate),
    }

    # Persist outputs
    json_path = OUT_DIR / "r1__metrics.json"
    with open(json_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("wrote %s", json_path)

    # per_symbol.csv: cell 1 per-symbol detail
    sym_records = cell1.get("per_symbol_bootstrap", []) if cell1 else []
    if sym_records:
        pd.DataFrame(sym_records).to_csv(OUT_DIR / "r1__per_symbol.csv", index=False)
        log.info("wrote r1__per_symbol.csv (%d rows)", len(sym_records))

    # hold_sweep.csv
    pd.DataFrame(hold_sweep_records).to_csv(OUT_DIR / "r1__hold_sweep.csv", index=False)
    log.info("wrote r1__hold_sweep.csv (%d rows)", len(hold_sweep_records))

    pd.DataFrame(z_sweep_records).to_csv(OUT_DIR / "r1__z_sweep.csv", index=False)
    log.info("wrote r1__z_sweep.csv (%d rows)", len(z_sweep_records))

    log.info("==== VERDICT: %s ====", verdict)
    log.info("focus cell 1: n=%d mean_bp=%.2f sigex=%.2f ci_lower_bp=%.2f perm_p=%.4f",
             cell_breakdown["1"].get("n_trades", 0),
             cell_breakdown["1"].get("mean_bp", float("nan")),
             focus_eval.get("fee_aware_perm", {}).get("signal_t_excess", float("nan")),
             focus_eval.get("bootstrap_ci", {}).get("ci_lower", float("nan")) * 10000,
             focus_eval.get("fee_aware_perm", {}).get("perm_p_two_sided", float("nan")))
    log.info("symmetric variants mean_bp: c1=%.2f c2=%.2f c3=%.2f c4=%.2f",
             cell_breakdown["1"].get("mean_bp", float("nan")),
             cell_breakdown["2"].get("mean_bp", float("nan")),
             cell_breakdown["3"].get("mean_bp", float("nan")),
             cell_breakdown["4"].get("mean_bp", float("nan")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
