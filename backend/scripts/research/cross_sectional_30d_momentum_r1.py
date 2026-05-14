"""R-1 PoC — Cross-sectional 30-day momentum CONTINUATION (crypto perps).

Universe: 14 Binance USDT-perp symbols (ADA, AVAX, BCH, BNB, BTC, DOGE, ETH,
FIL, LINK, LTC, NEAR, SOL, WIF, XRP).

Hypothesis: Every Monday 00:00 UTC, LONG the trailing-30d winner and SHORT the
trailing-30d loser; hold to Friday close. Pair returns are hypothesized to be
systematically POSITIVE (Carhart-style cross-sectional momentum CONTINUATION).

This is the mode-flipped, longer-lookback successor of
cross_sectional_weekly_momentum_reversal (5d MR, graveyarded). The MR test
showed gross +2.70%/wk for the OPPOSITE-side trade (long winner + short
loser), suggesting a continuation regime worth direct testing at the
classical equity-momentum 1-3mo timescale.

Sub-hypotheses
  H1 — Main pair return: mean, t, Sharpe, win rate, n_weeks (gross).
  H2 — Fee-aware net EV: round-trip 8 bps × 2 = 16 bps per pair-week.
  H3 — Permutation null: shuffle winner/loser identity across the 14 syms on
       each Monday; preserves marginal sym return distributions. n=1000.
  H4 — Sub-decile robustness: 2-long/2-short variant.
  H5 — Alternative lookback robustness: scan {20, 30, 45, 60}d. Pass if ≥2/4
       lookbacks share positive net direction.
  H6 — Vol-regime split: high-vol weeks vs low-vol weeks (median split on
       trailing-30d universe-mean absolute daily return).

Sign convention
  pair_gross > 0 → momentum CONTINUATION (hypothesis confirmed).
  pair_gross < 0 → momentum REVERSED (graveyard cause, since MR-5d already
                   showed reversal exists but at a shorter horizon).

Output: backend/runs/research_track/cross_sectional_30d_momentum_continuation/r1__metrics.json
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("cross_sectional_30d_momentum_r1")

PARADIGM = "cross_sectional_30d_momentum_continuation"
OUT_PATH = ROOT / "runs" / "research_track" / PARADIGM / "r1__metrics.json"

SYMBOLS = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT",
    "FILUSDT", "LINKUSDT", "LTCUSDT", "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]
LOOKBACK_DAYS = 30           # main test
LOOKBACK_GRID = [20, 30, 45, 60]  # H5
FEE_ROUND_TRIP_PER_LEG = 0.0008  # 8 bps × 2 legs = 16 bps per pair-week
FEE_PAIR = FEE_ROUND_TRIP_PER_LEG * 2
PERM_N = 1000
RNG_SEED = 42


# ---------- data loading ----------

def load_daily_close(db, sym: str) -> pd.Series:
    """Resample 1m ohlcv to daily close on UTC date alignment."""
    rows = db.execute(text(
        "SELECT timestamp, close FROM ohlcv "
        "WHERE symbol=:s AND time_frame='1m' ORDER BY timestamp"
    ), {"s": sym}).fetchall()
    if not rows:
        return pd.Series(dtype=float, name=sym)
    df = pd.DataFrame(rows, columns=["timestamp", "close"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    daily_close = df["close"].resample("1D").last()
    daily_close.name = sym
    return daily_close


def build_universe_panel(db) -> pd.DataFrame:
    series = {}
    for sym in SYMBOLS:
        s = load_daily_close(db, sym)
        if s.empty:
            log.warning("skip %s — no rows", sym)
            continue
        series[sym] = s
        log.info("%s: %d daily closes, %s → %s", sym, len(s), s.index.min().date(), s.index.max().date())
    panel = pd.DataFrame(series).sort_index()
    panel = panel.dropna(how="all")
    return panel


# ---------- core sim ----------

def find_mondays(panel: pd.DataFrame, lookback_days: int) -> list[pd.Timestamp]:
    """Mondays where we have ≥ lookback_days BEFORE and Friday close (≤ panel max) after."""
    mondays = []
    for d in panel.index:
        if d.weekday() != 0:  # Monday = 0
            continue
        before = panel.index[panel.index < d]
        if len(before) < lookback_days + 1:
            continue
        fri_target = d + pd.Timedelta(days=4)
        if fri_target > panel.index.max():
            continue
        mondays.append(d)
    return mondays


def compute_weekly_pair_returns(panel: pd.DataFrame, mondays: list[pd.Timestamp],
                                  lookback_days: int) -> pd.DataFrame:
    """For each Monday: trailing N-trading-day return per sym, rank, identify
    winner/loser, compute pair return from Mon close to Fri close.

    Pair gross = (+1) × w_ret + (-1) × l_ret   (LONG winner, SHORT loser).
    Top2 variant: average of top-2 longs minus average of bottom-2 shorts.
    """
    records = []
    for mon in mondays:
        before_idx = panel.index[panel.index < mon]
        if len(before_idx) < lookback_days + 1:
            continue
        lookback_start = before_idx[-lookback_days]
        lookback_end = before_idx[-1]
        start_pos = panel.index.get_loc(lookback_start)
        if start_pos < 1:
            continue
        t0 = panel.index[start_pos - 1]
        prev_closes = panel.loc[t0]
        recent_closes = panel.loc[lookback_end]
        trailing_ret = (recent_closes / prev_closes - 1).dropna()
        if len(trailing_ret) < 14:
            continue
        ranked = trailing_ret.sort_values()
        loser = ranked.index[0]
        winner = ranked.index[-1]
        loser2 = list(ranked.index[:2])
        winner2 = list(ranked.index[-2:])

        fri = mon + pd.Timedelta(days=4)
        if fri not in panel.index:
            cand = panel.index[panel.index <= fri]
            if len(cand) == 0 or cand[-1] <= mon:
                continue
            fri = cand[-1]
        try:
            entry = panel.loc[mon]
            exit_ = panel.loc[fri]
        except KeyError:
            continue
        if pd.isna(entry[winner]) or pd.isna(entry[loser]) or pd.isna(exit_[winner]) or pd.isna(exit_[loser]):
            continue
        w_ret = exit_[winner] / entry[winner] - 1
        l_ret = exit_[loser] / entry[loser] - 1
        # CONTINUATION: long winner, short loser.
        pair_gross = (+1.0) * w_ret + (-1.0) * l_ret
        pair_net = pair_gross - FEE_PAIR

        # top2 / bot2 variant — long avg(top2), short avg(bot2)
        w2_rets = [exit_[s] / entry[s] - 1 for s in winner2
                    if not pd.isna(entry[s]) and not pd.isna(exit_[s])]
        l2_rets = [exit_[s] / entry[s] - 1 for s in loser2
                    if not pd.isna(entry[s]) and not pd.isna(exit_[s])]
        if not w2_rets or not l2_rets:
            top2_pair_gross = None
            top2_pair_net = None
        else:
            w2_ret = float(np.mean(w2_rets))
            l2_ret = float(np.mean(l2_rets))
            top2_pair_gross = (+1.0) * w2_ret + (-1.0) * l2_ret
            top2_pair_net = top2_pair_gross - FEE_PAIR * 2  # 4 legs

        records.append({
            "monday": mon,
            "friday": fri,
            "winner": winner,
            "loser": loser,
            "w_ret": float(w_ret),
            "l_ret": float(l_ret),
            "pair_gross": float(pair_gross),
            "pair_net": float(pair_net),
            "top2_pair_gross": float(top2_pair_gross) if top2_pair_gross is not None else np.nan,
            "top2_pair_net": float(top2_pair_net) if top2_pair_net is not None else np.nan,
        })

    return pd.DataFrame(records)


def compute_universe_vol(panel: pd.DataFrame, mondays_used: list[pd.Timestamp]) -> dict:
    """For each Monday, trailing-30d universe-mean abs daily return."""
    daily_ret = panel.pct_change()
    abs_ret = daily_ret.abs().mean(axis=1)
    out = {}
    for mon in mondays_used:
        window = abs_ret[abs_ret.index < mon].tail(30)
        if len(window) < 10:
            continue
        out[mon] = float(window.mean())
    return out


def permutation_test(panel: pd.DataFrame, mondays: list[pd.Timestamp],
                      observed_t: float, n_perm: int = PERM_N, seed: int = RNG_SEED) -> dict:
    """Shuffle winner/loser identity. For each Monday, randomly pick 2 syms as
    (fake winner, fake loser), apply CONTINUATION pair return, aggregate t,
    compare to observed.
    """
    rng = np.random.default_rng(seed)
    syms = list(panel.columns)
    perm_ts = []
    for _ in range(n_perm):
        pair_rets = []
        for mon in mondays:
            fri = mon + pd.Timedelta(days=4)
            if fri not in panel.index:
                cand = panel.index[panel.index <= fri]
                if len(cand) == 0 or cand[-1] <= mon:
                    continue
                fri = cand[-1]
            try:
                entry = panel.loc[mon]
                exit_ = panel.loc[fri]
            except KeyError:
                continue
            avail = [s for s in syms if not pd.isna(entry[s]) and not pd.isna(exit_[s])]
            if len(avail) < 2:
                continue
            picks = rng.choice(avail, size=2, replace=False)
            fake_w, fake_l = picks[0], picks[1]
            w_ret = exit_[fake_w] / entry[fake_w] - 1
            l_ret = exit_[fake_l] / entry[fake_l] - 1
            pair = (+1.0) * w_ret + (-1.0) * l_ret
            pair_rets.append(pair)
        if not pair_rets:
            continue
        arr = np.array(pair_rets)
        if arr.std() == 0:
            continue
        t = arr.mean() / (arr.std() / np.sqrt(len(arr)))
        perm_ts.append(t)
    perm_ts = np.array(perm_ts)
    p = float(np.mean(np.abs(perm_ts) >= abs(observed_t))) if len(perm_ts) else None
    return {
        "n_perm": int(len(perm_ts)),
        "perm_t_mean": float(perm_ts.mean()) if len(perm_ts) else None,
        "perm_t_std": float(perm_ts.std()) if len(perm_ts) else None,
        "perm_p_two_sided": p,
    }


def summarize_series(s: pd.Series, label: str) -> dict:
    s = s.dropna()
    if len(s) == 0:
        return {"label": label, "n": 0}
    mean = float(s.mean())
    std = float(s.std())
    n = len(s)
    t = mean / (std / np.sqrt(n)) if std > 0 and n > 1 else 0.0
    sharpe_ann = mean / std * np.sqrt(52) if std > 0 else 0.0
    return {
        "label": label,
        "n": int(n),
        "mean_pct": round(mean * 100, 4),
        "median_pct": round(float(s.median()) * 100, 4),
        "std_pct": round(std * 100, 4),
        "t_stat": round(float(t), 3),
        "sharpe_ann": round(float(sharpe_ann), 3),
        "win_rate": round(float((s > 0).mean()), 3),
    }


# ---------- main ----------

def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        log.info("loading 14-symbol daily panel …")
        panel = build_universe_panel(db)
        log.info("panel shape: %s", panel.shape)
        log.info("panel range: %s → %s", panel.index.min().date(), panel.index.max().date())

        # Main lookback = 30d
        mondays = find_mondays(panel, LOOKBACK_DAYS)
        log.info("found %d candidate Mondays (lookback=%dd)", len(mondays), LOOKBACK_DAYS)
        full = panel.dropna()
        mondays = [m for m in mondays if m in full.index]
        log.info("Mondays with full 14-sym coverage: %d", len(mondays))

        log.info("computing weekly pair returns (continuation, lookback=30d) …")
        weekly = compute_weekly_pair_returns(panel, mondays, LOOKBACK_DAYS)
        log.info("weekly records: %d", len(weekly))

        if len(weekly) < 10:
            out = {"paradigm": PARADIGM, "verdict": "graveyard",
                   "reason": "insufficient_weeks", "n_weeks": len(weekly)}
            OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
            log.warning("insufficient weeks (%d) — graveyard", len(weekly))
            return 0

        h1 = summarize_series(weekly["pair_gross"], "H1_pair_gross")
        h2 = summarize_series(weekly["pair_net"], "H2_pair_net")
        h2["alpha_ann_pct"] = round(h2["mean_pct"] * 52, 3)

        log.info("H1 (gross): %s", json.dumps(h1))
        log.info("H2 (net):   %s", json.dumps(h2))

        log.info("running permutation test (n=%d) …", PERM_N)
        perm = permutation_test(panel, weekly["monday"].tolist(), observed_t=h1["t_stat"])
        log.info("H3 perm: %s", json.dumps(perm))

        # H4 — top2/bot2 variant
        h4_gross = summarize_series(weekly["top2_pair_gross"], "H4_top2_gross")
        h4_net = summarize_series(weekly["top2_pair_net"], "H4_top2_net")
        log.info("H4 (top2 gross): %s", json.dumps(h4_gross))
        log.info("H4 (top2 net):   %s", json.dumps(h4_net))

        # H5 — lookback grid
        h5_grid = []
        for lb in LOOKBACK_GRID:
            m_lb = find_mondays(panel, lb)
            m_lb = [m for m in m_lb if m in full.index]
            w_lb = compute_weekly_pair_returns(panel, m_lb, lb)
            if len(w_lb) < 5:
                h5_grid.append({"lookback_days": lb, "n_weeks": int(len(w_lb)),
                                "note": "insufficient"})
                continue
            s_gross = summarize_series(w_lb["pair_gross"], f"H5_lb{lb}_gross")
            s_net = summarize_series(w_lb["pair_net"], f"H5_lb{lb}_net")
            h5_grid.append({
                "lookback_days": lb,
                "n_weeks": s_gross["n"],
                "gross_mean_pct": s_gross["mean_pct"],
                "net_mean_pct": s_net["mean_pct"],
                "t_stat": s_gross["t_stat"],
                "sharpe_ann": s_net["sharpe_ann"],
                "win_rate": s_gross["win_rate"],
            })
        log.info("H5 lookback grid: %s", json.dumps(h5_grid))
        h5_consistent = sum(1 for r in h5_grid if r.get("net_mean_pct", 0) > 0)
        log.info("H5 consistent (net_mean>0): %d/%d", h5_consistent, len(LOOKBACK_GRID))

        # H6 — vol regime split (on main 30d run)
        univ_vol = compute_universe_vol(panel, weekly["monday"].tolist())
        weekly["univ_vol"] = weekly["monday"].map(univ_vol)
        weekly_with_vol = weekly.dropna(subset=["univ_vol"])
        median_vol = float(weekly_with_vol["univ_vol"].median()) if len(weekly_with_vol) else 0.0
        hi = weekly_with_vol[weekly_with_vol["univ_vol"] > median_vol]["pair_gross"]
        lo = weekly_with_vol[weekly_with_vol["univ_vol"] <= median_vol]["pair_gross"]
        h6_hi = summarize_series(hi, "H6_high_vol_gross")
        h6_lo = summarize_series(lo, "H6_low_vol_gross")
        log.info("H6 (high vol gross): %s", json.dumps(h6_hi))
        log.info("H6 (low vol gross):  %s", json.dumps(h6_lo))

        # Verdict per R-1 graveyard / candidate-for-R2 criteria.
        t_abs = abs(h1["t_stat"])
        sharpe = h2["sharpe_ann"]
        net_mean = h2["mean_pct"] / 100
        perm_p = perm["perm_p_two_sided"]
        n_weeks = h1["n"]
        sign_pair = np.sign(h1["mean_pct"])  # + = continuation; - = reversed
        h4_t = abs(h4_gross["t_stat"]) if h4_gross.get("t_stat") is not None else 0.0
        h4_net_mean = h4_net.get("mean_pct", 0)

        reasons = []
        if t_abs < 1.8:
            reasons.append(f"H1_t_below_1.8 ({t_abs:.2f})")
        if net_mean <= 0:
            reasons.append(f"net_mean_nonpositive ({net_mean*100:.2f}%)")
        if perm_p is None or perm_p > 0.10:
            reasons.append(f"perm_p_above_0.10 ({perm_p})")
        if sign_pair < 0:
            reasons.append("pair_direction_opposite_continuation_failed")
        if n_weeks < 25:
            reasons.append(f"n_weeks_below_25 ({n_weeks})")
        if sharpe < 0.3:
            reasons.append(f"sharpe_below_0.3 ({sharpe:.2f})")
        if h5_consistent < 2:
            reasons.append(f"H5_lookback_consistency_below_2of4 ({h5_consistent}/4)")

        # H4 informational: same-direction check
        h4_robust = (np.sign(h4_net_mean) == sign_pair) and (h4_t >= 1.5)

        if reasons:
            verdict = "graveyard"
        elif (t_abs >= 2.5 and net_mean > 0 and perm_p <= 0.01 and sharpe >= 1.0
              and h4_robust and h5_consistent >= 3):
            verdict = "candidate_for_r2"
        else:
            verdict = "borderline"

        out = {
            "paradigm": PARADIGM,
            "type": "T",
            "universe": SYMBOLS,
            "panel_start": str(panel.index.min().date()),
            "panel_end": str(panel.index.max().date()),
            "n_weeks": int(n_weeks),
            "lookback_days_main": LOOKBACK_DAYS,
            "lookback_grid": LOOKBACK_GRID,
            "hold_days": 4,
            "fee_round_trip_pair_pct": FEE_PAIR * 100,
            "h1_pair_gross": h1,
            "h2_pair_net": h2,
            "h3_permutation": perm,
            "h4_top2_gross": h4_gross,
            "h4_top2_net": h4_net,
            "h4_robust_flag": bool(h4_robust),
            "h5_lookback_grid": h5_grid,
            "h5_consistent_count": h5_consistent,
            "h6_high_vol_gross": h6_hi,
            "h6_low_vol_gross": h6_lo,
            "first_weeks": weekly.head(5).to_dict(orient="records"),
            "last_weeks": weekly.tail(5).to_dict(orient="records"),
            "verdict": verdict,
            "graveyard_reasons": reasons,
        }
        OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
        log.info("saved → %s", OUT_PATH)
        log.info("VERDICT: %s%s", verdict, f" — {reasons}" if reasons else "")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
