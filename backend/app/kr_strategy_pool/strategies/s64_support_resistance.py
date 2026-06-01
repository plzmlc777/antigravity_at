"""S64: Support/Resistance bounce, intraday long, EOD-flat.

Built specifically for 061090 (세나테크). Computes classic daily pivot levels
from the PRIOR day's H/L/C (no lookahead) and trades support bounces long:
buy when intraday price dips into a support level and holds (bounce), target a
resistance level above, stop below, flat by close.

Rationale from prior 061090 research: the name is a high-vol −69% downtrend where
(a) holding overnight is fatal (gap-downs), (b) momentum/breakout/bull-pattern
entries are continuation traps, (c) the only surviving edge is rare intraday
long entries with tight risk. Support-bounce is the mean-reversion complement to
the open-drive momentum capture — buy fear at a known level, sell into the bounce.

Pivot formulas (from prior day H,L,C):
  PP = (H+L+C)/3
  R1 = 2*PP - L ; S1 = 2*PP - H
  R2 = PP + (H-L) ; S2 = PP - (H-L)
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..base import KrStrategyBase


class S64SupportResistance(KrStrategyBase):
    name = "s64_support_resistance"
    TIMEFRAME = "15m"
    # Defaults = robustness-optimum on 061090 from a full interval x param x structural
    # sweep (scripts/dev_061090_research.py). Buy at the prior-day S1 pivot on an intraday
    # TOUCH (no same-bar reclaim required — the bounce typically completes on the next 15m
    # bar, so requiring reclaim filtered out good entries), take a quick fixed +2.5%, stop
    # 1.5% below S1, EOD-flat. The 15m interval is the structural sweet spot (inverted-U:
    # 1m too noisy, 30m/60m too coarse for risk control). The trend filter is OFF — at 15m
    # the tight 1.5% stop already handles crash risk, so the filter only removed good trades.
    #   FULL (incl. Nov −66% crash): +15.96% / sharpe 1.97 / PF 2.22 / 47 trades / WF 5/6
    #   TEST 2.22 · OOS-mid 1.46 · OOS-recent(forward) 1.62  → every window sharpe >= 1.46
    #   Per-fold: even the Nov-crash fold is +3.9% (tight stops + bounces). Max per-fold DD ~6%.
    # See [[project-061090-regime-verdict]].
    DEFAULT_PARAMS: Dict[str, Any] = {
        "support_level": "s1",        # 's1' | 's2' | 's1s2' (buy at either)
        "target_level": "fixed",       # 'pp' | 'r1' | 'fixed'
        "tp_pct": 0.025,               # used when target_level == 'fixed'
        "touch_buffer_pct": 0.005,     # bar low within this below support counts as touch
        "require_hold": False,         # require bar close >= support (bounce confirm)
        "sl_mode": "below",            # 'below' (stop = support*(1-sl_pct)) | 'fixed'
        "sl_pct": 0.015,
        "one_per_level_per_day": True,
        "entry_cutoff_time": "14:30",
        # "don't catch a falling knife" trend filter (uses only PRIOR days):
        #   require prior close >= SMA(prior closes, trend_sma_days) * (1 - trend_tol)
        "use_trend_filter": False,
        "trend_sma_days": 5,
        "trend_tol": 0.05,
        # skip the day entirely if prior-day return <= this (crash-continuation guard);
        # 0.0 disables
        "skip_if_prior_day_down": 0.0,
        "buy_size_pct": 0.7,
        "exit_time": "15:25",
    }

    # ------------------------------------------------------------------
    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]

        # per-day OHLC (regular session)
        days: Dict[str, Dict[str, float]] = {}
        order = []
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
                d["c"] = cl  # last close of day

        # pivots for day D from day D-1, plus per-day regime gate (prior days only)
        self._piv: Dict[str, Dict[str, float]] = {}
        self._regime_ok: Dict[str, bool] = {}
        sma_n = int(self.config["trend_sma_days"])
        tol = float(self.config["trend_tol"])
        down_thr = float(self.config["skip_if_prior_day_down"])
        use_tf = bool(self.config["use_trend_filter"])
        for i in range(1, len(order)):
            prev = days[order[i - 1]]
            H, L, C = prev["h"], prev["l"], prev["c"]
            pp = (H + L + C) / 3.0
            self._piv[order[i]] = {
                "pp": pp,
                "r1": 2 * pp - L,
                "s1": 2 * pp - H,
                "r2": pp + (H - L),
                "s2": pp - (H - L),
            }
            ok = True
            # trend filter: prior close vs SMA of prior closes
            if use_tf and i >= sma_n:
                closes = [days[order[j]]["c"] for j in range(i - sma_n, i)]
                sma = sum(closes) / len(closes)
                if C < sma * (1 - tol):
                    ok = False
            # crash-continuation guard: prior-day return
            if down_thr < 0 and i >= 2:
                prev_prev_c = days[order[i - 2]]["c"]
                if prev_prev_c > 0 and (C - prev_prev_c) / prev_prev_c <= down_thr:
                    ok = False
            self._regime_ok[order[i]] = ok

        self._entry: Optional[float] = None
        self._tgt: Optional[float] = None
        self._stp: Optional[float] = None
        self._used: Dict[str, set] = {}   # day -> set of support keys already traded

    # ------------------------------------------------------------------
    def _sell_all(self, price: float, reason: str) -> None:
        qty = self.ctx.holdings.get(self.symbol, 0)
        if qty > 0:
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": reason})
        self._entry = self._tgt = self._stp = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = str(candle["timestamp"])
        if len(ts) < 16:
            return
        day = ts[:10]
        t = ts[11:16]
        price = float(candle["close"])
        low = float(candle["low"])

        # ----- manage open position -----
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

        piv = self._piv.get(day)
        if not piv:
            return
        if not self._regime_ok.get(day, True):
            return
        if t >= str(self.config["entry_cutoff_time"]):
            return

        # candidate support keys
        sel = str(self.config["support_level"])
        keys = {"s1": ["s1"], "s2": ["s2"], "s1s2": ["s1", "s2"]}.get(sel, ["s1"])
        buf = float(self.config["touch_buffer_pct"])
        used = self._used.setdefault(day, set())

        for k in keys:
            if self.config["one_per_level_per_day"] and k in used:
                continue
            sup = piv[k]
            if sup <= 0:
                continue
            # touch: bar low dipped to/below support (within buffer)
            touched = low <= sup * (1 + buf)
            if not touched:
                continue
            # hold/bounce confirm: close back above support
            if self.config["require_hold"] and price < sup * (1 - buf):
                continue

            # choose target
            tmode = str(self.config["target_level"])
            if tmode == "pp":
                tgt = piv["pp"]
            elif tmode == "r1":
                tgt = piv["r1"]
            else:
                tgt = price * (1 + float(self.config["tp_pct"]))
            if tgt <= price:  # support above PP edge-case; fall back to fixed
                tgt = price * (1 + float(self.config["tp_pct"]))

            # stop
            if str(self.config["sl_mode"]) == "below":
                stp = sup * (1 - float(self.config["sl_pct"]))
            else:
                stp = price * (1 - float(self.config["sl_pct"]))
            if stp >= price:
                continue

            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE

            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty <= 0:
                return
            tr = self.ctx.buy(self.symbol, qty, price=price,
                              metadata={"reason": f"support_{k}", "sup": sup, "tgt": tgt})
            if tr and tr.get("type") == "buy":
                self._entry = float(tr.get("price", price))
                self._tgt = tgt
                self._stp = stp
                used.add(k)
            return
