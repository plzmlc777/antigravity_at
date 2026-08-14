"""paradigm_253 R-1 backtest — CBOE VIX z-extreme × 14 alts bilateral 7d.

Design:
  Signal:  vix_z_90d = (VIX_t - rolling(90).mean) / rolling(90).std
  Trigger: |vix_z| >= T  for T in {1.0, 1.5, 2.0}
  Quadrants (Symmetric Negative Test, Lesson #19):
    A_focus  : vix_z >  +T  -> LONG  alt   (contrarian: fear peak = buy)
    A_mirror : vix_z >  +T  -> SHORT alt   (follow    : risk-off contagion)
    B_focus  : vix_z <  -T  -> SHORT alt   (contrarian: complacency = sell)
    B_mirror : vix_z <  -T  -> LONG  alt   (follow    : greed = momentum)

  R-0 pretest corr(vix_z, fwd_7d) is POSITIVE (BTC OOS +0.087), so B_mirror
  (LONG on low VIX) and A_focus (LONG on high VIX contrarian) are the
  candidate winning quadrants. Full 4-quadrant SNT still mandatory.

Lookahead invariant (Lesson #82 candidate):
  - trigger detected at day T (uses VIX close 21:15 UTC of day T)
  - entry at day T+1 UTC 00:00 open   (2h45m gap, clean)
  - exit  at day T+1+7 UTC 00:00 open (7 calendar days hold)
  - non-overlapping: cooldown = 7 days per symbol

Fee model: 8 bp round-trip = 0.0008

Full sweep (Lesson #37): 3 thresholds × 4 quadrants × 14 syms = 168 cells.
Report all cells; identify best per (T, quadrant) for tier3_gate handoff.

Outputs:
  runs/research_track/paradigm_253_.../r1__metrics.json
  runs/research_track/paradigm_253_.../trades__{sym}__{quad}__T{T}.json
    (for tier3_gate --trades input, only best cell per sym is written)
"""
from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "scripts"))
from research._perm_utils import bootstrap_ci, fee_aware_perm_test  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("paradigm_253_r1")

PARADIGM = "paradigm_253_cboe_vix_extreme_regime_alt_bilateral_7d"
OUT_DIR = BASE / "runs" / "research_track" / PARADIGM

FRED_VIX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

UNIVERSE = [
    "ADAUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "BTCUSDT",
    "DOGEUSDT", "ETHUSDT", "FILUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SOLUSDT", "WIFUSDT", "XRPUSDT",
]

ROLL_WINDOW = 90
HOLD_DAYS = 7
THRESHOLDS = [1.0, 1.5, 2.0]
FEE_ROUND_TRIP = 0.0008
QUADRANTS = ["A_focus", "A_mirror", "B_focus", "B_mirror"]


def _curl(url: str, timeout: int = 30) -> str:
    result = subprocess.run(
        ["curl", "-sS", "--max-time", str(timeout), url],
        capture_output=True, timeout=timeout + 10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.decode()[:200]}")
    return result.stdout.decode("utf-8", errors="replace")


def fetch_vix() -> pd.DataFrame:
    log.info("FRED VIX fetch")
    raw = _curl(FRED_VIX_URL, timeout=30)
    df = pd.read_csv(io.StringIO(raw))
    df.columns = [c.strip() for c in df.columns]
    date_col = "observation_date" if "observation_date" in df.columns else "DATE"
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.rename(columns={date_col: "d", "VIXCLS": "vix"})
    df["vix"] = pd.to_numeric(df["vix"], errors="coerce")
    df = df.dropna(subset=["d", "vix"]).set_index("d").sort_index()
    log.info("VIX rows=%d span=%s..%s", len(df),
             df.index.min().date(), df.index.max().date())
    return df


