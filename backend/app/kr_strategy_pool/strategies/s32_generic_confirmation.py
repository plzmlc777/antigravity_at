"""
S32 Generic Confirmation — 임의의 N개 시그널 조합 confirmation 전략.

config["selected_strategies"]의 strategy 이름 list를 받아 그 시그널들의
buy/sell condition을 합성하여 confirmation entry/exit.

전체 30개 시그널의 buy/sell boolean을 한 번 계산 후 selected만 합산.
"""
from typing import Any, ClassVar, Dict, List, Optional

import numpy as np
import pandas as pd

from ..base import KrStrategyBase
from ..indicators import (
    rsi, bollinger, vwap_intraday, donchian, macd,
    atr, ema, obv, supertrend, keltner,
    stochastic, williams_r, zscore as zscore_ind,
    adx, mfi, ichimoku, natr,
)


def compute_all_30_signals(
    df: pd.DataFrame, params: Dict, period_mult: int = 1
) -> Dict[str, Dict[str, pd.Series]]:
    """
    30개 strategy의 buy/sell boolean series를 한 번 계산.

    period_mult: indicator period 배수 (1=default 5분봉용, 3=1분봉 시간동등용 등).

    Returns: {strategy_name: {"buy": Series[bool], "sell": Series[bool]}}
    """
    sig: Dict[str, Dict[str, pd.Series]] = {}
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp"])
    df["day_id"] = df["ts"].dt.date.astype(str)

    pm = int(period_mult)

    # ── S1 RSI Reversion
    r = rsi(df["close"], 14 * pm)
    sig["s1_rsi"] = {"buy": r < 30, "sell": r > 70}

    # ── S2 BB Reversion
    upper, mid, lower = bollinger(df["close"], 25 * pm, 2.0)
    sig["s2_bb"] = {"buy": df["close"] < lower, "sell": df["close"] > mid}

    # ── S3 Gap Fill (간단 buy/sell signal — 시초 봉만)
    # 단순화: prev_day 마지막 close 대비 -1% 갭다운 시 entry
    daily_close = df.groupby("day_id")["close"].last()
    prev_close = df["day_id"].map(daily_close.shift(1))
    is_first = ~df["day_id"].duplicated(keep="first")
    gap_pct = (df["open"] - prev_close) / prev_close * 100
    sig["s3_gap"] = {"buy": is_first & (gap_pct <= -1.0), "sell": pd.Series(False, index=df.index)}

    # ── S4 ORB (시초 30분 high 돌파, day별)
    df["t_str"] = df["ts"].dt.strftime("%H:%M")
    or_high = df[(df["t_str"] >= "09:00") & (df["t_str"] < "09:30")].groupby("day_id")["high"].max()
    df["or_high"] = df["day_id"].map(or_high)
    sig["s4_orb"] = {"buy": (df["t_str"] >= "09:30") & (df["close"] > df["or_high"] * 1.001),
                     "sell": pd.Series(False, index=df.index)}

    # ── S5 VWAP Reversion
    vwap = vwap_intraday(df["high"], df["low"], df["close"], df["volume"], df["day_id"])
    sig["s5_vwap"] = {"buy": df["close"] < vwap * 0.985, "sell": df["close"] >= vwap}

    # ── S6 Donchian Breakout
    dch_u, dch_m, dch_l = donchian(df["high"], df["low"], 20 * pm)
    sig["s6_donchian"] = {"buy": df["close"] > dch_u, "sell": df["close"] < dch_l}

    # ── S7 MACD Cross
    m, s, _ = macd(df["close"], 12 * pm, 26 * pm, 9 * pm)
    sig["s7_macd"] = {"buy": (m.shift(1) <= s.shift(1)) & (m > s),
                       "sell": (m.shift(1) >= s.shift(1)) & (m < s)}

    # ── S8 Supertrend
    st_val, st_dir = supertrend(df["high"], df["low"], df["close"], 10 * pm, 3.0)
    sig["s8_supertrend"] = {"buy": (st_dir.shift(1) == -1) & (st_dir == 1),
                              "sell": (st_dir.shift(1) == 1) & (st_dir == -1)}

    # ── S9 Volume Spike
    avg_v = df["volume"].rolling(20 * pm).mean()
    vol_ratio = df["volume"] / avg_v.replace(0, 1e9)
    bullish = df["close"] > df["open"]
    sig["s9_vol_spike"] = {"buy": (vol_ratio >= 3.0) & bullish,
                            "sell": pd.Series(False, index=df.index)}

    # ── S10 OBV trend
    ob = obv(df["close"], df["volume"])
    ob_ema = ema(ob, 20 * pm)
    slope = ob_ema.diff(5 * pm)
    sig["s10_obv"] = {"buy": (slope.shift(1) <= 0) & (slope > 0),
                      "sell": (slope.shift(1) > 0) & (slope <= 0)}

    # ── S11 Keltner breakout
    ku, km, kl = keltner(df["high"], df["low"], df["close"], 20 * pm, 10 * pm, 2.0)
    sig["s11_keltner"] = {"buy": df["close"] > ku, "sell": df["close"] <= km}

    # ── S12 Closing Range Breakout (14:30~15:00 high 돌파, 15:00~15:25)
    cr_high = df[(df["t_str"] >= "14:30") & (df["t_str"] < "15:00")].groupby("day_id")["high"].max()
    df["cr_high"] = df["day_id"].map(cr_high)
    sig["s12_cr_break"] = {
        "buy": (df["t_str"] >= "15:00") & (df["t_str"] < "15:25")
                & (df["close"] > df["cr_high"] * 1.001),
        "sell": pd.Series(False, index=df.index),
    }

    # ── S13 Last Hour Momentum (14:00 봉, 시초 대비 +0.5% 이상)
    daily_open = df.groupby("day_id")["open"].first()
    df["day_open"] = df["day_id"].map(daily_open)
    sig["s13_last_hour"] = {
        "buy": (df["t_str"] == "14:00") & ((df["close"] - df["day_open"]) / df["day_open"] >= 0.005),
        "sell": pd.Series(False, index=df.index),
    }

    # ── S14 Daily Trend + 5m RSI Pullback (daily ema period는 timeframe-independent)
    daily_close_series = df.groupby("day_id")["close"].last()
    daily_ema = ema(daily_close_series, 5)
    daily_uptrend = (daily_close_series > daily_ema).fillna(False).shift(1).fillna(False)
    df["daily_up"] = df["day_id"].map(daily_uptrend)
    sig["s14_daily_trend_pullback"] = {
        "buy": df["daily_up"] & (r < 35), "sell": r > 65,
    }

    # ── S15 Inside Bar Breakout
    prev_h = df["high"].shift(1)
    prev_l = df["low"].shift(1)
    prev_prev_h = df["high"].shift(2)
    prev_prev_l = df["low"].shift(2)
    inside = (prev_h < prev_prev_h) & (prev_l > prev_prev_l)
    sig["s15_inside_bar"] = {"buy": inside & (df["close"] > prev_h),
                              "sell": pd.Series(False, index=df.index)}

    # ── S16 Stochastic Reversion
    k_stoch, _ = stochastic(df["high"], df["low"], df["close"], 14 * pm, 3)
    sig["s16_stoch"] = {"buy": k_stoch < 20, "sell": k_stoch > 80}

    # ── S17 Williams %R Reversion
    wr = williams_r(df["high"], df["low"], df["close"], 14 * pm)
    sig["s17_williams_r"] = {"buy": wr < -80, "sell": wr > -20}

    # ── S18 Z-score Reversion
    z = zscore_ind(df["close"], 30 * pm)
    sig["s18_zscore"] = {"buy": z < -2.0, "sell": z > 0}

    # ── S19 EMA 5/20 Cross
    ef = ema(df["close"], 5 * pm)
    es = ema(df["close"], 20 * pm)
    sig["s19_ema_cross"] = {"buy": (ef.shift(1) <= es.shift(1)) & (ef > es),
                              "sell": (ef.shift(1) >= es.shift(1)) & (ef < es)}

    # ── S20 Ichimoku Momentum
    conv, base, span_a, span_b = ichimoku(df["high"], df["low"], df["close"], 9 * pm, 26 * pm, 52 * pm)
    cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    cloud_bottom = pd.concat([span_a, span_b], axis=1).min(axis=1)
    above_cloud = df["close"] > cloud_top
    bull_cross = (conv.shift(1) <= base.shift(1)) & (conv > base)
    bear_cross = (conv.shift(1) >= base.shift(1)) & (conv < base)
    below_cloud = df["close"] < cloud_bottom
    sig["s20_ichimoku"] = {"buy": above_cloud & bull_cross,
                              "sell": bear_cross | below_cloud}

    # ── S21 ADX Filter + RSI
    a_adx = adx(df["high"], df["low"], df["close"], 14 * pm)
    sig["s21_adx_rsi"] = {"buy": (a_adx > 25) & (r < 35), "sell": r > 70}

    # ── S22 MFI Reversion
    m_mfi = mfi(df["high"], df["low"], df["close"], df["volume"], 14 * pm)
    sig["s22_mfi"] = {"buy": m_mfi < 20, "sell": m_mfi > 80}

    # ── S23 ATR Channel Reversion
    sma20 = df["close"].rolling(20 * pm).mean()
    a_atr = atr(df["high"], df["low"], df["close"], 14 * pm)
    sig["s23_atr_channel"] = {"buy": df["close"] < sma20 - 1.5 * a_atr,
                                "sell": df["close"] > sma20}

    # ── S24 NATR Filter + RSI
    nt = natr(df["high"], df["low"], df["close"], 14 * pm)
    sig["s24_natr_rsi"] = {"buy": (nt > 0.3) & (r < 30), "sell": r > 70}

    # ── S25 Lunch Fade (12:00~13:00 low 터치)
    lunch_low = df[(df["t_str"] >= "12:00") & (df["t_str"] < "13:00")].groupby("day_id")["low"].min()
    df["lunch_low"] = df["day_id"].map(lunch_low)
    sig["s25_lunch"] = {
        "buy": (df["t_str"] >= "12:30") & (df["t_str"] < "13:30")
                & df["lunch_low"].notna() & (df["close"] <= df["lunch_low"] * 1.001),
        "sell": pd.Series(False, index=df.index),
    }

    # ── S26 Open Drive (09:00 봉 close - open >= 0.5%)
    first_bar_drive = (df["t_str"] == "09:00") & ((df["close"] - df["open"]) / df["open"] >= 0.005)
    df["drive_today"] = first_bar_drive.groupby(df["day_id"]).transform("any")
    sig["s26_open_drive"] = {"buy": (df["t_str"] == "09:05") & df["drive_today"],
                               "sell": pd.Series(False, index=df.index)}

    # ── S27 15m EMA Trend (간단화 — daily uptrend로 대체)
    sig["s27_15m_ema_trend"] = {"buy": df["daily_up"] & (r < 35), "sell": r > 65}

    # ── S28 Daily ATR Filter (어제 daily ATR% > 2%)
    daily_high = df.groupby("day_id")["high"].max()
    daily_low = df.groupby("day_id")["low"].min()
    daily_clo = df.groupby("day_id")["close"].last()
    d_atr = atr(daily_high, daily_low, daily_clo, 5)
    d_atr_pct = (d_atr / daily_clo * 100).shift(1).fillna(0)
    df["d_atr_pct"] = df["day_id"].map(d_atr_pct)
    sig["s28_daily_atr"] = {"buy": (df["d_atr_pct"] > 2.0) & (r < 30), "sell": r > 70}

    # ── S29 Bullish Engulfing
    prev_o = df["open"].shift(1)
    prev_c = df["close"].shift(1)
    bearish_prev = prev_c < prev_o
    bullish_now = df["close"] > df["open"]
    sig["s29_engulfing"] = {
        "buy": bearish_prev & bullish_now & (df["close"] > prev_o) & (df["open"] < prev_c),
        "sell": pd.Series(False, index=df.index),
    }

    # ── S30 Bullish Pin Bar
    body = (df["close"] - df["open"]).abs()
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    pin = (df["close"] > df["open"]) & (lower_wick >= 2 * body.replace(0, 1e-9)) & (lower_wick > upper_wick)
    sig["s30_pin_bar"] = {"buy": pin, "sell": pd.Series(False, index=df.index)}

    return sig


