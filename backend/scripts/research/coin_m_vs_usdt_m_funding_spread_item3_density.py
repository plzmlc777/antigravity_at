"""Paradigm 225 R-0 Item 3 sample density prescreen.

Loads COIN-M funding rate parquets from S3-backfilled ZIPs + USDT-M funding rates
from PostgreSQL DB, computes per-symbol spread = coinm - usdtm, applies 30d rolling
z-score on 8h cadence (90 periods), measures empirical trigger rate at |z|>=1.5 and
|z|>=1.0. Also reports Item 7 asymmetry ratio.
"""
from __future__ import annotations
import io
import json
import logging
import os
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

LOG = logging.getLogger("paradigm225.item3")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

ROOT = Path("backend/runs/research_track/coin_m_vs_usdt_m_funding_spread")
COINM_ROOT = ROOT / "coinm_raw"
ART = ROOT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

PAIRS = [
    ("BTCUSD_PERP", "BTCUSDT"),
    ("ETHUSD_PERP", "ETHUSDT"),
    ("BNBUSD_PERP", "BNBUSDT"),
    ("XRPUSD_PERP", "XRPUSDT"),
    ("ADAUSD_PERP", "ADAUSDT"),
]


def load_coinm_series(sym: str) -> pd.DataFrame:
    files = sorted((COINM_ROOT / sym).glob("*.zip"))
    frames = []
    for f in files:
        try:
            with zipfile.ZipFile(f) as z:
                for name in z.namelist():
                    if name.endswith(".csv"):
                        with z.open(name) as fh:
                            df = pd.read_csv(fh)
                            frames.append(df)
        except Exception as e:
            LOG.warning("skip %s: %s", f, e)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # calc_time is ms epoch
    df["ts"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True).dt.tz_convert(None)
    df["rate"] = df["last_funding_rate"].astype(float)
    df = df.sort_values("ts").drop_duplicates("ts")
    # normalize timestamp to nearest 8h boundary (COIN-M funding is at 00/08/16 UTC)
    df["ts_norm"] = df["ts"].dt.floor("h")
    # Some CM funding timestamps have millisecond drift; round to 8h grid
    df["ts_8h"] = df["ts"].dt.round("8h")
    return df[["ts_8h", "rate"]].rename(columns={"ts_8h": "ts"}).drop_duplicates("ts")


def load_usdtm_series(sym: str) -> pd.DataFrame:
    conn = psycopg2.connect(host="localhost",
                            database=os.getenv("POSTGRES_DB", "antigravity"),
                            user=os.getenv("POSTGRES_USER", "antigravity"),
                            password=os.getenv("POSTGRES_PASSWORD", "antigravity"))
    df = pd.read_sql("SELECT funding_time AS ts, funding_rate::float AS rate FROM binance_funding_rate WHERE symbol=%s ORDER BY funding_time",
                     conn, params=(sym,))
    conn.close()
    df["ts"] = pd.to_datetime(df["ts"]).dt.round("8h")
    return df.drop_duplicates("ts")


