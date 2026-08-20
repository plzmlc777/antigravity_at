"""RSI 트랙 카테고리 분류용 종목 메타 — **`ohlcv_1m` 한 곳에서만** 뽑는다.

⚠ 왜 이 스크립트가 따로 있나 (2026-08-20)
    어제 "신규상장 39종목이 수익의 대부분" 이라고 보고했는데 **오보**였다.
    거래는 `ohlcv_1m` 에서 나왔는데 상장일·유동성은 `ohlcv_daily` 에서 읽었고,
    `ohlcv_daily` 는 **구 `ohlcv` 테이블**을 집계한 것이라 41종목이 33~35일밖에
    없었다. 얇은 종목이 "최근 상장" 으로 둔갑했다.

    교훈: **분석 대상과 분류 기준은 같은 기질에서 나와야 한다.**

출처 두 곳, 둘 다 명시적:
  · 상장일  → 거래소 원본 `/fapi/v1/exchangeInfo` 의 `onboardDate`
             (`ohlcv_1m` 은 백필 창에 잘려 상장일을 답할 수 없다)
  · 유동성·변동성·커버리지 → `ohlcv_1m`, 백테스트와 **같은 구간**

사용:
  python3 -m scripts.research.rsi_symbol_meta --start 2025-08-17 --end 2026-08-17
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import text  # noqa: E402

from app.db.session import engine  # noqa: E402

log = logging.getLogger("rsi_meta")

EXINFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"

# 종목 하나를 한 번에 — (symbol, ts) 인덱스를 탄다.
# 일별로 접어서 집계한다: 하루 달러거래대금·하루 수익률을 만들고
# 그 분포를 요약한다. 분 단위 통계는 마이크로구조에 오염돼 분류에 못 쓴다.
AGG = text("""
WITH d AS (
    SELECT date_trunc('day', ts) AS day,
           sum(close * volume)                              AS dv,
           count(*)                                         AS nm,
           max(close) FILTER (WHERE rd = 1)                 AS c,
           max(open)  FILTER (WHERE ra = 1)                 AS o
    FROM (
        SELECT ts, open, close, volume,
               row_number() OVER (PARTITION BY date_trunc('day', ts)
                                  ORDER BY ts)      AS ra,
               row_number() OVER (PARTITION BY date_trunc('day', ts)
                                  ORDER BY ts DESC) AS rd
        FROM ohlcv_1m
        WHERE symbol = :sym AND ts >= :a AND ts < :b
    ) x
    GROUP BY day
)
SELECT count(*)                                   AS days,
       sum(nm)                                    AS minutes,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY dv)  AS dv_med,
       avg(dv)                                    AS dv_avg,
       min(day)                                   AS first_day,
       max(day)                                   AS last_day,
       stddev_samp(c / NULLIF(o, 0) - 1.0)        AS daily_vol,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY c) AS px_med,
       count(*) FILTER (WHERE nm < 1400)          AS thin_days
FROM d
""")


def fetch_onboard(symbols: list[str]) -> dict[str, dict]:
    """상장일은 거래소만 안다. 요청 1건."""
    data = json.load(urllib.request.urlopen(EXINFO, timeout=30))
    info = {s["symbol"]: s for s in data["symbols"]}
    out = {}
    for s in symbols:
        i = info.get(s)
        if not i:
            log.warning("exchangeInfo 에 없다 — %s (상장폐지 추정)", s)
            continue
        out[s] = {
            "onboard": str(dt.datetime.fromtimestamp(
                i["onboardDate"] / 1000, dt.UTC).date()),
            "status": i["status"],
            "base": i["baseAsset"],
        }
    return out


def one(sym: str, a: str, b: str) -> tuple[str, dict]:
    with engine.connect() as c:
        r = c.execute(AGG, {"sym": sym, "a": a, "b": b}).fetchone()
    if not r or not r[0]:
        return sym, {"days": 0}
    return sym, {
        "days": int(r[0]),
        "minutes": int(r[1] or 0),
        "dv_med": float(r[2] or 0.0),
        "dv_avg": float(r[3] or 0.0),
        "first_day": str(r[4])[:10],
        "last_day": str(r[5])[:10],
        "daily_vol": float(r[6] or 0.0),
        "px_med": float(r[7] or 0.0),
        "thin_days": int(r[8] or 0),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--universe", default="configs/rsi_paper_universe.txt")
    p.add_argument("--start", required=True, help="YYYY-MM-DD 포함")
    p.add_argument("--end", required=True, help="YYYY-MM-DD 미포함")
    p.add_argument("--workers", type=int, default=3,
                   help="격자와 동시에 돌 수 있어 기본을 낮게 둔다")
    p.add_argument("--out", default="runs/research_track/rsi_tp_sl/symbol_meta.json")
    a = p.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    uni = [s.strip() for s in Path(a.universe).read_text().split() if s.strip()]
    log.info("유니버스 %d종목 · 구간 %s ~ %s · 워커 %d",
             len(uni), a.start, a.end, a.workers)

    onboard = fetch_onboard(uni)
    log.info("상장일 확보 %d/%d (거래소 원본)", len(onboard), len(uni))

    meta: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for sym, m in ex.map(lambda s: one(s, a.start, a.end), uni):
            meta[sym] = {**m, **onboard.get(sym, {})}
            done += 1
            if done % 25 == 0:
                log.info("[%d/%d종목]", done, len(uni))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"window": [a.start, a.end], "source": "ohlcv_1m + exchangeInfo",
         "symbols": meta}, indent=1))
    ok = sum(1 for m in meta.values() if m.get("days", 0) >= 360)
    log.info("저장 %s · 창 완전 %d/%d종목", out, ok, len(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
