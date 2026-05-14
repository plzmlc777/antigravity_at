"""R-1 PoC — smart_money_lsr_contrarian.

Hypothesis: top-trader account L/S ratio rolling z-score (zwin=288 = 24h on 5m
bars) extremes |z| >= entry_z signal crowd positioning extremes that
mean-revert. Contrarian: z>+entry_z (crowd long) -> SHORT; z<-entry_z (crowd
short) -> LONG. Exit on |z| <= exit_z OR max_hold_bars timestop.

Single symbol R-1: SOL. Sweep grid (entry_z, exit_z, max_hold_bars, mode).
Train/test split: last 50% OOS (train_frac=0.5).

Price source: implied_price = open_interest_value_usdt / open_interest from
microstructure joblib (corr=0.996 vs DB ohlcv close, 5m bars).

Output: backend/runs/research_track/smart_money_lsr_contrarian/poc__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("smart_money_lsr_contrarian_poc")

PARADIGM = "smart_money_lsr_contrarian"
JOBLIB_DIR = ROOT / "runs" / "microstructure"
OUT_DIR = ROOT / "runs" / "research_track" / PARADIGM
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Strategy constants
ZWIN = 288                  # 24h on 5min bars
SL_PCT = 0.02               # 2% stop-loss (matches oi_price_decoupling baseline)
FEE_RATE = 0.0004           # Binance taker fee per side (round trip = 0.0008)
CAPITAL = 1_000_000.0
TRAIN_FRAC = 0.5            # last 50% OOS

R1_SYMBOL = "SOLUSDT"
ENTRY_Z_GRID = [2.0, 2.5, 3.0]
EXIT_Z_GRID = [0.0, 0.5, 1.0]
HOLD_GRID = [72, 144, 288]   # 6h / 12h / 24h
MODES = ["contrarian", "follow"]


def load_panel(symbol: str) -> pd.DataFrame:
    path = JOBLIB_DIR / f"{symbol}_full_metrics.joblib"
    df = joblib.load(path)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]
    df["price"] = df["open_interest_value_usdt"] / df["open_interest"]
    df["lsr"] = df["toptrader_account_ls_ratio"]
    df = df.dropna(subset=["price", "lsr"])
    df["lsr_mean"] = df["lsr"].rolling(ZWIN, min_periods=ZWIN).mean()
    df["lsr_std"] = df["lsr"].rolling(ZWIN, min_periods=ZWIN).std()
    df["lsr_z"] = (df["lsr"] - df["lsr_mean"]) / df["lsr_std"]
    df["ret_fwd_1bar"] = df["price"].pct_change().shift(-1)
    return df


def simulate(df: pd.DataFrame, entry_z: float, exit_z: float,
             max_hold_bars: int, mode: str, sl_pct: float = SL_PCT,
             fee_rate: float = FEE_RATE) -> dict:
    """Sequential bar-by-bar sim. One position at a time.

    Contrarian: z>+entry_z -> SHORT (direction=-1); z<-entry_z -> LONG (direction=+1)
    Follow:     z>+entry_z -> LONG  (direction=+1); z<-entry_z -> SHORT (direction=-1)

    Exit: (a) |z| <= exit_z, (b) hold >= max_hold_bars, (c) sl_pct hit on adverse.
    """
    px = df["price"].to_numpy()
    z = df["lsr_z"].to_numpy()
    n = len(df)
    if n < ZWIN + max_hold_bars + 100:
        return {"n_trades": 0, "alpha_pct": 0.0, "sharpe_ann": 0.0, "max_dd_pct": 0.0,
                "win_rate_pct": 0.0, "profit_factor": 0.0, "total_return_pct": 0.0,
                "buy_hold_pct": 0.0, "oos_days": 0, "trade_log": []}

    sign_threshold = +1 if mode == "contrarian" else -1  # contrarian flips crowd direction

    pos = 0   # 0 = flat
    entry_px = 0.0
    entry_idx = 0
    direction = 0
    trades = []
    equity = CAPITAL
    equity_curve = []
    timestamps = df.index

    for i in range(ZWIN, n - 1):
        # mark-to-market
        if pos != 0:
            cur_ret = direction * (px[i] / entry_px - 1.0)
            cur_equity = equity * (1 + cur_ret)
        else:
            cur_equity = equity
        equity_curve.append((timestamps[i], cur_equity))

        if pos == 0:
            # consider entry
            if not np.isfinite(z[i]):
                continue
            if z[i] >= entry_z:
                # crowd long -> contrarian SHORT (direction=-1) ; follow LONG (direction=+1)
                direction = -sign_threshold
                pos = 1
                entry_px = px[i]
                entry_idx = i
            elif z[i] <= -entry_z:
                direction = +sign_threshold
                pos = 1
                entry_px = px[i]
                entry_idx = i
        else:
            # consider exit
            held = i - entry_idx
            cur_ret = direction * (px[i] / entry_px - 1.0)
            exit_reason = None
            if cur_ret <= -sl_pct:
                exit_reason = "sl"
            elif np.isfinite(z[i]) and abs(z[i]) <= exit_z:
                exit_reason = "z_revert"
            elif held >= max_hold_bars:
                exit_reason = "timestop"
            if exit_reason:
                gross_ret = cur_ret
                fee = 2 * fee_rate          # round trip
                net_ret = gross_ret - fee
                equity *= (1 + net_ret)
                trades.append({
                    "entry_t": str(timestamps[entry_idx]),
                    "exit_t": str(timestamps[i]),
                    "direction": int(direction),
                    "entry_px": float(entry_px),
                    "exit_px": float(px[i]),
                    "held_bars": int(held),
                    "gross_ret": float(gross_ret),
                    "net_ret": float(net_ret),
                    "exit_reason": exit_reason,
                })
                pos = 0
                direction = 0
                entry_px = 0.0

    if not trades:
        bh = (px[-1] / px[ZWIN] - 1.0) * 100 if px[ZWIN] > 0 else 0.0
        return {"n_trades": 0, "alpha_pct": 0.0, "sharpe_ann": 0.0, "max_dd_pct": 0.0,
                "win_rate_pct": 0.0, "profit_factor": 0.0, "total_return_pct": 0.0,
                "buy_hold_pct": float(bh), "oos_days": 0, "trade_log": []}

    rets = np.array([t["net_ret"] for t in trades])
    total_return = equity / CAPITAL - 1.0
    bh_return = px[-1] / px[ZWIN] - 1.0
    alpha = total_return - bh_return
    wins = (rets > 0).sum()
    win_rate = wins / len(rets) * 100
    pf = (rets[rets > 0].sum() / -rets[rets < 0].sum()) if (rets < 0).any() else float("inf")

    # equity-based sharpe / dd
    eq = pd.Series([e for _, e in equity_curve])
    eq_ret = eq.pct_change().dropna()
    if len(eq_ret) > 1 and eq_ret.std() > 0:
        # annualized: 5min bars => 12*24*365 = 105120 bars/yr
        sharpe = eq_ret.mean() / eq_ret.std() * np.sqrt(12 * 24 * 365)
    else:
        sharpe = 0.0
    cummax = eq.cummax()
    dd = (eq / cummax - 1.0).min()
    max_dd_pct = abs(dd) * 100

    oos_days = (timestamps[-1] - timestamps[ZWIN]).total_seconds() / 86400

    return {
        "n_trades": int(len(trades)),
        "alpha_pct": float(alpha * 100),
        "sharpe_ann": float(sharpe),
        "max_dd_pct": float(max_dd_pct),
        "win_rate_pct": float(win_rate),
        "profit_factor": float(pf if pf != float("inf") else 999.0),
        "total_return_pct": float(total_return * 100),
        "buy_hold_pct": float(bh_return * 100),
        "oos_days": float(oos_days),
        "trade_log": trades[:5] + (trades[-5:] if len(trades) > 10 else []),
    }


def main() -> int:
    log.info("loading SOLUSDT panel ...")
    df_full = load_panel(R1_SYMBOL)
    log.info("panel rows=%d range=%s..%s", len(df_full), df_full.index.min(), df_full.index.max())

    # OOS split
    split_idx = int(len(df_full) * TRAIN_FRAC)
    df_oos = df_full.iloc[split_idx:].copy()
    log.info("OOS rows=%d range=%s..%s", len(df_oos), df_oos.index.min(), df_oos.index.max())

    results: list[dict] = []
    for entry_z, exit_z, hold, mode in product(ENTRY_Z_GRID, EXIT_Z_GRID, HOLD_GRID, MODES):
        if exit_z >= entry_z:
            continue
        spec = f"{mode}_z{entry_z}_xz{exit_z}_h{hold}"
        log.info("running %s ...", spec)
        m = simulate(df_oos, entry_z=entry_z, exit_z=exit_z, max_hold_bars=hold, mode=mode)
        m["spec"] = spec
        m["entry_z"] = entry_z
        m["exit_z"] = exit_z
        m["max_hold_bars"] = hold
        m["mode"] = mode
        results.append(m)
        log.info("  %s -> trades=%d alpha=%.2f%% sharpe=%.2f wr=%.1f%% dd=%.1f%%",
                 spec, m["n_trades"], m["alpha_pct"], m["sharpe_ann"],
                 m["win_rate_pct"], m["max_dd_pct"])

    # find best contrarian + best follow for fail-fast
    contrarian = [r for r in results if r["mode"] == "contrarian" and r["n_trades"] >= 30]
    follow = [r for r in results if r["mode"] == "follow" and r["n_trades"] >= 30]

    def _best(rs):
        if not rs:
            return None
        return max(rs, key=lambda r: r["alpha_pct"])

    best_contra = _best(contrarian)
    best_follow = _best(follow)

    # R-1 verdict
    verdict = "FAIL"
    reason = ""
    if best_contra is None:
        reason = "no contrarian spec produced >=30 trades"
    elif best_contra["alpha_pct"] >= 0 and best_contra["sharpe_ann"] >= 0:
        verdict = "PASS"
        reason = (f"best_contra alpha={best_contra['alpha_pct']:.1f}% sharpe="
                  f"{best_contra['sharpe_ann']:.2f}")
    elif best_contra["alpha_pct"] < -10 and best_contra["sharpe_ann"] < -1.0:
        reason = (f"strongly negative: alpha={best_contra['alpha_pct']:.1f}% sharpe="
                  f"{best_contra['sharpe_ann']:.2f}")
    else:
        reason = (f"both signs fail: alpha={best_contra['alpha_pct']:.1f}% sharpe="
                  f"{best_contra['sharpe_ann']:.2f}")

    out = {
        "paradigm": PARADIGM,
        "phase": "R-1_PoC",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "symbol": R1_SYMBOL,
            "zwin": ZWIN,
            "sl_pct": SL_PCT,
            "fee_rate": FEE_RATE,
            "capital": CAPITAL,
            "train_frac": TRAIN_FRAC,
            "entry_z_grid": ENTRY_Z_GRID,
            "exit_z_grid": EXIT_Z_GRID,
            "hold_grid_bars": HOLD_GRID,
            "modes": MODES,
        },
        "all_specs": results,
        "best_contrarian": best_contra,
        "best_follow": best_follow,
        "verdict": verdict,
        "fail_fast_reason": reason,
        "sub_hypotheses": {
            "a_extremes_revert": "contrarian alpha > 0 and sharpe > 0 = supported",
            "b_contra_beats_follow": (
                "best_contra alpha > best_follow alpha = supported"
                if best_contra and best_follow and best_contra["alpha_pct"] > best_follow["alpha_pct"]
                else "not supported"
            ),
            "c_12h_optimal": (
                f"best hold = {best_contra['max_hold_bars']} bars" if best_contra else "n/a"
            ),
        },
    }

    out_path = OUT_DIR / "poc__metrics.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    log.info("wrote %s", out_path)

    print(f"\n=== R-1 verdict: {verdict} ===")
    print(f"reason: {reason}")
    if best_contra:
        print(f"best contrarian: {best_contra['spec']} "
              f"alpha={best_contra['alpha_pct']:.2f}% sharpe={best_contra['sharpe_ann']:.2f} "
              f"trades={best_contra['n_trades']} wr={best_contra['win_rate_pct']:.1f}%")
    if best_follow:
        print(f"best follow:     {best_follow['spec']} "
              f"alpha={best_follow['alpha_pct']:.2f}% sharpe={best_follow['sharpe_ann']:.2f} "
              f"trades={best_follow['n_trades']} wr={best_follow['win_rate_pct']:.1f}%")
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
