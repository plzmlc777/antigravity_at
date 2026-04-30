"""
키움 ka10080 (주식분봉차트조회요청) 연속조회로 단일 종목 분봉을 끝까지 fetch.

- 결과는 staging JSON 파일로 저장 (DB 직접 INSERT 안 함).
- Atomic DB swap은 별도 스크립트에서 수행.
- 토큰은 KiwoomTokenManager 통해 발급 (자동 refresh).
- rate limit은 어댑터의 _rate_limited_post 활용.

Usage:
    cd backend && source venv/bin/activate
    python3 fetch_kiwoom_minute_history.py --symbol 061090 \
        --interval 1 --max-pages 200 --staging /tmp/061090_1m_staging.jsonl
"""
import asyncio
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from app.core.token_manager import KiwoomTokenManager
from app.core.http_client import HttpClientManager
from app.core import security
from app.core.trading_env import get_api_url, env_from_string
from app.db.session import SessionLocal
from app.models.user import User
from app.models.account import ExchangeAccount
from app.adapters.kiwoom_real import _rate_limited_post


def get_active_real_credentials():
    """real(production) 활성 키움 계정 우선, 없으면 첫 활성 계정."""
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
            ea = (
                db.query(ExchangeAccount)
                .filter(ExchangeAccount.exchange_name.ilike("%kiwoom%"))
                .filter(ExchangeAccount.is_disabled == False)
                .first()
            )
        if not ea:
            return None
        env = env_from_string(ea.environment or "real")
        return {
            "ea_id": ea.id,
            "ea_name": ea.account_name,
            "environment": ea.environment,
            "app_key": security.decrypt_key(ea.encrypted_access_key),
            "secret_key": security.decrypt_key(ea.encrypted_secret_key),
            "api_url": get_api_url(env),
        }
    finally:
        db.close()


async def fetch_minute_history(
    symbol: str,
    interval: int,
    base_url: str,
    token: str,
    max_pages: int,
    staging_path: str,
):
    """
    ka10080 연속조회 루프.
    - 최신부터 과거 방향으로 페이지네이션
    - 한 페이지 = 한 응답 (보통 600~900 봉)
    - cont-yn=Y가 아니거나 next-key 비면 종료
    - 페이지마다 staging_path(JSONL)에 즉시 append (중간 실패 대비)
    """
    url = f"{base_url}/api/dostk/chart"
    cont_yn = None
    next_key = None
    page = 0
    total_bars = 0
    earliest_ts = None
    latest_ts = None

    # staging file 초기화 (truncate)
    with open(staging_path, "w") as f:
        pass

    while page < max_pages:
        page += 1
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": "ka10080",
        }
        if cont_yn == "Y" and next_key:
            headers["cont-yn"] = "Y"
            headers["next-key"] = next_key

        payload = {
            "stk_cd": symbol,
            "tic_scope": str(interval),
            "upd_stkpc_tp": "1",
        }

        try:
            resp = await _rate_limited_post(url, headers=headers, json=payload, timeout=15.0)
        except Exception as e:
            print(f"[page {page}] HTTP exception: {e}", flush=True)
            break

        if resp.status_code != 200:
            print(f"[page {page}] HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
            break

        data = resp.json()
        if data.get("return_code") != 0:
            print(f"[page {page}] API error: {data.get('return_msg')}", flush=True)
            break

        items = data.get("stk_min_pole_chart_qry", []) or []
        if not items:
            print(f"[page {page}] empty response, stop.", flush=True)
            break

        # 페이지 내 최소/최대 timestamp
        page_ts = [it.get("cntr_tm") for it in items if it.get("cntr_tm")]
        page_ts.sort()
        page_min = page_ts[0] if page_ts else "?"
        page_max = page_ts[-1] if page_ts else "?"

        if earliest_ts is None or page_min < earliest_ts:
            earliest_ts = page_min
        if latest_ts is None or page_max > latest_ts:
            latest_ts = page_max

        # JSONL append
        with open(staging_path, "a") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

        total_bars += len(items)

        cont_yn = resp.headers.get("cont-yn", "")
        next_key = resp.headers.get("next-key", "")

        print(
            f"[page {page:>3}] bars={len(items):>4} "
            f"page_range={page_min}~{page_max} "
            f"total={total_bars:>6} cont={cont_yn} next_key_len={len(next_key)}",
            flush=True,
        )

        if cont_yn != "Y" or not next_key:
            print(f"[page {page}] no continuation, stop.", flush=True)
            break

    return {
        "pages": page,
        "total_bars": total_bars,
        "earliest_ts": earliest_ts,
        "latest_ts": latest_ts,
        "staging_path": staging_path,
    }


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--interval", type=int, default=1, choices=[1, 3, 5, 10, 15, 30, 45, 60])
    p.add_argument("--max-pages", type=int, default=300, help="안전 상한 (필요시 증가)")
    p.add_argument("--staging", required=True, help="JSONL staging path")
    args = p.parse_args()

    creds = get_active_real_credentials()
    if not creds:
        print("ERROR: 활성 키움 계정 없음.", file=sys.stderr)
        sys.exit(1)
    print(f"EA={creds['ea_name']} ({creds['environment']}) URL={creds['api_url']}")

    HttpClientManager.get_instance()
    tm = KiwoomTokenManager.get_instance()
    token = await tm.get_token(creds["app_key"], creds["secret_key"], creds["api_url"])
    if not token:
        print("ERROR: 토큰 발급 실패", file=sys.stderr)
        sys.exit(1)
    print(f"토큰 발급 OK (len={len(token)})")
    print(
        f"FETCH symbol={args.symbol} interval={args.interval}m "
        f"max_pages={args.max_pages} staging={args.staging}"
    )
    started = datetime.now()
    result = await fetch_minute_history(
        args.symbol,
        args.interval,
        creds["api_url"],
        token,
        args.max_pages,
        args.staging,
    )
    elapsed = (datetime.now() - started).total_seconds()

    print()
    print("=" * 60)
    print(f"DONE pages={result['pages']} total_bars={result['total_bars']} "
          f"elapsed={elapsed:.1f}s")
    print(f"  range: {result['earliest_ts']} ~ {result['latest_ts']}")
    print(f"  staging: {result['staging_path']}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
