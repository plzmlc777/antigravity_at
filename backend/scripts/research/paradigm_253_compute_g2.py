"""Compute G2 inputs for paradigm 253 tier3_gate:
- edge_after_1bar_delay: same trades but shift entry by +1 day (and exit by +1 day)
- friction: FEE_ROUND_TRIP
- hold_min: 7 * 1440
- cycle_min: 1440
- lookahead_clean: True (VIX close 21:15 UTC -> entry next day 00:00 UTC, 2h45m gap)
"""
from __future__ import annotations
import io, json, subprocess, sys
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent.parent
PARADIGM = "paradigm_253_cboe_vix_extreme_regime_alt_bilateral_7d"
OUT_DIR = BASE / "runs" / "research_track" / PARADIGM

FRED_VIX_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"

ROLL_WINDOW = 90
HOLD_DAYS = 7
FEE_ROUND_TRIP = 0.0008


def _curl(url, timeout=30):
    r = subprocess.run(["curl", "-sS", "--max-time", str(timeout), url],
                       capture_output=True, timeout=timeout + 10)
    if r.returncode != 0:
        raise RuntimeError(f"curl: {r.stderr.decode()[:200]}")
    return r.stdout.decode()


def fetch_vix():
    raw = _curl(FRED_VIX_URL)
    df = pd.read_csv(io.StringIO(raw))
    df.columns = [c.strip() for c in df.columns]
    dc = "observation_date" if "observation_date" in df.columns else "DATE"
    df[dc] = pd.to_datetime(df[dc], errors="coerce")
    df = df.rename(columns={dc: "d", "VIXCLS": "vix"})
    df["vix"] = pd.to_numeric(df["vix"], errors="coerce")
    df = df.dropna(subset=["d", "vix"]).set_index("d").sort_index()
    return df


def fetch_binance_daily(sym, limit=1000):
    url = f"{BINANCE_KLINES}?symbol={sym}&interval=1d&limit={limit}"
    data = json.loads(_curl(url, timeout=15))
    rows = []
    for k in data:
        rows.append({"d": pd.to_datetime(k[0], unit="ms"),
                     "open": float(k[1]), "close": float(k[4])})
    return pd.DataFrame(rows).set_index("d").sort_index() if rows else pd.DataFrame()


def z90(s, window=ROLL_WINDOW):
    mu = s.rolling(window, min_periods=window // 2).mean()
    sd = s.rolling(window, min_periods=window // 2).std()
    return (s - mu) / sd


def build_trades_with_delay(vix_z, alt, threshold, quadrant, delay_days=0,
                            hold_days=HOLD_DAYS, fee=FEE_ROUND_TRIP):
    alt_open = alt["open"].copy()
    alt_open.index = pd.to_datetime(alt_open.index).normalize()
    vz = vix_z.copy()
    vz.index = pd.to_datetime(vz.index).normalize()
    df = pd.concat([vz.rename("z"), alt_open.rename("px")], axis=1).dropna().sort_index()

    if quadrant in ("A_focus", "A_mirror"):
        mask = df["z"] >= threshold
    else:
        mask = df["z"] <= -threshold
    direction = +1 if quadrant in ("A_focus", "B_mirror") else -1

    trades = []
    i, last_exit_i = 0, -1
    while i < len(df) - hold_days - 1 - delay_days:
        if mask.iloc[i] and i > last_exit_i:
            entry_i = i + 1 + delay_days
            exit_i = i + 1 + delay_days + hold_days
            if exit_i >= len(df):
                break
            gross = (df["px"].iloc[exit_i] / df["px"].iloc[entry_i] - 1.0) * direction
            trades.append({
                "entry_ts": df.index[entry_i].isoformat(),
                "exit_ts": df.index[exit_i].isoformat(),
                "gross_ret": float(gross),
                "net_ret": float(gross - fee),
            })
            last_exit_i = exit_i - 1
        i += 1
    return trades


TARGETS = [
    ("LINKUSDT", 1.0, "B_mirror"),
    ("ADAUSDT",  1.0, "B_mirror"),
    ("AVAXUSDT", 1.0, "B_mirror"),
    ("XRPUSDT",  1.0, "B_mirror"),
    ("SOLUSDT",  1.0, "B_mirror"),
    ("XRPUSDT",  1.0, "A_focus"),
]


def main():
    vix = fetch_vix()
    vix_z = z90(vix["vix"]).dropna()

    g2_report = {}
    for sym, T, quad in TARGETS:
        alt = fetch_binance_daily(sym)
        if alt.empty:
            g2_report[f"{sym}_T{T}_{quad}"] = {"error": "no alt data"}
            continue
        base_trades = build_trades_with_delay(vix_z, alt, T, quad, delay_days=0)
        delayed_trades = build_trades_with_delay(vix_z, alt, T, quad, delay_days=1)

        # write both files
        (OUT_DIR / f"trades__{sym}__{quad}__T{T}.json").write_text(
            json.dumps({"trades": base_trades}, indent=2))
        (OUT_DIR / f"trades_delayed__{sym}__{quad}__T{T}.json").write_text(
            json.dumps({"trades": delayed_trades}, indent=2))

        base_mean = float(np.mean([t["net_ret"] for t in base_trades])) if base_trades else 0.0
        delayed_mean = float(np.mean([t["net_ret"] for t in delayed_trades])) if delayed_trades else 0.0
        # For G2: edge_after_1bar_delay should be the DELAYED per-trade net edge (soft)
        # tier3_gate treats input as fraction (0.01 = 1%)
        g2_report[f"{sym}_T{T}_{quad}"] = {
            "n_base": len(base_trades),
            "n_delayed": len(delayed_trades),
            "base_mean_net_pct": round(base_mean * 100, 4),
            "delayed_mean_net_pct": round(delayed_mean * 100, 4),
            "edge_after_1bar_delay_frac": round(delayed_mean, 6),
            "friction_frac": FEE_ROUND_TRIP,
            "hold_min": HOLD_DAYS * 1440,
            "cycle_min": 1440,
            "lookahead_clean": True,
        }
        print(f"{sym} T={T} {quad}: base_net={base_mean*100:+.4f}% | "
              f"delayed_net={delayed_mean*100:+.4f}% | n_base={len(base_trades)}")

    (OUT_DIR / "g2_inputs.json").write_text(json.dumps(g2_report, indent=2))
    print(f"\nsaved: {OUT_DIR / 'g2_inputs.json'}")


if __name__ == "__main__":
    main()
