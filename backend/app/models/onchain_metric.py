"""온체인 지표 — CoinMetrics Community API 수집분.

왜 필요한가
    2026-08-15 에 가격 기반 접근이 다섯 번 기각됐다(신규상장·종목선별·성질선별·
    무차별규칙·횡단면모멘텀). 기억의 교훈 #77 이 그 진단을 이미 갖고 있다:
    "2024 alpha exogenous, endogenous reformulation 회피불가, **non-OHLCV
    substrate 전환 필요**".

    그리고 `Crypto factor zoo`(2026)가 36요인 중 알파를 흡수하는 핵심으로
    turnover volatility · bid-ask spread · **new-address-to-price** 를 꼽는다.
    마지막이 온체인이고 우리에게 없던 것이다.

출처 — **완전 무료·키 불필요**
    `community-api.coinmetrics.io` — 등록도 결제도 없다. 대표님 원칙
    (완전무료 + 공개데이터 + 자체수집, freemium 금지)에 맞는다.

    실측(2026-08-15): BTC 는 2011년부터, 한 번 요청에 3,147행(8.6년)이
    페이지네이션 없이 온다.

⚠ 커버리지가 우리 유니버스와 크게 어긋난다
    지원 17종 확인 · **SOL/AVAX/MATIC/ATOM/NEAR/FIL/SHIB/PEPE/WIF 없음**.
    일부는 갱신이 멈췄다(DOT 2022-06, BNB 2019-04). 우리 유동성 유니버스는
    190종이라 교집합이 작다. **이 한계를 모르고 쓰면 표본이 조용히 줄어든다.**

⚠ `market_cap` 과 `supply` 가 특히 값지다
    2026-08-15 에 SMB(사이즈) 요인과 회전율(거래대금/시총)을 **유통량이 없어
    못 만들었다.** 이 두 컬럼이 그걸 연다.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Date, DateTime, Float, Index, Integer, String, UniqueConstraint,
)

from ..db.base import Base


class OnchainMetric(Base):
    __tablename__ = "onchain_metric"

    id = Column(Integer, primary_key=True, index=True)

    # CoinMetrics 자산 코드(btc/eth/…). 거래소 심볼(BTCUSDT)과 다르다 —
    # 매핑은 수집기가 갖고 있고 여기엔 원본 코드를 그대로 둔다.
    asset = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    active_addresses = Column(Float, nullable=True)   # AdrActCnt
    tx_count = Column(Float, nullable=True)           # TxCnt
    market_cap = Column(Float, nullable=True)         # CapMrktCurUSD
    supply = Column(Float, nullable=True)             # SplyCur
    fee_total = Column(Float, nullable=True)          # FeeTotNtv
    hash_rate = Column(Float, nullable=True)          # HashRate
    issuance_usd = Column(Float, nullable=True)       # IssTotUSD

    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # 증분 수집이 멱등하려면 필요하다
        UniqueConstraint("asset", "date", name="uq_onchain_asset_date"),
        Index("ix_onchain_asset_date", "asset", "date"),
    )
