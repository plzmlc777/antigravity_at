"""
Environment Encoder — 상속 기반 시장별 확장 구조.

```
EnvEncoderBase (universal 10dim, market-agnostic)
    ├─ KrEnvEncoder      (+ time_sin/cos + dow one-hot 5 = +7dim → 총 17dim)
    ├─ CryptoEnvEncoder  (v1: +0dim → 총 10dim, future: + funding/dominance)
    └─ UsStockEnvEncoder (+ premarket_gap, vix_proxy, spy_corr_5d, session_flag = +4 → 14dim)
```

원칙:
  1. UNIVERSAL_FEATURES (10개) 는 base class가 정의 — 시장 무관.
  2. EXTENSION_FEATURES 는 subclass가 add — 시장 특수 미시구조.
  3. SESSION_WINDOW 는 subclass가 결정 — daily resample 시 between_time 필터.
  4. Schema (feature_names) 는 base + extension 순서로 결정. 모델은 자기 encoder type을 기억.

신규 시장 추가:
  - HkStockEnvEncoder, JpStockEnvEncoder 등 EnvEncoderBase 상속
  - EXTENSION_FEATURES 정의
  - SESSION_WINDOW 설정
  - _encode_extension(self, feed_1m, ts) 구현
  - ENCODER_REGISTRY 등록
"""
from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List, Optional, Tuple, Type

import numpy as np
import pandas as pd


# ───────────────────────── Base helpers ─────────────────────────


def _safe(v: float) -> float:
    if v is None or not np.isfinite(v):
        return 0.0
    return float(v)


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _donchian(high: pd.Series, low: pd.Series, period: int = 20):
    upper = high.shift(1).rolling(period).max()
    lower = low.shift(1).rolling(period).min()
    mid = (upper + lower) / 2.0
    return upper, mid, lower


def _resample_with_session(
    df_1m: pd.DataFrame,
    freq: str,
    session_window: Optional[Tuple[str, str]] = None,
) -> pd.DataFrame:
    src = df_1m
    if session_window is not None:
        src = src.between_time(session_window[0], session_window[1])
    if not len(src):
        return pd.DataFrame()
    if freq.upper() == "1D":
        out = src.resample("1D").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        ).dropna(subset=["open"])
    else:
        out = src.resample(freq).agg(
            {"open": "first", "high": "max", "low": "min",
             "close": "last", "volume": "sum"}
        ).dropna(subset=["open"])
    return out


# ───────────────────────── Base class ─────────────────────────


