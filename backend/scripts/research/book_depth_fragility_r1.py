"""Book-depth fragility SHORT — R-1 PoC.

Hypothesis (single sentence):
  When daily book-depth `top1_concentration_mean` rises into its rolling 30d
  p80 AND `near_imbalance_mean < -0.1` (ask-pressure) on the same day,
  the next day's open->close return on Binance Futures perpetuals shows
  systematic SHORT bias (fragile top-of-book + ask-side pressure ->
  leveraged unwind trigger).

Sub-hypotheses:
  H1 — main directional test (signal vs random-day baseline)
  H2 — fee-aware net EV (8 bps round-trip)
  H3 — permutation null (1000x shuffle)
  H4 — sample-size sanity (n_signals, per-sym distribution)

Output: backend/runs/research_track/book_depth_fragility_short/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("book_depth_fragility_r1")

SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT",
    "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT",
    "WIFUSDT", "XRPUSDT",
]
BOOKDEPTH_DIR = ROOT / "runs" / "book_depth"
OUT_DIR = ROOT / "runs" / "research_track" / "book_depth_fragility_short"
OUT_PATH = OUT_DIR / "r1__metrics.json"

# Trigger rule
P80_LOOKBACK = 30        # rolling-30d p80 for top1_concentration
NEAR_IMBAL_THR = -0.10   # ask-pressure side

# Trading cost
ROUND_TRIP_FEE = 0.0008  # 8 bps

# Permutation
N_PERM = 1000
SEED = 42


def load_bookdepth(sym: str) -> pd.DataFrame:
    path = BOOKDEPTH_DIR / f"{sym}_bookdepth.joblib"
    if not path.exists():
        return pd.DataFrame()
    df = joblib.load(path)
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    df = df.sort_index().copy()
    df.index = pd.to_datetime(df.index)
    return df


def load_ohlcv_1m(db, sym: str, start: datetime, end: datetime) -> pd.DataFrame:
    rows = db.execute(
        text(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m' "
            "AND timestamp >= :st AND timestamp < :en "
            "ORDER BY timestamp"
        ),
        {"s": sym, "st": start, "en": end},
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    return df


def daily_open_close(df_1m: pd.DataFrame) -> pd.DataFrame:
    """Resample 1m to UTC-day open/close (first/last bar)."""
    if df_1m.empty:
        return pd.DataFrame()
    g = df_1m.groupby(df_1m.index.normalize())
    o = g["open"].first()
    c = g["close"].last()
    out = pd.DataFrame({"open": o, "close": c})
    out["ret"] = out["close"] / out["open"] - 1.0
    return out


def t_stat(x: np.ndarray) -> float:
    if len(x) < 2:
        return float("nan")
    sd = float(np.std(x, ddof=1))
    if sd == 0:
        return float("nan")
    return float(np.mean(x) / (sd / np.sqrt(len(x))))


def build_signals_for_sym(bd: pd.DataFrame, oc: pd.DataFrame) -> dict:
    """Align book-depth signal day d to next-day (d+1) open->close return."""
    if bd.empty or oc.empty:
        return {"signal_rets": np.array([]), "all_rets": np.array([]), "n_signals": 0, "n_days": 0}

    bd = bd.copy()
    bd["p80"] = bd["top1_concentration_mean"].rolling(P80_LOOKBACK, min_periods=15).quantile(0.80)
    bd["trigger"] = (
        (bd["top1_concentration_mean"] > bd["p80"]) &
        (bd["near_imbalance_mean"] < NEAR_IMBAL_THR)
    )
    bd["next_date"] = bd.index + pd.Timedelta(days=1)
    # Map to next-day return
    oc_idx = oc.index.normalize()
    oc_lookup = pd.Series(oc["ret"].values, index=oc_idx)

    rets = []
    all_rets_collected = []
    triggered_dates = []

    for d, row in bd.iterrows():
        nxt = (d + pd.Timedelta(days=1)).normalize()
        r_next = oc_lookup.get(nxt, np.nan)
        if pd.notna(r_next):
            all_rets_collected.append(r_next)
            if bool(row["trigger"]):
                rets.append(r_next)
                triggered_dates.append(str(nxt.date()))

    return {
        "signal_rets": np.array(rets, dtype=float),
        "all_rets": np.array(all_rets_collected, dtype=float),
        "n_signals": int(np.sum(bd["trigger"].fillna(False))),
        "n_days": int(len(bd)),
        "triggered_dates": triggered_dates,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        per_sym = {}
        pool_signal = []
        pool_all = []

        for sym in SYMBOLS:
            bd = load_bookdepth(sym)
            if bd.empty:
                log.warning("No book-depth for %s", sym)
                continue
            # OHLCV window aligned to bd index (need d+1 day for last sig)
            start = bd.index.min() - pd.Timedelta(days=2)
            end = bd.index.max() + pd.Timedelta(days=2)
            df_1m = load_ohlcv_1m(db, sym, start.to_pydatetime(), end.to_pydatetime())
            if df_1m.empty:
                log.warning("No OHLCV for %s", sym)
                continue
            oc = daily_open_close(df_1m)
            res = build_signals_for_sym(bd, oc)
            sig = res["signal_rets"]
            allr = res["all_rets"]
            per_sym[sym] = {
                "n_signals": int(len(sig)),
                "n_days_aligned": int(len(allr)),
                "signal_mean": float(np.mean(sig)) if len(sig) > 0 else None,
                "signal_median": float(np.median(sig)) if len(sig) > 0 else None,
                "signal_t": t_stat(sig) if len(sig) >= 2 else None,
                "signal_win_neg": float(np.mean(sig < 0)) if len(sig) > 0 else None,
                "all_mean": float(np.mean(allr)) if len(allr) > 0 else None,
            }
            log.info(
                "%s: n_sig=%d n_days=%d sig_mean=%.4f%% sig_t=%s",
                sym, len(sig), len(allr),
                (np.mean(sig) * 100) if len(sig) > 0 else float("nan"),
                f"{per_sym[sym]['signal_t']:.2f}" if per_sym[sym]["signal_t"] is not None else "nan",
            )
            pool_signal.append(sig)
            pool_all.append(allr)

        all_signal = np.concatenate(pool_signal) if pool_signal else np.array([])
        all_baseline = np.concatenate(pool_all) if pool_all else np.array([])

        # H1 — main test
        h1 = {
            "n_signals_total": int(len(all_signal)),
            "n_baseline_total": int(len(all_baseline)),
            "signal_mean": float(np.mean(all_signal)) if len(all_signal) > 0 else None,
            "signal_median": float(np.median(all_signal)) if len(all_signal) > 0 else None,
            "signal_t_vs_zero": t_stat(all_signal) if len(all_signal) >= 2 else None,
            "signal_win_neg_rate": float(np.mean(all_signal < 0)) if len(all_signal) > 0 else None,
            "baseline_mean": float(np.mean(all_baseline)) if len(all_baseline) > 0 else None,
            "baseline_t_vs_zero": t_stat(all_baseline) if len(all_baseline) >= 2 else None,
        }

        # H2 — fee-aware net EV (SHORT side: pnl = -ret - fee)
        if len(all_signal) > 0:
            short_pnl_gross = -all_signal
            short_pnl_net = short_pnl_gross - ROUND_TRIP_FEE
            # estimate trades_per_year_per_sym
            n_syms_active = sum(1 for s in per_sym.values() if s["n_signals"] > 0)
            total_days = max(1, max((s["n_days_aligned"] for s in per_sym.values()), default=1))
            trades_per_year_per_sym = (len(all_signal) / max(1, n_syms_active)) * (365.0 / total_days)
            h2 = {
                "gross_mean": float(np.mean(short_pnl_gross)),
                "gross_t": t_stat(short_pnl_gross),
                "net_mean": float(np.mean(short_pnl_net)),
                "net_t": t_stat(short_pnl_net),
                "net_win_rate": float(np.mean(short_pnl_net > 0)),
                "round_trip_fee": ROUND_TRIP_FEE,
                "trades_per_year_per_sym_est": float(trades_per_year_per_sym),
                "annualized_alpha_est_pct": float(np.mean(short_pnl_net) * trades_per_year_per_sym * 100),
            }
        else:
            h2 = {"net_mean": None, "net_t": None}

        # H3 — permutation null (shuffle trigger labels across full pool)
        h3 = {"perm_p_value": None, "n_perm": 0}
        if len(all_signal) >= 2 and len(all_baseline) >= len(all_signal):
            obs_t = h1["signal_t_vs_zero"]
            rng = np.random.default_rng(SEED)
            n_sig = len(all_signal)
            base = all_baseline
            null_ts = np.empty(N_PERM, dtype=float)
            for i in range(N_PERM):
                idx = rng.choice(len(base), size=n_sig, replace=False)
                sample = base[idx]
                sd = sample.std(ddof=1)
                null_ts[i] = (sample.mean() / (sd / np.sqrt(n_sig))) if sd > 0 else 0.0
            # two-sided p (we hypothesize negative so direction matters; report both)
            p_two = float(np.mean(np.abs(null_ts) >= abs(obs_t)))
            p_left = float(np.mean(null_ts <= obs_t))
            h3 = {
                "perm_p_two_sided": p_two,
                "perm_p_left_tail": p_left,
                "obs_t": obs_t,
                "null_t_mean": float(null_ts.mean()),
                "null_t_std": float(null_ts.std(ddof=1)),
                "n_perm": N_PERM,
            }

        # H4 — sample size sanity
        per_sym_n = {k: v["n_signals"] for k, v in per_sym.items()}
        n_syms_lt5 = sum(1 for n in per_sym_n.values() if n < 5)
        h4 = {
            "n_signals_total": int(len(all_signal)),
            "per_sym_n": per_sym_n,
            "n_syms_with_lt5_signals": int(n_syms_lt5),
            "underpowered": bool(len(all_signal) < 100 or n_syms_lt5 > len(per_sym_n) / 2),
        }

        # Verdict
        def fmt(v, fallback="nan"):
            return v if v is not None else fallback

        t1 = h1.get("signal_t_vs_zero")
        net_m = h2.get("net_mean") if isinstance(h2, dict) else None
        perm_p = h3.get("perm_p_two_sided")
        n_sig_total = h4["n_signals_total"]

        is_graveyard = False
        is_candidate = False
        reasons = []

        if t1 is None or abs(t1) < 1.5:
            is_graveyard = True
            reasons.append(f"H1 |t|<1.5 ({t1})")
        if net_m is not None and net_m <= 0:
            is_graveyard = True
            reasons.append(f"H2 net_mean<=0 ({net_m:.5f})")
        if perm_p is not None and perm_p > 0.10:
            is_graveyard = True
            reasons.append(f"H3 perm_p>0.10 ({perm_p:.3f})")
        if n_sig_total < 100:
            is_graveyard = True
            reasons.append(f"H4 n_signals<100 ({n_sig_total})")
        if t1 is not None and t1 > 0 and h1.get("signal_mean", 0) > 0:
            is_graveyard = True
            reasons.append("H1 direction OPPOSITE (next-day positive)")

        if (
            t1 is not None and abs(t1) >= 2.0
            and net_m is not None and net_m > 0  # short net positive => signal_mean negative
            and perm_p is not None and perm_p <= 0.05
            and n_sig_total >= 200
        ):
            is_candidate = True
            is_graveyard = False
            reasons = ["all candidate criteria met"]

        if not is_graveyard and not is_candidate:
            verdict = "BORDERLINE"
        elif is_candidate:
            verdict = "CANDIDATE-FOR-R2"
        else:
            verdict = "GRAVEYARD"

        out = {
            "paradigm": "book_depth_fragility_short",
            "phase": "R-1",
            "generated_at": datetime.utcnow().isoformat(),
            "trigger_rule": {
                "top1_conc_pctile": 80,
                "rolling_lookback_days": P80_LOOKBACK,
                "near_imbalance_threshold": NEAR_IMBAL_THR,
            },
            "symbols": SYMBOLS,
            "H1_main": h1,
            "H2_fee_net": h2,
            "H3_perm": h3,
            "H4_sample": h4,
            "per_sym": per_sym,
            "verdict": verdict,
            "verdict_reasons": reasons,
        }

        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("wrote %s", OUT_PATH)

        # Console summary
        print("=" * 70)
        print(f"PARADIGM: book_depth_fragility_short  (R-1)")
        print(f"  Symbols active     : {sum(1 for s in per_sym.values() if s['n_signals'] > 0)}/{len(SYMBOLS)}")
        print(f"  H1 n_signals       : {h1['n_signals_total']}")
        print(f"  H1 signal_mean ret : {h1['signal_mean']*100 if h1['signal_mean'] else float('nan'):.3f}% per day")
        print(f"  H1 baseline_mean   : {h1['baseline_mean']*100 if h1['baseline_mean'] else float('nan'):.3f}% per day")
        print(f"  H1 t-stat vs 0     : {t1:.3f}" if t1 is not None else "  H1 t-stat vs 0     : nan")
        print(f"  H1 win_neg_rate    : {h1['signal_win_neg_rate']*100 if h1['signal_win_neg_rate'] else float('nan'):.1f}%")
        print(f"  H2 net_mean (short): {h2.get('net_mean')*100 if h2.get('net_mean') is not None else float('nan'):.4f}%")
        print(f"  H2 net_t           : {h2.get('net_t')}")
        print(f"  H2 alpha_annual_est: {h2.get('annualized_alpha_est_pct')}%")
        print(f"  H3 perm_p_two_side : {h3.get('perm_p_two_sided')}")
        print(f"  H3 perm_p_left     : {h3.get('perm_p_left_tail')}")
        print(f"  H4 underpowered    : {h4['underpowered']}")
        print(f"  H4 syms with <5 sig: {h4['n_syms_with_lt5_signals']}/{len(SYMBOLS)}")
        print(f"  VERDICT            : {verdict}")
        print(f"  reasons            : {reasons}")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
