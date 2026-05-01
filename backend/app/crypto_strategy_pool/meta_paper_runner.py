"""
Crypto MetaPaperRunner — Phase 5 wire-in (mirror of KR MetaPaperRunner).

Each cycle:
  1. fetch 1m feed since session.start_date (Binance USDT-M, 24/7)
  2. encode environment at the last 1m bar
  3. load meta-learner, predict expected Sharpe per strategy in session.meta_pool
  4. apply safety gates (min Sharpe, top1-top2 confidence)
  5. backtest the chosen strategy (or cash-hold if gate triggers)
  6. append cycle record + update session meta

Differences vs KR:
  - CryptoBacktestEngine 사용 (taker fee 0.04% x 2, no tax)
  - log root: runs/crypto_paper/ (KR: runs/kr_paper/)
  - default fallback strategy: c40_vwap_atr_1m5m
  - capital은 USD 기준 (default 10000)
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Type

from sqlalchemy.engine import Engine

from ..core.crypto_backtest_engine import CryptoBacktestEngine
from .base import CryptoStrategyBase
from .data_utils import fetch_1m_feed, resample_ohlcv
from .env_encoder import encode_environment
from .meta_learner import load_meta_learner

DEFAULT_LOG_ROOT = Path(__file__).resolve().parents[2] / "runs" / "crypto_paper"

_TF_MAP = {"1m": None, "5m": "5min", "15m": "15min",
           "30m": "30min", "60m": "60min", "1d": "1D"}


@dataclass
class MetaPaperSession:
    session_id: str
    symbol: str
    start_date: str
    initial_capital: int  # USD
    meta_model_path: str
    meta_pool: List[str]
    meta_strategy_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    meta_min_sharpe: float = 0.5
    meta_confidence_min: float = 0.3
    meta_fallback_strategy: str = "c40_vwap_atr_1m5m"
    capital_gate_dd_pct: float = -15.0
    grace_days_after_dd: int = 7
    status: str = "ACTIVE"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_cycle_at: Optional[str] = None
    last_selected_strategy: Optional[str] = None
    last_predicted_sharpe: Optional[float] = None
    last_confidence: Optional[float] = None
    last_final_equity: Optional[float] = None
    last_return_pct: Optional[float] = None
    last_max_dd: Optional[float] = None
    cycle_count: int = 0


class MetaPaperRunner:
    def __init__(
        self,
        engine: Engine,
        registry: Dict[str, Type[CryptoStrategyBase]],
        log_root: Path = DEFAULT_LOG_ROOT,
    ):
        self.engine = engine
        self.registry = registry
        self.log_root = Path(log_root)
        (self.log_root / "sessions").mkdir(parents=True, exist_ok=True)
        (self.log_root / "cycles").mkdir(parents=True, exist_ok=True)

    def session_meta_path(self, sid: str) -> Path:
        return self.log_root / "sessions" / f"{sid}.json"

    def session_cycles_path(self, sid: str) -> Path:
        return self.log_root / "cycles" / f"{sid}.jsonl"

    def load_session(self, sid: str) -> Optional[MetaPaperSession]:
        p = self.session_meta_path(sid)
        if not p.exists():
            return None
        with open(p) as f:
            return MetaPaperSession(**json.load(f))

    def save_session(self, s: MetaPaperSession) -> None:
        with open(self.session_meta_path(s.session_id), "w") as f:
            json.dump(asdict(s), f, indent=2, ensure_ascii=False)

    def create_session(
        self,
        session_id: str,
        symbol: str,
        start_date: str,
        meta_model_path: str,
        meta_pool: List[str],
        initial_capital: int = 10_000,
        **kwargs,
    ) -> MetaPaperSession:
        if self.load_session(session_id):
            raise ValueError(f"Session {session_id} already exists")
        s = MetaPaperSession(
            session_id=session_id,
            symbol=symbol,
            start_date=start_date,
            initial_capital=initial_capital,
            meta_model_path=meta_model_path,
            meta_pool=meta_pool,
            **kwargs,
        )
        self.save_session(s)
        return s

    async def run_cycle(self, session: MetaPaperSession) -> Dict[str, Any]:
        feed = fetch_1m_feed(self.engine, session.symbol, start_date=session.start_date)
        if not feed:
            raise RuntimeError(f"No 1m data for {session.symbol} from {session.start_date}")
        last_ts = feed[-1]["timestamp"]

        env_vec = encode_environment(feed, last_ts)

        meta_path = session.meta_model_path
        if not Path(meta_path).is_absolute():
            meta_path = str(Path(__file__).resolve().parents[2] / meta_path)
        meta = load_meta_learner(meta_path)

        preds: Dict[str, float] = {}
        for name in meta["strategies"]:
            if name in session.meta_pool:
                preds[name] = float(meta["models"][name].predict(env_vec.reshape(1, -1))[0])
        if not preds:
            raise RuntimeError("meta_pool ∩ trained strategies is empty")

        ranked = sorted(preds.items(), key=lambda x: -x[1])
        top1_name, top1_sh = ranked[0]
        top2_sh = ranked[1][1] if len(ranked) > 1 else 0.0
        confidence = top1_sh - top2_sh

        if top1_sh < session.meta_min_sharpe:
            gate, chosen = "below_min_sharpe", None
        elif confidence < session.meta_confidence_min:
            gate, chosen = "low_confidence", session.meta_fallback_strategy
        else:
            gate, chosen = "ok", top1_name

        cycle = {
            "cycle_at": datetime.now().isoformat(),
            "data_first_ts": feed[0]["timestamp"],
            "data_last_ts": last_ts,
            "data_bars": len(feed),
            "env": env_vec.tolist(),
            "predicted_sharpes": preds,
            "top1_strategy": top1_name,
            "top1_predicted_sharpe": top1_sh,
            "top2_predicted_sharpe": top2_sh,
            "confidence": confidence,
            "safety_gate": gate,
            "chosen_strategy": chosen,
        }

        if chosen is None:
            cycle["mode"] = "cash_hold"
            cycle["return_pct"] = 0.0
            cycle["final_equity"] = session.initial_capital
            cycle["max_drawdown"] = 0.0
            cycle["trades_count"] = 0
        else:
            cls = self.registry[chosen]
            params = session.meta_strategy_params.get(chosen, {})
            cfg = {"symbol": session.symbol, **params}
            freq = _TF_MAP.get(cls.TIMEFRAME)
            run_feed = feed if freq is None else resample_ohlcv(feed, freq)

            engine_bt = CryptoBacktestEngine(cls, exchange_name="BinanceFutures")
            stats = await engine_bt.run_single_backtest(
                config=cfg, feed=run_feed,
                initial_capital=session.initial_capital,
                symbol=session.symbol,
            )
            cycle.update({
                "mode": "live_backtest",
                "final_equity": stats.get("final_equity"),
                "return_pct": stats.get("return_pct"),
                "max_drawdown": stats.get("max_drawdown"),
                "sharpe": stats.get("sharpe_ratio"),
                "win_rate": stats.get("win_rate"),
                "trades_count": stats.get("trades_count"),
                "crypto_total_friction": stats.get("crypto_total_friction"),
            })

            max_dd = stats.get("max_drawdown") or 0
            if max_dd < session.capital_gate_dd_pct and session.status == "ACTIVE":
                session.status = "DEGRADED"
                cycle["status_change"] = (
                    f"ACTIVE → DEGRADED (maxDD {max_dd:.2f}% < {session.capital_gate_dd_pct}%)"
                )
            session.last_final_equity = stats.get("final_equity")
            session.last_return_pct = stats.get("return_pct")
            session.last_max_dd = max_dd

        session.last_cycle_at = cycle["cycle_at"]
        session.last_selected_strategy = chosen
        session.last_predicted_sharpe = top1_sh
        session.last_confidence = confidence
        session.cycle_count += 1
        self.save_session(session)

        with open(self.session_cycles_path(session.session_id), "a") as f:
            f.write(json.dumps(cycle, ensure_ascii=False) + "\n")
        return cycle
