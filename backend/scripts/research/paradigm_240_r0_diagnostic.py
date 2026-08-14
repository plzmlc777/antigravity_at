"""Paradigm 240 R-0 substrate + empirical distribution diagnostic.

Verifies:
 - Actual funding+OI overlap window and per-timestamp coverage.
 - DWFE aggregate signal computation feasibility.
 - Empirical distribution of DWFE_z (z-score over 90-period rolling window).
 - Trigger rate at |z|>=1.5/2.0/2.5/3.0 and n_events per quadrant.
 - Lesson #11 / #23 sample-density prescreen.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("paradigm_240_r0")

OUT_DIR = Path("/home/mint/auto_trading/backend/runs/research_track/paradigm_240_alt_cross_sym_oi_dollar_weighted_funding_ecosystem_z_bilateral_4h")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DB_CFG = dict(
    host=os.environ.get("POSTGRES_SERVER", "localhost"),
    user=os.environ.get("POSTGRES_USER", "antigravity_user"),
    password=os.environ.get("POSTGRES_PASSWORD", "antigravity_password"),
    dbname=os.environ.get("POSTGRES_DB", "antigravity_db"),
)


def load_funding_oi() -> pd.DataFrame:
    """Load funding + OI aligned at funding timestamps for the overlap universe."""
    with psycopg2.connect(**DB_CFG) as conn:
        # Overlap syms with 5m OI history
        syms_df = pd.read_sql(
            """
            SELECT DISTINCT o.symbol
            FROM binance_open_interest_hist o
            INNER JOIN binance_funding_rate f ON o.symbol = f.symbol
            WHERE o.interval_str='5m'
            """,
            conn,
        )
        syms = tuple(syms_df["symbol"].tolist())
        LOG.info("Universe: %d syms → %s", len(syms), syms)

        funding = pd.read_sql(
            """
            SELECT symbol, funding_time, funding_rate::float8 AS funding_rate,
                   mark_price::float8 AS mark_price
            FROM binance_funding_rate
            WHERE symbol IN %s
              AND funding_time >= '2026-04-05'
              AND funding_time <= '2026-07-28'
            """,
            conn,
            params=(syms,),
        )
        LOG.info("Funding rows: %d", len(funding))

        oi = pd.read_sql(
            """
            SELECT symbol, timestamp AS oi_time,
                   sum_open_interest::float8 AS sum_oi,
                   sum_open_interest_value::float8 AS sum_oi_usd
            FROM binance_open_interest_hist
            WHERE symbol IN %s
              AND interval_str='5m'
              AND timestamp >= '2026-04-05'
              AND timestamp <= '2026-07-28'
            """,
            conn,
            params=(syms,),
        )
        LOG.info("OI rows: %d", len(oi))

    funding["funding_time"] = pd.to_datetime(funding["funding_time"])
    oi["oi_time"] = pd.to_datetime(oi["oi_time"])
    funding.sort_values(["symbol", "funding_time"], inplace=True)
    oi.sort_values(["symbol", "oi_time"], inplace=True)

    merged_parts = []
    for sym in syms:
        f_sub = funding[funding["symbol"] == sym].reset_index(drop=True)
        o_sub = oi[oi["symbol"] == sym].drop(columns=["symbol"]).reset_index(drop=True)
        if f_sub.empty or o_sub.empty:
            continue
        m = pd.merge_asof(
            f_sub,
            o_sub,
            left_on="funding_time",
            right_on="oi_time",
            direction="backward",
            tolerance=pd.Timedelta("15min"),
        )
        merged_parts.append(m)
    merged = pd.concat(merged_parts, ignore_index=True)
    merged = merged.dropna(subset=["funding_rate", "sum_oi_usd"])
    LOG.info("Merged funding+OI rows: %d", len(merged))
    return merged


def compute_dwfe(merged: pd.DataFrame) -> pd.DataFrame:
    """DWFE(t) = sum_i [OI_usd_i * funding_i] / sum_i [OI_usd_i], per funding_time."""
    def _agg(df):
        total = df["sum_oi_usd"].sum()
        dwfe = (df["sum_oi_usd"] * df["funding_rate"]).sum() / total if total > 0 else np.nan
        return pd.Series({
            "n_syms": len(df),
            "total_oi_usd": total,
            "dwfe": dwfe,
            "unweighted_mean_funding": df["funding_rate"].mean(),
        })

    g = merged.groupby("funding_time").apply(_agg).reset_index()
    g = g.dropna(subset=["dwfe"]).reset_index(drop=True)
    return g


def rolling_zscore(series: pd.Series, window: int = 90) -> pd.Series:
    m = series.rolling(window, min_periods=window).mean()
    s = series.rolling(window, min_periods=window).std(ddof=1)
    return (series - m) / s


def main() -> None:
    merged = load_funding_oi()
    if merged.empty:
        result = {"phase": "R-0-GRAVEYARD", "reason": "no_merged_rows"}
        (OUT_DIR / "r0_diagnostic.json").write_text(json.dumps(result, indent=2))
        LOG.error("HALT: no merged rows")
        return

    dwfe = compute_dwfe(merged)
    LOG.info("Aggregate timestamps: %d", len(dwfe))
    dwfe["dwfe_z"] = rolling_zscore(dwfe["dwfe"], window=90)
    dwfe_measurable = dwfe.dropna(subset=["dwfe_z"]).reset_index(drop=True)

    z_vals = dwfe_measurable["dwfe_z"].values
    dwfe_vals = dwfe_measurable["dwfe"].values
    thresholds = [1.5, 2.0, 2.5, 3.0]
    trig_stats = {}
    for T in thresholds:
        n_long = int(np.sum(z_vals <= -T))
        n_short = int(np.sum(z_vals >= T))
        trig_stats[str(T)] = {
            "n_long_triggers": n_long,
            "n_short_triggers": n_short,
            "n_total_triggers": n_long + n_short,
            "trigger_rate_pct": round(100.0 * (n_long + n_short) / max(1, len(z_vals)), 3),
        }

    diag = {
        "phase": "R-0-DIAGNOSTIC",
        "n_universe_syms": int(merged["symbol"].nunique()),
        "n_funding_timestamps_raw": int(dwfe.shape[0]),
        "n_funding_timestamps_measurable_z": int(dwfe_measurable.shape[0]),
        "window_z_period_count": 90,
        "date_range": {
            "min": str(dwfe_measurable["funding_time"].min()) if not dwfe_measurable.empty else None,
            "max": str(dwfe_measurable["funding_time"].max()) if not dwfe_measurable.empty else None,
        },
        "dwfe_stats": {
            "p01_bp": round(float(np.percentile(dwfe_vals, 1)) * 1e4, 4),
            "p10_bp": round(float(np.percentile(dwfe_vals, 10)) * 1e4, 4),
            "p50_bp": round(float(np.percentile(dwfe_vals, 50)) * 1e4, 4),
            "p90_bp": round(float(np.percentile(dwfe_vals, 90)) * 1e4, 4),
            "p99_bp": round(float(np.percentile(dwfe_vals, 99)) * 1e4, 4),
            "mean_bp": round(float(dwfe_vals.mean()) * 1e4, 4),
            "std_bp": round(float(dwfe_vals.std(ddof=1)) * 1e4, 4),
            "min_bp": round(float(dwfe_vals.min()) * 1e4, 4),
            "max_bp": round(float(dwfe_vals.max()) * 1e4, 4),
        },
        "dwfe_z_stats": {
            "min": round(float(z_vals.min()), 3),
            "max": round(float(z_vals.max()), 3),
            "p01": round(float(np.percentile(z_vals, 1)), 3),
            "p99": round(float(np.percentile(z_vals, 99)), 3),
        },
        "trigger_stats": trig_stats,
        "lesson_11_min_events_per_cell_required": 30,
        "lesson_23_min_events_per_quadrant_required": 30,
    }

    primary_T = "2.0"
    n_long = trig_stats[primary_T]["n_long_triggers"]
    n_short = trig_stats[primary_T]["n_short_triggers"]
    diag["lesson_11_23_verdict"] = {
        "primary_T": primary_T,
        "n_long_triggers": n_long,
        "n_short_triggers": n_short,
        "min_events_per_quadrant": min(n_long, n_short),
        "pass_lesson_11_23": min(n_long, n_short) >= 30,
    }

    # Also check T=1.5 (relaxed)
    n_long_15 = trig_stats["1.5"]["n_long_triggers"]
    n_short_15 = trig_stats["1.5"]["n_short_triggers"]
    diag["lesson_11_23_relaxed_T15"] = {
        "n_long_triggers": n_long_15,
        "n_short_triggers": n_short_15,
        "min_events_per_quadrant": min(n_long_15, n_short_15),
        "pass_lesson_11_23_relaxed": min(n_long_15, n_short_15) >= 30,
    }

    (OUT_DIR / "r0_diagnostic.json").write_text(json.dumps(diag, indent=2, default=str))
    dwfe_measurable.to_parquet(OUT_DIR / "dwfe_series.parquet", index=False)
    LOG.info("R-0 diagnostic saved. verdict=%s", diag["lesson_11_23_verdict"])
    print(json.dumps(diag["lesson_11_23_verdict"], indent=2))
    print(json.dumps(diag["lesson_11_23_relaxed_T15"], indent=2))


if __name__ == "__main__":
    main()
