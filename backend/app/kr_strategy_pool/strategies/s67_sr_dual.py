"""S67: Dual S/R — support bounce (down days) + breakout-retest (up days), EOD-flat.

The frequency problem with S64 is that its single trigger (S1 support bounce)
only fires on days price dips to S1 (~50% of days, mostly down/choppy days).
S67 adds an ORTHOGONAL trigger that fires on UP days: a classic breakout-retest —
price breaks above the prior-day high (resistance), then pulls back to it
(now support) and reclaims → buy. Because the two triggers fire on different
kinds of days, they should ADD trade frequency without competing for / diluting
the same setups.

Triggers (both long, intraday, EOD-flat, tight stop):
  A. S1 bounce: intraday touch of prior-day pivot S1 (no reclaim required — best
     for S1 per earlier research).
  B. PDH breakout-retest: after price's intraday high exceeds prior-day high
     (PDH) by brk_buffer, a later pullback that touches PDH and reclaims it → buy.

One position at a time; each trigger at most once/day; fixed TP, stop below the
relevant level.

Validated on 061090 (15m). The orthogonal second trigger DOUBLES frequency while
preserving/improving edge (level-stacking dilutes; orthogonal day-types add):
  2026:  71 trades / +19.35% / sharpe 2.28   (vs S1-only 35 / +16.74% / 2.08)
  FULL:  90 trades / +15.09% / sharpe 1.96 / WF 5/6 (crash fold +2.33%)
  FULL-recent OOS sharpe 2.21 ; last-10-trading-days entries 11 (vs S1-only 5)
See [[project-061090-regime-verdict]].
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..base import KrStrategyBase


class S67SRDual(KrStrategyBase):
    name = "s67_sr_dual"
    TIMEFRAME = "15m"
    DEFAULT_PARAMS: Dict[str, Any] = {
        # trigger A: S1 support bounce
        "use_s1": True,
        "s1_require_hold": False,
        # trigger B: prior-day-high breakout-retest
        "use_breakout_retest": True,
        "brk_buffer_pct": 0.005,        # how far above PDH counts as a break
        "retest_buffer_pct": 0.008,     # touch window around PDH on pullback
        # shared
        "touch_buffer_pct": 0.005,
        "tp_pct": 0.025,
        "sl_pct": 0.012,
        "sl_mode": "below",
        "max_entries_per_day": 2,
        "entry_cutoff_time": "14:30",
        "buy_size_pct": 0.7,
        "exit_time": "15:25",
    }

    # ------------------------------------------------------------------
    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        days: Dict[str, Dict[str, float]] = {}
        order: List[str] = []
        for c in feed:
            ts = str(c["timestamp"])
            if len(ts) < 16:
                continue
            day = ts[:10]
            h, l, cl = float(c["high"]), float(c["low"]), float(c["close"])
            d = days.get(day)
            if d is None:
                days[day] = {"h": h, "l": l, "c": cl}
                order.append(day)
            else:
                d["h"] = max(d["h"], h)
                d["l"] = min(d["l"], l)
                d["c"] = cl

        # prior-day-derived levels for each day D
        self._s1: Dict[str, float] = {}
        self._pdh: Dict[str, float] = {}
        for i in range(1, len(order)):
            p = days[order[i - 1]]
            H, L, C = p["h"], p["l"], p["c"]
            pp = (H + L + C) / 3.0
            self._s1[order[i]] = 2 * pp - H
            self._pdh[order[i]] = H

        self._entry: Optional[float] = None
        self._tgt: Optional[float] = None
        self._stp: Optional[float] = None
        self._used: Dict[str, set] = {}
        self._day_count: Dict[str, int] = {}
        self._broke_pdh: Dict[str, bool] = {}   # has price broken PDH today

    # ------------------------------------------------------------------
    def _sell_all(self, price: float, reason: str) -> None:
        qty = self.ctx.holdings.get(self.symbol, 0)
        if qty > 0:
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": reason})
        self._entry = self._tgt = self._stp = None

    def _enter(self, price: float, level: float, tag: str, used: set, day: str) -> None:
        from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
        cash = self.ctx.cash * float(self.config["buy_size_pct"])
        qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
        if qty <= 0:
            return
        tr = self.ctx.buy(self.symbol, qty, price=price, metadata={"reason": tag, "lvl": level})
        if tr and tr.get("type") == "buy":
            self._entry = float(tr.get("price", price))
            self._tgt = self._entry * (1 + float(self.config["tp_pct"]))
            if str(self.config["sl_mode"]) == "below":
                self._stp = level * (1 - float(self.config["sl_pct"]))
            else:
                self._stp = self._entry * (1 - float(self.config["sl_pct"]))
            used.add(tag)
            self._day_count[day] = self._day_count.get(day, 0) + 1

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = str(candle["timestamp"])
        if len(ts) < 16:
            return
        day = ts[:10]
        t = ts[11:16]
        price = float(candle["close"])
        low = float(candle["low"])
        high = float(candle["high"])

        # track PDH break (even while holding, so retest can fire after exit)
        pdh = self._pdh.get(day)
        if pdh and high > pdh * (1 + float(self.config["brk_buffer_pct"])):
            self._broke_pdh[day] = True

        if self._has_position():
            if t >= str(self.config["exit_time"]):
                self._sell_all(price, "eod_exit")
                return
            if self._stp and price <= self._stp:
                self._sell_all(price, "stop")
                return
            if self._tgt and price >= self._tgt:
                self._sell_all(price, "target")
                return
            return

        if day not in self._s1:
            return
        if t >= str(self.config["entry_cutoff_time"]):
            return
        if self._day_count.get(day, 0) >= int(self.config["max_entries_per_day"]):
            return
        used = self._used.setdefault(day, set())
        buf = float(self.config["touch_buffer_pct"])

        # Trigger A: S1 bounce
        if bool(self.config["use_s1"]) and "s1" not in used:
            s1 = self._s1[day]
            if s1 > 0 and low <= s1 * (1 + buf):
                if not (bool(self.config["s1_require_hold"]) and price < s1 * (1 - buf)):
                    self._enter(price, s1, "s1", used, day)
                    return

        # Trigger B: PDH breakout-retest (only after an intraday break)
        if bool(self.config["use_breakout_retest"]) and "brk" not in used and self._broke_pdh.get(day):
            rbuf = float(self.config["retest_buffer_pct"])
            # pullback touches PDH from above and reclaims
            if pdh and low <= pdh * (1 + rbuf) and price >= pdh * (1 - rbuf):
                self._enter(price, pdh, "brk", used, day)
                return
