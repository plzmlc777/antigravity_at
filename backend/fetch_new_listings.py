"""
키움 REST API ka10099 (종목정보 리스트)를 호출하여
최근 N개월 이내 신규 상장 종목을 추출하는 독립 스크립트.

Usage:
    cd backend
    source venv/bin/activate
    python fetch_new_listings.py [--months 6] [--market kosdaq] [--json]
"""
import asyncio
import argparse
import json
import sys
import os
from datetime import datetime, timedelta

# Add parent path for app imports
sys.path.insert(0, os.path.dirname(__file__))

from app.core.config import settings
from app.core.token_manager import KiwoomTokenManager
from app.core.http_client import HttpClientManager
from app.core import security
from app.db.session import SessionLocal
from app.models.user import User  # Required for SQLAlchemy relationship resolution
from app.models.account import ExchangeAccount


MARKET_CODES = {
    "kospi": "0",
    "kosdaq": "10",
    "etf": "8",
    "konex": "50",
}


def get_first_account_credentials():
    """DB에서 첫 번째 활성 계정의 복호화된 credentials 반환"""
    db = SessionLocal()
    try:
        account = db.query(ExchangeAccount).filter(
            ExchangeAccount.is_disabled == False
        ).first()

        if not account:
            print("ERROR: DB에 활성화된 계정이 없습니다.")
            return None

        app_key = security.decrypt_key(account.encrypted_access_key)
        secret_key = security.decrypt_key(account.encrypted_secret_key)

        # Get API URL from trading environment
        from app.core.trading_env import get_api_url, env_from_string
        env = env_from_string(account.environment or "real")
        api_url = get_api_url(env)

        print(f"계정: {account.account_name} ({account.environment}) -> {api_url}")
        return {
            "app_key": app_key,
            "secret_key": secret_key,
            "api_url": api_url,
        }
    finally:
        db.close()


async def fetch_stock_list(base_url: str, token: str, market_type: str) -> list:
    """ka10099 종목정보 리스트 호출 (연속조회 포함)"""
    url = f"{base_url}/api/dostk/stkinfo"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": f"Bearer {token}",
        "api-id": "ka10099",
    }
    payload = {"mrkt_tp": market_type}

    client = HttpClientManager.get_instance().get_client()
    all_items = []
    cont_yn = None
    next_key = None
    page = 0

    while True:
        page += 1
        req_headers = {**headers}
        if cont_yn == "Y" and next_key:
            req_headers["cont-yn"] = "Y"
            req_headers["next-key"] = next_key

        resp = await client.post(url, headers=req_headers, json=payload)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("list", [])
        all_items.extend(items)
        print(f"  페이지 {page}: {len(items)}건 (누적: {len(all_items)}건)")

        # Check continuation
        cont_yn = resp.headers.get("cont-yn", data.get("cont-yn", ""))
        next_key = resp.headers.get("next-key", data.get("next-key", ""))

        if cont_yn != "Y" or not next_key:
            break

    return all_items


def filter_new_listings(items: list, months: int, stocks_only: bool = False) -> list:
    """regDay 기준으로 최근 N개월 이내 상장 종목 필터링 (SPAC 제외)"""
    cutoff = datetime.now() - timedelta(days=months * 30)
    cutoff_str = cutoff.strftime("%Y%m%d")

    # ETF/ETN/채권 등 제외를 위한 키워드
    EXCLUDE_KEYWORDS = [
        "TIGER", "KODEX", "RISE", "ACE", "SOL", "PLUS", "KoAct", "KIWOOM",
        "HANARO", "FOCUS", "WON", "BNK", "ITF", "TIME", "HK",
        "ETN", "ETF", "레버리지", "인버스", "채권", "액티브", "커버드콜",
        "선물", "X클래스", "1Q ", "마이티", "N2 ",
    ]

    result = []
    for item in items:
        reg_day = item.get("regDay", "")
        if not reg_day or len(reg_day) < 8:
            continue
        if reg_day < cutoff_str:
            continue
        # SPAC 제외
        name = item.get("name", "")
        if "스팩" in name or "SPAC" in name.upper():
            continue
        # ETF/ETN/채권 등 제외 (--stocks-only)
        if stocks_only and any(kw in name for kw in EXCLUDE_KEYWORDS):
            continue
        result.append(item)

    # Sort by listing date descending
    result.sort(key=lambda x: x.get("regDay", ""), reverse=True)
    return result