class EnvEncoderBase(ABC):
    """
    Market-agnostic universal env encoder.

    Universal feature layout (10 dims, 순서 고정):
        0  vol_regime              30-period rolling realized-vol pct rank (daily)
        1  trend_short             EMA20_1h slope (current vs 3-bar back)
        2  trend_long              (close_1d - EMA10_1d) / |close_1d|
        3  range_width_short       Donchian20 width / close (1h)
        4  range_width_long        Donchian20 width / close (1d)
        5  liquidity_z             5d MA volume z-score vs 30d distribution
        6  momentum_short          1d return
        7  momentum_long           5d return
        8  realized_vol_intraday   std of 1m returns over recent intraday_window bars
        9  vol_of_vol              std of last 5 daily vol values

    Subclasses override:
      - EXTENSION_FEATURES: List[str]  (추가 feature 이름들)
      - SESSION_WINDOW: Optional[Tuple[str, str]]  (intraday session 필터)
      - INTRADAY_WINDOW: int  (realized_vol_intraday 계산용 1m bar 수)
      - _encode_extension(self, df, target, prior_days, h1_df) -> np.ndarray
    """

    # Universal — 모든 시장 공통 (override 금지)
    UNIVERSAL_FEATURES: List[str] = [
        "vol_regime",
        "trend_short",
        "trend_long",
        "range_width_short",
        "range_width_long",
        "liquidity_z",
        "momentum_short",
        "momentum_long",
        "realized_vol_intraday",
        "vol_of_vol",
    ]

    # Extension — subclass가 override
    EXTENSION_FEATURES: List[str] = []

    # 시장별 세션 windowq — None이면 24/7
    SESSION_WINDOW: Optional[Tuple[str, str]] = None

    # realized_vol_intraday 계산용 1m bar 수 — 시장별 1 trading day 근사
    INTRADAY_WINDOW: int = 240

    # 식별자 — model artifact에 저장됨
    MARKET_TAG: str = "base"

    # ─── public API ───

    @property
    def feature_names(self) -> List[str]:
        return list(self.UNIVERSAL_FEATURES) + list(self.EXTENSION_FEATURES)

    @property
    def feature_dim(self) -> int:
        return len(self.feature_names)

    def encode(self, feed_1m: List[Dict[str, Any]], ts: str) -> np.ndarray:
        """Encode market state at timestamp `ts`. Returns (feature_dim,) array."""
        if not feed_1m:
            return np.zeros(self.feature_dim, dtype=float)

        df = pd.DataFrame(feed_1m)
        df["ts"] = pd.to_datetime(df["timestamp"])
        df = df.set_index("ts").sort_index()

        target = pd.Timestamp(ts)
        df = df.loc[df.index <= target]
        if df.empty:
            return np.zeros(self.feature_dim, dtype=float)

        # Common derivative DFs
        daily_df = _resample_with_session(df, "1D", session_window=self.SESSION_WINDOW)
        prior_days = (
            daily_df.loc[daily_df.index < target.normalize()]
            if not daily_df.empty else pd.DataFrame()
        )
        h1_df = _resample_with_session(df, "1H", session_window=self.SESSION_WINDOW)

        # Universal 10
        u_vec = self._encode_universal(df, target, prior_days, h1_df)

        # Extension (subclass)
        e_vec = self._encode_extension(df, target, prior_days, h1_df)

        vec = np.concatenate([u_vec, e_vec])
        vec = np.where(np.isfinite(vec), vec, 0.0)
        return vec

    # ─── universal logic (final, do not override) ───

    def _encode_universal(
        self,
        df: pd.DataFrame,
        target: pd.Timestamp,
        prior_days: pd.DataFrame,
        h1_df: pd.DataFrame,
    ) -> np.ndarray:
        # 0. vol_regime
        if len(prior_days) >= 5:
            d_returns = prior_days["close"].pct_change().dropna()
            vol_30 = d_returns.rolling(30, min_periods=5).std()
            if len(vol_30.dropna()) >= 1:
                rank = vol_30.rank(pct=True)
                vol_regime = _safe(rank.iloc[-1])
            else:
                vol_regime = 0.5
        else:
            vol_regime = 0.5

        # 1. trend_short
        trend_short = 0.0
        if len(h1_df) >= 5:
            e1h = _ema(h1_df["close"], 20)
            if len(e1h.dropna()) >= 4:
                cur = e1h.iloc[-1]
                prev = e1h.iloc[-4]
                denom = abs(prev) if abs(prev) > 1e-9 else 1.0
                trend_short = _safe((cur - prev) / denom)

        # 2. trend_long
        trend_long = 0.0
        if len(prior_days) >= 3:
            e1d = _ema(prior_days["close"], 10)
            if len(e1d.dropna()) >= 1:
                last_close = prior_days["close"].iloc[-1]
                last_ema = e1d.iloc[-1]
                denom = abs(last_close) if abs(last_close) > 1e-9 else 1.0
                trend_long = _safe((last_close - last_ema) / denom)

        # 3. range_width_short
        range_width_short = 0.0
        if len(h1_df) >= 21:
            upper, mid, lower = _donchian(h1_df["high"], h1_df["low"], 20)
            cur_close = h1_df["close"].iloc[-1]
            if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]) and abs(cur_close) > 1e-9:
                range_width_short = _safe((upper.iloc[-1] - lower.iloc[-1]) / cur_close)

        # 4. range_width_long
        range_width_long = 0.0
        if len(prior_days) >= 21:
            upper, mid, lower = _donchian(prior_days["high"], prior_days["low"], 20)
            cur_close = prior_days["close"].iloc[-1]
            if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]) and abs(cur_close) > 1e-9:
                range_width_long = _safe((upper.iloc[-1] - lower.iloc[-1]) / cur_close)

        # 5. liquidity_z
        liquidity_z = 0.0
        if len(prior_days) >= 5:
            v = prior_days["volume"]
            v_5 = v.rolling(5, min_periods=2).mean()
            v_30_mean = v.rolling(30, min_periods=5).mean()
            v_30_std = v.rolling(30, min_periods=5).std(ddof=0)
            last_v5 = v_5.iloc[-1]
            last_mean = v_30_mean.iloc[-1]
            last_std = v_30_std.iloc[-1]
            if pd.notna(last_v5) and pd.notna(last_mean) and pd.notna(last_std) and last_std > 0:
                liquidity_z = _safe((last_v5 - last_mean) / last_std)

        # 6. momentum_short
        momentum_short = 0.0
        if len(prior_days) >= 2:
            c0 = prior_days["close"].iloc[-1]
            c1 = prior_days["close"].iloc[-2]
            if abs(c1) > 1e-9:
                momentum_short = _safe(c0 / c1 - 1.0)

        # 7. momentum_long
        momentum_long = 0.0
        if len(prior_days) >= 6:
            last5 = prior_days["close"].iloc[-1]
            prior5 = prior_days["close"].iloc[-6]
            if abs(prior5) > 1e-9:
                momentum_long = _safe(last5 / prior5 - 1.0)

        # 8. realized_vol_intraday
        realized_vol_intraday = 0.0
        last_n = df.tail(self.INTRADAY_WINDOW)
        if len(last_n) >= 30:
            rets = last_n["close"].pct_change().dropna()
            if len(rets) >= 20:
                realized_vol_intraday = _safe(float(rets.std(ddof=0)))

        # 9. vol_of_vol
        vol_of_vol = 0.0
        if len(prior_days) >= 10:
            d_returns = prior_days["close"].pct_change().dropna()
            vol_series = d_returns.rolling(5, min_periods=3).std().dropna()
            if len(vol_series) >= 5:
                recent_vols = vol_series.iloc[-5:]
                vol_of_vol = _safe(float(recent_vols.std(ddof=0)))

        return np.array(
            [
                vol_regime, trend_short, trend_long,
                range_width_short, range_width_long,
                liquidity_z, momentum_short, momentum_long,
                realized_vol_intraday, vol_of_vol,
            ],
            dtype=float,
        )

    # ─── extension (subclass override) ───

    def _encode_extension(
        self,
        df: pd.DataFrame,
        target: pd.Timestamp,
        prior_days: pd.DataFrame,
        h1_df: pd.DataFrame,
    ) -> np.ndarray:
        """기본 구현: 빈 array. Subclass override 권장."""
        return np.zeros(len(self.EXTENSION_FEATURES), dtype=float)


