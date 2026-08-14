"""R-1 verify — run fee-aware perm + bootstrap on top 3 cells by t_stat.

If none pass 3-gate, R-1 is definitively GRAVEYARD.
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
log = logging.getLogger("p239_r1v")

OUT_DIR = ROOT / "runs" / "research_track" / "alt_btc_dominance_regime_shift_alt_rotation_24h_to_72h"

BTC = "BTCUSDT"
ALT_UNIVERSE = ["ADAUSDT","AVAXUSDT","BCHUSDT","BNBUSDT","DOGEUSDT","ETHUSDT","FILUSDT","LINKUSDT","LTCUSDT","NEARUSDT","SOLUSDT","WIFUSDT","XRPUSDT"]
POC = "SOLUSDT"
FEE_RT = 0.0008


def load_daily(sym):
    df = load_ohlcv_1m_cached(sym)
    return df["close"].resample("1D").last().dropna() if not df.empty else pd.Series(dtype=float)


def dom_z(btc, alts, w, sp):
    b = btc.pct_change(sp)
    a = pd.DataFrame({s: c.pct_change(sp) for s, c in alts.items()}).reindex(b.index).mean(axis=1)
    s = b - a
    return (s - s.rolling(w).mean()) / s.rolling(w).std(ddof=1)


def build(z, close, T, h, q):
    close = close.reindex(z.index)
    mask = (z <= -T) if q in ("A_focus", "A_mirror") else (z >= T)
    direction = +1 if q in ("A_focus", "B_mirror") else -1
    ts = z.index[mask]
    out, last = [], None
    for e in ts:
        if last is not None and e < last:
            continue
        p = z.index.get_loc(e)
        if p + h >= len(z.index):
            break
        ep, xp = close.iloc[p], close.iloc[p + h]
        if pd.notna(ep) and pd.notna(xp) and ep > 0:
            out.append({"e": e, "x": z.index[p + h], "r": (xp / ep - 1.0) * direction - FEE_RT})
            last = z.index[p + h]
    return pd.DataFrame(out)


def cand_pool(z, close, h, direction):
    close = close.reindex(z.index)
    pool = []
    for i in range(len(close) - h):
        ep, xp = close.iloc[i], close.iloc[i + h]
        if pd.notna(ep) and pd.notna(xp) and ep > 0:
            pool.append((xp / ep - 1.0) * direction)
    return pool


def main():
    btc = load_daily(BTC)
    alts = {s: load_daily(s) for s in ALT_UNIVERSE}
    alts = {s: c for s, c in alts.items() if not c.empty}
    idx = btc.index
    for c in alts.values():
        idx = idx.intersection(c.index)
    btc = btc.reindex(idx)
    alts = {s: c.reindex(idx) for s, c in alts.items()}
    sol = alts[POC]

    # Top 3 cells from R-1 output
    top_cells = [
        {"window": 120, "spread": 5, "T": 2.0, "hold_d": 1, "quadrant": "A_focus"},
        {"window": 90, "spread": 7, "T": 1.0, "hold_d": 2, "quadrant": "B_mirror"},
        {"window": 90, "spread": 7, "T": 1.0, "hold_d": 1, "quadrant": "B_mirror"},
        {"window": 120, "spread": 7, "T": 1.0, "hold_d": 3, "quadrant": "B_mirror"},
    ]

    results = []
    for tc in top_cells:
        z = dom_z(btc, alts, tc["window"], tc["spread"]).dropna()
        trades = build(z, sol, tc["T"], tc["hold_d"], tc["quadrant"])
        direction = +1 if tc["quadrant"] in ("A_focus", "B_mirror") else -1
        pool = cand_pool(z, sol, tc["hold_d"], direction)
        if len(trades) < 30:
            results.append({**tc, "n": len(trades), "verdict": "INSUFFICIENT"})
            continue
        obs = pd.Series(trades["r"].values)
        perm = fee_aware_perm_test(observed_net_returns=obs, candidate_pool_returns=pool,
                                    fee_per_trade=FEE_RT, n_perms=1000)
        ci = bootstrap_ci(obs, n_boot=2000, block_size=10)
        gate = (perm.get("signal_t_excess", -99) >= 2.0
                and ci.get("ci_lower", -99) > 0
                and perm.get("perm_p_two_sided", 1.0) <= 0.10)
        results.append({
            **tc,
            "n": len(trades),
            "signal_t_excess": round(perm["signal_t_excess"], 3),
            "ci_lower_bp": round(ci["ci_lower"] * 10000, 2),
            "perm_p_two_sided": round(perm["perm_p_two_sided"], 3),
            "perm_p_one_above": round(perm["perm_p_one_sided_above"], 3),
            "obs_t": round(perm["obs_t"], 3),
            "null_mean_t": round(perm["null_mean_t"], 3),
            "gate3": "PASS" if gate else "FAIL",
        })

    log.info("verify results:")
    for r in results:
        log.info("  %s", r)

    out = {"phase": "R-1-verify", "top_cells": results}
    (OUT_DIR / "r1__top_cells_verify.json").write_text(json.dumps(out, indent=2, default=str))

    n_pass = sum(1 for r in results if r.get("gate3") == "PASS")
    log.info("gate3 pass: %d/%d", n_pass, len(results))
    return 0 if n_pass > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
