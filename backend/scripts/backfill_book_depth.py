"""Download Binance Futures bookDepth daily archive and aggregate to daily features.

URL: data.binance.vision/data/futures/um/daily/bookDepth/{SYM}/{SYM}-bookDepth-YYYY-MM-DD.zip
Each daily file ~ 450KB, ~27k rows (snapshot interval ~30s, 10 percentage levels per snapshot).

We do incremental aggregation: download → parse → daily summary → save → discard raw.
This keeps memory footprint small (raw 14×365×27k = 138M rows would not fit).

Output: backend/runs/book_depth/{SYMBOL}_bookdepth.joblib
DataFrame indexed by date with columns:
  bid_depth_total, ask_depth_total, imbalance, near_imbalance,
  far_imbalance, top1_concentration, snapshots_per_day
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_book_depth")

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/bookDepth"


def _aggregate_one_day(df_raw: pd.DataFrame) -> dict | None:
    """Reduce one daily file's raw rows → single daily summary dict."""
    if df_raw is None or df_raw.empty:
        return None
    # Group by snapshot timestamp; for each snapshot compute bid/ask totals.
    g = df_raw.groupby("timestamp")
    rows = []
    for ts, sub in g:
        # bid side: percentage < 0; ask side: percentage > 0
        bid = sub.loc[sub["percentage"] < 0, "notional"].sum()
        ask = sub.loc[sub["percentage"] > 0, "notional"].sum()
        # near (±1%)
        near_bid = sub.loc[sub["percentage"] == -1, "notional"].sum()
        near_ask = sub.loc[sub["percentage"] == 1, "notional"].sum()
        # far (±5%)
        far_bid = sub.loc[sub["percentage"] == -5, "notional"].sum()
        far_ask = sub.loc[sub["percentage"] == 5, "notional"].sum()
        rows.append({"timestamp": ts, "bid": bid, "ask": ask,
                     "near_bid": near_bid, "near_ask": near_ask,
                     "far_bid": far_bid, "far_ask": far_ask})
    snap_df = pd.DataFrame(rows)
    if snap_df.empty:
        return None

    snap_df["imbalance"] = (snap_df["bid"] - snap_df["ask"]) / (snap_df["bid"] + snap_df["ask"]).replace(0, np.nan)
    snap_df["near_imbalance"] = (snap_df["near_bid"] - snap_df["near_ask"]) / \
                                 (snap_df["near_bid"] + snap_df["near_ask"]).replace(0, np.nan)
    snap_df["far_imbalance"] = (snap_df["far_bid"] - snap_df["far_ask"]) / \
                                (snap_df["far_bid"] + snap_df["far_ask"]).replace(0, np.nan)
    snap_df["top1_concentration"] = (snap_df["near_bid"] + snap_df["near_ask"]) / \
                                     (snap_df["bid"] + snap_df["ask"]).replace(0, np.nan)

    # Daily summary from snapshots
    return {
        "bid_depth_mean": float(snap_df["bid"].mean()),
        "ask_depth_mean": float(snap_df["ask"].mean()),
        "imbalance_mean": float(snap_df["imbalance"].mean()),
        "imbalance_std": float(snap_df["imbalance"].std()),
        "near_imbalance_mean": float(snap_df["near_imbalance"].mean()),
        "far_imbalance_mean": float(snap_df["far_imbalance"].mean()),
        "top1_concentration_mean": float(snap_df["top1_concentration"].mean()),
        "imb_extreme_long_freq": float((snap_df["imbalance"] > 0.2).mean()),
        "imb_extreme_short_freq": float((snap_df["imbalance"] < -0.2).mean()),
        "snapshots": int(len(snap_df)),
    }


def _fetch_and_aggregate(sym: str, date, session: requests.Session, retries: int = 2):
    url = f"{ARCHIVE_BASE}/{sym}/{sym}-bookDepth-{date.isoformat()}.zip"
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                names = z.namelist()
                if not names:
                    return None
                with z.open(names[0]) as fh:
                    df_raw = pd.read_csv(fh)
            agg = _aggregate_one_day(df_raw)
            if agg is None:
                return None
            agg["date"] = date
            return agg
        except Exception as e:
            if attempt == retries:
                log.warning("Failed %s/%s: %s", sym, date, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True)
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--end-date", default=None)
    p.add_argument("--parallel", type=int, default=12)
    p.add_argument("--out-dir", default=str(ROOT / "runs" / "book_depth"))
    args = p.parse_args()

    out_dir = Path(args.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    end_date = (datetime.utcnow() - timedelta(days=1)).date() if args.end_date is None \
        else datetime.strptime(args.end_date, "%Y-%m-%d").date()
    start_date = end_date - timedelta(days=args.days - 1)
    log.info("Range: %s ~ %s (%d days)", start_date, end_date, args.days)

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    target_days = [start_date + timedelta(days=i) for i in range(args.days)]

    for sym in syms:
        out_path = out_dir / f"{sym}_bookdepth.joblib"
        if out_path.exists():
            existing = joblib.load(out_path)
            log.info("[%s] skip — exists with %d rows", sym, len(existing))
            continue
        t0 = time.time()
        rows = []
        session = requests.Session()
        with ThreadPoolExecutor(max_workers=args.parallel) as ex:
            futs = {ex.submit(_fetch_and_aggregate, sym, d, session): d for d in target_days}
            for i, f in enumerate(as_completed(futs), 1):
                row = f.result()
                if row is not None:
                    rows.append(row)
                if i % 50 == 0:
                    log.info("[%s] %d/%d aggregated", sym, i, len(target_days))
        if not rows:
            log.warning("[%s] empty", sym)
            continue
        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        joblib.dump(df, out_path, compress=3)
        log.info("[%s] saved %d days in %.1fs (%s ~ %s)",
                 sym, len(df), time.time() - t0, df.index[0].date(), df.index[-1].date())
    return 0


if __name__ == "__main__":
    sys.exit(main())