def main():
    Z_STRICT = 1.5
    Z_RELAXED = 1.0
    ZWIN = 90  # 30d at 8h cadence

    report = {"pairs": [], "aggregate": {}}
    per_sym_stats = {}

    for cm_sym, um_sym in PAIRS:
        cm = load_coinm_series(cm_sym)
        um = load_usdtm_series(um_sym)
        if cm.empty or um.empty:
            LOG.warning("empty %s or %s", cm_sym, um_sym)
            continue
        # Restrict to 2024-01-01 -> 2026-05-15 intersection
        start = pd.Timestamp("2024-01-01")
        end = pd.Timestamp("2026-05-16")
        cm = cm[(cm["ts"] >= start) & (cm["ts"] <= end)]
        um = um[(um["ts"] >= start) & (um["ts"] <= end)]
        merged = pd.merge(cm.rename(columns={"rate": "cm_rate"}),
                          um.rename(columns={"rate": "um_rate"}),
                          on="ts", how="inner").sort_values("ts")
        merged["spread"] = merged["cm_rate"] - merged["um_rate"]
        merged["mu"] = merged["spread"].rolling(ZWIN, min_periods=ZWIN).mean()
        merged["sd"] = merged["spread"].rolling(ZWIN, min_periods=ZWIN).std()
        merged["z"] = (merged["spread"] - merged["mu"]) / merged["sd"]
        merged = merged.dropna(subset=["z"])
        n = len(merged)
        n_pos_15 = int((merged["z"] >= Z_STRICT).sum())
        n_neg_15 = int((merged["z"] <= -Z_STRICT).sum())
        n_pos_10 = int((merged["z"] >= Z_RELAXED).sum())
        n_neg_10 = int((merged["z"] <= -Z_RELAXED).sum())

        rate_15 = (n_pos_15 + n_neg_15) / n if n else 0
        rate_10 = (n_pos_10 + n_neg_10) / n if n else 0
        # asymmetry ratio Item 7 at |z|>=1.5
        asym_15 = max(n_pos_15, n_neg_15) / max(1, min(n_pos_15, n_neg_15))
        asym_10 = max(n_pos_10, n_neg_10) / max(1, min(n_pos_10, n_neg_10))

        stat = {
            "cm_sym": cm_sym, "um_sym": um_sym,
            "n_obs_zvalid": n,
            "n_pos_z15": n_pos_15, "n_neg_z15": n_neg_15,
            "n_pos_z10": n_pos_10, "n_neg_z10": n_neg_10,
            "rate_15": round(rate_15, 4), "rate_10": round(rate_10, 4),
            "asym_15": round(asym_15, 2), "asym_10": round(asym_10, 2),
            "spread_stats": {
                "mean": float(merged["spread"].mean()),
                "std": float(merged["spread"].std()),
                "p01": float(merged["spread"].quantile(0.01)),
                "p50": float(merged["spread"].quantile(0.50)),
                "p99": float(merged["spread"].quantile(0.99)),
            }
        }
        per_sym_stats[cm_sym] = stat
        report["pairs"].append(stat)
        LOG.info("%s -> n=%d rate15=%.4f rate10=%.4f asym15=%.2f asym10=%.2f",
                 cm_sym, n, rate_15, rate_10, asym_15, asym_10)

    # Aggregate density calc: 4-quadrant x 4-quarter = 16 cells, but with 5 syms
    n_syms = len(per_sym_stats)
    total_obs = sum(s["n_obs_zvalid"] for s in per_sym_stats.values())
    tot_trig_15 = sum(s["n_pos_z15"] + s["n_neg_z15"] for s in per_sym_stats.values())
    tot_trig_10 = sum(s["n_pos_z10"] + s["n_neg_z10"] for s in per_sym_stats.values())
    n_cells = 16
    per_cell_15 = tot_trig_15 / n_cells
    per_cell_10 = tot_trig_10 / n_cells

    # Per-quadrant per-symbol density (Lesson #16 for narrow universe)
    # A_focus + A_mirror share A trigger cohort; B same for B. So per 4-quadrant = 2 unique cohorts
    # But 4 quarters -> 8 cells effectively for cohort density
    n_cells_effective = 8
    per_cell_eff_15 = tot_trig_15 / n_cells_effective
    per_cell_eff_10 = tot_trig_10 / n_cells_effective

    report["aggregate"] = {
        "n_syms": n_syms,
        "total_obs": total_obs,
        "total_triggers_z15": tot_trig_15,
        "total_triggers_z10": tot_trig_10,
        "per_cell_16way_z15": round(per_cell_15, 1),
        "per_cell_16way_z10": round(per_cell_10, 1),
        "per_cell_8way_z15": round(per_cell_eff_15, 1),
        "per_cell_8way_z10": round(per_cell_eff_10, 1),
        "verdict_15": "PASS" if per_cell_15 >= 30 else "FAIL",
        "verdict_10": "PASS" if per_cell_10 >= 30 else "FAIL",
    }

    out = ART / "item3_density.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    LOG.info("wrote %s", out)
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
