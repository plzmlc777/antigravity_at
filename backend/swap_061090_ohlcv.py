"""
061090 OHLCV atomic swap:
  1) staging JSONL parse → OHLCV rows
  2) BEGIN tx
     DELETE FROM ohlcv WHERE symbol='061090' AND time_frame='1m'
     INSERT bulk (chunked)
     COMMIT
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.db.session import engine


def to_int(x):
    try:
        return abs(int(str(x).replace("+", "").replace("-", "")))
    except Exception:
        return 0


def parse_jsonl(path: str):
    rows = []
    with open(path) as f:
        for ln in f:
            it = json.loads(ln)
            ts_str = it.get("cntr_tm")
            if not ts_str or len(ts_str) != 14:
                continue
            ts = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
            rows.append(
                {
                    "symbol": "061090",
                    "timestamp": ts,
                    "time_frame": "1m",
                    "open": to_int(it.get("open_pric")),
                    "high": to_int(it.get("high_pric")),
                    "low": to_int(it.get("low_pric")),
                    "close": to_int(it.get("cur_prc")),
                    "volume": int(it.get("trde_qty", 0)),
                }
            )
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--staging", required=True)
    p.add_argument("--symbol", default="061090")
    p.add_argument("--time-frame", default="1m")
    p.add_argument("--chunk", type=int, default=2000)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    print(f"Parsing staging: {args.staging}")
    rows = parse_jsonl(args.staging)
    print(f"Parsed {len(rows)} rows")
    if not rows:
        print("ERROR: no rows", file=sys.stderr)
        sys.exit(1)

    # 사전 검증: 중복 체크
    seen = set()
    for r in rows:
        k = (r["symbol"], r["timestamp"], r["time_frame"])
        if k in seen:
            print(f"ERROR: duplicate timestamp {r['timestamp']}", file=sys.stderr)
            sys.exit(1)
        seen.add(k)
    print("Dedup check OK")

    if args.dry_run:
        print("[dry-run] skipping DB swap")
        return

    insert_sql = text(
        """
        INSERT INTO ohlcv
          (symbol, timestamp, time_frame, open, high, low, close, volume, created_at)
        VALUES
          (:symbol, :timestamp, :time_frame, :open, :high, :low, :close, :volume, NOW())
        """
    )

    with engine.begin() as conn:  # transaction
        before = conn.execute(
            text(
                "SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame=:tf"
            ),
            {"s": args.symbol, "tf": args.time_frame},
        ).scalar()
        print(f"Before delete: {before} rows for {args.symbol}/{args.time_frame}")

        deleted = conn.execute(
            text(
                "DELETE FROM ohlcv WHERE symbol=:s AND time_frame=:tf"
            ),
            {"s": args.symbol, "tf": args.time_frame},
        ).rowcount
        print(f"Deleted: {deleted} rows")

        inserted = 0
        for i in range(0, len(rows), args.chunk):
            batch = rows[i : i + args.chunk]
            conn.execute(insert_sql, batch)
            inserted += len(batch)
            if (i // args.chunk) % 5 == 0:
                print(f"  inserted {inserted}/{len(rows)}")

        after = conn.execute(
            text(
                "SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame=:tf"
            ),
            {"s": args.symbol, "tf": args.time_frame},
        ).scalar()
        print(f"After insert: {after} rows")

        if after != len(rows):
            raise RuntimeError(
                f"Row count mismatch: expected {len(rows)}, found {after}"
            )

    print(f"\nSWAP DONE: {deleted} → {inserted} rows ({args.symbol}/{args.time_frame})")


if __name__ == "__main__":
    main()
