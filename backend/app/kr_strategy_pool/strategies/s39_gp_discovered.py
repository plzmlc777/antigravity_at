"""
S39 GP Discovered Indicator — Genetic Programming으로 발견된 indicator를
KrBacktestEngine에 wrapping하여 KR 환경 (거래세 0.18% 등)에서 정밀 검증.

config["expr_str"]: GP 결과 JSON의 expr 문자열 (DEAP PrimitiveTree.__str__).
"""
import operator
from typing import Any, ClassVar, Dict, Optional

import numpy as np
import pandas as pd
from deap import gp

from ..base import KrStrategyBase


def _safe_div(a, b):
    if isinstance(b, pd.Series):
        return a / b.replace(0, np.nan)
    if b == 0:
        return a if isinstance(a, pd.Series) else 0
    return a / b


def _safe_log(s):
    if isinstance(s, pd.Series):
        return np.log(s.abs().replace(0, np.nan))
    return np.log(abs(s)) if s != 0 else 0


def _safe_sqrt(s):
    if isinstance(s, pd.Series):
        return np.sqrt(s.abs())
    return np.sqrt(abs(s))


def _safe_neg(s):
    return -s


def _to_window(n):
    if isinstance(n, pd.Series):
        try:
            n = float(n.mean())
        except Exception:
            return 10
    try:
        n = int(abs(float(n)))
    except (ValueError, TypeError):
        return 10
    return max(2, min(n, 100))


def _ma(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).mean()


def _rstd(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).std()


def _rmax(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).max()


def _rmin(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.rolling(_to_window(n)).min()


def _pct_change_n(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([0.0])
    return s.pct_change(_to_window(n))


def _shift_n(s, n):
    if not isinstance(s, pd.Series):
        return pd.Series([float(s)])
    return s.shift(_to_window(n))


# Build pset matching gp_universal_indicator
_pset = gp.PrimitiveSet("MAIN", arity=5)
_pset.addPrimitive(operator.add, 2, name="add")
_pset.addPrimitive(operator.sub, 2, name="sub")
_pset.addPrimitive(operator.mul, 2, name="mul")
_pset.addPrimitive(_safe_div, 2, name="div")
_pset.addPrimitive(_safe_neg, 1, name="neg")
_pset.addPrimitive(_safe_log, 1, name="log")
_pset.addPrimitive(_safe_sqrt, 1, name="sqrt")
_pset.addPrimitive(_ma, 2, name="ma")
_pset.addPrimitive(_rstd, 2, name="rstd")
_pset.addPrimitive(_rmax, 2, name="rmax")
_pset.addPrimitive(_rmin, 2, name="rmin")
_pset.addPrimitive(_pct_change_n, 2, name="pct")
_pset.addPrimitive(_shift_n, 2, name="shift")
for _val in [5, 10, 14, 20, 30, 50, 60, 100]:
    _pset.addTerminal(_val, name=f"int_{_val}")
_pset.renameArguments(ARG0="close", ARG1="open", ARG2="high", ARG3="low", ARG4="volume")


class S39_GP_Discovered(KrStrategyBase):
    """GP 발견 indicator로 z-score reversion 매매 (KR 거래세 적용)."""
    name = "s39_gp_discovered"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "expr_str": "",  # GP HoF 결과의 표현식 문자열
        "z_window": 60,
        "entry_z": -1.5,
        "exit_z": 0.0,
        "buy_size_pct": 0.7,
        "sl_pct": 0.025,
        "tp_pct": 0.04,
        "exit_time": "15:25",
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        expr_str = self.config["expr_str"]
        if not expr_str:
            raise ValueError("expr_str must be provided")
        # DEAP PrimitiveTree 문자열 → callable
        tree = gp.PrimitiveTree.from_string(expr_str, _pset)
        func = gp.compile(tree, _pset)
        indicator = func(df["close"], df["open"], df["high"], df["low"], df["volume"])
        if not isinstance(indicator, pd.Series):
            raise ValueError("expr did not produce a pd.Series")

        zw = int(self.config["z_window"])
        rmean = indicator.rolling(zw).mean()
        rsd = indicator.rolling(zw).std()
        z = ((indicator - rmean) / rsd.replace(0, np.nan)).fillna(0)
        self._z = dict(zip(df["timestamp"], z.values))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        z = self._z.get(ts, 0)
        if np.isnan(z) or np.isinf(z):
            return
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        # EOD 청산
        if self._has_position() and t >= str(self.config["exit_time"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            return

        if self._has_position() and self._entry:
            # SL/TP
            if price <= self._entry * (1 - float(self.config["sl_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "sl"})
                self._entry = None
                return
            if price >= self._entry * (1 + float(self.config["tp_pct"])):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "tp"})
                self._entry = None
                return
            # z-score exit
            if z > float(self.config["exit_z"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "z_revert"})
                self._entry = None
                return
            return

        # Entry
        if z < float(self.config["entry_z"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": f"gp_z<{self.config['entry_z']}"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
