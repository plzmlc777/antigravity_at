"""바이낸스 펀딩 이력 백필 — **무료 공개 API**, 인증 불필요.

## 왜 (2026-08-31 새벽)

24시간 보유는 펀딩 정산을 **세 번** 지난다. 8시간당 0.01% 면 하루 0.03% 로
**수수료 0.036% 와 같은 자릿수**다. 그런데 오늘 밤 모든 계산에서 펀딩을
빼먹었다.

그리고 이건 롱·숏 스프레드에서 상쇄되지 않는다 — 급등한 코인은 펀딩이
양수로 치솟고, 그걸 숏 치면 **받는다**. 정확히 되돌림 전략이 숏 치는 대상이다.

실사(2026-08-31): 캐시 240종목 중 펀딩 보유 144, 2024-08-01 이전부터 있는 건
**71종목뿐**. 60→240 종목에서 효과가 절반이 된 걸 봤으니 71종목 결과는
못 믿는다. 그래서 채운다.

## 규약

    GET /fapi/v1/fundingRate?symbol=X&startTime=..&limit=1000   (weight 1)

⚠ **덮어쓰지 않는다.** 이미 있는 (symbol, funding_time) 은 건너뛴다.
⚠ 응답이 빈 배열이면 그 종목은 그 구간에 상장 전이다 — 오류가 아니다.
⚠ 무료·공개만 쓴다(대표님 지시). 인증 헤더를 붙이지 않는다.

사용:
  python3 -m scripts.binance.backfill_funding --smoke 3
  python3 -m scripts.binance.backfill_funding --from 2024-07-01
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import text                                     # noqa: E402

from app.db.session import engine                               # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "runs" / "bars5m"
API = "https://fapi.binance.com/fapi/v1/fundingRate"
log = logging.getLogger("fund_bf")

INS = text("""INSERT INTO binance_funding_rate
             (symbol, funding_time, funding_rate, mark_price, created_at)
             VALUES (:s, :t, :r, :m, now())""")


def fetch(sym: str, start_ms: int, end_ms: int) -> list[dict]:
    out, cur = [], start_ms
    while cur < end_ms:
        url = f"{API}?symbol={sym}&startTime={cur}&limit=1000"
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.load(r)
        except Exception as e:                                  # noqa: BLE001
            log.warning("  ✗ %s @%d: %s", sym, cur, str(e)[:70])
            return out
        if not d:
            break                       # 그 구간엔 없다 — 상장 전이다
        out.extend(d)
        last = int(d[-1]["fundingTime"])
        if len(d) < 1000 or last <= cur:
            break
        cur = last + 1
        time.sleep(0.12)                # 예의상. weight 1 이라 여유 있다
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="d_from", default="2024-07-01")
    p.add_argument("--to", dest="d_to", default="")
    p.add_argument("--smoke", type=int, default=0)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    import datetime as dt
    s_ms = int(dt.datetime.fromisoformat(a.d_from).replace(
        tzinfo=dt.UTC).timestamp() * 1000)
    e_ms = (int(dt.datetime.fromisoformat(a.d_to).replace(
        tzinfo=dt.UTC).timestamp() * 1000) if a.d_to
        else int(time.time() * 1000))
    syms = sorted(x.stem for x in CACHE.glob("*.parquet"))
    if a.smoke:
        syms = syms[:a.smoke]
    log.info("종목 %d · %s ~ %s", len(syms), a.d_from, a.d_to or "지금")

    t0, got, ins, empty = time.time(), 0, 0, 0
    with engine.connect() as c:
        c.execute(text("SET statement_timeout='120s'"))
        for i, s in enumerate(syms, 1):
            have = {r[0] for r in c.execute(text(
                "SELECT funding_time FROM binance_funding_rate "
                "WHERE symbol=:s AND funding_time >= :a"),
                {"s": s, "a": a.d_from}).all()}
            rows = fetch(s, s_ms, e_ms)
            if not rows:
                empty += 1
                continue
            got += len(rows)
            new = []
            for x in rows:
                t = dt.datetime.fromtimestamp(
                    int(x["fundingTime"]) / 1000, dt.UTC).replace(tzinfo=None)
                # 초 단위 오차 흡수 — 정산은 정시다
                t = t.replace(second=0, microsecond=0)
                if t in have:
                    continue
                new.append({"s": s, "t": t, "r": str(x["fundingRate"]),
                            "m": str(x.get("markPrice") or 0)})
            if new:
                try:
                    c.execute(INS, new); c.commit(); ins += len(new)
                except Exception as e:                         # noqa: BLE001
                    c.rollback(); log.warning("  ✗ %s 삽입: %s", s, str(e)[:80])
            if i % 20 == 0 or i == len(syms):
                el = time.time() - t0
                log.info("[%d/%d] 받음 %s · 삽입 %s · 빈응답 %d · %.1f분 "
                         "· 남은 %.0f분", i, len(syms), f"{got:,}", f"{ins:,}",
                         empty, el/60, (len(syms)-i)*el/i/60)
    log.info("완료 — 받음 %s · 삽입 %s · 빈응답 %d · %.1f분",
             f"{got:,}", f"{ins:,}", empty, (time.time()-t0)/60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
