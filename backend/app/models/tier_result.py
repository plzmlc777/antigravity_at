"""1군/2군 결과 저장소 — 분석·조회용 **읽기 모델**.

왜 저장하는가
    결과가 전부 민트 파일시스템의 JSON 이라 조회가 안 되고, 읽는 규칙이
    소비자마다 따로였다. 2026-08-13 하루에만 같은 병으로 세 번 물렸다:
      · 무효 표시를 소비자 **6곳에 따로** 배선해야 했다
      · 일일 리포트가 "리그 세션" 정의를 잘못 잡아 251 → 136 으로 정정
      · 세션 트리에 만든 백업 디렉터리를 세션으로 세어 157 → 158

    DB 였다면 `WHERE invalid = false` 한 줄이고, 백업 디렉터리는 애초에 행이
    아니다. 프론트엔드에서 1군 상태를 볼 방법도 없었다.

⚠ 이 테이블들은 **원본이 아니다**
    정본 엔진은 계속 파일에 쓴다(`runs/paper_sessions/*/`). 여기는 적재된
    사본이다. 엔진이 DB 를 쓰게 하면 페이퍼 사이클에 실패 모드가 늘고 **실자금이
    그 경로를 탄다**. 적재는 실패해도 거래에 영향이 없다 — 분석이 하루 늦을 뿐.

    설계 근거: `.claude/plans/tier1_result_store_schema.md`
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Index, Integer, SmallInteger,
    String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from ..db.base import Base


class PaperTrade(Base):
    """페이퍼/시뮬 거래 한 건 — `trades.jsonl` 의 행.

    `invalid` 가 이 테이블의 존재 이유다. 2026-08-13 에 lifecycle 498거래를
    무효 처리했는데(팬텀 익절 354 / 재진입 395 / 숏 수수료 미부과 449),
    파일 기반에서는 **읽는 쪽 6곳을 각각 고쳐야** 했다. 성과를 인용하는 질의는
    전부 `WHERE invalid = false` 로 끝나야 한다.
    """

    __tablename__ = "paper_trade"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(String, nullable=False, index=True)
    # trades.jsonl 의 **행 번호**. 이게 진짜 자연키다.
    #
    # 2026-08-13: 처음엔 (session_id, entry_ts, exit_ts, side) 를 유일키로 잡았다가
    # 적재가 UNIQUE 위반으로 통째로 실패했다 — 한 세션에 **진입·청산 시각이 완전히
    # 같은 거래가 2건** 있었다(같은 바 왕복 2회). 시각·방향만으로는 거래를 구분할 수
    # 없다. 파일의 행이 곧 그 거래의 정체다.
    row_idx = Column(Integer, nullable=False)
    # 비정규화 — 세션 파일이 없어도 조회가 되게 한다(세션은 은퇴·삭제될 수 있다)
    session_name = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    tier = Column(SmallInteger, nullable=True, index=True)      # 1 / 2 / 3
    strategy = Column(String, nullable=True, index=True)        # lifecycle 등
    variant = Column(String, nullable=True)                     # earlyexit_d7 등

    side = Column(String, nullable=False)                       # long / short
    entry_ts = Column(DateTime, nullable=True, index=True)
    exit_ts = Column(DateTime, nullable=True, index=True)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    qty = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)
    pnl_cash = Column(Float, nullable=True)
    exit_reason = Column(String, nullable=True, index=True)
    prediction_at_entry = Column(Float, nullable=True)

    invalid = Column(Boolean, nullable=False, default=False, index=True)
    invalid_defects = Column(JSONB, nullable=True)   # ["phantom_tp","reentry",…]
    invalidated_on = Column(Date, nullable=True)

    ingested_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        # 재적재 멱등 — 같은 거래를 두 번 넣지 않는다
        UniqueConstraint("session_id", "row_idx", name="uq_paper_trade_session_row"),
        Index("ix_paper_trade_valid", "invalid", "strategy", "exit_ts"),
    )


class ResearchResult(Base):
    """백테스트·포트폴리오 시뮬·어블레이션 결과 한 건.

    종류가 계속 늘어나므로 **지표는 JSONB**, 조회 축만 컬럼으로 뺀다.

    `git_commit` 이 핵심이다. 2026-08-12~13 에 숏 수수료·재진입·팬텀 익절 수정이
    연달아 들어가면서 **같은 이름의 수치가 코드에 따라 다른 뜻**을 갖게 됐다.
    커밋을 적지 않으면 몇 달 뒤 어느 수치가 유효한지 알 수 없다.
    """

    __tablename__ = "research_result"

    id = Column(Integer, primary_key=True, index=True)

    kind = Column(String, nullable=False, index=True)     # backtest/portfolio_sim/ablation
    strategy = Column(String, nullable=False, index=True)
    variant = Column(String, nullable=True, index=True)
    cohort_n = Column(Integer, nullable=True)
    window_start = Column(Date, nullable=True)
    window_end = Column(Date, nullable=True)

    params = Column(JSONB, nullable=True)     # 사이징·수수료·SL 등 입력
    metrics = Column(JSONB, nullable=True)    # mean/median/win/t/mdd/sharpe 등 출력

    git_commit = Column(String, nullable=True)
    script = Column(String, nullable=True)        # 산출 스크립트
    source_file = Column(String, nullable=True)   # 원본 JSON 경로
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("kind", "strategy", "variant", "created_at",
                         name="uq_research_result_natural"),
    )


class Tier1LayerObservation(Base):
    """1군 4층 동기화 관측 — 한 행 = (상장 사건, 층).

    1군의 핵심 질문("백테스트/페이퍼/실거래 관계성이 성립하는가")에 답하는 표다.

      BT     백테스트(순수규칙)   상장일 바 시가
      CANON  System-2 정본        바 시가 체결
      PA     계좌 12 페이퍼       드라이버 시장가, 고정 $200
      REAL   계좌 8 실거래        드라이버 시장가, 지갑 20%

    PA 와 REAL 은 같은 드라이버·시각·가격이라 수량만 다르다. 따라서
    **CANON↔PA = 체결 지연**, **PA↔REAL = 사이징** 으로 격차가 분리된다.

    `n_trades != 1` 이면 재진입이고 수익률 비교가 무의미하다.
    """

    __tablename__ = "tier1_layer_observation"

    id = Column(Integer, primary_key=True, index=True)

    symbol = Column(String, nullable=False, index=True)
    listing_date = Column(Date, nullable=False, index=True)
    layer = Column(String, nullable=False, index=True)     # BT / CANON / PA / REAL

    n_trades = Column(Integer, nullable=True)
    entry_date = Column(Date, nullable=True)
    entry_price = Column(Float, nullable=True)
    qty = Column(Float, nullable=True)
    return_pct = Column(Float, nullable=True)    # BT / CANON
    pnl_usdt = Column(Float, nullable=True)      # PA / REAL
    reentry = Column(Boolean, nullable=True)

    observed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("symbol", "listing_date", "layer", "observed_at",
                         name="uq_tier1_layer_natural"),
    )


class EngineGateRun(Base):
    """정본(Canon) 관문 실행 기록.

    지금은 `/tmp` 로그뿐이라 재부팅하면 사라진다. **관문이 언제 주문을 막았는지**
    는 사후 감사에서 가장 먼저 묻는 질문이다.
    """

    __tablename__ = "engine_gate_run"

    id = Column(Integer, primary_key=True, index=True)

    ran_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    mode = Column(String, nullable=False)          # fast / full

    unit_passed = Column(Integer, nullable=True)
    unit_total = Column(Integer, nullable=True)
    golden_matched = Column(Integer, nullable=True)
    golden_mismatched = Column(Integer, nullable=True)
    parity_pass = Column(Integer, nullable=True)   # fast 모드에는 없다
    parity_fail = Column(Integer, nullable=True)
    parity_skip = Column(Integer, nullable=True)

    verdict = Column(String, nullable=False, index=True)   # pass / fail
    orders_blocked = Column(Boolean, nullable=False, default=False)
    detail = Column(JSONB, nullable=True)
