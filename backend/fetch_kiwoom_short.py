"""
키움 ka10014 (공매도추이요청) — 종목 일별 공매도 데이터 fetch.

Output: 일별 공매도량 / 매매비중 / 공매도평균가 등.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from app.core.token_manager import KiwoomTokenManager
from app.core.http_client import HttpClientManager
from app.core import security
from app.core.trading_env import get_api_url, env_from_string
from app.db.session import SessionLocal
from app.models.user import User
from app.models.account import ExchangeAccount
from app.adapters.kiwoom_real import _rate_limited_post


def get_creds():
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
        env = env_from_string(ea.environment or "real")
        return {
            "app_key": security.decrypt_key(ea.encrypted_access_key),
            "secret_key": security.decrypt_key(ea.encrypted_secret_key),
            "api_url": get_api_url(env),
        }
    finally:
        db.close()


async def fetch_short_history(symbol: str, start: str, end: str, max_pages: int = 10):
    creds = get_creds()
    HttpClientManager.get_instance()
    tm = KiwoomTokenManager.get_instance()
    token = await tm.get_token(creds["app_key"], creds["secret_key"], creds["api_url"])
    print(f"Token OK")

    url = f"{creds['api_url']}/api/dostk/shsa"
    base_headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "api-id": "ka10014",
    }
    payload = {
        "stk_cd": symbol,
        "tm_tp": "1",   # 1: 기간
        "strt_dt": start,
        "end_dt": end,
    }

    all_rows = []
    cont_yn = None
    next_key = None
    page = 0
    while page < max_pages:
        page += 1
        headers = {**base_headers}
        if cont_yn == "Y" and next_key:
            headers["cont-yn"] = "Y"
            headers["next-key"] = next_key

        resp = await _rate_limited_post(url, headers=headers, json=payload, timeout=15.0)
        if resp.status_code != 200:
            print(f"[page {page}] HTTP {resp.status_code}")
            break

        data = resp.json()
        if data.get("return_code") != 0:
            print(f"[page {page}] API error: {data.get('return_msg')}")
            break

        rows = data.get("shrts_trnsn", []) or []
        if not rows:
            break

        all_rows.extend(rows)
        cont_yn = resp.headers.get("cont-yn", "")
        next_key = resp.headers.get("next-key", "")
        print(
            f"[page {page}] rows={len(rows)} total={len(all_rows)} "
            f"first_dt={rows[0].get('dt')} last_dt={rows[-1].get('dt')} "
            f"cont={cont_yn}"
        )
        if cont_yn != "Y" or not next_key:
            break

    return all_rows


def parse_int(s):
    if not s:
        return 0
    try:
        return int(str(s).replace("+", "").replace(",", "").replace("-", ""))
    except (ValueError, AttributeError):
        return 0


def parse_float(s):
    if not s:
        return 0.0
    try:
        return float(str(s).replace("+", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--start", default="2025-11-14")
    p.add_argument("--end", default=None)
    p.add_argument("--output", required=True)
    args = p.parse_args()

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    start_str = args.start.replace("-", "")
    end_str = end.replace("-", "")
    print(f"Fetch short data: {args.symbol} {start_str} ~ {end_str}")

    started = datetime.now()
    rows = await fetch_short_history(args.symbol, start_str, end_str)
    elapsed = (datetime.now() - started).total_seconds()

    if not rows:
        print("ERROR: no data")
        sys.exit(1)

    cleaned = []
    for r in rows:
        dt = r.get("dt", "")
        if not dt or len(dt) != 8:
            continue
        cleaned.append({
            "dt": f"{dt[:4]}-{dt[4:6]}-{dt[6:8]}",
            "close": parse_int(r.get("close_pric")),
            "trde_qty": parse_int(r.get("trde_qty")),       # 거래량
            "shrts_qty": parse_int(r.get("shrts_qty")),     # 공매도량
            "ovr_shrts_qty": parse_int(r.get("ovr_shrts_qty")),  # 누적 공매도량
            "trde_wght": parse_float(r.get("trde_wght")),   # 매매비중 (공매도/거래량 %)
            "shrts_trde_prica": parse_int(r.get("shrts_trde_prica")),
            "shrts_avg_pric": parse_int(r.get("shrts_avg_pric")),
        })
    cleaned.sort(key=lambda x: x["dt"])

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in cleaned:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== DONE ===")
    print(f"  rows: {len(cleaned)}")
    print(f"  range: {cleaned[0]['dt']} ~ {cleaned[-1]['dt']}")
    print(f"  output: {out}")
    print(f"  elapsed: {elapsed:.1f}s")

    # 기본 통계
    import numpy as np
    sh = np.array([r["shrts_qty"] for r in cleaned])
    wt = np.array([r["trde_wght"] for r in cleaned])
    print(f"\n=== Short volume stats ===")
    print(f"  mean: {sh.mean():.0f}, std: {sh.std():.0f}")
    print(f"  min: {sh.min()}, max: {sh.max()}")
    print(f"  zero days: {(sh == 0).sum()}/{len(sh)} ({(sh == 0).mean()*100:.1f}%)")
    print(f"\n=== Short trade weight (%) stats ===")
    print(f"  mean: {wt.mean():.2f}%, std: {wt.std():.2f}%")
    print(f"  max: {wt.max():.2f}%, min: {wt.min():.2f}%")
    print(f"  high days (>10%): {(wt > 10).sum()}, very high (>20%): {(wt > 20).sum()}")


if __name__ == "__main__":
    asyncio.run(main())
