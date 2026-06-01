"""S62: Open-Drive + Intraday-Breakout, EOD-flat, smart-money flow filtered.

Discovered for 061090 (세나테크) — a high-volatility KOSDAQ mid-cap whose
2025-11 ~ 2026-04 history is a brutal −69% downtrend riddled with overnight
gap-downs. Empirical research (scripts/dev_061090_research.py) showed that the
ONLY profitable archetype on this stock is intraday momentum capture that never
holds overnight: s26_open_drive returned +3.92% (sharpe 0.76, MDD 6.5%) over a
window where buy-&-hold lost 75.8%.

S62 generalizes s26 to clear the validation gates (n_trades, sharpe):

  Trigger A — Open Drive:  at 09:05, if the 09:00 5m candle drove up
              >= min_open_drive_pct, enter long.
  Trigger B — Intraday Breakout (optional): after the morning range
              (09:00..breakout_window_min) is established, if price breaks
              above that range high and we are flat, enter long (one B-entry
              per day). Lifts trade frequency on days the open was weak.

  Quality filter (optional) — prior-day smart-money flow:
              only enter when the *previous day's* (foreign + institutional)
              5-day cumulative net buying >= flow_min_smart_5d. Skips
              distribution days. Uses investor_flow_daily (T+1, no lookahead).

  Risk:       SL / TP / hard EOD exit at exit_time. Never holds overnight.

EOD-flat is the core edge — overnight gap risk is what destroyed every
holding strategy on this name.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from ..base import KrStrategyBase


class S62OpenDriveFlow(KrStrategyBase):
    name = "s62_open_drive_flow"
    TIMEFRAME = "5m"
    # Defaults = grid-best config on 061090 (scripts/dev_061090_research.py 24-cell grid).
    # Key finding: wide SL/TP monotonically beats tight across ALL drive levels — capping
    # winners hurts; let the morning move run, with EOD-flat as the real exit. Flow filter
    # OFF wins on the full window here (more trades + uncapped winners). Trigger B (intraday
    # breakout) proved harmful (bull-trap in downtrend) — kept OFF.
    #   FULL +11.37% / sharpe 1.23 / 21 trades / WF 3/6 ; TEST +4.65% / sharpe 1.34.
    # NOTE: passes the 4 validation gates on the full window but is NOT "overwhelming"
    # (≈+25%/yr, recent-half sample only 5 trades). Defensive, not life-changing. Do not
    # live-promote without explicit user approval. See [[project-061090-regime-verdict]].
    DEFAULT_PARAMS: Dict[str, Any] = {
        # Trigger A: open drive
        "min_open_drive_pct": 0.005,      # 09:00 candle close/open - 1
        # Trigger B: intraday range breakout (OFF — harmful on 061090)
        "use_intraday_breakout": False,
        "breakout_window_min": 30,         # minutes from 09:00 to build range
        "breakout_buffer_pct": 0.001,      # require break above range high by buffer
        "breakout_cutoff_time": "13:30",   # no B-entries after this (need hold room)
        # Quality filter: prior-day smart-money flow (OFF by default; ON improves
        # per-trade quality but halves trade count below the sample line)
        "use_flow_filter": False,
        "flow_min_smart_5d": 0.0,          # prior-day (foreign+inst) 5d cum net >= this
        # Risk — wide: let winners run to EOD, modest stop
        "sl_pct": 0.02,
        "tp_pct": 0.07,
        "buy_size_pct": 0.7,
        "exit_time": "15:25",
    }

    # ------------------------------------------------------------------
    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]

        win = int(self.config["breakout_window_min"])
        # window end "HH:MM" (09:00 + win minutes), capped within session
        end_min = 9 * 60 + win
        self._range_end = f"{end_min // 60:02d}{end_min % 60:02d}"  # e.g. "0930"

        per_day: Dict[str, Dict[str, Any]] = {}
        for c in feed:
            ts = str(c["timestamp"])
            if len(ts) < 16:
                continue
            day = ts[:10]
            hm = ts[11:13] + ts[14:16]  # "HHMM"
            d = per_day.setdefault(day, {"drive": None, "range_high": 0.0})
            # 09:00 open-drive
            if hm == "0900" and d["drive"] is None:
                o = max(float(c["open"]), 1.0)
                d["drive"] = (float(c["close"]) - o) / o
            # morning range high (09:00 .. range_end inclusive)
            if "0900" <= hm <= self._range_end:
                d["range_high"] = max(d["range_high"], float(c["high"]))
        self._day = per_day

        # ---- prior-day smart-money flow (optional) ----
        self._flow_ok_by_day: Dict[str, bool] = {}
        if bool(self.config["use_flow_filter"]):
            try:
                from app.microstructure.kr_investor_flow import (
                    build_flow_features,
                    fetch_investor_flow,
                )

                flow_df = fetch_investor_flow(self.symbol)
                feats = build_flow_features(flow_df) if flow_df is not None and len(flow_df) else pd.DataFrame()
            except Exception:
                feats = pd.DataFrame()

            if not feats.empty and "flow_smart_5d_cum" in feats.columns:
                smart = feats["flow_smart_5d_cum"]
                # index -> date string; shift(1) so day D uses day D-1's value (no lookahead)
                prev = smart.shift(1)
                thr = float(self.config["flow_min_smart_5d"])
                for idx, val in prev.items():
                    day_key = str(idx)[:10]
                    self._flow_ok_by_day[day_key] = bool(pd.notna(val) and val >= thr)
            else:
                # no flow data -> filter is a no-op (allow all)
                self._flow_filter_active = False
            self._flow_filter_active = bool(self._flow_ok_by_day)
        else:
            self._flow_filter_active = False

        self._entry: Optional[float] = None
        self._b_used_day: Optional[str] = None  # day on which a B-entry was taken

    # ------------------------------------------------------------------
    def _flow_ok(self, day: str) -> bool:
        if not self._flow_filter_active:
            return True
        # default-deny only when we actually have a flow map; missing day -> allow
        return self._flow_ok_by_day.get(day, True)

    def _buy_full(self, price: float, reason: str, meta_extra: Dict[str, Any] | None = None) -> None:
        from ...core.kr_backtest_engine import KR_BUY_FEE_RATE

        cash = self.ctx.cash * float(self.config["buy_size_pct"])
        qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
        if qty <= 0:
            return
        md = {"reason": reason}
        if meta_extra:
            md.update(meta_extra)
        tr = self.ctx.buy(self.symbol, qty, price=price, metadata=md)
        if tr and tr.get("type") == "buy":
            self._entry = float(tr.get("price", price))

    def _sell_all(self, price: float, reason: str) -> None:
        qty = self.ctx.holdings.get(self.symbol, 0)
        if qty > 0:
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": reason})
        self._entry = None

    # ------------------------------------------------------------------
    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = str(candle["timestamp"])
        if len(ts) < 16:
            return
        day = ts[:10]
        t = ts[11:16]          # "HH:MM"
        hm = t[:2] + t[3:]     # "HHMM"
        price = float(candle["close"])

        # ----- manage open position -----
        if self._has_position():
            if t >= str(self.config["exit_time"]):
                self._sell_all(price, "eod_exit")
                return
            if self._entry and price <= self._entry * (1 - float(self.config["sl_pct"])):
                self._sell_all(price, "sl")
                return
            if self._entry and price >= self._entry * (1 + float(self.config["tp_pct"])):
                self._sell_all(price, "tp")
                return
            return

        info = self._day.get(day)
        if not info:
            return

        # ----- Trigger A: open drive at 09:05 -----
        if t == "09:05":
            drive = info.get("drive")
            if drive is not None and drive >= float(self.config["min_open_drive_pct"]) and self._flow_ok(day):
                self._buy_full(price, "open_drive", {"drive_pct": drive})
            return

        # ----- Trigger B: intraday range breakout -----
        if not bool(self.config["use_intraday_breakout"]):
            return
        if self._b_used_day == day:
            return
        # only after the range window closes, and before cutoff
        if hm <= self._range_end:
            return
        if t >= str(self.config["breakout_cutoff_time"]):
            return
        rng_high = info.get("range_high", 0.0)
        if rng_high <= 0:
            return
        buf = float(self.config["breakout_buffer_pct"])
        if price >= rng_high * (1 + buf) and self._flow_ok(day):
            self._b_used_day = day
            self._buy_full(price, "intraday_breakout", {"range_high": rng_high})
