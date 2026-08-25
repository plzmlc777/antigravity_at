"""1분봉 원장 모델.

⚠ 2026-08-25 — 테이블이 `ohlcv` → `ohlcv_1m` 으로 바뀌었다.
   같은 1분봉을 두 테이블에 두 번 담고 있었다. 구 `ohlcv` 는 2.67억 행 47GB
   (힙 29 + 인덱스 19), `ohlcv_1m` 은 같은 데이터를 행당 135바이트로 담는다
   (구 190바이트 — `id` PK 와 인덱스 4개 탓). 실사 결과 구 테이블의
   `time_frame` 은 **`1m` 하나뿐**이었고, 구에 있는 종목은 100% 신에도 있었다.
   결손 7,439만 행을 `migrate_ohlcv_to_1m.py` 로 옮긴 뒤 이 모델을 돌렸다.

⚠ `time_frame` 컬럼이 없다 — 이 테이블은 **1분봉 전용**이다.
   상위 봉이 필요하면 읽어서 만든다(`binance_market_data._aggregate_candles`).
   호출부가 `time_frame` 으로 거르고 있었다면 그 조건은 지워야 한다.

⚠ `id` 도 없다. 키는 (symbol, ts) 이고 유니크 인덱스
   `uq_ohlcv_1m_symbol_ts` 가 그걸 강제한다. upsert 는 제약 이름 대신
   `index_elements=["symbol", "ts"]` 로 건다.

파이썬 쪽 속성 이름은 `timestamp` 를 유지한다 — 호출부 40여 곳을 건드리지
않기 위해서다. 실제 컬럼은 `ts` 이고 매핑으로 잇는다.
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, String, false, true

from ..db.base import Base


class OHLCV(Base):
    __tablename__ = "ohlcv_1m"

    symbol = Column(String, primary_key=True, nullable=False)
    # 컬럼은 `ts`, 파이썬 속성은 `timestamp` — 기존 호출부 호환.
    timestamp = Column("ts", DateTime, primary_key=True, nullable=False)

    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    # upsert 대상 컬럼. 제약 이름이 아니라 이 컬럼 조합으로 건다.
    CONFLICT_COLS = ("symbol", "ts")

    @classmethod
    def tf_filter(cls, interval: str):
        """질의 조건용 시간대 필터. 이 테이블은 **1분봉 전용**이다.

        ⚠ `OHLCV.time_frame == x` 로 쓰면 안 된다. `time_frame` 은 컬럼이
          아니라 파이썬 프로퍼티라서 클래스 수준 비교가 그냥 `False` 로
          접히고, SQLAlchemy 는 그걸 `WHERE false` 로 컴파일한다.
          **예외 없이 0행**이 나온다 — 2026-08-25 실측으로 실서비스
          28곳이 이 상태였다.
        """
        return true() if str(interval) == "1m" else false()

    @property
    def time_frame(self) -> str:
        """이 테이블은 1분봉 전용. 옛 호출부가 값을 읽기만 할 때를 위한 것으로,
        **질의 조건으로는 쓸 수 없다**(컬럼이 아니다)."""
        return "1m"

    @time_frame.setter
    def time_frame(self, v: str) -> None:
        """`OHLCV(time_frame="1m", ...)` 형태의 옛 생성부를 살려둔다.

        ⚠ 1분봉이 아니면 **소리내어 막는다**. 구 `ohlcv` 에는 미국 주식
          일봉(`1d`)도 섞여 있었다(SPY·QQQ 각 1,716행). 조용히 통과시키면
          일봉이 1분봉 테이블로 들어가 원장이 오염된다.
        """
        if v and str(v) != "1m":
            raise ValueError(
                f"`ohlcv_1m` 은 1분봉 전용인데 time_frame={v!r} 로 쓰려 한다. "
                "일봉은 `ohlcv_daily`, 미국 주식은 전용 경로를 쓰라.")

    @property
    def created_at(self) -> datetime | None:      # 구 모델 호환 — 값 없음
        return None
