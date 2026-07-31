#!/usr/bin/env python3
"""
미국 ETF 유니버스 일봉 백필 (기본 6년).

us_universe.json 의 코어(+옵션으로 레버리지) 심볼을 순회하며
USMarketDataService.fetch_daily_history() 로 OHLCV(time_frame='1d')를 채운다.

실행:
  cd backend && python -m scripts.backfill_us_daily                 # 코어 전체 6년
  cd backend && python -m scripts.backfill_us_daily --limit 5       # 앞 5종목만
  cd backend && python -m scripts.backfill_us_daily --include-leveraged
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

import logging  # noqa: E402

from app.core.http_client import HttpClientManager  # noqa: E402
from app.models.user import User  # noqa: E402,F401
from app.services.us_market_data_service import USMarketDataService  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

UNIVERSE_PATH = BACKEND_DIR / "configs" / "us_universe.json"


async def run(symbols: list, years: float) -> dict:
    await HttpClientManager.get_instance().start()
    svc = USMarketDataService()
    result = {"ok": [], "empty": [], "error": []}
    try:
        for i, sym in enumerate(symbols, 1):
            t0 = time.time()
            try:
                n = await svc.fetch_daily_history(sym, years=years)
                bucket = "ok" if n else "empty"
                result[bucket].append((sym, n))
                print(f"[{i:3}/{len(symbols)}] {sym:6} {n:5}봉 ({time.time() - t0:.1f}s)")
            except Exception as e:
                result["error"].append((sym, str(e)[:120]))
                print(f"[{i:3}/{len(symbols)}] {sym:6} 실패: {str(e)[:120]}")
    finally:
        await HttpClientManager.get_instance().stop()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=6.0)
    ap.add_argument("--limit", type=int, default=0, help="앞 N개만 (0=전체)")
    ap.add_argument("--include-leveraged", action="store_true")
    args = ap.parse_args()

    if not UNIVERSE_PATH.exists():
        print(f"실패: {UNIVERSE_PATH} 없음 — 먼저 build_us_universe 를 실행하십시오")
        return 1

    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    symbols = [r["symbol"] for r in universe.get("core", [])]
    if args.include_leveraged:
        symbols += [r["symbol"] for r in universe.get("leveraged", [])]
    if args.limit:
        symbols = symbols[: args.limit]

    print(f"대상 {len(symbols)}종목 × {args.years}년 일봉\n")
    t0 = time.time()
    result = asyncio.run(run(symbols, args.years))

    total_bars = sum(n for _, n in result["ok"])
    print(f"\n완료 {time.time() - t0:.1f}s — 성공 {len(result['ok'])} / "
          f"빈결과 {len(result['empty'])} / 실패 {len(result['error'])}")
    print(f"총 {total_bars:,}봉 적재")
    if result["empty"]:
        print("빈결과:", ", ".join(s for s, _ in result["empty"]))
    if result["error"]:
        for s, e in result["error"]:
            print(f"  실패 {s}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
