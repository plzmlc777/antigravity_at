"""키움 ka10059 (종목별투자자기관별차트요청) 백필.

여러 종목에 대해 가장 최신 일자부터 과거 방향으로 페이지네이션하면서
investor_flow_daily 테이블에 ON CONFLICT DO NOTHING 으로 insert.

- amt_qty_tp = '1' (금액), unit_tp = '1000' → 단위는 백만원
- trde_tp = '0' (순매수)
- API endpoint: /api/dostk/stkinfo, list_key: stk_invsr_orgn
- ka10059 응답 단위 검증 (acc_trde_prica 백만원) 완료

Usage:
    python3 fetch_kiwoom_investor_flow.py --symbols 005930,122630,061090 \
        --start-dt 20260430 --min-dt 20250502
"""
import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.core.token_manager import KiwoomTokenManager
from app.core.http_client import HttpClientManager
from app.core import security
from app.core.trading_env import get_api_url, env_from_string
from app.db.session import SessionLocal, engine
from app.models.user import User  # noqa: F401 — needed for SQLAlchemy mapper
from app.models.account import ExchangeAccount
from app.adapters.kiwoom_real import _rate_limited_post


def _signed_int(v):
    """Kiwoom returns numbers as strings with optional +/- sign. Convert to int."""
    if v is None or v == "":
        return None
    try:
        s = str(v).strip()
        return int(s)
    except (ValueError, TypeError):
        return None


def _abs_int(v):
    """For values that are conceptually unsigned (price, volume) but Kiwoom may return with sign chars."""
    n = _signed_int(v)
    return abs(n) if n is not None else None


def get_credentials():
    db = SessionLocal()
    try:
        ea = (
            db.query(ExchangeAccount)
            .filter(ExchangeAccount.exchange_name.ilike("%kiwoom%"))
            .filter(ExchangeAccount.is_disabled == False)
            .filter(ExchangeAccount.environment == "real")
            .order_by(ExchangeAccount.id.desc())
            .first()
        )
        if not ea:
            return None
        env = env_from_string(ea.environment or "real")
        return {
            "app_key": security.decrypt_key(ea.encrypted_access_key),
            "secret_key": security.decrypt_key(ea.encrypted_secret_key),
            "api_url": get_api_url(env),
            "ea_name": ea.account_name,
        }
    finally:
        db.close()


async def fetch_one_page(base_url, token, symbol, dt_str, cont_yn=None, next_key=None):
    url = f"{base_url}/api/dostk/stkinfo"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "api-id": "ka10059",
    }
    if cont_yn == "Y" and next_key:
        headers["cont-yn"] = "Y"
        headers["next-key"] = next_key
    payload = {
        "dt": dt_str,
        "stk_cd": symbol,
        "amt_qty_tp": "1",
        "trde_tp": "0",
        "unit_tp": "1000",
    }
    resp = await _rate_limited_post(url, headers=headers, json=payload, timeout=15.0)
    return resp


def parse_item(symbol, it):
    """Map ka10059 item (one day) to investor_flow_daily row."""
    dt_str = it.get("dt")
    if not dt_str or len(dt_str) != 8:
        return None
    try:
        date = datetime.strptime(dt_str, "%Y%m%d").date()
    except ValueError:
        return None
    return {
        "symbol": symbol,
        "date": date,
        "close_price": _abs_int(it.get("cur_prc")),
        "acc_trade_value": _abs_int(it.get("acc_trde_prica")),
        "individual_net": _signed_int(it.get("ind_invsr")),
        "foreign_net": _signed_int(it.get("frgnr_invsr")),
        "institutional_net": _signed_int(it.get("orgn")),
        "fin_inv_net": _signed_int(it.get("fnnc_invt")),
        "insurance_net": _signed_int(it.get("insrnc")),
        "trust_net": _signed_int(it.get("invtrt")),
        "etc_fin_net": _signed_int(it.get("etc_fnnc")),
        "bank_net": _signed_int(it.get("bank")),
        "pension_net": _signed_int(it.get("penfnd_etc")),
        "private_fund_net": _signed_int(it.get("samo_fund")),
        "govt_net": _signed_int(it.get("natn")),
        "corp_net": _signed_int(it.get("etc_corp")),
        "natfor_net": _signed_int(it.get("natfor")),
    }