def fetch_binance_daily(symbol: str, limit: int = 1000) -> pd.DataFrame:
    url = f"{BINANCE_KLINES}?symbol={symbol}&interval=1d&limit={limit}"
    raw = _curl(url, timeout=15)
    data = json.loads(raw)
    if not data:
        return pd.DataFrame()
    rows = []
    for k in data:
        rows.append({
            "d": pd.to_datetime(k[0], unit="ms"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "quote_vol": float(k[7]),
        })
    df = pd.DataFrame(rows).set_index("d").sort_index()
    return df


def z90(s: pd.Series, window: int = ROLL_WINDOW) -> pd.Series:
    mu = s.rolling(window, min_periods=window // 2).mean()
    sd = s.rolling(window, min_periods=window // 2).std()
    return (s - mu) / sd


def build_trades(vix_z: pd.Series, alt: pd.DataFrame,
                 threshold: float, quadrant: str,
                 hold_days: int = HOLD_DAYS,
                 fee: float = FEE_ROUND_TRIP) -> list:
    """Generate trades for a (threshold, quadrant) cell on one symbol.

    Non-overlapping: after each trade, skip hold_days before next trigger.
    """
    # Align on date
    alt_open = alt["open"].copy()
    alt_open.index = pd.to_datetime(alt_open.index).normalize()
    vz = vix_z.copy()
    vz.index = pd.to_datetime(vz.index).normalize()

    df = pd.concat([vz.rename("z"), alt_open.rename("px")], axis=1).dropna()
    df = df.sort_index()

    # trigger mask
    if quadrant in ("A_focus", "A_mirror"):
        mask = df["z"] >= threshold
    else:  # B_focus / B_mirror
        mask = df["z"] <= -threshold

    if quadrant in ("A_focus", "B_mirror"):
        direction = +1  # LONG
    else:
        direction = -1  # SHORT

    trades = []
    dates = df.index
    n = len(dates)
    # need px[i+1] as entry and px[i+1+hold] as exit
    i = 0
    last_exit_i = -1
    while i < n - hold_days - 1:
        if mask.iloc[i] and i > last_exit_i:
            entry_i = i + 1
            exit_i = i + 1 + hold_days
            if exit_i >= n:
                break
            px_entry = df["px"].iloc[entry_i]
            px_exit = df["px"].iloc[exit_i]
            gross = (px_exit / px_entry - 1.0) * direction
            net = gross - fee
            trades.append({
                "entry_ts": dates[entry_i].isoformat(),
                "exit_ts": dates[exit_i].isoformat(),
                "gross_ret": float(gross),
                "net_ret": float(net),
                "vix_z": float(df["z"].iloc[i]),
                "px_entry": float(px_entry),
                "px_exit": float(px_exit),
                "direction": direction,
            })
            last_exit_i = exit_i - 1  # allow next trigger at exit day
        i += 1

    return trades


def candidate_pool_gross(alt: pd.DataFrame, hold_days: int = HOLD_DAYS,
                         direction: int = +1) -> np.ndarray:
    """All possible non-trigger 7d gross returns, for perm null pool."""
    px = alt["open"].copy()
    n = len(px)
    if n < hold_days + 2:
        return np.array([])
    entry = px.iloc[1 : n - hold_days].values
    exit_ = px.iloc[1 + hold_days :].values
    m = min(len(entry), len(exit_))
    gross = (exit_[:m] / entry[:m] - 1.0) * direction
    return gross[np.isfinite(gross)]


def evaluate_cell(trades: list, pool_gross: np.ndarray) -> dict:
    """3-gate metrics for one cell."""
    if len(trades) < 5:
        return {"n_trades": len(trades), "status": "too_few_trades"}
    net = np.array([t["net_ret"] for t in trades], dtype=float)
    gross = np.array([t["gross_ret"] for t in trades], dtype=float)

    perm = fee_aware_perm_test(
        observed_net_returns=net,
        candidate_pool_returns=pool_gross,
        fee_per_trade=FEE_ROUND_TRIP,
        n_perms=1000,
    )
    ci = bootstrap_ci(net, n_boot=2000, block_size=1)

    return {
        "n_trades": int(len(net)),
        "mean_net_pct": round(float(net.mean()) * 100, 4),
        "mean_gross_pct": round(float(gross.mean()) * 100, 4),
        "std_net_pct": round(float(net.std(ddof=1)) * 100, 4),
        "sharpe_annualized": round(
            float(net.mean() / net.std(ddof=1) * np.sqrt(365 / HOLD_DAYS))
            if net.std(ddof=1) > 0 else 0.0, 3),
        "signal_t_excess": round(perm.get("signal_t_excess", float("nan")), 3),
        "obs_t": round(perm.get("obs_t", 0.0), 3),
        "null_mean_t": round(perm.get("null_mean_t", 0.0), 3),
        "perm_p_two_sided": round(perm.get("perm_p_two_sided", 1.0), 4),
        "ci_lower_pct": round(float(ci.get("ci_lower", float("nan"))) * 100, 4),
        "ci_upper_pct": round(float(ci.get("ci_upper", float("nan"))) * 100, 4),
        "prob_positive": round(float(ci.get("prob_positive", 0.5)), 3),
    }


def main() -> int:
    started = datetime.utcnow()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=== paradigm 253 R-1 backtest ===")
    vix = fetch_vix()
    vix_z = z90(vix["vix"]).dropna()

    # load all 14 alts
    alt_data = {}
    for sym in UNIVERSE:
        try:
            df = fetch_binance_daily(sym, limit=1000)
        except Exception as exc:
            log.warning("skip %s: %s", sym, exc)
            continue
        if df.empty or len(df) < 200:
            log.warning("skip %s: too few rows (%d)", sym, len(df))
            continue
        alt_data[sym] = df
        log.info("loaded %s rows=%d span=%s..%s", sym, len(df),
                 df.index.min().date(), df.index.max().date())

    log.info("universe loaded: %d symbols", len(alt_data))

    # sweep
    all_cells = []
    per_sym_best = {}  # sym -> {best_cell_id, best_verdict_score, best_trades}

    for sym, alt in alt_data.items():
        # per-symbol pool for both LONG and SHORT (direction-adjusted)
        pool_long = candidate_pool_gross(alt, HOLD_DAYS, direction=+1)
        pool_short = candidate_pool_gross(alt, HOLD_DAYS, direction=-1)

        for T in THRESHOLDS:
            for quad in QUADRANTS:
                trades = build_trades(vix_z, alt, T, quad)
                direction = +1 if quad in ("A_focus", "B_mirror") else -1
                pool = pool_long if direction == +1 else pool_short
                metrics = evaluate_cell(trades, pool)
                cell = {
                    "sym": sym,
                    "threshold": T,
                    "quadrant": quad,
                    "direction": direction,
                    **metrics,
                }
                all_cells.append(cell)

                # persist trades for cells that MIGHT pass tier3_gate G1
                if (metrics.get("n_trades", 0) >= 20
                        and metrics.get("mean_net_pct", -999) > 0
                        and metrics.get("obs_t", 0.0) >= 1.0):
                    fname = (OUT_DIR / f"trades__{sym}__{quad}__T{T}.json")
                    fname.write_text(json.dumps({"trades": trades}, indent=2))

    # Lesson #39 symmetric check: for each (sym, T), sum of A_focus + A_mirror
    # and B_focus + B_mirror mean_net should be near -2*fee (16 bp) if trigger
    # has zero directional info.
    snt_table = []
    for sym in alt_data:
        for T in THRESHOLDS:
            def _get(quad):
                m = next((c for c in all_cells if c["sym"] == sym
                          and c["threshold"] == T and c["quadrant"] == quad), {})
                return m.get("mean_net_pct")
            af, am = _get("A_focus"), _get("A_mirror")
            bf, bm = _get("B_focus"), _get("B_mirror")
            snt_table.append({
                "sym": sym, "threshold": T,
                "A_focus_pct": af, "A_mirror_pct": am,
                "A_sum_pct": (af + am) if af is not None and am is not None else None,
                "B_focus_pct": bf, "B_mirror_pct": bm,
                "B_sum_pct": (bf + bm) if bf is not None and bm is not None else None,
                "fee_floor_expected_pct": round(-2 * FEE_ROUND_TRIP * 100, 4),
            })

    # rank all cells that pass basic filters
    def _score(c):
        if c.get("status") == "too_few_trades":
            return -999.0
        # composite score: mean * sqrt(n) / std, penalize p
        m = c.get("mean_net_pct", 0.0)
        se = c.get("signal_t_excess", 0.0)
        n = c.get("n_trades", 0)
        return (m if m > 0 else -10) + se * 0.5 + (n / 100)

    ranked = sorted(all_cells, key=_score, reverse=True)

    # Also flag cells satisfying full 3-gate PASS
    def _passes_3gate(c):
        return (
            c.get("n_trades", 0) >= 20 and
            c.get("signal_t_excess", -99) >= 2.0 and
            c.get("ci_lower_pct", -99) > 0 and
            c.get("perm_p_two_sided", 1.0) <= 0.10
        )
    three_gate_pass = [c for c in all_cells if _passes_3gate(c)]

    metrics_out = {
        "paradigm": PARADIGM,
        "paradigm_number": 253,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.utcnow().isoformat(timespec="seconds"),
        "universe_loaded": sorted(alt_data.keys()),
        "n_universe": len(alt_data),
        "sweep_cells_total": len(all_cells),
        "thresholds": THRESHOLDS,
        "quadrants": QUADRANTS,
        "hold_days": HOLD_DAYS,
        "fee_round_trip": FEE_ROUND_TRIP,
        "three_gate_pass_count": len(three_gate_pass),
        "three_gate_pass_cells": three_gate_pass,
        "top_20_by_score": ranked[:20],
        "symmetric_negative_test_lesson39": snt_table,
        "all_cells": all_cells,
    }

    (OUT_DIR / "r1__metrics.json").write_text(
        json.dumps(metrics_out, indent=2, ensure_ascii=False))
    log.info("R-1 written: %s", OUT_DIR / "r1__metrics.json")
    log.info("sweep total: %d cells / 3-gate PASS: %d",
             len(all_cells), len(three_gate_pass))
    return 0


if __name__ == "__main__":
    sys.exit(main())
