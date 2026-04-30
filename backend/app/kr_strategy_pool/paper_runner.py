"""
KR EOD Paper Runner.

매일 장 마감 후 발화 (PM2 cron 또는 수동). 다음을 수행:
  1. 키움 분봉 incremental fetch (이번 턴에서는 DB의 데이터만 사용)
  2. session.start_date ~ 오늘까지 백테스트 (KrBacktestEngine + fee/tax/tick)
  3. 누적 stats를 sessions/{session_id}.jsonl에 append
  4. 자본 게이트 (max_dd_threshold) 위반 시 status=DEGRADED

이 runner는 backend의 SAS Binance 인프라와 독립 — 자체 JSONL 로그.
나중에 C 단계에서 PM2 cron + DB persistence로 확장.
"""
import asyncio
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from sqlalchemy.engine import Engine

from ..core.kr_backtest_engine import KrBacktestEngine
from .base import KrStrategyBase
from .data_utils import fetch_1m_feed, resample_ohlcv

DEFAULT_LOG_ROOT = Path(__file__).resolve().parents[2] / "runs" / "kr_paper"


@dataclass
class PaperSession:
    """페이퍼 세션 메타. status: ACTIVE / DEGRADED / GRADUATED / FAILED."""
    session_id: str
    symbol: str
    strategy_name: str
    strategy_class: str
    params: Dict[str, Any]
    start_date: str
    initial_capital: int
    status: str = "ACTIVE"
    capital_gate_dd_pct: float = -15.0  # 자본 1단계 게이트
    grace_days_after_dd: int = 7
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_cycle_at: Optional[str] = None
    last_final_equity: Optional[float] = None
    last_return_pct: Optional[float] = None
    last_max_dd: Optional[float] = None
    cycle_count: int = 0


class PaperRunner:
    def __init__(
        self,
        engine: Engine,
        log_root: Path = DEFAULT_LOG_ROOT,
    ):
        self.engine = engine
        self.log_root = Path(log_root)
        self.log_root.mkdir(parents=True, exist_ok=True)
        (self.log_root / "sessions").mkdir(parents=True, exist_ok=True)
        (self.log_root / "cycles").mkdir(parents=True, exist_ok=True)

    def session_meta_path(self, session_id: str) -> Path:
        return self.log_root / "sessions" / f"{session_id}.json"

    def session_cycles_path(self, session_id: str) -> Path:
        return self.log_root / "cycles" / f"{session_id}.jsonl"

    def load_session(self, session_id: str) -> Optional[PaperSession]:
        p = self.session_meta_path(session_id)
        if not p.exists():
            return None
        with open(p) as f:
            data = json.load(f)
        return PaperSession(**data)

    def save_session(self, session: PaperSession) -> None:
        with open(self.session_meta_path(session.session_id), "w") as f:
            json.dump(asdict(session), f, indent=2, ensure_ascii=False)

    def create_session(
        self,
        session_id: str,
        symbol: str,
        strategy_class: Type[KrStrategyBase],
        params: Dict[str, Any],
        start_date: str,
        initial_capital: int = 3_000_000,
        capital_gate_dd_pct: float = -15.0,
    ) -> PaperSession:
        existing = self.load_session(session_id)
        if existing:
            raise ValueError(f"Session {session_id} already exists at {self.session_meta_path(session_id)}")
        session = PaperSession(
            session_id=session_id,
            symbol=symbol,
            strategy_name=getattr(strategy_class, "name", strategy_class.__name__),
            strategy_class=strategy_class.__name__,
            params=params,
            start_date=start_date,
            initial_capital=initial_capital,
            capital_gate_dd_pct=capital_gate_dd_pct,
        )
        self.save_session(session)
        return session

    async def run_cycle(
        self,
        session: PaperSession,
        strategy_class: Type[KrStrategyBase],
    ) -> Dict[str, Any]:
        """
        세션의 시작일~오늘까지 백테스트를 돌려 누적 stats 산출.
        매일 1회 호출되면 전일치 데이터까지 반영된 stats가 누적된다.
        """
        feed_1m = fetch_1m_feed(self.engine, session.symbol, start_date=session.start_date)
        if not feed_1m:
            raise RuntimeError(f"No data for {session.symbol} from {session.start_date}")

        # strategy의 TIMEFRAME 따라 resample
        TF_MAP = {
            "1m": None, "5m": "5min", "15m": "15min",
            "30m": "30min", "60m": "60min", "1d": "1D",
        }
        freq = TF_MAP.get(strategy_class.TIMEFRAME)
        feed = feed_1m if freq is None else resample_ohlcv(feed_1m, freq)

        eng = KrBacktestEngine(strategy_class, exchange_name="Kiwoom")
        cfg = {"symbol": session.symbol, **session.params}
        stats = await eng.run_single_backtest(
            config=cfg, feed=feed,
            initial_capital=session.initial_capital,
            symbol=session.symbol,
        )

        cycle_record = {
            "cycle_at": datetime.now().isoformat(),
            "data_first_ts": feed[0]["timestamp"],
            "data_last_ts": feed[-1]["timestamp"],
            "data_bars": len(feed),
            "trading_days": len({str(c["timestamp"])[:10] for c in feed}),
            "final_equity": stats.get("final_equity"),
            "return_pct": stats.get("return_pct"),
            "max_drawdown": stats.get("max_drawdown"),
            "sharpe": stats.get("sharpe_ratio"),
            "win_rate": stats.get("win_rate"),
            "trades_count": stats.get("trades_count"),
            "total_cycles": stats.get("total_cycles"),
            "kr_total_friction": stats.get("kr_total_friction"),
            "kr_total_fee": stats.get("kr_total_fee"),
            "kr_total_tax": stats.get("kr_total_tax"),
        }

        # 자본 게이트 체크
        prev_status = session.status
        max_dd = stats.get("max_drawdown") or 0
        if max_dd < session.capital_gate_dd_pct and session.status == "ACTIVE":
            session.status = "DEGRADED"
            cycle_record["status_change"] = f"ACTIVE → DEGRADED (maxDD {max_dd:.2f}% < {session.capital_gate_dd_pct}%)"

        # session 메타 업데이트
        session.last_cycle_at = cycle_record["cycle_at"]
        session.last_final_equity = stats.get("final_equity")
        session.last_return_pct = stats.get("return_pct")
        session.last_max_dd = max_dd
        session.cycle_count += 1
        self.save_session(session)

        # cycle JSONL append
        with open(self.session_cycles_path(session.session_id), "a") as f:
            f.write(json.dumps(cycle_record, ensure_ascii=False) + "\n")

        return cycle_record

    def list_cycles(self, session_id: str) -> List[Dict[str, Any]]:
        p = self.session_cycles_path(session_id)
        if not p.exists():
            return []
        out = []
        with open(p) as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    out.append(json.loads(ln))
        return out
