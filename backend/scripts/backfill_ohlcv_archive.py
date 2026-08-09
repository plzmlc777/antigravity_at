"""Download 1m kline archives from data.binance.vision for Binance Futures USDT-perp,
parse, and INSERT into the ohlcv table (idempotent ON CONFLICT DO NOTHING).

URL pattern:
  https://data.binance.vision/data/futures/um/daily/klines/{SYMBOL}/1m/{SYMBOL}-1m-YYYY-MM-DD.zip

CSV columns:
  open_time, open, high, low, close, volume, close_time, quote_volume,
  count, taker_buy_volume, taker_buy_quote_volume, ignore

(open_time is in milliseconds UTC.)

Usage:
  # 고정 목록 + 고정 일수 (기존 방식, 유지)
  python3 -m scripts.backfill_ohlcv_archive --symbols BNBUSDT,XRPUSDT --days 800

  # 자기치유 모드 (2026-08-09 신설, 권장) — 거래소에서 유니버스를 받아
  # 종목별로 DB 가 어디서 끊겼는지 보고 그만큼만 채운다
  python3 -m scripts.backfill_ohlcv_archive --universe-min-vol 5000000 --auto-gap

왜 자기치유 모드가 필요한가 (2026-08-09)
----------------------------------------
`--symbols` 하드코딩 목록이 **세 번 연속 같은 사고를 냈다**:
  2026-05-13  14개 세션이 마지막 봉에서 정지 (목록에 없던 종목)
  2026-07-11  16/26 세션 정지 — ADA/BCH/BNB/FIL/LTC/NEAR/WIF/XRP 누락
  2026-08-09  DB 1m 214종목 중 168개가 2026-05-12 에 멈춤. 유동성 통과
              132종목 중 과거 온전+최신인 종목이 **12개뿐**이었고,
              그 substrate 로 내린 3군 판정들이 위조됐다 (paradigm 251 은
              decay_ratio 0.138 로 GRAVEYARD → 재판정 0.481 PASS 반전).
목록을 손으로 늘리는 건 매번 사후 대응이고, 신규 상장이 생기면 또 뚫린다.
그래서 두 가지를 바꿨다:
  1. 유니버스를 거래소 exchangeInfo + 24h 거래대금에서 **매번 새로 받는다**
  2. 일수를 고정하지 않고 **종목별 DB 마지막 봉**부터 채운다 (자기치유)
이러면 어떤 종목이 며칠 밀려 있어도 다음 실행에서 스스로 복구된다.
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal, engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_ohlcv_archive")

ARCHIVE_BASE = "https://data.binance.vision/data/futures/um/daily/klines"
EXCHANGE_INFO = "https://fapi.binance.com/fapi/v1/exchangeInfo"
TICKER_24H = "https://fapi.binance.com/fapi/v1/ticker/24hr"

# 자기치유 모드 기본값
DEFAULT_OVERLAP_DAYS = 2      # 아카이브 늦은 게시 대비 (ON CONFLICT 로 멱등)
DEFAULT_MAX_DAYS = 150        # 일 배치가 폭주하지 않도록 종목당 상한
DEFAULT_NEW_SYMBOL_DAYS = 30  # DB 에 데이터가 없는 신규 종목의 초기 확보 일수
KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "count",
    "taker_buy_volume", "taker_buy_quote_volume", "ignore",
]


def resolve_universe(min_quote_vol: float, timeout: float = 30.0) -> list[str]:
    """거래소에서 USDT 무기한 계약 유니버스를 받아 24h 거래대금으로 거른다.

    DB 상태에 의존하지 않는다 — DB 가 비어 있거나 낡아도 올바른 목록이 나와야
    한다. 신규 상장은 자동으로 포함된다.
    """
    ses = requests.Session()
    ses.headers.update({"User-Agent": "Mozilla/5.0"})
    info = ses.get(EXCHANGE_INFO, timeout=timeout).json()
    tradable = {
        s["symbol"] for s in info.get("symbols", [])
        if s.get("contractType") == "PERPETUAL"
        and s.get("status") == "TRADING"
        and s.get("quoteAsset") == "USDT"
    }
    tickers = ses.get(TICKER_24H, timeout=timeout).json()
    out = []
    for t in tickers:
        sym = t.get("symbol")
        if sym not in tradable:
            continue
        try:
            qv = float(t.get("quoteVolume") or 0.0)
        except (TypeError, ValueError):
            continue
        if qv >= min_quote_vol:
            out.append(sym)
    log.info("유니버스: 거래가능 %d종목 → 24h 거래대금 >= $%s 필터 후 %d종목",
             len(tradable), f"{min_quote_vol:,.0f}", len(out))
    return sorted(out)


def db_symbols() -> list[str]:
    """DB 에 이미 있는 1m 종목 전체.

    왜 필요한가 — 라이브 유니버스(현재 24h 거래대금 기준)만 갱신하면, 과거엔
    유동했으나 지금 얇아진 종목이 DB 안에서 영구 정지 상태로 남는다. 그러면
    두 가지가 동시에 나빠진다:
      1. 그걸 섞어 쓰는 횡단면은 정지 시점에 구성이 축소되는 아티팩트를 얻는다
         (2026-08-09 paradigm 251 검정에서 실제로 132 → 32 축소가 관측됐다)
      2. 반대로 최신 종목만 쓰면 **생존편향** — 얇아져 죽은 종목을 빼는 셈이라
         수익률이 위로 편향된다
    DB 에 있는 건 전부 최신으로 유지하고, 유동성 판단은 연구 시점에 한다.

    상장폐지 종목은 아카이브에 이후 데이터가 없어 그냥 빈 결과가 온다(무해).
    다만 매일 헛질의하게 되므로 이 옵션은 **일 배치가 아니라 일회성 catch-up**
    용도다 — 일 배치는 라이브 유니버스만 본다.
    """
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT DISTINCT symbol FROM ohlcv WHERE time_frame='1m'")).fetchall()
        return sorted(r[0] for r in rows)
    finally:
        db.close()


def db_last_bar(symbol: str):
    """DB 에 있는 마지막 1m 봉의 날짜. 없으면 None."""
    db = SessionLocal()
    try:
        return db.execute(text(
            "SELECT max(timestamp)::date FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m'"), {"s": symbol}).scalar()
    finally:
        db.close()


def db_first_bar(symbol: str):
    """DB 에 있는 첫 1m 봉의 날짜. 없으면 None."""
    db = SessionLocal()
    try:
        return db.execute(text(
            "SELECT min(timestamp)::date FROM ohlcv "
            "WHERE symbol=:s AND time_frame='1m'"), {"s": symbol}).scalar()
    finally:
        db.close()


def load_listing_dates() -> dict:
    """상장일. 상장 전 구간을 요청하면 아카이브가 404 만 주므로 하한으로 쓴다."""
    import json
    p = ROOT / "runs" / "research_track" / "lifecycle_phase" / "listing_dates.json"
    if not p.exists():
        log.warning("상장일 파일 없음 — 과거 백필이 상장 전 구간을 헛질의할 수 있다")
        return {}
    raw = json.loads(p.read_text())
    out = {}
    for sym, v in raw.items():
        od = (v or {}).get("onboard_date")
        if od:
            out[sym] = datetime.strptime(od, "%Y-%m-%d").date()
    return out


def past_range(symbol: str, past_start, listings: dict, overlap_days: int = 1):
    """과거 방향 결손 구간 — (past_start ~ DB 첫 봉) 을 채운다.

    `--auto-gap` 은 마지막 봉부터 **앞으로만** 채우므로 잘려나간 과거를 복구하지
    못한다. BTCUSDT 가 2026-03-21 부터만 있어 150일 warmup 이 필요한 패러다임이
    구조적으로 발화하지 못한 것이 이 결손 때문이다 (2026-08-09 규명).

    상장일 하한을 적용한다 — 상장 전 구간은 애초에 존재하지 않는다.
    """
    first = db_first_bar(symbol)
    lower = past_start
    ob = listings.get(symbol)
    if ob is not None and ob > lower:
        lower = ob
    if first is None:
        return None                      # 데이터가 아예 없으면 auto-gap 이 담당
    upper = first - timedelta(days=1) + timedelta(days=overlap_days)
    if lower > upper:
        return None                      # 이미 충분히 과거를 갖고 있다
    return lower, upper, f"{(upper - lower).days + 1}일 (과거)"


def gap_range(symbol: str, end_date, overlap_days: int, max_days: int,
              new_symbol_days: int):
    """종목별로 채워야 할 (start, end). 자기치유의 핵심.

    DB 마지막 봉에서 overlap 만큼 뒤로 물러나 시작한다. 이미 최신이면 None.
    """
    last = db_last_bar(symbol)
    if last is None:
        start = end_date - timedelta(days=new_symbol_days - 1)
        return start, end_date, "신규"
    start = last - timedelta(days=overlap_days)
    if start > end_date:
        return None
    gap = (end_date - start).days + 1
    if gap <= 0:
        return None
    if gap > max_days:
        # 상한을 넘으면 최근 max_days 만 — 나머지는 다음 실행이 이어받는다.
        start = end_date - timedelta(days=max_days - 1)
        return start, end_date, f"상한적용({gap}일 중 {max_days}일)"
    return start, end_date, f"{gap}일"


def _archive_url(symbol: str, date) -> str:
    return f"{ARCHIVE_BASE}/{symbol}/1m/{symbol}-1m-{date.isoformat()}.zip"


def _parse_zip(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        names = z.namelist()
        if not names:
            return pd.DataFrame()
        with z.open(names[0]) as fh:
            # Some zips include a header row, some don't. Try both.
            data = fh.read()
            head_text = data[:200].decode("utf-8", errors="replace").lower()
            has_header = "open_time" in head_text or "open" in head_text.split(",")[0]
            df = pd.read_csv(io.BytesIO(data),
                             names=KLINE_COLUMNS,
                             header=0 if has_header else None)
    if df.empty:
        return df
    return df


def _fetch_one(symbol: str, date, session: requests.Session, retries: int = 2):
    url = _archive_url(symbol, date)
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None  # not yet uploaded / weekend skip
            r.raise_for_status()
            return _parse_zip(r.content)
        except Exception as e:
            if attempt == retries:
                log.warning("Failed %s: %s", url, e)
                return None
            time.sleep(1.0 * (attempt + 1))
    return None


def download_klines_range(symbol: str, start_date, end_date, parallel: int = 16) -> pd.DataFrame:
    days = (end_date - start_date).days + 1
    if days <= 0:
        return pd.DataFrame()
    target = [start_date + timedelta(days=i) for i in range(days)]
    log.info("[%s] downloading %d days", symbol, days)
    frames = []
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futures = {ex.submit(_fetch_one, symbol, d, session): d for d in target}
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_values("open_time")
    return out


def insert_to_db(symbol: str, df: pd.DataFrame) -> int:
    """Bulk insert via COPY FROM into a temp table, then INSERT ... ON CONFLICT DO NOTHING.

    ~100x faster than row-by-row executemany on 1M rows.
    """
    if df.empty:
        return 0
    out = pd.DataFrame({
        "symbol": symbol,
        "time_frame": "1m",
        "timestamp": pd.to_datetime(df["open_time"].astype("int64"), unit="ms"),
        "open": df["open"].astype(float),
        "high": df["high"].astype(float),
        "low": df["low"].astype(float),
        "close": df["close"].astype(float),
        "volume": df["volume"].astype(float),
    })
    csv_buf = io.StringIO()
    out.to_csv(csv_buf, index=False, header=False)
    csv_buf.seek(0)

    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            cur.execute("""
                CREATE TEMP TABLE _tmp_ohlcv (
                    symbol VARCHAR(50),
                    time_frame VARCHAR(10),
                    timestamp TIMESTAMP,
                    open DOUBLE PRECISION,
                    high DOUBLE PRECISION,
                    low DOUBLE PRECISION,
                    close DOUBLE PRECISION,
                    volume DOUBLE PRECISION
                ) ON COMMIT DROP
            """)
            cur.copy_expert(
                "COPY _tmp_ohlcv (symbol,time_frame,timestamp,open,high,low,close,volume) "
                "FROM STDIN WITH (FORMAT CSV)",
                csv_buf,
            )
            cur.execute("""
                INSERT INTO ohlcv (symbol, time_frame, timestamp, open, high, low, close, volume)
                SELECT symbol, time_frame, timestamp, open, high, low, close, volume
                FROM _tmp_ohlcv
                ON CONFLICT (symbol, time_frame, timestamp) DO NOTHING
            """)
        raw.commit()
    finally:
        raw.close()
    return len(out)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default=None,
                   help="쉼표 구분 목록. --universe-min-vol 과 함께 쓰면 합집합.")
    p.add_argument("--universe-min-vol", type=float, default=None,
                   help="거래소에서 유니버스를 받아 24h 거래대금(USD)으로 필터")
    p.add_argument("--auto-gap", action="store_true",
                   help="종목별 DB 마지막 봉부터 채운다 (--days 무시)")
    p.add_argument("--past-start", default=None,
                   help="과거 방향 백필 — 이 날짜까지 DB 첫 봉 앞을 채운다 "
                        "(예 2021-01-01). 상장일 하한 자동 적용")
    p.add_argument("--include-db-symbols", action="store_true",
                   help="DB 에 이미 있는 종목 전체를 대상에 합친다. 일회성 "
                        "catch-up 용 — 일 배치에는 쓰지 않는다 (db_symbols 주석 참조)")
    p.add_argument("--days", type=int, default=800)
    p.add_argument("--end-date", default=None)
    p.add_argument("--parallel", type=int, default=16)
    p.add_argument("--overlap-days", type=int, default=DEFAULT_OVERLAP_DAYS)
    p.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS,
                   help="auto-gap 종목당 상한 (초과분은 다음 실행이 이어받음)")
    p.add_argument("--new-symbol-days", type=int, default=DEFAULT_NEW_SYMBOL_DAYS)
    p.add_argument("--dry-run", action="store_true",
                   help="대상과 구간만 출력하고 다운로드하지 않는다")
    args = p.parse_args()

    end_date = (datetime.utcnow() - timedelta(days=1)).date() if args.end_date is None \
        else datetime.strptime(args.end_date, "%Y-%m-%d").date()

    syms = []
    if args.universe_min_vol is not None:
        syms.extend(resolve_universe(args.universe_min_vol))
    if args.include_db_symbols:
        dbs = db_symbols()
        log.info("DB 기존 종목 %d개 합침 (생존편향·구성변화 방지)", len(dbs))
        syms.extend(dbs)
    if args.symbols:
        syms.extend(s.strip().upper() for s in args.symbols.split(",") if s.strip())
    if not syms:
        log.error("--symbols 또는 --universe-min-vol 중 하나는 필요하다")
        return 2
    syms = sorted(set(syms))
    log.info("대상 %d종목 | end_date=%s | 모드=%s",
             len(syms), end_date, "auto-gap" if args.auto_gap else f"고정 {args.days}일")

    # 종목별 구간을 먼저 계산해 총량을 보고한다 (조용한 폭주 방지)
    plan = {}
    if args.past_start:
        past_start = datetime.strptime(args.past_start, "%Y-%m-%d").date()
        listings = load_listing_dates()
        log.info("과거 백필 모드 — %s 까지 | 상장일 %d종목 확보",
                 past_start, len(listings))
        skipped = 0
        for sym in syms:
            r = past_range(sym, past_start, listings, args.overlap_days)
            if r is None:
                skipped += 1
                continue
            plan[sym] = r
        total_days = sum((e - s0).days + 1 for s0, e, _ in plan.values())
        log.info("계획: %d종목 채움 / %d종목 불필요 | 합계 %s 종목·일",
                 len(plan), skipped, f"{total_days:,}")
        for sym, (s0, e0, why) in sorted(
                plan.items(), key=lambda kv: -((kv[1][1] - kv[1][0]).days))[:12]:
            log.info("  %-12s %s ~ %s  (%s)", sym, s0, e0, why)
    elif args.auto_gap:
        skipped = 0
        for sym in syms:
            g = gap_range(sym, end_date, args.overlap_days, args.max_days,
                          args.new_symbol_days)
            if g is None:
                skipped += 1
                continue
            plan[sym] = g
        total_days = sum((e - s).days + 1 for s, e, _ in plan.values())
        log.info("계획: %d종목 채움 / %d종목 이미 최신 | 합계 %s 종목·일",
                 len(plan), skipped, f"{total_days:,}")
        for sym, (s0, e0, why) in sorted(plan.items(), key=lambda kv: -( (kv[1][1]-kv[1][0]).days ))[:10]:
            log.info("  %-12s %s ~ %s  (%s)", sym, s0, e0, why)
    else:
        start_date = end_date - timedelta(days=args.days - 1)
        log.info("Range: %s ~ %s (%d days)", start_date, end_date, args.days)
        plan = {sym: (start_date, end_date, f"{args.days}일") for sym in syms}

    if args.dry_run:
        log.info("dry-run — 다운로드하지 않고 종료한다")
        return 0

    for sym in sorted(plan):
        start_date, end_date_sym, _why = plan[sym]
        # Check current row count first
        db = SessionLocal()
        try:
            n_before = db.execute(text("SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame='1m'"),
                                  {"s": sym}).scalar()
        finally:
            db.close()
        log.info("[%s] before: %s rows in DB", sym, f"{n_before:,}")

        t0 = time.time()
        df = download_klines_range(sym, start_date, end_date_sym, parallel=args.parallel)
        elapsed = time.time() - t0
        log.info("[%s] downloaded %s rows in %.1fs", sym, f"{len(df):,}", elapsed)

        if df.empty:
            log.warning("[%s] empty download result, skip insert", sym)
            continue

        t0 = time.time()
        n = insert_to_db(sym, df)
        elapsed = time.time() - t0
        log.info("[%s] insert %s rows in %.1fs", sym, f"{n:,}", elapsed)

        db = SessionLocal()
        try:
            n_after = db.execute(text("SELECT COUNT(*) FROM ohlcv WHERE symbol=:s AND time_frame='1m'"),
                                 {"s": sym}).scalar()
        finally:
            db.close()
        log.info("[%s] after: %s rows in DB (delta: +%s)", sym, f"{n_after:,}", f"{n_after - n_before:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