class S32GenericConfirmation(KrStrategyBase):
    """selected_strategies list로 임의 조합 confirmation 전략."""
    name = "s32_generic_confirmation"
    TIMEFRAME = "5m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        "selected_strategies": [],
        "min_buy_confirmations": 2,
        "min_sell_confirmations": 1,
        "buy_size_pct": 0.7,
        "sl_pct": 0.025,
        "tp_pct": 0.03,
        "exit_time": "15:25",
        "period_multiplier": 1,
    }


class S32_1m_x3(S32GenericConfirmation):
    """1분봉 + period × 3 wrapper for combinatorial sweep."""
    name = "s32_1m_x3"
    TIMEFRAME = "1m"
    DEFAULT_PARAMS: ClassVar[Dict[str, Any]] = {
        **S32GenericConfirmation.DEFAULT_PARAMS,
        "period_multiplier": 3,
    }

    def initialize(self) -> None:
        feed = self.ctx.feeds[self.symbol]
        df = pd.DataFrame(feed)
        period_mult = int(self.config.get("period_multiplier", 1))
        all_signals = compute_all_30_signals(df, self.config, period_mult=period_mult)

        selected: List[str] = list(self.config["selected_strategies"])
        if not selected:
            raise ValueError("selected_strategies must not be empty")

        # 합산 buy_count, sell_count
        bc = pd.DataFrame({s: all_signals[s]["buy"].fillna(False).astype(int) for s in selected}).sum(axis=1)
        sc = pd.DataFrame({s: all_signals[s]["sell"].fillna(False).astype(int) for s in selected}).sum(axis=1)

        self._bc = dict(zip(df["timestamp"], bc.values))
        self._sc = dict(zip(df["timestamp"], sc.values))
        self._entry: Optional[float] = None

    def on_data(self, candle: Dict[str, Any]) -> None:
        ts = candle["timestamp"]
        price = float(candle["close"])
        bc = self._bc.get(ts, 0)
        sc = self._sc.get(ts, 0)
        t = str(ts)[11:16] if len(str(ts)) >= 16 else ""

        # EOD 청산
        if self._has_position() and t >= str(self.config["exit_time"]):
            qty = self.ctx.holdings.get(self.symbol, 0)
            self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": "eod_exit"})
            self._entry = None
            return

        # SL/TP/sell-confirm
        if self._has_position() and self._entry:
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
            if sc >= int(self.config["min_sell_confirmations"]):
                qty = self.ctx.holdings.get(self.symbol, 0)
                self.ctx.sell(self.symbol, qty, price=price, metadata={"reason": f"sell={sc}"})
                self._entry = None
                return
            return

        # 진입
        if bc >= int(self.config["min_buy_confirmations"]):
            from ...core.kr_backtest_engine import KR_BUY_FEE_RATE
            cash = self.ctx.cash * float(self.config["buy_size_pct"])
            qty = int(cash / (price * (1 + KR_BUY_FEE_RATE)))
            if qty > 0:
                tr = self.ctx.buy(self.symbol, qty, price=price,
                                  metadata={"reason": f"buy={bc}"})
                if tr and tr.get("type") == "buy":
                    self._entry = float(tr.get("price", price))
