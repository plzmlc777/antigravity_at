#!/usr/bin/env python3
"""
미국주식 Paper 계좌 생성 (exchange_name='KiwoomUS', environment='paper').

왜 필요한가:
    미국주식은 키움 모의투자 서버가 없고, 보유 중인 ISA 계좌는 해외증권 주문
    권한이 없다(ust21070 -> 508540). 대신 Paper 모드로 돌린다 — 체결은
    OrderExecutionService 가 시뮬레이션하고, 시세만 실서버(/api/us/*)에서 받는다.

자격증명:
    미국주식 API 는 국내와 동일한 앱키/시크릿으로 열린다(실측 확인). 기존
    실서버 Kiwoom 계정의 암호화 키를 그대로 복사한다 — 평문 노출 없음.

멱등: 이미 있으면 생성하지 않고 현재 상태만 출력한다.

실행: cd backend && python -m scripts.create_us_paper_account
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR.parent / ".env")

from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402,F401
from app.models.account import ExchangeAccount  # noqa: E402

ACCOUNT_NAME = "키움 미국 페이퍼"
SOURCE_ACCOUNT_NAME = "키움 ISA 2000"   # 앱키를 빌려올 실서버 계정
DEFAULT_SYMBOL = "AAPL"


def main() -> int:
    db = SessionLocal()
    try:
        existing = (
            db.query(ExchangeAccount)
            .filter(ExchangeAccount.exchange_name == "KiwoomUS")
            .first()
        )
        if existing:
            print(f"이미 존재: id={existing.id} name={existing.account_name} "
                  f"env={existing.environment} url={existing.api_url}")
            return 0

        source = (
            db.query(ExchangeAccount)
            .filter(
                ExchangeAccount.exchange_name == "Kiwoom",
                ExchangeAccount.environment == "real",
                ExchangeAccount.account_name == SOURCE_ACCOUNT_NAME,
            )
            .first()
        )
        if source is None:
            print(f"실패: 키 원본 계정('{SOURCE_ACCOUNT_NAME}')을 찾을 수 없습니다")
            return 1

        account = ExchangeAccount(
            user_id=source.user_id,
            exchange_name="KiwoomUS",
            account_name=ACCOUNT_NAME,
            encrypted_access_key=source.encrypted_access_key,
            encrypted_secret_key=source.encrypted_secret_key,
            environment="paper",
            account_number=None,     # Paper 는 계좌번호 불필요 (주문 미전송)
            last_symbol=DEFAULT_SYMBOL,
            saved_symbols=[
                {"code": "AAPL", "name": "애플"},
                {"code": "NVDA", "name": "엔비디아"},
                {"code": "MSFT", "name": "마이크로소프트"},
                {"code": "SPY", "name": "S&P 500 SPDR ETF"},
            ],
            is_disabled=False,
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        print(f"생성 완료: id={account.id} name={account.account_name}")
        print(f"  exchange={account.exchange_name} env={account.environment}")
        print(f"  api_url={account.api_url} (시세 전용, 주문은 Paper 시뮬레이션)")
        print(f"  is_paper={account.is_paper} is_simulation={account.is_simulation}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