# ───────────────────────── KR (한국 주식) ─────────────────────────


class KrEnvEncoder(EnvEncoderBase):
    """
    한국 주식 — KOSPI/KOSDAQ 정규장 09:00-15:30 KST.

    KR-specific 미시구조:
      - time_sin/cos: 일중 6.5h 세션 위치 (개장/점심/종장 효과)
      - dow_one_hot: 월/금 주말효과 + 화/목 차이
    """

    EXTENSION_FEATURES = [
        "time_sin",
        "time_cos",
        "dow_mon",
        "dow_tue",
        "dow_wed",
        "dow_thu",
        "dow_fri",
    ]
    SESSION_WINDOW = ("09:00", "15:30")
    INTRADAY_WINDOW = 390  # 6.5h × 60 = 1 KR trading day
    MARKET_TAG = "kr"

    _SESSION_OPEN_MIN = 9 * 60        # 540
    _SESSION_LEN_MIN = 6 * 60 + 30    # 390

    def _encode_extension(self, df, target, prior_days, h1_df) -> np.ndarray:
        # time_sin/cos — minute-of-session
        minute = target.hour * 60 + target.minute - self._SESSION_OPEN_MIN
        minute = max(0, min(self._SESSION_LEN_MIN, minute))
        angle = 2.0 * np.pi * (minute / max(self._SESSION_LEN_MIN, 1))
        time_sin = float(np.sin(angle))
        time_cos = float(np.cos(angle))

        # dow one-hot (Mon=0..Fri=4)
        dow_oh = [0.0] * 5
        wd = target.weekday()
        if 0 <= wd <= 4:
            dow_oh[wd] = 1.0

        return np.array([time_sin, time_cos, *dow_oh], dtype=float)


# ───────────────────────── Crypto (Binance USDT-M Futures) ─────────────────────────


class CryptoEnvEncoder(EnvEncoderBase):
    """
    Binance USDT-M Perpetual Futures — 24/7.

    v1: extension 없음 (universal 10dim만).
    Future v2: funding_rate_z, btc_dominance_change, oi_z 추가 가능 (placeholder).
    """

    EXTENSION_FEATURES = []  # v1
    SESSION_WINDOW = None     # 24/7
    INTRADAY_WINDOW = 240     # 4h
    MARKET_TAG = "crypto"

    def _encode_extension(self, df, target, prior_days, h1_df) -> np.ndarray:
        return np.array([], dtype=float)


