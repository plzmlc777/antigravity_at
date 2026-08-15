"""Deribit DVOL 수집 — 무료·키 불필요·5.4년.

⚠ 한 번에 1,000행 상한이다
    `get_volatility_index_data` 는 요청당 최대 1,000행을 준다. 그냥 부르면
    최근 1,000일만 받고 "이게 전부"라고 착각한다. **뒤로 페이징**한다.

⚠ 옵션은 BTC·ETH 만 있다
    SOL·XRP 는 활성 옵션 0개다(2026-08-15 실측). 그래서 이 기질은
    **횡단면 요인이 못 되고 시장 국면 지표**로만 쓸 수 있다.

사용:
  python3 -m scripts.collect_deribit_dvol
  python3 -m scripts.collect_deribit_dvol --incremental
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dvol")

BASE = "https://www.deribit.com/api/v2/public/"
CURRENCIES = ["BTC", "ETH"]
DAY_MS = 86_400_000
ORIGIN_MS = 1_600_000_000_000 - 20 * 365 * DAY_MS   # 넉넉히 과거


def api(ep: str, **kw) -> dict:
    q = "&".join(f"{k}={v}" for k, v in kw.items())
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{BASE}{ep}?{q}", timeout=45) as r:
                return json.load(r)["result"]
        except Exception as exc:
            if attempt == 3:
                raise
            log.warning("재시도 %d — %s", attempt + 1, exc)
            time.sleep(2 * (attempt + 1))
    return {}


def fetch_all(cur: str, since_ms: int) -> list[list]:
    """뒤로 페이징해 전 이력을 모은다. 행 = [ts, open, high, low, close]."""
    out: list[list] = []
    end = int(time.time() * 1000)
    for _ in range(40):
        d = api("get_volatility_index_data", currency=cur,
                start_timestamp=since_ms, end_timestamp=end,
                resolution=86400)
        rows = d.get("data") or []
        if not rows:
            break
        out = rows + out
        new_end = rows[0][0] - DAY_MS
        if new_end >= end:
            break
        end = new_end
        if len(rows) < 900:      # 상한에 안 걸렸으면 더 과거가 없다
            break
    # 같은 날짜 중복 제거 (페이징 경계에서 겹칠 수 있다)
    seen, uniq = set(), []
    for r in sorted(out, key=lambda x: x[0]):
        d0 = datetime.fromtimestamp(r[0] / 1000, timezone.utc).date()
        if d0 in seen:
            continue
        seen.add(d0)
        uniq.append(r)
    return uniq


def main() -> int:
    p = argparse.ArgumentParser(description="Deribit DVOL 수집")
    p.add_argument("--incremental", action="store_true")
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    total, t0 = 0, time.time()
    with engine.connect() as conn:
        for cur in CURRENCIES:
            since = ORIGIN_MS
            if a.incremental:
                last = conn.execute(text(
                    "SELECT max(date) FROM deribit_dvol WHERE currency = :c"),
                    {"c": cur}).scalar()
                if last:
                    since = int(datetime(last.year, last.month, last.day,
                                         tzinfo=timezone.utc).timestamp() * 1000)
            rows = fetch_all(cur, since)
            got = 0
            for ts, o, h, l, c in rows:
                d0 = datetime.fromtimestamp(ts / 1000, timezone.utc).date()
                if d0 >= date.today():        # 오늘은 아직 안 닫혔다
                    continue
                conn.execute(text(
                    "INSERT INTO deribit_dvol (currency, date, dvol_open, "
                    "dvol_high, dvol_low, dvol_close, fetched_at) VALUES "
                    "(:c, :d, :o, :h, :l, :cl, now()) "
                    "ON CONFLICT (currency, date) DO UPDATE SET "
                    "dvol_open = EXCLUDED.dvol_open, "
                    "dvol_high = EXCLUDED.dvol_high, "
                    "dvol_low = EXCLUDED.dvol_low, "
                    "dvol_close = EXCLUDED.dvol_close, fetched_at = now()"),
                    {"c": cur, "d": d0, "o": o, "h": h, "l": l, "cl": c})
                got += 1
            conn.commit()
            total += got
            log.info("%s — %d일", cur, got)

    print("=" * 70)
    with engine.connect() as c:
        for cur in CURRENCIES:
            n, d0, d1 = c.execute(text(
                "SELECT count(*), min(date), max(date) FROM deribit_dvol "
                "WHERE currency = :c"), {"c": cur}).one()
            print(f"  {cur}  {n:>6,}행 · {d0} ~ {d1}")
    print(f"  총 {total:,}행 · {time.time()-t0:.0f}초")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
