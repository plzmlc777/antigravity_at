"""R-2 expansion — smart_money_lsr_contrarian.

Apply best R-1 spec (contrarian, entry_z=2.5, exit_z=0.5, hold=288 bars=24h)
to 10 paper-pool standard symbols. Per symbol: simulate, perm-test (n=200),
bootstrap CI on alpha (n=1000).

Pass criteria (PARADIGM_QUEUE_2026Q2 standard):
  alpha_pos_count >= 6/10 AND sharpe_pos_count >= 5/10

Output: backend/runs/research_track/smart_money_lsr_contrarian/r2__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# reuse simulate from poc
from scripts.research.smart_money_lsr_contrarian_poc import (  # noqa: E402
    CAPITAL,
    FEE_RATE,
    JOBLIB_DIR,
    OUT_DIR,
    SL_PCT,
    TRAIN_FRAC,
    ZWIN,
    load_panel,
    simulate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("smart_money_lsr_contrarian_r2")

PARADIGM = "smart_money_lsr_contrarian"
SYMBOLS = ["SOLUSDT", "AVAXUSDT", "DOGEUSDT", "HBARUSDT", "LINKUSDT",
           "UNIUSDT", "LDOUSDT", "ETCUSDT", "AXSUSDT", "COMPUSDT"]

# Best from R-1 sweep
BEST_SPEC = {"entry_z": 2.5, "exit_z": 0.5, "max_hold_bars": 288, "mode": "contrarian"}

PERM_N = 200
BOOTSTRAP_N = 1000
RNG = np.random.default_rng(42)


def perm_test(df: pd.DataFrame, base_alpha: float, n: int = PERM_N) -> dict:
    """Shuffle the LSR signal time-index then re-simulate. p = P(perm_alpha >= base_alpha)."""
    perm_alphas = []
    for k in range(n):
        df_perm = df.copy()
        # shuffle lsr_z within OOS only
        z_shuffled = df_perm["lsr_z"].dropna().sample(frac=1.0, random_state=int(RNG.integers(0, 2**31))).reset_index(drop=True)
        df_perm = df_perm.dropna(subset=["lsr_z"]).copy()
        df_perm["lsr_z"] = z_shuffled.values
        try:
            m = simulate(df_perm, **BEST_SPEC)
        except Exception:
            continue
        perm_alphas.append(m["alpha_pct"])
    perm_alphas = np.array(perm_alphas)
    p = float((perm_alphas >= base_alpha).mean())
    if perm_alphas.std() > 0:
        sigma = (base_alpha - perm_alphas.mean()) / perm_alphas.std()
    else:
        sigma = 0.0
    return {
        "perm_n": int(len(perm_alphas)),
        "perm_alpha_mean": float(perm_alphas.mean()) if len(perm_alphas) else 0.0,
        "perm_alpha_std": float(perm_alphas.std()) if len(perm_alphas) else 0.0,
        "perm_p": p,
        "perm_sigma": float(sigma),
    }


def bootstrap_alpha(trade_rets: list[float], n: int = BOOTSTRAP_N) -> dict:
    if len(trade_rets) < 30:
        return {"boot_n": 0, "boot_alpha_mean": 0.0, "boot_ci_lo": 0.0, "boot_ci_hi": 0.0}
    arr = np.array(trade_rets)
    boot_means = []
    for _ in range(n):
        sample = RNG.choice(arr, size=len(arr), replace=True)
        # cumulative compounded growth
        eq = np.prod(1 + sample) - 1.0
        boot_means.append(eq * 100)
    boot_means = np.array(boot_means)
    return {
        "boot_n": int(n),
        "boot_alpha_mean": float(boot_means.mean()),
        "boot_ci_lo": float(np.percentile(boot_means, 2.5)),
        "boot_ci_hi": float(np.percentile(boot_means, 97.5)),
    }


def run_symbol(symbol: str) -> dict:
    log.info("loading %s ...", symbol)
    try:
        df_full = load_panel(symbol)
    except FileNotFoundError:
        log.warning("  joblib missing for %s", symbol)
        return {"symbol": symbol, "error": "joblib_missing"}
    if len(df_full) < ZWIN + 5000:
        return {"symbol": symbol, "error": "insufficient_data", "n": int(len(df_full))}

    split_idx = int(len(df_full) * TRAIN_FRAC)
    df_oos = df_full.iloc[split_idx:].copy()
    log.info("  OOS rows=%d range=%s..%s", len(df_oos), df_oos.index.min(), df_oos.index.max())

    base = simulate(df_oos, **BEST_SPEC)
    base["symbol"] = symbol

    # need trade_rets list for bootstrap; reconstruct from trade_log truncation OK,
    # but for full sample we need to call sim with full log retention
    # quick re-sim to capture all trade rets
    trade_rets = _full_trade_rets(df_oos)

    boot = bootstrap_alpha(trade_rets)
    log.info("  base alpha=%.2f%% sharpe=%.2f trades=%d -> running %d perms ...",
             base["alpha_pct"], base["sharpe_ann"], base["n_trades"], PERM_N)

    perm = perm_test(df_oos, base_alpha=base["alpha_pct"])
    log.info("  perm_p=%.3f perm_sigma=%.2f boot_ci=[%.1f, %.1f]",
             perm["perm_p"], perm["perm_sigma"], boot["boot_ci_lo"], boot["boot_ci_hi"])

    return {**base, **perm, **boot}


def _full_trade_rets(df: pd.DataFrame) -> list[float]:
    """Re-run simulate but extract all trade.net_ret values."""
    # patch simulate behaviour by post-processing trade_log
    px = df["price"].to_numpy()
    z = df["lsr_z"].to_numpy()
    n = len(df)
    sign_threshold = +1  # contrarian
    pos = 0; entry_px = 0.0; entry_idx = 0; direction = 0
    rets = []
    entry_z = BEST_SPEC["entry_z"]; exit_z = BEST_SPEC["exit_z"]; max_hold = BEST_SPEC["max_hold_bars"]
    for i in range(ZWIN, n - 1):
        if pos == 0:
            if not np.isfinite(z[i]):
                continue
            if z[i] >= entry_z:
                direction = -sign_threshold; pos = 1; entry_px = px[i]; entry_idx = i
            elif z[i] <= -entry_z:
                direction = +sign_threshold; pos = 1; entry_px = px[i]; entry_idx = i
        else:
            held = i - entry_idx
            cur_ret = direction * (px[i] / entry_px - 1.0)
            done = False
            if cur_ret <= -SL_PCT: done = True
            elif np.isfinite(z[i]) and abs(z[i]) <= exit_z: done = True
            elif held >= max_hold: done = True
            if done:
                rets.append(cur_ret - 2 * FEE_RATE)
                pos = 0; direction = 0; entry_px = 0.0
    return rets


def main() -> int:
    results = []
    for sym in SYMBOLS:
        try:
            r = run_symbol(sym)
            results.append(r)
        except Exception as e:
            log.exception("error on %s: %s", sym, e)
            results.append({"symbol": sym, "error": str(e)})

    valid = [r for r in results if "error" not in r and r.get("n_trades", 0) >= 30]

    alpha_pos = sum(1 for r in valid if r["alpha_pct"] > 0)
    sharpe_pos = sum(1 for r in valid if r["sharpe_ann"] > 0)
    perm_p_pass = sum(1 for r in valid if r.get("perm_p", 1.0) <= 0.05)

    aggregate = {
        "n_valid": len(valid),
        "alpha_pos_count": alpha_pos,
        "sharpe_pos_count": sharpe_pos,
        "perm_p_pass_count": perm_p_pass,
        "alpha_pct_mean": float(np.mean([r["alpha_pct"] for r in valid])) if valid else 0.0,
        "alpha_pct_median": float(np.median([r["alpha_pct"] for r in valid])) if valid else 0.0,
        "sharpe_mean": float(np.mean([r["sharpe_ann"] for r in valid])) if valid else 0.0,
        "trades_total": int(sum(r["n_trades"] for r in valid)),
    }

    # PARADIGM_QUEUE_2026Q2 fail-fast
    verdict = "FAIL"
    if alpha_pos >= 6 and sharpe_pos >= 5:
        verdict = "PASS"
        reason = (f"alpha_pos {alpha_pos}/10 ≥ 6 AND sharpe_pos {sharpe_pos}/10 ≥ 5")
    else:
        reason = (f"alpha_pos {alpha_pos}/10 (need ≥6), sharpe_pos {sharpe_pos}/10 (need ≥5)")

    out = {
        "paradigm": PARADIGM,
        "phase": "R-2_multi_symbol",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "symbols": SYMBOLS,
            "best_spec": BEST_SPEC,
            "zwin": ZWIN,
            "sl_pct": SL_PCT,
            "fee_rate": FEE_RATE,
            "capital": CAPITAL,
            "train_frac": TRAIN_FRAC,
            "perm_n": PERM_N,
            "bootstrap_n": BOOTSTRAP_N,
        },
        "per_symbol": results,
        "aggregate": aggregate,
        "verdict": verdict,
        "fail_fast_reason": reason,
    }
    out_path = OUT_DIR / "r2__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", out_path)

    print(f"\n=== R-2 verdict: {verdict} ===")
    print(f"reason: {reason}")
    print(f"alpha mean={aggregate['alpha_pct_mean']:.1f}% median={aggregate['alpha_pct_median']:.1f}%")
    print(f"sharpe mean={aggregate['sharpe_mean']:.2f}")
    print(f"perm p <=0.05 in {perm_p_pass}/{len(valid)} syms")
    print(f"\nper-symbol (alpha%, sharpe, perm_p, trades):")
    for r in results:
        if "error" in r:
            print(f"  {r['symbol']:10s}  ERROR: {r['error']}")
        else:
            print(f"  {r['symbol']:10s}  alpha={r['alpha_pct']:7.2f}%  sharpe={r['sharpe_ann']:5.2f}  "
                  f"perm_p={r.get('perm_p', 0):.3f}  perm_σ={r.get('perm_sigma', 0):5.2f}  "
                  f"trades={r['n_trades']}")
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
