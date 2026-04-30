"""
KR 전략 토너먼트 러너.

여러 전략(KrStrategyBase 서브클래스)을 동일 데이터로 백테스트하고 결과를 비교.
각 전략의 TIMEFRAME 클래스 변수를 보고 적절한 resample 데이터를 자동 공급.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

import numpy as np

from ..core.kr_backtest_engine import KrBacktestEngine
from .base import KrStrategyBase
from .data_utils import resample_ohlcv

TIMEFRAME_TO_FREQ = {
    "1m": None,  # raw
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "60m": "60min",
    "1d": "1D",
}


@dataclass
class TournamentEntry:
    name: str
    strategy_class: Type[KrStrategyBase]
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

    def as_row(self) -> List[Any]:
        # NOTE: backend _generate_stats가 max_drawdown / win_rate을 이미 %로 출력 → 그대로 표시
        return [
            self.name,
            self.timeframe,
            f"{self.return_pct:+.2f}%",
            f"{self.pnl:+,.0f}",
            self.trades,
            f"{self.sharpe:.2f}" if self.sharpe is not None else "n/a",
            f"{self.max_drawdown:.2f}%" if self.max_drawdown is not None else "n/a",
            f"{self.win_rate:.1f}%" if self.win_rate is not None else "n/a",
            f"{self.friction:,.0f}",
        ]


class KrTournament:
    HEADERS = [
        "strategy", "TF", "return", "pnl",
        "trades", "sharpe", "maxDD", "winRate", "friction",
    ]

    def __init__(
        self,
        symbol: str,
        feed_1m: List[Dict[str, Any]],
        initial_capital: int,
        exchange_name: str = "Kiwoom",
    ):
        self.symbol = symbol
        self.feed_1m = feed_1m
        self.initial_capital = initial_capital
        self.exchange_name = exchange_name
        self.entries: List[TournamentEntry] = []
        # cache resampled feeds by frequency
        self._feed_cache: Dict[str, List[Dict[str, Any]]] = {}

    def add(
        self,
        strategy_class: Type[KrStrategyBase],
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        note: str = "",
    ) -> "KrTournament":
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

        engine = KrBacktestEngine(
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
            friction=stats.get("kr_total_friction", 0.0),
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

    @staticmethod
    def rank(
        results: List[TournamentResult], metric: str = "return_pct"
    ) -> List[TournamentResult]:
        def key(r: TournamentResult):
            v = getattr(r, metric, 0)
            return -(v if v is not None else -1e18)
        return sorted(results, key=key)

    @staticmethod
    def format_table(results: List[TournamentResult]) -> str:
        rows = [r.as_row() for r in results]
        rows.insert(0, KrTournament.HEADERS)
        widths = [max(len(str(c)) for c in col) for col in zip(*rows)]
        lines = []
        for i, row in enumerate(rows):
            line = "  ".join(str(c).rjust(w) for c, w in zip(row, widths))
            lines.append(line)
            if i == 0:
                lines.append("  ".join("-" * w for w in widths))
        return "\n".join(lines)
