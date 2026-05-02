"""ka10059 (종목별투자자기관별차트요청) 탐색.

Endpoint, payload field, response list_key, item field 을 결정한다.
1회 호출로 1년치 데이터 한 종목 응답을 받는 것이 목표.
"""
import asyncio
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from app.core.token_manager import KiwoomTokenManager
from app.core.http_client import HttpClientManager
from app.core import security
from app.core.trading_env import get_api_url, env_from_string
from app.db.session import SessionLocal
from app.models.user import User  # noqa: F401 — needed for SQLAlchemy mapper resolution
from app.models.account import ExchangeAccount
from app.adapters.kiwoom_real import _rate_limited_post


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


async def try_endpoint(endpoint, base_url, token, symbol, dt_str):
    url = f"{base_url}{endpoint}"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "api-id": "ka10059",
    }
    payload = {
        "dt": dt_str,           # 조회 일자 (가장 최신)
        "stk_cd": symbol,
        "amt_qty_tp": "1",      # 1: 금액
        "trde_tp": "0",         # 0: 순매수
        "unit_tp": "1000",      # 1000: 천주
    }
    try:
        resp = await _rate_limited_post(url, headers=headers, json=payload, timeout=15.0)
    except Exception as e:
        return {"endpoint": endpoint, "error": f"exception: {e}"}
    return {
        "endpoint": endpoint,
        "status": resp.status_code,
        "headers": dict(resp.headers),
        "body": resp.text[:5000],
    }


async def main():
    creds = get_credentials()
    if not creds:
        print("no kiwoom creds", file=sys.stderr)
        sys.exit(1)
    print(f"Using EA={creds['ea_name']} URL={creds['api_url']}")

    HttpClientManager.get_instance()
    tm = KiwoomTokenManager.get_instance()
    token = await tm.get_token(creds["app_key"], creds["secret_key"], creds["api_url"])
    if not token:
        print("token fail", file=sys.stderr)
        sys.exit(1)

    symbol = "005930"
    dt_str = "20260430"

    for ep in ["/api/dostk/chart", "/api/dostk/stkinfo", "/api/dostk/foinvsr", "/api/dostk/frgnistt"]:
        print(f"\n=== Try endpoint: {ep} ===")
        r = await try_endpoint(ep, creds["api_url"], token, symbol, dt_str)
        print(f"  status: {r.get('status')}")
        if r.get("status") == 200:
            try:
                body = json.loads(r["body"])
                print(f"  return_code: {body.get('return_code')}")
                print(f"  return_msg: {body.get('return_msg')}")
                # top-level keys
                print(f"  keys: {list(body.keys())}")
                # find list-like keys
                for k, v in body.items():
                    if isinstance(v, list):
                        print(f"    {k}: list of {len(v)}")
                        if v:
                            print(f"      sample[0]: {json.dumps(v[0], ensure_ascii=False)[:500]}")
                            break
                if r.get("status") == 200 and body.get("return_code") == 0:
                    print(f"\n  >>> SUCCESS endpoint: {ep}")
                    # dump full JSON to file for review
                    out = "/tmp/ka10059_probe.json"
                    with open(out, "w") as f:
                        json.dump(body, f, indent=2, ensure_ascii=False)
                    print(f"  full body saved: {out}")
                    return
            except Exception as e:
                print(f"  parse fail: {e}")
                print(f"  raw: {r['body'][:500]}")
        else:
            print(f"  body[:300]: {r.get('body', '')[:300]}")

    print("\nAll endpoints failed.")


if __name__ == "__main__":
    asyncio.run(main())
