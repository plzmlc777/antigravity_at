"""호가 수집 — 바이낸스 `bookTicker`, 무료·키 불필요.

한 요청에 **737종목 최우선호가**가 온다(가중치 5). 종목별 `depth` 는 요청이
종목 수만큼 필요해 비싸므로 최우선호가만 모은다 — 스프레드 요인에는 충분하다.

⚠ 과거 데이터가 없다
    호가는 지나가면 사라진다. **검정 가능한 표본까지 최소 6개월**이다.
    이 수집기는 그 6개월을 시작하는 것이지 오늘 답을 주지 않는다.

⚠ 원자료는 커진다
    5분 간격이면 737종목 × 288 = 하루 21만 행, 1년 7,700만 행이다.
    그래서 `--rollup` 으로 일별 집계를 만들고 `--prune` 으로 원자료를 정리한다.
    **집계를 먼저 만들고 정리해야** 한다 — 순서가 바뀌면 데이터가 사라진다.

유니버스
    유동성 게이트를 통과한 종목만 저장한다(현재 190종). 737종 전부 저장하면
    행이 4배가 되는데, 거래도 못 할 종목의 호가는 쓸 데가 없다(교훈 #78).

사용:
  python3 -m scripts.collect_orderbook --once        # 1회 수집 (크론)
  python3 -m scripts.collect_orderbook --rollup      # 일별 집계
  python3 -m scripts.collect_orderbook --prune 30    # 30일 넘은 원자료 삭제
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("orderbook")

URL = "https://fapi.binance.com/fapi/v1/ticker/bookTicker"
GATE = ROOT / "configs" / "liquid_universe.json"


def fetch(retries: int = 3) -> list[dict]:
    for i in range(retries):
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "antigravity"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:
            if i == retries - 1:
                raise
            log.warning("재시도 %d: %s", i + 1, exc)
            time.sleep(2 * (i + 1))
    return []


def gate_symbols() -> set[str] | None:
    """유동성 통과 종목. 파일이 없으면 None(전 종목 저장)."""
    if not GATE.exists():
        log.warning("%s 없음 — 전 종목을 저장한다(행이 4배가 된다)", GATE)
        return None
    try:
        return set(json.load(open(GATE))["symbols"])
    except Exception:
        return None


def collect_once(conn, keep: set[str] | None) -> int:
    from sqlalchemy import text
    rows = fetch()
    now = datetime.utcnow().replace(second=0, microsecond=0)
    sql = text("""
        INSERT INTO orderbook_snapshot
            (symbol, ts, exchange_ts, bid_price, ask_price, bid_qty, ask_qty,
             spread_bp, mid, imbalance)
        VALUES (:symbol, :ts, :ex_ts, :bp, :ap, :bq, :aq, :spread, :mid, :imb)
        ON CONFLICT (symbol, ts) DO NOTHING
    """)
    n = 0
    for r in rows:
        sym = r.get("symbol", "")
        if keep is not None and sym not in keep:
            continue
        try:
            bp, ap = float(r["bidPrice"]), float(r["askPrice"])
            bq, aq = float(r.get("bidQty") or 0), float(r.get("askQty") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        # 한쪽 호가가 비면 스프레드가 무의미하다 — 저장하지 않는다.
        # 0 으로 넣으면 나중에 '스프레드 0'으로 읽혀 최고 유동성으로 오독된다.
        if bp <= 0 or ap <= 0 or ap < bp:
            continue
        mid = (ap + bp) / 2
        conn.execute(sql, {
            "symbol": sym, "ts": now,
            "ex_ts": (datetime.utcfromtimestamp(r["time"] / 1000)
                      if r.get("time") else None),
            "bp": bp, "ap": ap, "bq": bq, "aq": aq,
            "spread": (ap - bp) / mid * 10000, "mid": mid,
            "imb": ((bq - aq) / (bq + aq)) if (bq + aq) > 0 else None,
        })
        n += 1
    conn.commit()
    return n


def rollup(conn, days: int) -> int:
    """일별 집계. **중앙값**이 대표값이다 — 평균은 순간 급확대에 끌려간다."""
    from sqlalchemy import text
    sql = text("""
        INSERT INTO orderbook_daily
            (symbol, date, n_samples, spread_bp_med, spread_bp_mean,
             spread_bp_p90, spread_bp_std, imbalance_mean, top_depth_usd_med,
             built_at)
        SELECT symbol, date_trunc('day', ts) AS d, count(*),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY spread_bp),
               avg(spread_bp),
               percentile_cont(0.9) WITHIN GROUP (ORDER BY spread_bp),
               stddev_samp(spread_bp),
               avg(imbalance),
               percentile_cont(0.5) WITHIN GROUP
                   (ORDER BY (bid_price * bid_qty + ask_price * ask_qty)),
               now()
        FROM orderbook_snapshot
        WHERE ts >= now() - (:days || ' days')::interval
        GROUP BY symbol, date_trunc('day', ts)
        ON CONFLICT (symbol, date) DO UPDATE SET
            n_samples = EXCLUDED.n_samples,
            spread_bp_med = EXCLUDED.spread_bp_med,
            spread_bp_mean = EXCLUDED.spread_bp_mean,
            spread_bp_p90 = EXCLUDED.spread_bp_p90,
            spread_bp_std = EXCLUDED.spread_bp_std,
            imbalance_mean = EXCLUDED.imbalance_mean,
            top_depth_usd_med = EXCLUDED.top_depth_usd_med,
            built_at = now()
    """)
    r = conn.execute(sql, {"days": days})
    conn.commit()
    return r.rowcount or 0


def prune(conn, keep_days: int) -> int:
    """원자료 정리. **집계가 있는 날만** 지운다 — 순서가 바뀌면 데이터가 사라진다."""
    from sqlalchemy import text
    r = conn.execute(text("""
        DELETE FROM orderbook_snapshot s
        WHERE s.ts < now() - (:d || ' days')::interval
          AND EXISTS (SELECT 1 FROM orderbook_daily x
                      WHERE x.symbol = s.symbol
                        AND x.date = date_trunc('day', s.ts))
    """), {"d": keep_days})
    conn.commit()
    return r.rowcount or 0


def main() -> int:
    p = argparse.ArgumentParser(description="호가 수집 (바이낸스 bookTicker)")
    p.add_argument("--once", action="store_true", help="1회 수집")
    p.add_argument("--rollup", action="store_true", help="일별 집계")
    p.add_argument("--rollup-days", type=int, default=3,
                   help="집계 대상 최근 일수(오늘 포함해 다시 만든다)")
    p.add_argument("--prune", type=int, default=0,
                   help="이 일수 넘은 **집계 완료분** 원자료 삭제")
    p.add_argument("--status", action="store_true")
    a = p.parse_args()
    if not (a.once or a.rollup or a.prune or a.status):
        raise SystemExit("--once / --rollup / --prune / --status 중 하나")

    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        if a.once:
            keep = gate_symbols()
            t0 = time.time()
            n = collect_once(conn, keep)
            log.info("수집 %d종목 (%.1f초)", n, time.time() - t0)
        if a.rollup:
            n = rollup(conn, a.rollup_days)
            log.info("일별 집계 %d행", n)
        if a.prune:
            n = prune(conn, a.prune)
            log.info("원자료 정리 %d행 (집계 완료분만)", n)

        s = conn.execute(text("""
            SELECT (SELECT count(*) FROM orderbook_snapshot),
                   (SELECT count(distinct symbol) FROM orderbook_snapshot),
                   (SELECT min(ts) FROM orderbook_snapshot),
                   (SELECT max(ts) FROM orderbook_snapshot),
                   (SELECT count(*) FROM orderbook_daily)
        """)).one()
        print("=" * 72)
        print(f"호가 스냅샷 {s[0]:,}행 · 종목 {s[1]} · {s[2]} ~ {s[3]}")
        print(f"일별 집계   {s[4]:,}행")
        if s[0]:
            top = conn.execute(text("""
                SELECT symbol, spread_bp FROM orderbook_snapshot
                WHERE ts = (SELECT max(ts) FROM orderbook_snapshot)
                ORDER BY spread_bp LIMIT 5
            """)).fetchall()
            wide = conn.execute(text("""
                SELECT symbol, spread_bp FROM orderbook_snapshot
                WHERE ts = (SELECT max(ts) FROM orderbook_snapshot)
                ORDER BY spread_bp DESC LIMIT 5
            """)).fetchall()
            print(f"  최신 스냅샷 — 최저 스프레드: "
                  + ", ".join(f"{r[0]} {r[1]:.2f}bp" for r in top))
            print(f"                최고 스프레드: "
                  + ", ".join(f"{r[0]} {r[1]:.1f}bp" for r in wide))
        print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
