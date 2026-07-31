from sqlalchemy import (
    BigInteger, Column, Date, DateTime, Float, Integer, String, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB

from ..db.base import Base
from datetime import datetime


class USRankSnapshot(Base):
    """키움 미국주식 순위정보(/api/us/rkinfo) 일일 스냅샷.

    왜 저장하는가:
        순위 API 는 "조회 시점"의 값만 주고 과거 시계열을 제공하지 않는다.
        키움 거래상위(한국 개인 수급 쏠림)나 주간거래 괴리율(Blue Ocean 세션 vs
        정규장 괴리)은 미국 현지 데이터에 존재하지 않는 고유 substrate 인데,
        지금부터 쌓지 않으면 영영 백테스트할 수 없다.

    한 행 = (영업일, 랭킹 종류, 종목).
    rank_type 별로 컬럼 의미가 조금씩 다르므로 공통 필드만 정규화하고
    나머지는 extra(JSONB)에 원본 그대로 보존한다.
    """

    __tablename__ = "us_rank_snapshot"

    id = Column(Integer, primary_key=True, index=True)

    business_date = Column(Date, nullable=False, index=True)   # 미국 현지 영업일
    rank_type = Column(String, nullable=False, index=True)     # trade_value / market_cap / kiwoom_trade ...
    api_id = Column(String, nullable=False)                    # usa20541 등 (감사용)

    rank = Column(Integer, nullable=True)                      # 순위 (없는 API 는 수집 순서)
    symbol = Column(String, nullable=False, index=True)
    stex_tp = Column(String, nullable=True)                    # ND / NY / AM / NA
    name_kr = Column(String, nullable=True)

    price = Column(Float, nullable=True)
    change_pct = Column(Float, nullable=True)
    volume = Column(BigInteger, nullable=True)
    trade_value = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    extra = Column(JSONB, nullable=True)                       # 원본 행 전체

    collected_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("business_date", "rank_type", "symbol",
                         name="uix_us_rank_date_type_symbol"),
        Index("ix_us_rank_type_date", "rank_type", "business_date"),
    )
