"""펀딩비 이력 수집 — 바이낸스 공개 REST (무료·키 불필요).

왜 필요한가
    알트 바스켓을 **몇 달씩 숏**으로 들고 있으면 펀딩이 손익의 주요 항목이 된다.
    8시간마다 정산되므로 연 1,095회다. 평균 +0.01%/회면 연 **+11%**, 반대면
    -11% 다. 이걸 안 재고 "알트가 더 빠지니 숏이 이긴다"고 말할 수 없다 —
    [[feedback-lesson-82-deviation-scales-with-its-own-toll]] 가 정확히 그 병이다
    (USDT/USDC 괴리 t +425 인데 마찰 넣으니 순익 0/28).

    기존 `binance_funding_rate` 는 **26종목 · 2023-11 이후**뿐이었다. 유니버스
    전체를 못 재므로 바스켓 손익을 못 낸다.

데이터원
    GET https://fapi.binance.com/fapi/v1/fundingRate
        ?symbol=X&startTime=<ms>&limit=1000
    공개 엔드포인트다 — API 키가 필요 없고 요금도 없다.

⚠ 기존 행은 덮지 않는다
    `ON CONFLICT DO NOTHING`. 이미 수집된 26종목의 값은 그대로 둔다.

⚠ 부호 규약
    `funding_rate` 가 **양수면 롱이 숏에게 지급**한다. 즉 숏 포지션은 양수
    펀딩에서 **번다.** 바스켓 숏 손익에 더할 때 부호를 뒤집지 마라.

사용:
  python3 -m scripts.collect_funding_history --universe --since 2021-01-01
  python3 -m scripts.collect_funding_history --symbols BTCUSDT,ETHUSDT
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("funding")

REST = "https://fapi.binance.com/fapi/v1/fundingRate"
PAGE = 1000


def fetch(sym: str, start_ms: int) -> list[dict]:
    """한 종목의 펀딩 이력 전부. 1000건씩 넘겨받는다."""
    out, cur = [], start_ms
    while True:
        q = urllib.parse.urlencode({"symbol": sym, "startTime": cur,
                                    "limit": PAGE})
        try:
            with urllib.request.urlopen(f"{REST}?{q}", timeout=60) as r:
                data = json.load(r)
        except Exception as exc:
            log.warning("%s 실패(%s) — 여기까지만", sym, exc)
            break
        if not data:
            break
        out.extend(data)
        nxt = int(data[-1]["fundingTime"]) + 1
        if nxt <= cur or len(data) < PAGE:
            break
        cur = nxt
        # 공개 엔드포인트라도 예의는 지킨다
        time.sleep(0.12)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="펀딩비 이력 수집")
    p.add_argument("--universe", action="store_true",
                   help="ohlcv_daily 에 있는 전 종목")
    p.add_argument("--symbols", default="")
    p.add_argument("--since", default="2021-01-01")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine
    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.universe:
        with engine.connect() as c:
            syms = [r[0] for r in c.execute(text(
                "SELECT DISTINCT symbol FROM ohlcv_daily ORDER BY symbol"))]
    else:
        raise SystemExit("--universe 또는 --symbols 가 필요하다")
    if a.limit:
        syms = syms[:a.limit]

    start_ms = int(datetime.strptime(a.since, "%Y-%m-%d")
                   .replace(tzinfo=timezone.utc).timestamp() * 1000)
    log.info("대상 %d종목 · %s 이후", len(syms), a.since)

    total, miss, t0 = 0, 0, time.time()
    with engine.connect() as conn:
        for i, sym in enumerate(syms, 1):
            rows = fetch(sym, start_ms)
            if not rows:
                miss += 1
                continue
            new = 0
            for r in rows:
                try:
                    ft = datetime.fromtimestamp(int(r["fundingTime"]) / 1000,
                                                timezone.utc).replace(tzinfo=None)
                    fr = float(r["fundingRate"])
                    mp = float(r.get("markPrice") or 0) or None
                except (ValueError, KeyError, TypeError):
                    continue
                res = conn.execute(text(
                    "INSERT INTO binance_funding_rate "
                    "(symbol, funding_time, funding_rate, mark_price, created_at) "
                    "VALUES (:s, :t, :r, :m, now()) "
                    "ON CONFLICT DO NOTHING"),
                    {"s": sym, "t": ft, "r": fr, "m": mp})
                new += res.rowcount or 0
            conn.commit()
            total += new
            if i % 20 == 0 or new:
                log.info("[%d/%d] %s — 수신 %d · 신규 %d · 누적 %s",
                         i, len(syms), sym, len(rows), new, f"{total:,}")

    print("=" * 76)
    with engine.connect() as c:
        n, s, lo, hi = c.execute(text(
            "SELECT count(*), count(distinct symbol), min(funding_time), "
            "max(funding_time) FROM binance_funding_rate")).one()
        print(f"  binance_funding_rate  {n:>9,}행 · 종목 {s:>4} · {lo} ~ {hi}")
    print(f"  신규 {total:,}행 · 이력 없음 {miss}종목 · {time.time()-t0:.0f}초")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
