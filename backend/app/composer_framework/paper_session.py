"""PaperSession — persisted state for one running paper-trading session.

Each session has:
  - config: which Pipeline (sources/composer/policy) to use
  - state: cash, position, equity, history
  - status: active / paused / terminated

Sessions are stored as JSON files under runs/paper_sessions/{session_id}/.
Cycles are recorded as JSONL append-only logs (trades, equity, predictions).
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from .kernel import DEFAULT_FEE_RATE

logger = logging.getLogger(__name__)


SessionStatus = Literal["active", "paused", "terminated"]
SessionMode = Literal["paper", "live"]
PositionSide = Literal["flat", "long", "short"]


@dataclass
class PaperSession:
    """Self-contained record of one paper session."""
    # Identity
    session_id: str
    name: str
    symbol: str
    mode: SessionMode = "paper"
    status: SessionStatus = "active"

    # Pipeline config (JSON-serializable)
    pipeline_spec: dict = field(default_factory=dict)

    # Runtime knobs
    initial_capital: float = 1_000_000.0
    refit_interval_days: int = 30
    fee_rate: float = DEFAULT_FEE_RATE
    # 3d — 종전에는 orchestrator 가 0.95 를 하드코딩했다. 세션마다 다르게 둘 수
    # 있어야 하고, 무엇보다 값이 코드가 아니라 기록에 남아야 재현이 된다.
    size_pct: float = 0.95
    # 3e — 바 커버리지. 종전에는 orchestrator 안의 지역 상수였다.
    #   catchup_cap_bars: 한 사이클이 몰아 재생할 최대 바 수(5분봉 약 1주).
    #                     긴 장애 뒤 첫 실행이 무한정 길어지지 않게 한다.
    #   fresh_start_bars: 새 세션이 몇 바 전부터 시작하는가. 1 = 최신 바만
    #                     (라이브 세션이지 백테스트가 아니므로 과거를 재생하지 않는다).
    catchup_cap_bars: int = 2016
    fresh_start_bars: int = 1

    # Position state
    cash: float = 0.0
    qty: float = 0.0
    side: PositionSide = "flat"
    entry_price: float = 0.0
    entry_ts: Optional[str] = None
    sl_price: float = 0.0
    tp_price: float = 0.0
    bars_held: int = 0

    # Cycle bookkeeping
    last_cycle_ts: Optional[str] = None
    last_fit_ts: Optional[str] = None
    n_cycles: int = 0
    n_trades: int = 0

    # Aggregate stats (derived; updated by orchestrator)
    final_equity: float = 0.0
    total_return_pct: float = 0.0

    # Metadata
    created_at: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.cash == 0.0 and self.side == "flat" and self.n_cycles == 0:
            self.cash = self.initial_capital
            self.final_equity = self.initial_capital
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat(timespec="seconds")
        if not self.session_id:
            self.session_id = str(uuid.uuid4())[:12]

    # ───────────────────── persistence ─────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PaperSession":
        return cls(**d)


@dataclass
class CycleResult:
    """One cycle's outcome — appended to predictions.jsonl."""
    timestamp: str
    prediction: float
    action_kind: str
    action_note: str
    bar_open: float
    bar_close: float
    side_before: str
    side_after: str
    cash_after: float
    equity_after: float
    sl_price: float = 0.0
    tp_price: float = 0.0
    trade_id: Optional[str] = None
    forced_exit_reason: Optional[str] = None


@dataclass
class TradeRecord:
    """Closed trade — appended to trades.jsonl."""
    trade_id: str
    side: str
    entry_ts: str
    exit_ts: str
    entry_price: float
    exit_price: float
    qty: float
    return_pct: float
    pnl_cash: float
    exit_reason: str
    prediction_at_entry: float


# ───────────────────── store ─────────────────────


class SessionStore:
    """Per-session directory layout:
        {root}/{session_id}/
            session.json     (PaperSession dataclass)
            trades.jsonl     (one TradeRecord per line)
            equity.jsonl     (timestamp, equity)
            predictions.jsonl (one CycleResult per line)
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, session_id: str) -> Path:
        d = self.root / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save(self, session: PaperSession) -> None:
        d = self._dir(session.session_id)
        with open(d / "session.json", "w") as f:
            json.dump(session.to_dict(), f, indent=2, default=str)

    def load(self, session_id: str) -> PaperSession:
        path = self.root / session_id / "session.json"
        if not path.exists():
            raise FileNotFoundError(f"No session at {path}")
        with open(path) as f:
            return PaperSession.from_dict(json.load(f))

    def list_all(self) -> list[PaperSession]:
        out: list[PaperSession] = []
        for d in sorted(self.root.iterdir()):
            f = d / "session.json"
            if f.exists():
                try:
                    out.append(PaperSession.from_dict(json.load(open(f))))
                except Exception as exc:
                    logger.warning("Failed to load %s: %s", f, exc)
        return out

    def append_cycle(self, session_id: str, cycle: CycleResult) -> None:
        with open(self._dir(session_id) / "predictions.jsonl", "a") as f:
            f.write(json.dumps(asdict(cycle), default=str) + "\n")

    def append_trade(self, session_id: str, trade: TradeRecord) -> None:
        with open(self._dir(session_id) / "trades.jsonl", "a") as f:
            f.write(json.dumps(asdict(trade), default=str) + "\n")

    def append_equity(self, session_id: str, ts: str, equity: float) -> None:
        with open(self._dir(session_id) / "equity.jsonl", "a") as f:
            f.write(json.dumps({"timestamp": ts, "equity": equity}, default=str) + "\n")

    def read_trades(self, session_id: str) -> list[dict]:
        path = self.root / session_id / "trades.jsonl"
        if not path.exists():
            return []
        out = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def read_equity(self, session_id: str) -> list[dict]:
        path = self.root / session_id / "equity.jsonl"
        if not path.exists():
            return []
        out = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
