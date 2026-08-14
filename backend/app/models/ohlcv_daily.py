"""일봉 캐시 — 1분봉에서 유도한 **읽기 모델**.

왜 필요한가
    `ohlcv` 는 1분봉만 담고 45GB · 약 2.5억 행이다. 범위를 좁히면 인덱스가
    잘 듣지만(30일 조회 1.4초), **종목 전체 이력**을 긁으면 응답이 안 온다.
    유니버스 스캔은 종목마다 전체 이력이 필요하므로 608 종목이면 몇 시간이다.

    2026-08-14 실측: 전 종목 스캔이 11분에 25종목도 못 넘겼다.

    일봉으로 내리면 608종목 × 약 1,000일 ≈ 60만 행이다. 45GB → 수십 MB.

⚠ 원본이 아니다
    `ohlcv` 에서 유도한 사본이다. 지우고 다시 만들어도 정보가 사라지지 않는다.
    다만 **되만드는 비용이 크므로**(초기 적재 30~60분) 함부로 비우지 않는다.

경계
    하루는 **UTC 자정 기준**이다. 바이낸스 일봉과 같고, 기존
    `daily_bars()` 의 `resample("1D")` 과도 같다 — 다르면 백테스트 두 경로가
    갈린다.

    `is_partial` 은 그날 1분봉이 1440개에 못 미친다는 뜻이다. 오늘(진행 중)과
    상장 첫날, 그리고 데이터 결손 구간이 여기 걸린다. **부분 봉을 완전한 것처럼
    쓰면 시가·종가가 틀린다.**
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Index, Integer, String,
    UniqueConstraint,
)

from ..db.base import Base


class OhlcvDaily(Base):
    __tablename__ = "ohlcv_daily"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)      # UTC 자정 기준

    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    # 그날 1분봉 개수. 1440 미만이면 부분 봉이다 — 오늘·상장 첫날·결손 구간.
    n_minutes = Column(Integer, nullable=False)
    is_partial = Column(Boolean, nullable=False, default=False, index=True)

    built_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # 증분 갱신이 멱등하려면 이 유일키가 필요하다
        UniqueConstraint("symbol", "date", name="uq_ohlcv_daily_symbol_date"),
        # 유니버스 스캔은 (종목, 날짜) 순으로 훑는다
        Index("ix_ohlcv_daily_symbol_date", "symbol", "date"),
    )
