#!/usr/bin/env python3
"""
키움 미국주식 순위정보 일일 스냅샷 수집기.

왜 매일 돌려야 하는가:
    순위 API 는 과거 시계열을 제공하지 않는다. 오늘 안 받으면 오늘 값은 영영
    없다. 여기서 모으는 3종은 미국 현지 데이터에 존재하지 않는 고유 substrate 다:

      kiwoom_trade    키움 거래 상위(ETF) — 한국 개인투자자 수급 쏠림
      day_disparity   주간거래 괴리율     — Blue Ocean 오버나이트 vs 정규장 종가
      consecutive     연속 상승/하락일수  — 서버측 계산 연속일

    나머지(trade_value / market_cap / turnover)는 유니버스 유지·유동성 필터용.

영업일 귀속:
    미국 정규장 마감 직후에 돌린다는 전제로, 스냅샷은 "마지막으로 열렸던
    영업일"에 귀속시킨다. 오버나이트가 진행 중이어도 순위 자체는 그날 장의
    결과이므로 일봉과 달리 미완결 배제를 적용하지 않는다 — 대신 collected_at
    으로 언제 찍었는지 남긴다.

멱등: (business_date, rank_type, symbol) 유니크 → 같은 날 재실행하면 갱신.

실행: cd backend && python -m scripts.collect_us_rank_snapshot [--dry-run]
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

import logging  # noqa: E402

from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.adapters.kiwoom_us import KiwoomUSAdapter, KiwoomUSError, _f  # noqa: E402
from app.core import security  # noqa: E402
from app.core.http_client import HttpClientManager  # noqa: E402
from app.core.us_trading_hours import is_trading_day, now_et  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.account import ExchangeAccount  # noqa: E402
from app.models.us_rank_snapshot import USRankSnapshot  # noqa: E402
from app.models.user import User  # noqa: E402,F401

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

RK_URL = "/api/us/rkinfo"

# (rank_type, api_id, 페이지수, 설명)
TARGETS = [
    ("kiwoom_trade",  "usa20881", 1, "키움 거래 상위(ETF) — 한국 개인 수급"),
    ("day_disparity", "usa24291", 4, "주간거래 괴리율 상위(ETF)"),
    ("consecutive",   "usa24161", 4, "연속 상승/하락(ETF)"),
    ("trade_value",   "usa20541", 5, "당일 거래대금 상위(ETF)"),
    ("market_cap",    "usa20551", 5, "시가총액 상위(ETF)"),
    ("turnover",      "usa24151", 4, "회전율 상위(ETF)"),
]


def target_business_date(now: datetime = None) -> date:
    """스냅샷을 귀속시킬 미국 영업일 = 마지막으로 열렸던 거래일."""
    et = now_et(now)
    d = et.date()
    # 프리마켓(04:00) 이전이면 아직 전날 장의 연장선 → 하루 뒤로
    if et.time() < __import__("datetime").time(4, 0):
        d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


async def build_adapter() -> KiwoomUSAdapter:
    db = SessionLocal()
    try:
        account = (
            db.query(ExchangeAccount)
            .filter(ExchangeAccount.exchange_name == "KiwoomUS").first()
        ) or (
            db.query(ExchangeAccount)
            .filter(ExchangeAccount.exchange_name == "Kiwoom",
                    ExchangeAccount.environment == "real").first()
        )
        if account is None:
            raise RuntimeError("키움 자격증명 계정을 찾을 수 없습니다")
        return KiwoomUSAdapter(
            app_key=security.decrypt_key(account.encrypted_access_key or ""),
            secret_key=security.decrypt_key(account.encrypted_secret_key or ""),
        )
    finally:
        db.close()


def normalize(row: dict, rank_type: str, api_id: str, bdate: date, seq: int) -> dict:
    """API 행 → 테이블 행. 공통 필드만 정규화하고 원본은 extra 에 보존."""
    return {
        "business_date": bdate,
        "rank_type": rank_type,
        "api_id": api_id,
        "rank": int(row["rank"]) if str(row.get("rank") or "").isdigit()
                else (int(row["kw_high_rank"]) if str(row.get("kw_high_rank") or "").isdigit() else seq),
        "symbol": (row.get("stk_cd") or "").strip().upper(),
        "stex_tp": row.get("stex_tp"),
        "name_kr": row.get("stk_nm"),
        "price": abs(_f(row.get("cur_prc"))) or None,
        "change_pct": _f(row.get("flu_rt")) or None,
        "volume": int(_f(row.get("acc_trde_qty"))) or None,
        "trade_value": _f(row.get("trde_prica")) or None,
        "market_cap": _f(row.get("mac")) or None,
        "extra": row,
    }


async def collect(adapter: KiwoomUSAdapter, rank_type: str, api_id: str,
                  pages: int, bdate: date) -> list:
    rows, cont_yn, next_key, seq = [], "N", "", 0
    for page in range(pages):
        try:
            data = await adapter._request(api_id, RK_URL, {}, cont_yn=cont_yn, next_key=next_key)
        except KiwoomUSError as e:
            print(f"  [{rank_type}] page {page} 실패: {e}")
            break
        key = next((k for k, v in data.items() if isinstance(v, list)), None)
        page_rows = (data.get(key) or []) if key else []
        for r in page_rows:
            seq += 1
            item = normalize(r, rank_type, api_id, bdate, seq)
            if item["symbol"]:
                rows.append(item)
        cont_yn, next_key = data.get("_cont_yn", "N"), data.get("_next_key", "")
        if cont_yn != "Y" or not page_rows:
            break
        await asyncio.sleep(0.15)

    # 같은 종목이 페이지 경계에서 중복되면 유니크 제약에 걸리므로 선착순 유지
    seen, uniq = set(), []
    for r in rows:
        if r["symbol"] in seen:
            continue
        seen.add(r["symbol"])
        uniq.append(r)
    return uniq


def upsert(rows: list) -> int:
    if not rows:
        return 0
    db = SessionLocal()
    try:
        stmt = insert(USRankSnapshot).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uix_us_rank_date_type_symbol",
            set_={
                "rank": stmt.excluded.rank,
                "price": stmt.excluded.price,
                "change_pct": stmt.excluded.change_pct,
                "volume": stmt.excluded.volume,
                "trade_value": stmt.excluded.trade_value,
                "market_cap": stmt.excluded.market_cap,
                "extra": stmt.excluded.extra,
                "collected_at": datetime.utcnow(),
            },
        )
        db.execute(stmt)
        db.commit()
        return len(rows)
    except Exception as e:
        db.rollback()
        print(f"  upsert 실패: {e}")
        return 0
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bdate = target_business_date()
    et = now_et()
    print(f"스냅샷 영업일 {bdate} (ET {et:%Y-%m-%d %H:%M})")

    async def run():
        await HttpClientManager.get_instance().start()
        try:
            adapter = await build_adapter()
            summary = {}
            for rank_type, api_id, pages, label in TARGETS:
                rows = await collect(adapter, rank_type, api_id, pages, bdate)
                n = len(rows) if args.dry_run else upsert(rows)
                summary[rank_type] = n
                print(f"  {rank_type:14} {api_id} {n:4}건  {label}")
            return summary
        finally:
            await HttpClientManager.get_instance().stop()

    summary = asyncio.run(run())
    total = sum(summary.values())
    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}총 {total}건")
    print(json.dumps({"business_date": str(bdate), "dry_run": args.dry_run,
                      "counts": summary, "total": total}, ensure_ascii=False))
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
