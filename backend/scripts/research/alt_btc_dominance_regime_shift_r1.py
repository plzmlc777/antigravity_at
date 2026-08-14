"""Paradigm 239 R-1 PoC — BTC dominance regime shift → alt rotation (SOL PoC).

Signal: dom_z = 90d z-score of (btc_7d_ret - alt_basket_7d_ret) spread.
4-quadrant SNT (Lesson #39):
- A_focus: dom_z <= -T → LONG SOL (hypothesis: BTC lagging → alt rotation up)
- A_mirror: dom_z <= -T → SHORT SOL (mirror direction)
- B_focus: dom_z >= +T → SHORT SOL (hypothesis: BTC dominating → alt drain)
- B_mirror: dom_z >= +T → LONG SOL (mirror direction)

Sweep: window ∈ {60,90,120}, spread ∈ {5,7,14}, z_T ∈ {1.0,1.5,2.0}, hold ∈ {1d,2d,3d}
Reduced from 324 to 108 cells by picking single symbol SOL (per Lesson #37 full sweep).

Concentration gate (single-sym PoC form):
- Best cell: alpha>0 AND sharpe>0 AND mean_net_bp>0 AND n>=30

Sub-class A test (Lesson #39): A_focus + A_mirror ≈ -2×fee → BROAD_FALSIFIED.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research._ohlcv_parquet_cache import load_ohlcv_1m_cached  # noqa: E402
from scripts.research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("p239_r1")

OUT_DIR = ROOT / "runs" / "research_track" / "alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BTC = "BTCUSDT"
ALT_UNIVERSE = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT",
    "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
POC_SYM = "SOLUSDT"

FEE_ONE_SIDE = 0.0004  # 4bp; round-trip 8bp
FEE_RT = 2 * FEE_ONE_SIDE


def load_daily_close(sym: str) -> pd.Series:
    df = load_ohlcv_1m_cached(sym)
    if df.empty:
        return pd.Series(dtype=float)
    return df["close"].resample("1D").last().dropna()


def compute_dom_z(btc_close, alt_closes, window, spread):
    btc_ret = btc_close.pct_change(spread)
    alt_ret_df = pd.DataFrame({s: c.pct_change(spread) for s, c in alt_closes.items()})
    alt_ret_df = alt_ret_df.reindex(btc_ret.index)
    alt_basket_ret = alt_ret_df.mean(axis=1)
    sp = btc_ret - alt_basket_ret
    dom_z = (sp - sp.rolling(window).mean()) / sp.rolling(window).std(ddof=1)
    return dom_z


def build_trades(dom_z: pd.Series, close: pd.Series, T: float, hold_d: int, side: str, quadrant: str):
    """Build non-overlapping trades. quadrant: A_focus|A_mirror|B_focus|B_mirror."""
    close = close.reindex(dom_z.index)
    if quadrant in ("A_focus", "A_mirror"):
        mask = dom_z <= -T
    else:
        mask = dom_z >= T
    if quadrant in ("A_focus",):
        direction = +1  # LONG (BTC lagging → LONG alts)
    elif quadrant in ("A_mirror",):
        direction = -1
    elif quadrant in ("B_focus",):
        direction = -1  # SHORT (BTC dominating → SHORT alts)
    else:  # B_mirror
        direction = +1

    ts_all = dom_z.index[mask]
    trades = []
    last_exit = None
    for entry_ts in ts_all:
        if last_exit is not None and entry_ts < last_exit:
            continue
        entry_pos = dom_z.index.get_loc(entry_ts)
        exit_pos = entry_pos + hold_d
        if exit_pos >= len(dom_z.index):
            break
        entry_price = close.iloc[entry_pos]
        exit_price = close.iloc[exit_pos]
        if pd.isna(entry_price) or pd.isna(exit_price) or entry_price <= 0:
            continue
        raw_ret = (exit_price / entry_price - 1.0) * direction
        net_ret = raw_ret - FEE_RT
        trades.append({
            "entry_ts": entry_ts, "exit_ts": dom_z.index[exit_pos],
            "raw_ret": raw_ret, "net_ret": net_ret,
        })
        last_exit = dom_z.index[exit_pos]
    return pd.DataFrame(trades)


def evaluate_cell(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty or len(trades_df) < 5:
        return {"n": len(trades_df), "verdict": "INSUFFICIENT"}
    r = trades_df["net_ret"].values
    n = len(r)
    mean = float(np.mean(r))
    std = float(np.std(r, ddof=1)) if n > 1 else 0.0
    t = mean / std * np.sqrt(n) if std > 0 else 0.0
    winrate = float(np.mean(r > 0))
    return {
        "n": int(n),
        "mean_net_bp": round(mean * 10000, 2),
        "median_net_bp": round(float(np.median(r)) * 10000, 2),
        "std_bp": round(std * 10000, 2),
        "t_stat": round(float(t), 3),
        "sharpe_ann": round(mean / std * np.sqrt(365 / 2) if std > 0 else 0.0, 3),  # ~1.5d avg
        "winrate": round(winrate, 3),
    }


def run():
    log.info("R-1 loading data")
    btc = load_daily_close(BTC)
    alts = {s: load_daily_close(s) for s in ALT_UNIVERSE}
    alts = {s: c for s, c in alts.items() if not c.empty}
    # align
    idx = btc.index
    for s, c in alts.items():
        idx = idx.intersection(c.index)
    btc = btc.reindex(idx)
    alts = {s: c.reindex(idx) for s, c in alts.items()}
    log.info("aligned %d days, %d alts", len(idx), len(alts))

    sol_close = alts[POC_SYM]

    windows = [60, 90, 120]
    spreads = [5, 7, 14]
    thresholds = [1.0, 1.5, 2.0]
    holds = [1, 2, 3]
    quadrants = ["A_focus", "A_mirror", "B_focus", "B_mirror"]

    results = []
    log.info("sweeping %d × %d × %d × %d × %d = %d cells",
             len(windows), len(spreads), len(thresholds), len(holds), len(quadrants),
             len(windows)*len(spreads)*len(thresholds)*len(holds)*len(quadrants))

    for w in windows:
        for sp in spreads:
            dom_z = compute_dom_z(btc, alts, w, sp).dropna()
            for T in thresholds:
                for h in holds:
                    for q in quadrants:
                        trades = build_trades(dom_z, sol_close, T, h, "sol", q)
                        ev = evaluate_cell(trades)
                        cell = {
                            "window": w, "spread": sp, "T": T, "hold_d": h, "quadrant": q,
                            **ev,
                        }
                        results.append(cell)

    df = pd.DataFrame(results)
    df["passes"] = (
        (df.get("n", 0) >= 30)
        & (df.get("mean_net_bp", -999).astype(float) > 0)
        & (df.get("t_stat", -999).astype(float) > 0)
        & (df.get("sharpe_ann", -999).astype(float) > 0)
    )
    n_pass = int(df["passes"].sum())
    log.info("cells: %d total, %d pass concentration gate", len(df), n_pass)

    # Sub-class A (Lesson #39): pair A_focus + A_mirror per (w,sp,T,h)
    a_pair = []
    for (w, sp, T, h), g in df.groupby(["window", "spread", "T", "hold_d"]):
        af = g[g["quadrant"] == "A_focus"]
        am = g[g["quadrant"] == "A_mirror"]
        if len(af) and len(am) and af.iloc[0].get("n", 0) >= 5 and am.iloc[0].get("n", 0) >= 5:
            sum_bp = float(af.iloc[0]["mean_net_bp"]) + float(am.iloc[0]["mean_net_bp"])
            a_pair.append({
                "window": w, "spread": sp, "T": T, "hold_d": h,
                "af_bp": float(af.iloc[0]["mean_net_bp"]),
                "am_bp": float(am.iloc[0]["mean_net_bp"]),
                "sum_bp": round(sum_bp, 2),
                "fee_floor_bp": round(-2 * FEE_RT * 10000, 2),
            })
    a_pair_df = pd.DataFrame(a_pair)

    # Top 10 cells by t_stat
    df_valid = df[df.get("n", 0).apply(lambda x: isinstance(x, (int, float)) and x >= 30)].copy()
    if not df_valid.empty:
        df_valid["t_stat"] = pd.to_numeric(df_valid["t_stat"], errors="coerce")
        top10 = df_valid.sort_values("t_stat", ascending=False).head(10)
    else:
        top10 = pd.DataFrame()

    # Concentration verdict
    passing_cells = df[df["passes"]].sort_values("t_stat" if "t_stat" in df.columns else "mean_net_bp", ascending=False)

    # Fee-aware perm test on TOP cell if any
    perm_result = None
    ci_result = None
    if not passing_cells.empty:
        top = passing_cells.iloc[0]
        w, sp, T, h, q = int(top["window"]), int(top["spread"]), float(top["T"]), int(top["hold_d"]), top["quadrant"]
        dom_z = compute_dom_z(btc, alts, w, sp).dropna()
        trades_top = build_trades(dom_z, sol_close, T, h, "sol", q)
        if len(trades_top) >= 30:
            obs_returns = pd.Series(trades_top["net_ret"].values)
            # Candidate pool: all possible hold-window returns on SOL over aligned period
            sol_aligned = sol_close.reindex(dom_z.index)
            direction = +1 if q in ("A_focus", "B_mirror") else -1
            cand_gross = []
            for i in range(len(sol_aligned) - h):
                ep = sol_aligned.iloc[i]
                xp = sol_aligned.iloc[i + h]
                if pd.notna(ep) and pd.notna(xp) and ep > 0:
                    cand_gross.append((xp / ep - 1.0) * direction)
            perm_result = fee_aware_perm_test(
                observed_net_returns=obs_returns,
                candidate_pool_returns=cand_gross,
                fee_per_trade=FEE_RT,
                n_perms=1000,
            )
            ci_result = bootstrap_ci(obs_returns, n_boot=2000, block_size=10)

    out = {
        "paradigm": "alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h",
        "phase": "R-1",
        "symbol": POC_SYM,
        "universe_alts": list(alts.keys()),
        "n_cells": len(df),
        "n_pass_concentration": int(n_pass),
        "top_10_cells_by_t_stat": top10.to_dict(orient="records") if not top10.empty else [],
        "passing_cells": passing_cells.head(20).to_dict(orient="records"),
        "subclass_A_lesson39_pairs_top10": a_pair_df.sort_values("sum_bp", ascending=False).head(10).to_dict(orient="records") if not a_pair_df.empty else [],
        "subclass_A_all_pairs_broad_fee_symmetric": bool((a_pair_df["sum_bp"] < -1.5 * FEE_RT * 10000).all()) if not a_pair_df.empty else None,
        "top_cell_perm": {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in perm_result.items()
        } if perm_result else None,
        "top_cell_bootstrap_ci": {
            k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
            for k, v in ci_result.items()
        } if ci_result else None,
    }

    out_path = OUT_DIR / "r1__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", out_path)

    # Verdict
    if n_pass == 0:
        log.error("R-1 GRAVEYARD: no cell passed concentration gate")
        return 1

    if perm_result:
        gate3 = (
            perm_result.get("signal_t_excess", -999) >= 2.0
            and ci_result.get("ci_lower", -999) > 0
            and perm_result.get("perm_p", 1.0) <= 0.10
        )
        log.info("Top cell 3-gate: signal_t_excess=%.3f, ci_lower=%.6f, perm_p=%.3f → %s",
                 perm_result.get("signal_t_excess"), ci_result.get("ci_lower"),
                 perm_result.get("perm_p"), "PASS" if gate3 else "FAIL")
        if not gate3:
            log.warning("R-1 concentration PASS but 3-gate FAIL on top cell")
            return 2
    log.info("R-1 PASS → proceed to R-2")
    return 0


if __name__ == "__main__":
    sys.exit(run())
