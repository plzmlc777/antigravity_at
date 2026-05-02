"""
S60: 005930 (대형주) 외인+기관 수급 consensus follow.

신호 (D 종가 후 발표):
  inst_3d_norm  = 기관 3일 누적 순매수 / 직전 20일 평균 거래대금
  frgn_3d_norm  = 외국인 3일 누적 순매수 / 직전 20일 평균 거래대금
  consensus_3d  = (frgn_3d>0) + (inst_3d>0)   ∈ {0,1,2}

진입: D+1 09:00 시가
  inst_3d_norm > inst_thr  AND  consensus_3d >= consensus_min

청산:
  ① 보유 hold_days(거래일) 경과 시 종가 청산
  ② inst_3d_norm < rev_thr 로 신호 반전 시 그 날 종가 청산
  ③ SL/TP

데이터 source: investor_flow_daily (Kiwoom ka10059, 단위 백만원)

검증 (2026-05-02, 1년 데이터 2025-05-02~2026-04-30 / 92,704 1m bars):
  Full 1y          : return +66.09%, sharpe 2.53, win 62.2%, maxDD -13.94%, 76 trades
  IS 6m / OOS 6m   : IS +10.07% (sharpe 1.08) / OOS +43.90% (sharpe 2.04)
  6-fold WF        : 4/6 positive, avg +8.32%/fold (~2m), worst -3.79%, best +21.97%
  Grid 72 combos   : 100% positive (robust plateau, not cliff). DEFAULT rank 19/72.

월 환산 (보수적, WF 기반): 약 +4.2%/월. 단순 1y/12: +5.5%/월. 복리 1y: +4.3%/월.

대조 (post-fix perf_matrix_005930): 기존 1m 풀 (s40-s53) 단일 양수 전략 0개,
oracle ceiling +4.31%/월 → S60 단일 +4.2%/월으로 oracle 근접 + 1m 풀 한계 돌파.
"""
from typing import Any, ClassVar, Dict, List
from datetime import date as Date

import numpy as np
import pandas as pd
from sqlalchemy import text

from ..base import KrStrategyBase
from ..multi_tf_helpers import feed_to_df


class S60_InstFlowConsensus(KrStrategyBase):
    name = "s60_instflow_consensus"
    TIMEFRAME: ClassVar[str] = "1m"

    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "buy_size_pct": 0.7,
        "inst_thr": 0.05,
        "consensus_min": 1,
        "rev_thr": 0.0,
        "hold_days": 5,
        "sl_pct": 0.05,
        "tp_pct": 0.10,
        "avg_trade_window": 20,
        "exit_minute": "15:20",
    }

    PARAMETER_SCHEMA: ClassVar[Dict[str, Any]] = {
        "inst_thr": {"type": "float", "min": -0.1, "max": 0.5},
        "consensus_min": {"type": "int", "min": 0, "max": 2},
        "hold_days": {"type": "int", "min": 1, "max": 15},
        "sl_pct": {"type": "float", "min": 0.01, "max": 0.15},
        "tp_pct": {"type": "float", "min": 0.02, "max": 0.30},
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df_1m = feed_to_df(feed)
        self._feed_ts = [c["timestamp"] for c in feed]

        flow = self._load_flow(self.symbol)
        self._enter_dates, self._inst_per_date = self._build_signals(flow)

        self._holding_entry_date: Date | None = None
        self._entry_price: float | None = None

    def _load_flow(self, symbol: str) -> pd.DataFrame:
        from app.db.session import engine

        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT date, foreign_net, institutional_net, acc_trade_value
                    FROM investor_flow_daily WHERE symbol=:s ORDER BY date
                    """
                ),
                {"s": symbol},
            ).fetchall()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["date", "foreign", "inst", "acc_trade_value"])
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").astype(float)

    def _build_signals(self, flow: pd.DataFrame):
        if flow.empty:
            return set(), {}

        w = int(self.config["avg_trade_window"])
        avg_trade = flow["acc_trade_value"].shift(1).rolling(w).mean()
        foreign_3d = flow["foreign"].shift(1).rolling(3).sum()
        inst_3d = flow["inst"].shift(1).rolling(3).sum()

        inst_norm = inst_3d / avg_trade.replace(0, np.nan)
        frgn_norm = foreign_3d / avg_trade.replace(0, np.nan)
        consensus = (frgn_norm > 0).astype(int) + (inst_norm > 0).astype(int)

        signal_at_d = (
            (inst_norm > float(self.config["inst_thr"]))
            & (consensus >= int(self.config["consensus_min"]))
        )

        enter_today = signal_at_d.shift(1).fillna(False)
        enter_dates = set(d.date() for d in flow.index[enter_today])
        inst_per_date = {d.date(): float(v) if not pd.isna(v) else None
                         for d, v in inst_norm.items()}
        return enter_dates, inst_per_date

    def _trading_days_held(self, current_date: Date) -> int:
        if self._holding_entry_date is None:
            return 0
        delta = (current_date - self._holding_entry_date).days
        return max(0, delta)

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        ts_str = str(ts)
        candle_dt = pd.to_datetime(ts)
        d = candle_dt.date()
        hhmm = candle_dt.strftime("%H:%M") if hasattr(candle_dt, "strftime") else ts_str[11:16]

        if not self._has_position():
            if hhmm == "09:00" and d in self._enter_dates:
                from app.core.kr_backtest_engine import KR_BUY_FEE_RATE
                cash = self.ctx.cash * float(self.config["buy_size_pct"])
                qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
                if qty > 0:
                    tr = self.ctx.buy(self.symbol, qty, price=price,
                                      metadata={"reason": self.name})
                    if tr and tr.get("type") == "buy":
                        self._entry_price = float(tr.get("price", price))
                        self._holding_entry_date = d
            return

        if self._entry_price is None:
            return

        if price <= self._entry_price * (1 - float(self.config["sl_pct"])):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
            self._entry_price = None
            self._holding_entry_date = None
            return
        if price >= self._entry_price * (1 + float(self.config["tp_pct"])):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
            self._entry_price = None
            self._holding_entry_date = None
            return

        if hhmm >= str(self.config["exit_minute"]):
            held = self._trading_days_held(d)
            if held >= int(self.config["hold_days"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price,
                              metadata={"reason": "time"})
                self._entry_price = None
                self._holding_entry_date = None
                return

            inst_now = self._inst_per_date.get(d)
            if inst_now is not None and inst_now < float(self.config["rev_thr"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price,
                              metadata={"reason": "rev"})
                self._entry_price = None
                self._holding_entry_date = None
                return
