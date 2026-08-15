"""바이낸스 공식 아카이브 수집 — `bookDepth` · `metrics`.

⚠ 이걸 먼저 확인했어야 했다
    2026-08-15 오전에 "OI 는 4개월뿐이라 표본 밖 검증 불가", "호가는 과거가
    없어 6개월 기다려야 한다"며 두 축을 닫았다. **둘 다 틀렸다.**
    `data.binance.vision` 이 처음부터 무료로 공개하고 있었다.

        bookDepth  BTCUSDT 1,318일 (2023-01-01~) · 0.62GB · 937종목
        metrics    BTCUSDT 2,173일 (2020-09-01~) · 25.3MB

    자체 수집기를 만들기 전에 **공개 아카이브부터 확인**하는 것이 순서다.

무엇을 받나
    bookDepth  1분마다 중간가 대비 ±1~5% 구간의 호가 깊이(수량·명목)
               → 최우선호가 스프레드보다 값지다. 우리 계좌 규모에서 진짜
                 문제는 스프레드가 아니라 **얼마를 밀어넣을 수 있는가**다.
    metrics    5분마다 OI, **상위 트레이더 롱숏 비율**, 테이커 롱숏 거래량 비율
               → 포지셔닝 축은 한 번도 제대로 못 써봤다.

⚠ bookTicker 는 받지 않는다
    같은 아카이브에 있지만 **하루 82MB/종목**이다(틱 단위 전량). 190종목 3년이면
    15TB 라 감당이 안 된다. bookDepth 는 하루 0.23MB 로 스냅샷 기반이고
    우리가 필요한 것을 준다.

⚠ 원본을 쌓지 않는다
    받아서 **일별로 집계하고 원본은 버린다.** 190종목 × 1,300일 원본이면
    수십 GB 이고, 우리가 쓰는 건 일별 요약뿐이다.

사용:
  python3 -m scripts.collect_binance_archive --kind metrics --days 800
  python3 -m scripts.collect_binance_archive --kind bookdepth --days 400
  python3 -m scripts.collect_binance_archive --kind both --incremental
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bn_archive")

BASE = "https://data.binance.vision/data/futures/um/daily"
GATE = ROOT / "configs" / "liquid_universe.json"

# 하루 한 건씩 순차로 받으면 190종목 × 1500일이 **7시간**이다(실측).
# 다운로드는 I/O 대기라 병렬이 그대로 이득이다. DB 쓰기는 주 스레드에서만 한다.
WORKERS = 12


def fetch_zip(kind: str, symbol: str, d: date) -> list[dict] | None:
    """하루치 CSV. 없으면 None(그 종목이 그날 상장 전이거나 결손)."""
    folder = {"metrics": "metrics", "bookdepth": "bookDepth"}[kind]
    name = f"{symbol}-{folder}-{d.isoformat()}.zip"
    url = f"{BASE}/{folder}/{symbol}/{name}"
    try:
        with urllib.request.urlopen(url, timeout=90) as r:
            blob = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        inner = z.namelist()[0]
        text = z.read(inner).decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def agg_metrics(rows: list[dict]) -> dict | None:
    """5분 관측 → 일별. **중앙값**을 대표값으로 (순간 급변에 끌려가지 않게)."""
    import statistics as st

    def col(k):
        out = []
        for r in rows:
            v = r.get(k)
            if v not in (None, ""):
                try:
                    out.append(float(v))
                except ValueError:
                    pass
        return out

    oi = col("sum_open_interest")
    oiv = col("sum_open_interest_value")
    tl = col("sum_toptrader_long_short_ratio")
    tlc = col("count_toptrader_long_short_ratio")
    lsr = col("count_long_short_ratio")
    tkr = col("sum_taker_long_short_vol_ratio")
    if not oi:
        return None
    return {
        "n_samples": len(rows),
        "oi_med": st.median(oi), "oi_last": oi[-1],
        "oi_value_med": st.median(oiv) if oiv else None,
        # 하루 안에서 OI 가 얼마나 움직였나 — 포지션 회전의 대리변수
        # ⚠ 0 방어 — OI 중앙값이 0 인 종목이 실제로 있다(거래가 멈춘 계약).
        #   막지 않으면 ZeroDivisionError 로 190종목 수집이 통째로 죽는다.
        "oi_range_pct": (((max(oi) - min(oi)) / st.median(oi) * 100)
                         if oi and st.median(oi) > 0 else None),
        "toptrader_ls_med": st.median(tl) if tl else None,
        "toptrader_ls_cnt_med": st.median(tlc) if tlc else None,
        "long_short_ratio_med": st.median(lsr) if lsr else None,
        "taker_ls_med": st.median(tkr) if tkr else None,
    }


def agg_bookdepth(rows: list[dict]) -> dict | None:
    """1분 × 10구간(±1~5%) → 일별.

    `percentage` 는 중간가 대비 %다(-5~-1 매수측, 1~5 매도측).
    ±1% 구간 명목이 **실제로 밀어넣을 수 있는 크기**에 가장 가깝다.
    """
    import statistics as st
    bid1, ask1, bid5, ask5 = [], [], [], []
    for r in rows:
        try:
            pct = float(r["percentage"])
            notional = float(r["notional"])
        except (KeyError, TypeError, ValueError):
            continue
        if pct == -1:
            bid1.append(notional)
        elif pct == 1:
            ask1.append(notional)
        elif pct == -5:
            bid5.append(notional)
        elif pct == 5:
            ask5.append(notional)
    if not bid1 or not ask1:
        return None
    b1, a1 = st.median(bid1), st.median(ask1)
    return {
        "n_samples": len(rows),
        "depth1_bid_usd": b1, "depth1_ask_usd": a1,
        "depth1_usd": b1 + a1,
        "depth5_bid_usd": st.median(bid5) if bid5 else None,
        "depth5_ask_usd": st.median(ask5) if ask5 else None,
        # 매수벽/매도벽 불균형. +면 매수가 두껍다
        "depth1_imbalance": (b1 - a1) / (b1 + a1) if (b1 + a1) else None,
        # 깊이의 하루 변동 — 유동성 안정성
        "depth1_bid_cv": (st.pstdev(bid1) / st.mean(bid1)) if len(bid1) > 2 else None,
    }


def symbols() -> list[str]:
    if GATE.exists():
        try:
            return json.load(open(GATE))["symbols"]
        except Exception:
            pass
    raise SystemExit(f"{GATE} 없음 — 먼저 유동성 게이트를 만드십시오")


def main() -> int:
    p = argparse.ArgumentParser(description="바이낸스 공개 아카이브 수집")
    p.add_argument("--kind", choices=["metrics", "bookdepth", "both"],
                   required=True)
    p.add_argument("--days", type=int, default=400, help="오늘 기준 소급 일수")
    p.add_argument("--incremental", action="store_true",
                   help="종목별 마지막 날짜 이후만")
    p.add_argument("--symbols", default="", help="쉼표 구분. 기본은 게이트 통과분")
    p.add_argument("--limit", type=int, default=0)
    a = p.parse_args()

    from sqlalchemy import text

    from app.db.session import engine

    syms = ([s.strip().upper() for s in a.symbols.split(",") if s.strip()]
            or symbols())
    if a.limit:
        syms = syms[:a.limit]
    kinds = ["metrics", "bookdepth"] if a.kind == "both" else [a.kind]
    end = date.today() - timedelta(days=1)      # 오늘치는 아직 안 올라온다
    start = end - timedelta(days=a.days)
    log.info("종목 %d · 종류 %s · %s ~ %s", len(syms), kinds, start, end)

    tbl = {"metrics": "binance_archive_metrics",
           "bookdepth": "binance_archive_depth"}
    total, t0 = 0, time.time()
    with engine.connect() as conn:
        for kind in kinds:
            last = {}
            if a.incremental:
                for s, d in conn.execute(text(
                        f"SELECT symbol, max(date) FROM {tbl[kind]} "
                        f"GROUP BY symbol")):
                    last[s] = d
            for i, sym in enumerate(syms, 1):
                d0 = max(start, (last[sym] + timedelta(days=1))
                         if sym in last else start)
                days = []
                cur = d0
                while cur <= end:
                    days.append(cur)
                    cur += timedelta(days=1)

                def one(day, _k=kind, _s=sym):
                    """받아서 **집계까지** 워커에서 끝낸다 — 원본을 주 스레드로
                    넘기면 메모리가 터진다(하루치가 3만 행이다)."""
                    try:
                        rows = fetch_zip(_k, _s, day)
                    except Exception as exc:
                        log.warning("%s %s %s: %s", _k, _s, day, exc)
                        return day, None
                    if not rows:
                        return day, None
                    try:
                        return day, (agg_metrics(rows) if _k == "metrics"
                                     else agg_bookdepth(rows))
                    except Exception as exc:
                        # 한 날짜의 집계 실패가 전체를 죽이면 안 된다
                        log.warning("%s %s %s 집계 실패: %s", _k, _s, day, exc)
                        return day, None

                got, miss = 0, 0
                with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                    results = list(ex.map(one, days))
                for cur, agg in results:
                    if True:
                        if agg:
                            cols = list(agg)
                            # fetched_at 은 NOT NULL 이다 — 빼면 넣을 때 터진다
                            conn.execute(text(
                                f"INSERT INTO {tbl[kind]} "
                                f"(symbol, date, {', '.join(cols)}, fetched_at) "
                                f"VALUES (:symbol, :date, "
                                f"{', '.join(':' + c for c in cols)}, now()) "
                                f"ON CONFLICT (symbol, date) DO UPDATE SET "
                                + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
                                + ", fetched_at = now()"),
                                {"symbol": sym, "date": cur, **agg})
                            got += 1
                        else:
                            miss += 1
                    else:
                        miss += 1
                conn.commit()
                total += got
                if got or i % 20 == 0:
                    log.info("[%s] %d/%d %s +%d일 (결손 %d) · 누적 %s",
                             kind, i, len(syms), sym, got, miss, f"{total:,}")

    print("=" * 76)
    print(f"아카이브 수집 — {total:,}일치 · {time.time()-t0:.0f}초")
    with engine.connect() as c:
        for kind in kinds:
            n, s, d0, d1 = c.execute(text(
                f"SELECT count(*), count(distinct symbol), min(date), max(date) "
                f"FROM {tbl[kind]}")).one()
            print(f"  {tbl[kind]:<26} {n:>8,}행 · 종목 {s:>4} · {d0} ~ {d1}")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
