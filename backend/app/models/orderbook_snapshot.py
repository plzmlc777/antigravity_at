"""호가 스냅샷 — 스프레드·깊이의 원자료.

왜 필요한가
    `Crypto factor zoo`(2026)가 36요인 중 알파를 흡수하는 핵심으로
    turnover volatility · **bid-ask spread** · new-address-to-price 를 꼽는다.
    2026-08-15 기준 셋 중 둘은 손댔고(회전율·온체인) 스프레드만 남았다.

⚠ 과거 데이터가 없다
    호가는 지나가면 사라진다. 지금 시작해도 **검정 가능한 표본이 쌓이려면
    최소 6개월**이다. OI·포지셔닝이 4개월뿐이라 표본 밖 검증을 못 하는 것과
    같은 처지다. 그래도 지금 시작 안 하면 6개월 뒤에도 없다.

무엇을 담나
    `bookTicker` 는 **737종목 최우선호가를 한 요청**에 준다(가중치 5).
    종목별 `depth` 는 요청이 종목 수만큼 필요해 비싸므로 최우선호가만 모은다.
    스프레드 요인에는 이것으로 충분하고, 깊이가 필요해지면 그때 확장한다.

    가격이 아니라 **비율**을 저장한다 — `spread_bp` 는 종목 간 비교가 되지만
    절대 스프레드는 안 된다(BTC 0.1 과 DOGE 0.00001 은 비교 불가).
"""
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, Index, Integer, String, UniqueConstraint,
)

from ..db.base import Base


class OrderbookSnapshot(Base):
    __tablename__ = "orderbook_snapshot"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String, nullable=False, index=True)
    # 수집 시각(우리 시계). 거래소가 준 `time` 은 `exchange_ts` 에 따로 둔다 —
    # 둘이 어긋나면 수집 지연을 알 수 있다.
    ts = Column(DateTime, nullable=False, index=True)
    exchange_ts = Column(DateTime, nullable=True)

    bid_price = Column(Float, nullable=False)
    ask_price = Column(Float, nullable=False)
    bid_qty = Column(Float, nullable=True)
    ask_qty = Column(Float, nullable=True)

    # 파생 — 저장 시점에 계산해 둔다. 조회마다 다시 재면 정의가 갈린다.
    spread_bp = Column(Float, nullable=False)      # (ask-bid)/mid × 10000
    mid = Column(Float, nullable=False)
    # 최우선호가 불균형. +면 매수벽이 두껍다
    imbalance = Column(Float, nullable=True)       # (bq-aq)/(bq+aq)

    __table_args__ = (
        UniqueConstraint("symbol", "ts", name="uq_ob_symbol_ts"),
        Index("ix_ob_symbol_ts", "symbol", "ts"),
    )


class OrderbookDaily(Base):
    """일별 집계 — 원자료는 커서 오래 못 둔다.

    스냅샷을 5분마다 받으면 737종목 × 288 = 하루 21만 행이다. 1년이면 7,700만
    행으로 `ohlcv`(2.5억) 급이 된다. 그래서 **일별로 말아 두고 원자료는
    보존기간을 둔다.**

    스프레드는 **중앙값**을 대표값으로 쓴다 — 평균은 순간 급확대 하나에
    끌려간다(유동성 게이트에서 거래대금에 중앙값을 쓴 것과 같은 이유).
    """

    __tablename__ = "orderbook_daily"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)

    n_samples = Column(Integer, nullable=False)
    spread_bp_med = Column(Float, nullable=True)
    spread_bp_mean = Column(Float, nullable=True)
    spread_bp_p90 = Column(Float, nullable=True)
    spread_bp_std = Column(Float, nullable=True)    # 스프레드 변동성
    imbalance_mean = Column(Float, nullable=True)
    top_depth_usd_med = Column(Float, nullable=True)

    built_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_ob_daily_symbol_date"),
        Index("ix_ob_daily_symbol_date", "symbol", "date"),
    )
