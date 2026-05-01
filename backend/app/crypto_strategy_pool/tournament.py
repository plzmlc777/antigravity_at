"""
Crypto 전략 토너먼트 러너 — KR KrTournament의 mirror.

여러 CryptoStrategyBase 서브클래스를 동일 데이터로 백테스트하고 결과를 비교.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from ..core.crypto_backtest_engine import CryptoBacktestEngine
from .base import CryptoStrategyBase
from .data_utils import resample_ohlcv

TIMEFRAME_TO_FREQ = {
    "1m": None,
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
    "1d": "1D",
}


@dataclass
class TournamentEntry:
    name: str
    strategy_class: Type[CryptoStrategyBase]
    config: Dict[str, Any] = field(default_factory=dict)
    note: str = ""


@dataclass
class TournamentResult:
    name: str
    strategy_class: str
    timeframe: str
    return_pct: float
    pnl: float
    trades: int
    sharpe: Optional[float]
    max_drawdown: Optional[float]
    win_rate: Optional[float]
    friction: float
    final_equity: float
    initial_capital: float
    note: str = ""


class CryptoTournament:
    HEADERS = [
        "strategy", "TF", "return", "pnl",
        "trades", "sharpe", "maxDD", "winRate", "friction",
    ]

    def __init__(
        self,
        symbol: str,
        feed_1m: List[Dict[str, Any]],
        initial_capital: int,
        exchange_name: str = "BinanceFutures",
    ):
        self.symbol = symbol
        self.feed_1m = feed_1m
        self.initial_capital = initial_capital
        self.exchange_name = exchange_name
        self.entries: List[TournamentEntry] = []
        self._feed_cache: Dict[str, List[Dict[str, Any]]] = {}

    def add(
        self,
        strategy_class: Type[CryptoStrategyBase],
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        note: str = "",
    ) -> "CryptoTournament":
        self.entries.append(
            TournamentEntry(
                name=name or strategy_class.name or strategy_class.__name__,
                strategy_class=strategy_class,
                config=config or {},
                note=note,
            )
        )
        return self

    def _get_feed(self, timeframe: str) -> List[Dict[str, Any]]:
        freq = TIMEFRAME_TO_FREQ.get(timeframe)
        if freq is None:
            return self.feed_1m
        if freq not in self._feed_cache:
            self._feed_cache[freq] = resample_ohlcv(self.feed_1m, freq)
        return self._feed_cache[freq]

    async def run_one(self, entry: TournamentEntry) -> TournamentResult:
        tf = entry.strategy_class.TIMEFRAME
        feed = self._get_feed(tf)

        cfg = dict(entry.config)
        cfg["symbol"] = self.symbol

        engine = CryptoBacktestEngine(
            entry.strategy_class, exchange_name=self.exchange_name
        )
        stats = await engine.run_single_backtest(
            config=cfg,
            feed=feed,
            initial_capital=self.initial_capital,
            symbol=self.symbol,
        )

        return TournamentResult(
            name=entry.name,
            strategy_class=entry.strategy_class.__name__,
            timeframe=tf,
            return_pct=stats.get("return_pct", 0.0),
            pnl=stats.get("pnl", 0.0),
            trades=stats.get("trades_count", 0),
            sharpe=stats.get("sharpe_ratio"),
            max_drawdown=stats.get("max_drawdown"),
            win_rate=stats.get("win_rate"),
            friction=stats.get("crypto_total_friction", 0.0),
            final_equity=stats.get("final_equity", 0.0),
            initial_capital=stats.get("initial_capital", self.initial_capital),
            note=entry.note,
        )

    async def run_all(self) -> List[TournamentResult]:
        results = []
        for entry in self.entries:
            try:
                r = await self.run_one(entry)
            except Exception as e:
                r = TournamentResult(
                    name=entry.name,
                    strategy_class=entry.strategy_class.__name__,
                    timeframe=entry.strategy_class.TIMEFRAME,
                    return_pct=0.0,
                    pnl=0.0,
                    trades=0,
                    sharpe=None,
                    max_drawdown=None,
                    win_rate=None,
                    friction=0.0,
                    final_equity=self.initial_capital,
                    initial_capital=self.initial_capital,
                    note=f"ERROR: {e}",
                )
            results.append(r)
        return results