def format_date(d: str) -> str:
    if len(d) >= 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


async def main():
    parser = argparse.ArgumentParser(description="키움 API로 신규 상장 종목 조회")
    parser.add_argument("--months", type=int, default=6, help="최근 N개월 (기본: 6)")
    parser.add_argument("--market", type=str, default="kosdaq",
                        choices=list(MARKET_CODES.keys()),
                        help="시장 구분 (기본: kosdaq)")
    parser.add_argument("--all-markets", action="store_true",
                        help="코스피+코스닥 모두 조회")
    parser.add_argument("--json", action="store_true",
                        help="target_assets import 형식으로 JSON 출력")
    parser.add_argument("--json-file", type=str, default=None,
                        help="JSON을 파일로 저장 (경로 지정)")
    parser.add_argument("--stocks-only", action="store_true",
                        help="일반 주식만 (ETF/ETN/채권 제외)")
    args = parser.parse_args()

    # Get credentials from DB
    creds = get_first_account_credentials()
    if not creds:
        sys.exit(1)

    app_key = creds["app_key"]
    secret_key = creds["secret_key"]
    base_url = creds["api_url"]

    # Init HTTP client
    HttpClientManager.get_instance()

    # Get token
    token_mgr = KiwoomTokenManager.get_instance()
    token = await token_mgr.get_token(app_key, secret_key, base_url)
    if not token:
        print("ERROR: 토큰 발급 실패")
        sys.exit(1)
    print(f"토큰 발급 완료 (서버: {base_url})")

    # Determine markets to query
    markets = ["kospi", "kosdaq"] if args.all_markets else [args.market]

    all_new = []
    for market in markets:
        market_code = MARKET_CODES[market]
        print(f"\n[{market.upper()}] 종목 리스트 조회 중... (mrkt_tp={market_code})")

        items = await fetch_stock_list(base_url, token, market_code)
        print(f"  전체 종목 수: {len(items)}")

        new_items = filter_new_listings(items, args.months, stocks_only=args.stocks_only)
        print(f"  최근 {args.months}개월 신규 상장: {len(new_items)}개")

        for item in new_items:
            item["_market"] = market.upper()
        all_new.extend(new_items)

    # Sort all by date
    all_new.sort(key=lambda x: x.get("regDay", ""), reverse=True)

    if not all_new:
        print(f"\n최근 {args.months}개월 이내 신규 상장 종목이 없습니다.")
        return

    # Display table
    print(f"\n{'='*80}")
    print(f"최근 {args.months}개월 신규 상장 종목 ({len(all_new)}개)")
    print(f"{'='*80}")
    print(f"{'No':>3}  {'종목코드':<10} {'종목명':<20} {'상장일':<12} {'시장':<8} {'상태'}")
    print(f"{'-'*80}")

    for i, item in enumerate(all_new, 1):
        code = item.get("code", "")
        name = item.get("name", "")
        reg_day = format_date(item.get("regDay", ""))
        market = item.get("_market", "")
        state = item.get("state", "")
        audit = item.get("auditInfo", "")
        warning = ""
        if audit and audit != "정상":
            warning = f" [{audit}]"
        print(f"{i:>3}  {code:<10} {name:<20} {reg_day:<12} {market:<8} {state}{warning}")

    # JSON output
    if args.json or args.json_file:
        symbols = []
        for item in all_new:
            symbols.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
            })

        target_assets = {
            "type": "target_assets",
            "version": "1.0",
            "description": f"최근 {args.months}개월 신규 상장 종목 ({datetime.now().strftime('%Y-%m-%d')} 기준)",
            "symbols": symbols
        }

        json_str = json.dumps(target_assets, ensure_ascii=False, indent=2)

        if args.json_file:
            with open(args.json_file, "w", encoding="utf-8") as f:
                f.write(json_str)
            print(f"\nJSON 저장 완료: {args.json_file}")
        else:
            print(f"\n{'='*80}")
            print("Target Assets JSON:")
            print(f"{'='*80}")
            print(json_str)


if __name__ == "__main__":
    asyncio.run(main())
