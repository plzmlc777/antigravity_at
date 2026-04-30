"""
Dynamic Strategy Selector.

매일/매주 재평가되어 strategy pool 중 현재 시점에 가장 적합한 1개를 선택.

기본 전략: rolling-window in-sample backtest.
  - 최근 N일 데이터로 모든 전략을 백테스트
  - metric (Sharpe + return + win_rate)으로 ranking
  - 최소 cycle 수 / maxDD 임계 등 hard filter 적용
  - top 1 반환

확장 (향후):
  - regime_detector 입력을 받아 레짐별 가중치 적용
  - 메타-학습 (어떤 레짐에서 어떤 전략이 잘 동작했는지 누적 학습)
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from ..core.kr_backtest_engine import KrBacktestEngine
from .base import KrStrategyBase
from .data_utils import resample_ohlcv
from .regime_detector import RegimeProfile


@dataclass
class StrategyEvaluation:
    name: str
    strategy_class: str
    return_pct: float
    sharpe: Optional[float]
    win_rate: Optional[float]
    max_drawdown: Optional[float]
    trades: int
    score: float
    rejected: bool = False
    reject_reason: str = ""

    def as_dict(self) -> Dict:
        return {
            "name": self.name,
            "strategy_class": self.strategy_class,
            "return_pct": self.return_pct,
            "sharpe": self.sharpe,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "trades": self.trades,
            "score": self.score,
            "rejected": self.rejected,
            "reject_reason": self.reject_reason,
        }


@dataclass
class SelectionResult:
    selected: Optional[StrategyEvaluation]
    all_evaluations: List[StrategyEvaluation]
    regime: Optional[RegimeProfile]
    confidence: float


def composite_score(
    return_pct: float,
    sharpe: Optional[float],
    win_rate: Optional[float],
    max_drawdown: Optional[float],
) -> float:
    """
    단순 합성 점수 (향후 정교화 필요).
      score = 0.5 * return_pct + 5 * sharpe + 0.1 * (win_rate - 50)
      penalty for maxDD < -20% (heavy)
    """
    s = 0.0
    s += 0.5 * (return_pct or 0.0)
    s += 5.0 * (sharpe or 0.0)
    s += 0.1 * ((win_rate or 50.0) - 50.0)
    if max_drawdown is not None and max_drawdown < -20:
        s -= abs(max_drawdown + 20) * 0.5  # 20% 초과분에 0.5 가중 페널티
    return s


class DynamicSelector:
    def __init__(
        self,
        symbol: str,
        strategy_pool: List[Type[KrStrategyBase]],
        capital: int = 3_000_000,
        exchange_name: str = "Kiwoom",
        # hard filters
        min_trades: int = 10,
        max_dd_threshold: float = -25.0,
        # composite score weights (future-extensible)
        scoring_fn=composite_score,
    ):
        self.symbol = symbol
        self.strategy_pool = strategy_pool
        self.capital = capital
        self.exchange_name = exchange_name
        self.min_trades = min_trades
        self.max_dd_threshold = max_dd_threshold
        self.scoring_fn = scoring_fn

    async def evaluate_one(
        self,
        strategy_class: Type[KrStrategyBase],
        feed: List[Dict[str, Any]],
        config: Optional[Dict[str, Any]] = None,
    ) -> StrategyEvaluation:
        cfg = dict(config or {})
        cfg["symbol"] = self.symbol
        eng = KrBacktestEngine(strategy_class, exchange_name=self.exchange_name)
        try:
            stats = await eng.run_single_backtest(
                config=cfg, feed=feed, initial_capital=self.capital, symbol=self.symbol,
            )
        except Exception as e:
            return StrategyEvaluation(
                name=getattr(strategy_class, "name", strategy_class.__name__),
                strategy_class=strategy_class.__name__,
                return_pct=0.0, sharpe=None, win_rate=None,
                max_drawdown=None, trades=0,
                score=-1e9, rejected=True, reject_reason=f"error: {e}",
            )

        ret = stats.get("return_pct", 0.0)
        sh = stats.get("sharpe_ratio")
        wr = stats.get("win_rate")
        dd = stats.get("max_drawdown")
        n = stats.get("trades_count", 0)

        score = self.scoring_fn(ret, sh, wr, dd)

        rejected = False
        reasons = []
        if n < self.min_trades:
            rejected = True
            reasons.append(f"trades<{self.min_trades}")
        if dd is not None and dd < self.max_dd_threshold:
            rejected = True
            reasons.append(f"maxDD<{self.max_dd_threshold}%")

        return StrategyEvaluation(
            name=getattr(strategy_class, "name", strategy_class.__name__),
            strategy_class=strategy_class.__name__,
            return_pct=ret, sharpe=sh, win_rate=wr,
            max_drawdown=dd, trades=n, score=score,
            rejected=rejected, reject_reason="|".join(reasons),
        )

    async def select(
        self,
        feed_1m: List[Dict[str, Any]],
        regime: Optional[RegimeProfile] = None,
    ) -> SelectionResult:
        """
        feed_1m을 받아 각 전략의 TIMEFRAME에 맞춰 resample 후 백테스트.
        score 가장 높은 전략 1개 선택.
        """
        # cache resampled feeds per timeframe
        feed_cache: Dict[str, List[Dict[str, Any]]] = {}
        TF_MAP = {
            "1m": None, "5m": "5min", "15m": "15min",
            "30m": "30min", "60m": "60min", "1d": "1D",
        }

        evaluations: List[StrategyEvaluation] = []
        for cls in self.strategy_pool:
            tf = cls.TIMEFRAME
            freq = TF_MAP.get(tf)
            if freq is None:
                feed = feed_1m
            else:
                if freq not in feed_cache:
                    feed_cache[freq] = resample_ohlcv(feed_1m, freq)
                feed = feed_cache[freq]
            ev = await self.evaluate_one(cls, feed)
            evaluations.append(ev)

        # 후보 (rejected 제외) 중 score 최고
        candidates = [e for e in evaluations if not e.rejected]
        if not candidates:
            return SelectionResult(
                selected=None, all_evaluations=evaluations,
                regime=regime, confidence=0.0,
            )

        candidates.sort(key=lambda e: e.score, reverse=True)
        winner = candidates[0]

        # confidence: 1위와 2위 점수 차이로 단순 산출 (0~1)
        if len(candidates) >= 2:
            gap = candidates[0].score - candidates[1].score
            confidence = min(1.0, max(0.0, gap / 10.0))
        else:
            confidence = 0.5

        return SelectionResult(
            selected=winner, all_evaluations=evaluations,
            regime=regime, confidence=confidence,
        )
