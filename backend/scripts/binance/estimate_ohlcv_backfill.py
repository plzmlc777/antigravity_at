#!/usr/bin/env python3
"""1m OHLCV 백필 견적 — 다운로드 용량 / DB 증가 / 소요시간.

배경 (2026-08-09):
  DB `ohlcv` 1m 이 214종목 중 **과거 온전(2024-01 시작) + 최신 갱신을 모두 갖춘
  종목이 12개뿐**이다. `binance-ohlcv-backfill` 은 정상 작동하지만 대상이 26종목
  하드코딩 + days=3 증분이라, 168종목은 2026-05-12 에 멈춰 있고 BTCUSDT 조차
  2026-03-21 부터만 있다(140일). "214종목 유니버스" 는 사실상 허구였다.

  이걸 메우려면 얼마가 드는지 실측한다 — 추정하지 않고 HEAD 프로브로 잰다.
  (메모리 선례: aggTrades 백필이 16.15GB 로 산정돼 중단됐다. klines 는 자릿수가
   다를 것으로 보지만 재보고 판단한다.)

소스: Binance public data archive (무료, 인증 불필요)
  https://data.binance.vision/data/futures/um/monthly/klines/{SYM}/1m/{SYM}-1m-{YYYY-MM}.zip

사용:
  cd backend && source venv/bin/activate
  python3 scripts/binance/estimate_ohlcv_backfill.py
  python3 scripts/binance/estimate_ohlcv_backfill.py --target-start 2021-01-01
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "app").exists():
    ROOT = Path("/home/mint/auto_trading/backend")
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bf_estimate")

ARCHIVE = ("https://data.binance.vision/data/futures/um/monthly/klines/"
           "{sym}/1m/{sym}-1m-{ym}.zip")
# 상장일 — 상장 전 구간은 "결손" 이 아니다. 이걸 빼지 않으면 2026년 신규상장
# 종목이 30개월씩 결손으로 잡혀 견적이 크게 부풀려진다 (첫 산정에서 실제로 그랬다).
LISTINGS = "runs/research_track/lifecycle_phase/listing_dates.json"
LIQ_MIN_USD = 5_000_000.0
PROBE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
                 "AVAXUSDT", "LINKUSDT", "SOLUSDT"]
PROBE_MONTHS = ["2024-03", "2025-06", "2026-05"]


def months_between(a: date, b: date) -> list[str]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def head_size(sym: str, ym: str, timeout: float = 20.0) -> int | None:
    url = ARCHIVE.format(sym=sym, ym=ym)
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        n = r.headers.get("Content-Length")
        return int(n) if n else None
    except Exception:
        return None


def load_listings() -> dict:
    import json
    p = ROOT / LISTINGS
    if not p.exists():
        log.warning("상장일 파일이 없다 — 보정 없이 견적한다 (과대추정)")
        return {}
    raw = json.loads(p.read_text())
    out = {}
    for sym, v in raw.items():
        od = (v or {}).get("onboard_date")
        if od:
            out[sym] = datetime.strptime(od, "%Y-%m-%d").date()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-start", default="2024-01-01",
                    help="이 날짜까지 과거를 메운다 (기본 2024-01-01)")
    ap.add_argument("--liq-min", type=float, default=LIQ_MIN_USD)
    args = ap.parse_args()
    target_start = datetime.strptime(args.target_start, "%Y-%m-%d").date()
    target_end = datetime.utcnow().date() - timedelta(days=1)

    db = SessionLocal()
    try:
        rows = db.execute(text("""
            WITH d AS (SELECT symbol, timestamp::date AS dd, sum(close*volume) AS qv
                       FROM ohlcv WHERE time_frame='1m' GROUP BY symbol, timestamp::date)
            SELECT symbol, min(dd) AS s, max(dd) AS e, count(*) AS days,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY qv) AS med_qv
            FROM d GROUP BY symbol ORDER BY symbol
        """)).fetchall()
        size_row = db.execute(text(
            "SELECT pg_total_relation_size('ohlcv') AS bytes, count(*) AS n FROM ohlcv"
        )).fetchone()
        bytes_per_row = float(size_row.bytes) / max(int(size_row.n), 1)
        log.info(f"현재 ohlcv 테이블 {size_row.bytes/1e9:.2f} GB / {size_row.n:,}행 "
                 f"→ 행당 {bytes_per_row:.1f} bytes (인덱스 포함)")
    finally:
        db.close()

    liquid = [r for r in rows if float(r.med_qv or 0) >= args.liq_min]
    listings = load_listings()
    log.info(f"종목 {len(rows)} | 유동성 통과 {len(liquid)} "
             f"(일 거래대금 중간값 >= ${args.liq_min:,.0f}) | 상장일 확보 {len(listings)}")

    # 실측 프로브 — 월별 zip 크기
    log.info("archive HEAD 프로브 중...")
    sizes = []
    for sym in PROBE_SYMBOLS:
        for ym in PROBE_MONTHS:
            n = head_size(sym, ym)
            if n:
                sizes.append(n)
                log.info(f"  {sym:9s} {ym}  {n/1e6:6.2f} MB")
            else:
                log.info(f"  {sym:9s} {ym}  (없음/실패)")
    if not sizes:
        log.error("프로브 전부 실패 — archive 접근을 확인해야 한다")
        return 1
    avg_zip = sum(sizes) / len(sizes)
    log.info(f"월별 zip 평균 {avg_zip/1e6:.2f} MB (표본 {len(sizes)})")

    # 종목별 결손 월 계산
    total_missing_months = 0
    total_missing_days = 0
    per_tier = {"과거만 결손": 0, "최근만 결손": 0, "양쪽 결손": 0, "온전": 0}
    detail = []
    no_listing = 0
    for r in liquid:
        # 상장 전은 결손이 아니다 — 종목별 시작점을 상장일로 클램프한다.
        onboard = listings.get(r.symbol)
        if onboard is None:
            no_listing += 1
            onboard = r.s          # 상장일 미확보 → 보유 시작을 하한으로 (보수적)
        sym_start = max(target_start, onboard)
        if sym_start > target_end:
            per_tier["온전"] += 1
            continue
        need = set(months_between(sym_start, target_end))
        have = set(months_between(r.s, r.e))
        miss = sorted(need - have)
        gap_past = r.s > sym_start
        gap_recent = r.e < target_end - timedelta(days=3)
        key = ("양쪽 결손" if gap_past and gap_recent else
               "과거만 결손" if gap_past else
               "최근만 결손" if gap_recent else "온전")
        per_tier[key] += 1
        # 결손 일수 (월 단위 근사 대신 실제 날짜 차)
        miss_days = 0
        if gap_past:
            miss_days += (r.s - sym_start).days
        if gap_recent:
            miss_days += (target_end - r.e).days
        total_missing_months += len(miss)
        total_missing_days += miss_days
        if miss:
            detail.append((r.symbol, str(r.s), str(r.e), len(miss), miss_days))

    dl_bytes = total_missing_months * avg_zip
    new_rows = total_missing_days * 1440
    db_growth = new_rows * bytes_per_row

    print()
    print("=" * 74)
    print(f"백필 견적 — 목표 구간 {target_start} ~ {target_end}")
    print("=" * 74)
    print(f"  대상 종목            {len(liquid)} (유동성 통과)")
    print(f"  상장일 보정          적용 (미확보 {no_listing}종목은 보유시작을 하한)")
    for k, v in per_tier.items():
        print(f"    {k:12s} {v}")
    print(f"  결손 월 합계          {total_missing_months:,} 종목·월")
    print(f"  결손 일수 합계        {total_missing_days:,} 종목·일")
    print(f"  다운로드 용량         {dl_bytes/1e9:.2f} GB  (월 zip 평균 {avg_zip/1e6:.2f} MB)")
    print(f"  삽입 행수             {new_rows:,} 행")
    print(f"  DB 증가 (인덱스 포함)  {db_growth/1e9:.2f} GB")
    print(f"  현재 DB               {size_row.bytes/1e9:.2f} GB → 예상 "
          f"{(size_row.bytes+db_growth)/1e9:.2f} GB")
    print()
    print("  결손 상위 15종목 (종목, 보유시작, 보유종료, 결손월, 결손일)")
    for d in sorted(detail, key=lambda x: -x[4])[:15]:
        print(f"    {d[0]:11s} {d[1]} ~ {d[2]}  {d[3]:3d}월  {d[4]:5d}일")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
