"""
Generic OHLCV atomic swap (symbol-agnostic).

  1) Parse staging JSONL (Kiwoom ka10080 schema)
  2) BEGIN tx
     DELETE FROM ohlcv WHERE symbol=:s AND time_frame=:tf
     INSERT bulk (chunked)
     COMMIT

Usage:
    python3 swap_ohlcv.py --symbol 005930 --staging /tmp/005930_1m.jsonl
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


def parse_jsonl(path: str, symbol: str):
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
                    "symbol": symbol,
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
    p.add_argument("--symbol", required=True)
    p.add_argument("--staging", required=True)
    p.add_argument("--time-frame", default="1m")
    p.add_argument("--chunk", type=int, default=2000)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    print(f"Parsing staging: {args.staging} (symbol={args.symbol})")
    rows = parse_jsonl(args.staging, args.symbol)
    print(f"Parsed {len(rows)} rows")
    if not rows:
        print("ERROR: no rows", file=sys.stderr)
        sys.exit(1)

    seen = set()
    for r in rows:
        k = (r["symbol"], r["timestamp"], r["time_frame"])
        if k in seen:
            print(f"ERROR: duplicate timestamp {r['timestamp']}", file=sys.stderr)
            sys.exit(1)
        seen.add(k)
    print("Dedup check OK")

    # 정규장 시간 outside (15:35 동시호가 등) 정보 출력 — fetcher가 그대로 보존
    out_of_session = sum(
        1 for r in rows
        if not (r["timestamp"].time() >= datetime(2000, 1, 1, 9, 0).time()
                and r["timestamp"].time() <= datetime(2000, 1, 1, 15, 35).time())
    )
    if out_of_session:
        print(f"  note: {out_of_session} bars outside 09:00-15:35 (kept as-is)")

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

    with engine.begin() as conn:
        before = conn.execute(
            text("SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame=:tf"),
            {"s": args.symbol, "tf": args.time_frame},
        ).scalar()
        print(f"Before delete: {before} rows for {args.symbol}/{args.time_frame}")

        deleted = conn.execute(
            text("DELETE FROM ohlcv WHERE symbol=:s AND time_frame=:tf"),
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
            text("SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame=:tf"),
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