# ───────────────────────── US Stocks (NYSE/NASDAQ) — stub ─────────────────────────


class UsStockEnvEncoder(EnvEncoderBase):
    """
    미국 주식 — NYSE/NASDAQ 정규장 09:30-16:00 EST.
    Stub: 데이터 파이프라인 없으면 extension은 0으로 채움.
    실데이터 가용 시 _encode_extension에 실제 계산 구현.

    예정 features:
      - premarket_gap_pct: 04:00-09:30 premarket 가격 변동
      - vix_proxy: 30-day realized vol annualized
      - spy_corr_5d: 5d return vs SPY 5d return correlation
      - session_phase: 0=open, 0.5=mid, 1=close 진행도 (intraday position)
    """

    EXTENSION_FEATURES = [
        "premarket_gap_pct",
        "vix_proxy",
        "spy_corr_5d",
        "session_phase",
    ]
    SESSION_WINDOW = ("09:30", "16:00")
    INTRADAY_WINDOW = 390  # 6.5h
    MARKET_TAG = "us"

    _SESSION_OPEN_MIN = 9 * 60 + 30    # 570
    _SESSION_LEN_MIN = 6 * 60 + 30     # 390

    def _encode_extension(self, df, target, prior_days, h1_df) -> np.ndarray:
        # Stub: vix_proxy + session_phase는 OHLCV로 계산 가능, 나머지는 0
        # vix_proxy: 30d realized vol × sqrt(252) annualized
        vix_proxy = 0.0
        if len(prior_days) >= 30:
            d_returns = prior_days["close"].pct_change().dropna().tail(30)
            if len(d_returns) >= 10:
                vix_proxy = _safe(float(d_returns.std(ddof=0)) * np.sqrt(252))

        # session_phase
        minute = target.hour * 60 + target.minute - self._SESSION_OPEN_MIN
        minute = max(0, min(self._SESSION_LEN_MIN, minute))
        session_phase = float(minute) / max(self._SESSION_LEN_MIN, 1)

        # premarket_gap_pct, spy_corr_5d: 데이터 없음 → 0
        return np.array([0.0, vix_proxy, 0.0, session_phase], dtype=float)


# ───────────────────────── Registry ─────────────────────────


ENCODER_REGISTRY: Dict[str, Type[EnvEncoderBase]] = {
    "kr": KrEnvEncoder,
    "crypto": CryptoEnvEncoder,
    "us": UsStockEnvEncoder,
}


def get_encoder(market: str) -> EnvEncoderBase:
    """Factory: market 이름 → encoder instance."""
    if market not in ENCODER_REGISTRY:
        raise ValueError(f"Unknown market: {market}. Available: {list(ENCODER_REGISTRY)}")
    return ENCODER_REGISTRY[market]()


# ───────────────────────── Backwards-compat (지금 코드용) ─────────────────────────

# 기존 함수형 API 사용한 코드를 위해 호환 wrapper 유지
def encode_environment_kr(feed_1m, ts):
    """Deprecated: KrEnvEncoder().encode(feed_1m, ts) 사용 권장."""
    return get_encoder("kr").encode(feed_1m, ts)


def encode_environment_crypto(feed_1m, ts):
    """Deprecated: CryptoEnvEncoder().encode(feed_1m, ts) 사용 권장."""
    return get_encoder("crypto").encode(feed_1m, ts)


def encode_environment(feed_1m, ts, session_window=None, intraday_window=240):
    """Deprecated: get_encoder(market).encode() 사용 권장."""
    if session_window is None:
        return get_encoder("crypto").encode(feed_1m, ts)
    elif session_window == ("09:00", "15:30"):
        return get_encoder("kr").encode(feed_1m, ts)
    elif session_window == ("09:30", "16:00"):
        return get_encoder("us").encode(feed_1m, ts)
    raise ValueError(f"Unknown session_window: {session_window}")


# 모듈 레벨 FEATURE_NAMES — universal 10개. encoder별은 .feature_names 사용.
FEATURE_NAMES = list(EnvEncoderBase.UNIVERSAL_FEATURES)
FEATURE_DIM = len(FEATURE_NAMES)
