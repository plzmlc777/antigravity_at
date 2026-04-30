"""
키움 ka10059 (종목별투자자기관별요청)로 종목 일별 외국인/기관/개인 데이터 fetch.

Usage:
    cd backend && source venv/bin/activate
    python3 fetch_kiwoom_foreign.py --symbol 061090 --output /tmp/061090_foreign.jsonl
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
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


async def fetch_history(symbol: str, max_pages: int = 10):
    creds = get_creds()
    HttpClientManager.get_instance()
    tm = KiwoomTokenManager.get_instance()
    token = await tm.get_token(creds["app_key"], creds["secret_key"], creds["api_url"])
    print(f"Token OK")

    url = f"{creds['api_url']}/api/dostk/stkinfo"
    base_headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "api-id": "ka10059",
    }
    payload = {
        "dt": datetime.now().strftime("%Y%m%d"),
        "stk_cd": symbol,
        "amt_qty_tp": "2",  # 수량
        "trde_tp": "0",     # 순매수
        "unit_tp": "1",     # 단주
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

        rows = data.get("stk_invsr_orgn", []) or []
        if not rows:
            break

        all_rows.extend(rows)
        cont_yn = resp.headers.get("cont-yn", "")
        next_key = resp.headers.get("next-key", "")
        print(
            f"[page {page}] rows={len(rows)} total={len(all_rows)} "
            f"first_dt={rows[0].get('dt')} last_dt={rows[-1].get('dt')} "
            f"cont={cont_yn} next_key={next_key[:8]}"
        )
        if cont_yn != "Y" or not next_key:
            break

    return all_rows


def parse_int(s: str | None) -> int:
    """양수 부호도 제거하고 int 변환."""
    if not s:
        return 0
    try:
        return int(s.replace("+", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--output", required=True, help="JSONL output path")
    p.add_argument("--max-pages", type=int, default=10)
    args = p.parse_args()

    started = datetime.now()
    rows = await fetch_history(args.symbol, max_pages=args.max_pages)
    elapsed = (datetime.now() - started).total_seconds()

    if not rows:
        print("ERROR: no data fetched")
        sys.exit(1)

    # 정리: dt를 ISO date, 매매량을 int로
    cleaned = []
    for r in rows:
        cleaned.append({
            "dt": f"{r['dt'][:4]}-{r['dt'][4:6]}-{r['dt'][6:8]}",
            "close": parse_int(r.get("cur_prc")),
            "volume": parse_int(r.get("acc_trde_qty")),
            "value": parse_int(r.get("acc_trde_prica")),  # 누적거래대금 (천원 단위 추정)
            "ind": parse_int(r.get("ind_invsr")),         # 개인 순매수 (단주)
            "frgnr": parse_int(r.get("frgnr_invsr")),     # 외국인
            "orgn": parse_int(r.get("orgn")),             # 기관계
            "fnnc_invt": parse_int(r.get("fnnc_invt")),   # 금융투자
            "invtrt": parse_int(r.get("invtrt")),         # 투신
            "penfnd": parse_int(r.get("penfnd_etc")),     # 연기금
            "etc_corp": parse_int(r.get("etc_corp")),     # 기타법인
        })

    # 날짜 오름차순 정렬
    cleaned.sort(key=lambda x: x["dt"])

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        for r in cleaned:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== DONE ===")
    print(f"  rows: {len(cleaned)}")
    print(f"  range: {cleaned[0]['dt']} ~ {cleaned[-1]['dt']}")
    print(f"  output: {out_path}")
    print(f"  elapsed: {elapsed:.1f}s")

    # 샘플 통계
    import numpy as np
    fr = np.array([r["frgnr"] for r in cleaned])
    org = np.array([r["orgn"] for r in cleaned])
    print(f"\n=== Foreign net buy stats ===")
    print(f"  mean: {fr.mean():+.0f}, std: {fr.std():.0f}")
    print(f"  min: {fr.min()}, max: {fr.max()}")
    print(f"  positive days: {(fr > 0).sum()}/{len(fr)} ({(fr > 0).mean()*100:.1f}%)")
    print(f"\n=== Institutional net buy stats ===")
    print(f"  mean: {org.mean():+.0f}, std: {org.std():.0f}")
    print(f"  positive days: {(org > 0).sum()}/{len(org)} ({(org > 0).mean()*100:.1f}%)")


if __name__ == "__main__":
    asyncio.run(main())