async def backfill_symbol(base_url, token, symbol, start_dt, min_dt, max_pages=50):
    """Fetch ka10059 for symbol from start_dt backwards until min_dt.
    Returns list of parsed rows."""
    rows = []
    seen_dates = set()
    cont_yn = None
    next_key = None
    page = 0
    while page < max_pages:
        page += 1
        try:
            resp = await fetch_one_page(base_url, token, symbol, start_dt, cont_yn, next_key)
        except Exception as e:
            print(f"  [{symbol}/page {page}] HTTP exception: {e}", flush=True)
            break
        if resp.status_code != 200:
            print(f"  [{symbol}/page {page}] HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
            break
        body = resp.json()
        if body.get("return_code") != 0:
            print(f"  [{symbol}/page {page}] API err: {body.get('return_msg')}", flush=True)
            break
        items = body.get("stk_invsr_orgn") or []
        if not items:
            print(f"  [{symbol}/page {page}] empty list, stop.", flush=True)
            break
        page_min_dt = "99999999"
        page_max_dt = "00000000"
        page_added = 0
        hit_min = False
        for it in items:
            row = parse_item(symbol, it)
            if not row:
                continue
            d_str = row["date"].strftime("%Y%m%d")
            if d_str < page_min_dt:
                page_min_dt = d_str
            if d_str > page_max_dt:
                page_max_dt = d_str
            if d_str < min_dt:
                hit_min = True
                continue
            if row["date"] not in seen_dates:
                rows.append(row)
                seen_dates.add(row["date"])
                page_added += 1
        cont_yn = resp.headers.get("cont-yn", "")
        next_key = resp.headers.get("next-key", "")
        print(
            f"  [{symbol}/page {page:>2}] items={len(items)} added={page_added} "
            f"range={page_min_dt}~{page_max_dt} cont={cont_yn} total={len(rows)}",
            flush=True,
        )
        if hit_min:
            print(f"  [{symbol}] reached min_dt={min_dt}, stop.", flush=True)
            break
        if cont_yn != "Y" or not next_key:
            print(f"  [{symbol}] no continuation, stop.", flush=True)
            break
    return rows


def insert_rows(rows):
    """Bulk insert with ON CONFLICT DO NOTHING (idempotent)."""
    if not rows:
        return 0
    insert_sql = text(
        """
        INSERT INTO investor_flow_daily
          (symbol, date, close_price, acc_trade_value,
           individual_net, foreign_net, institutional_net,
           fin_inv_net, insurance_net, trust_net, etc_fin_net,
           bank_net, pension_net, private_fund_net,
           govt_net, corp_net, natfor_net,
           unit, source, created_at)
        VALUES
          (:symbol, :date, :close_price, :acc_trade_value,
           :individual_net, :foreign_net, :institutional_net,
           :fin_inv_net, :insurance_net, :trust_net, :etc_fin_net,
           :bank_net, :pension_net, :private_fund_net,
           :govt_net, :corp_net, :natfor_net,
           '백만원', 'kiwoom_ka10059', NOW())
        ON CONFLICT (symbol, date) DO NOTHING
        """
    )
    with engine.begin() as conn:
        conn.execute(insert_sql, rows)
    return len(rows)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="comma-separated symbol codes")
    p.add_argument("--start-dt", default=datetime.now().strftime("%Y%m%d"), help="YYYYMMDD (latest)")
    p.add_argument("--min-dt", required=True, help="YYYYMMDD (earliest, inclusive)")
    p.add_argument("--max-pages", type=int, default=50)
    args = p.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    print(f"Symbols: {symbols}")
    print(f"Range: {args.min_dt} ~ {args.start_dt}")

    creds = get_credentials()
    if not creds:
        print("ERROR: no kiwoom credentials", file=sys.stderr)
        sys.exit(1)
    print(f"EA: {creds['ea_name']}  URL: {creds['api_url']}")

    HttpClientManager.get_instance()
    tm = KiwoomTokenManager.get_instance()
    token = await tm.get_token(creds["app_key"], creds["secret_key"], creds["api_url"])
    if not token:
        print("ERROR: token issue", file=sys.stderr)
        sys.exit(1)
    print(f"Token OK (len={len(token)})")

    grand_total = 0
    for sym in symbols:
        print(f"\n=== {sym} ===")
        started = datetime.now()
        rows = await backfill_symbol(creds["api_url"], token, sym, args.start_dt, args.min_dt, args.max_pages)
        print(f"  fetched {len(rows)} rows, inserting...")
        n_ins = insert_rows(rows)
        elapsed = (datetime.now() - started).total_seconds()
        print(f"  DONE {sym}: {n_ins} inserted, elapsed={elapsed:.1f}s")
        grand_total += n_ins

    print(f"\nGrand total inserted: {grand_total} rows")


if __name__ == "__main__":
    asyncio.run(main())
