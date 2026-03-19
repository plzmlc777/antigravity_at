"""
Martingale Fitness Screener.
Finds symbols optimal for martingale strategies:
  - Small moves (low big-move probability)
  - Frequent oscillations (high mean-reversion)
  - High volume & liquidity
  - Stable range (no expanding volatility)
  - Low trend strength

"작은 파도가 자주 치는 바다" = 마틴게일 천국
"""
import asyncio
import logging
import math
from datetime import datetime
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
import httpx

from config import BINANCE_FUTURES_BASE, COLLECT_SYMBOLS
from db import SessionLocal, OHLCVHourly, FundingRate

logger = logging.getLogger(__name__)

# Cache
_latest_result: Dict[str, Any] = {}

# Settings
SCREEN_INTERVAL_HOURS = 6
MIN_CANDLES = 168  # 7 days of hourly data minimum
ANALYSIS_CANDLES = 500  # ~20 days for robust stats


def _sanitize_for_json(obj):
    """Replace NaN/Inf with None."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _calc_hurst(price_series: pd.Series, max_lag: int = 100) -> float:
    """
    Hurst exponent via rescaled range (R/S) method on RETURNS (not price).
    H < 0.5 = mean-reverting (good for martingale)
    H = 0.5 = random walk
    H > 0.5 = trending (bad for martingale)
    """
    # Use log returns for stationarity
    returns = np.log(price_series / price_series.shift(1)).dropna().values
    n = len(returns)
    if n < 80:
        return 0.5  # insufficient data → neutral

    # Use multiple lag sizes (powers of 2 for clean division)
    lags = [int(2 ** i) for i in np.arange(3, min(np.log2(n / 2), 8), 0.5)]
    if len(lags) < 4:
        return 0.5

    rs_values = []
    for lag in lags:
        rs_list = []
        n_chunks = n // lag
        for i in range(n_chunks):
            chunk = returns[i * lag:(i + 1) * lag]
            mean_chunk = chunk.mean()
            deviations = chunk - mean_chunk
            cumdev = np.cumsum(deviations)
            R = cumdev.max() - cumdev.min()
            S = chunk.std(ddof=1)
            if S > 1e-12:
                rs_list.append(R / S)
        if len(rs_list) >= 2:
            rs_values.append((np.log(lag), np.log(np.mean(rs_list))))

    if len(rs_values) < 3:
        return 0.5

    x = np.array([v[0] for v in rs_values])
    y = np.array([v[1] for v in rs_values])
    slope, _ = np.polyfit(x, y, 1)
    return float(np.clip(slope, 0.0, 1.0))


def _calc_mean_crossing_rate(series: pd.Series, window: int = 48) -> float:
    """
    Mean-crossing frequency: how often price crosses its rolling mean.
    Higher = more oscillation = better for martingale.
    Returns crossings per 24 hours.
    """
    if len(series) < window + 10:
        return 0.0
    ma = series.rolling(window).mean()
    diff = series - ma
    diff = diff.dropna()
    crossings = ((diff.shift(1) * diff) < 0).sum()
    hours = len(diff)
    return round(float(crossings) / max(hours, 1) * 24, 4)


def _calc_autocorrelation(returns: pd.Series, lag: int = 1) -> float:
    """
    Returns autocorrelation at given lag.
    Negative = mean-reverting (good for martingale).
    """
    if len(returns) < lag + 20:
        return 0.0
    return float(returns.autocorr(lag=lag))


def _calc_range_stability(atr_series: pd.Series) -> float:
    """
    Coefficient of variation of ATR.
    Lower = more stable range = better for martingale.
    Returns 0-1 score (1 = perfectly stable).
    """
    atr = atr_series.dropna()
    if len(atr) < 20:
        return 0.5
    cv = float(atr.std() / atr.mean()) if atr.mean() > 0 else 1.0
    # cv typically 0.1 ~ 0.8, map to 0~1 score (lower cv = higher score)
    return float(np.clip(1.0 - cv, 0.0, 1.0))


def _calc_oscillation_intensity(df: pd.DataFrame) -> float:
    """
    Measures how actively price oscillates within its range.
    Sum of absolute per-bar returns / total range.
    Higher = more "choppy" movement = more martingale opportunities.
    """
    close = df['close']
    if len(close) < 50:
        return 0.0
    abs_returns = close.pct_change().abs().sum()
    total_range = (close.max() - close.min()) / close.mean()
    if total_range <= 0:
        return 0.0
    return float(abs_returns / max(total_range, 0.001))


def analyze_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Analyze a single symbol for martingale fitness.
    Returns fitness scores and component metrics.
    """
    db = SessionLocal()
    try:
        rows = db.query(OHLCVHourly).filter(
            OHLCVHourly.symbol == symbol,
        ).order_by(OHLCVHourly.timestamp.desc()).limit(ANALYSIS_CANDLES).all()

        if not rows or len(rows) < MIN_CANDLES:
            return None

        ohlcv = pd.DataFrame([{
            'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
            'low': r.low, 'close': r.close, 'volume': r.volume
        } for r in rows]).sort_values('timestamp').reset_index(drop=True)

        # Funding rate for holding cost
        earliest = ohlcv['timestamp'].min()
        fr_rows = db.query(FundingRate).filter(
            FundingRate.symbol == symbol,
            FundingRate.timestamp >= earliest,
        ).order_by(FundingRate.timestamp).all()
        avg_funding = 0.0
        if fr_rows:
            rates = [r.funding_rate for r in fr_rows]
            avg_funding = float(np.mean(np.abs(rates)))

    finally:
        db.close()

    close = ohlcv['close'].astype(float)
    high = ohlcv['high'].astype(float)
    low = ohlcv['low'].astype(float)
    volume = ohlcv['volume'].astype(float)

    # Skip symbols with no real price data
    if close.std() == 0 or close.iloc[-1] <= 0:
        return None

    returns = close.pct_change().dropna()

    # ========== Component Metrics ==========

    # 1. Hurst exponent (mean reversion)
    hurst = _calc_hurst(close)

    # 2. Mean-crossing rate (oscillation frequency)
    cross_rate_short = _calc_mean_crossing_rate(close, window=24)  # 1-day MA
    cross_rate_long = _calc_mean_crossing_rate(close, window=48)   # 2-day MA
    cross_rate = (cross_rate_short + cross_rate_long) / 2

    # 3. Autocorrelation (negative = mean-reverting)
    autocorr_1 = _calc_autocorrelation(returns, lag=1)
    autocorr_3 = _calc_autocorrelation(returns, lag=3)
    autocorr_avg = (autocorr_1 + autocorr_3) / 2

    # 4. Range stability (ATR consistency)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr_14 = tr.rolling(14).mean()
    atr_pct = (atr_14 / close).dropna()
    range_stability = _calc_range_stability(atr_pct)

    # 5. Oscillation intensity (choppiness)
    osc_intensity = _calc_oscillation_intensity(ohlcv)

    # 6. ADX (trend strength) — low is better
    plus_dm = high.diff().where(lambda x: (x > 0) & (x > -low.diff()), 0.0)
    minus_dm = (-low.diff()).where(lambda x: (x > 0) & (x > high.diff()), 0.0)
    atr_smooth = tr.rolling(14).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(14).mean()
    current_adx = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 25.0

    # 7. Volume & liquidity
    avg_volume_usd = float((volume * close).tail(72).mean())  # 3-day avg
    current_price = float(close.iloc[-1])
    current_atr_pct = float(atr_pct.iloc[-1]) if len(atr_pct) > 0 else 0.02

    # 8. Typical oscillation range (for grid spacing estimation)
    pct_moves = returns.abs()
    median_move = float(pct_moves.median())
    p75_move = float(pct_moves.quantile(0.75))

    # ========== Scoring ==========
    # Crypto Hurst typically 0.45~0.70. Lower = more mean-reverting.
    # H=0.40 → 30pts, H=0.50 → 18pts, H=0.60 → 6pts, H=0.65+ → 0pts

    # Mean reversion score (30 pts): Hurst-based + autocorrelation bonus
    hurst_score = max(0, (0.65 - hurst) / 0.25 * 25)  # 0-25 from Hurst
    autocorr_bonus = max(0, -autocorr_avg) * 50  # negative autocorr = bonus (0~5)
    mean_reversion_score = min(hurst_score + autocorr_bonus, 30)

    # Oscillation score (25 pts): frequent crossings + high intensity
    # cross_rate: typically 1.5-4 per day in crypto. 3+ = great
    osc_cross_score = min(cross_rate / 3.5, 1.5) * 12  # 0-18
    osc_intensity_score = min(osc_intensity / 30.0, 1.0) * 7  # 0-7
    oscillation_score = min(osc_cross_score + osc_intensity_score, 25)

    # Anti-trend score (20 pts): low ADX
    # ADX typically 15-60 in crypto. <25 = good for martingale
    adx_score = max(0, (35 - current_adx) / 35) * 20
    anti_trend_score = min(max(0, adx_score), 20)

    # Range stability score (15 pts)
    stability_score = range_stability * 15

    # Cost score (10 pts): low funding
    # avg_funding: typically 0.0001~0.001. Lower is better
    funding_score = max(0, (0.0008 - avg_funding) / 0.0008) * 10
    cost_score = max(0, min(funding_score, 10))

    # Total fitness (0-100)
    fitness = round(
        mean_reversion_score +
        oscillation_score +
        anti_trend_score +
        stability_score +
        cost_score,
    2)

    # Grade
    if fitness >= 65:
        grade = 'A'
    elif fitness >= 50:
        grade = 'B'
    elif fitness >= 35:
        grade = 'C'
    else:
        grade = 'D'

    # Recommended grid spacing based on typical oscillation
    # Grid = median move * 2 ~ p75 move * 1.5
    grid_spacing_pct = round((median_move * 2 + p75_move * 1.5) / 2 * 100, 3)
    grid_spacing_pct = max(grid_spacing_pct, 0.1)  # min 0.1%

    # Recommended max levels based on ATR
    # ATR * 5 / grid_spacing = approximate levels before hitting typical extreme
    max_levels = int(current_atr_pct * 100 * 5 / max(grid_spacing_pct, 0.1))
    max_levels = max(3, min(max_levels, 20))

    result = {
        'symbol': symbol,
        'current_price': current_price,
        'fitness': fitness,
        'grade': grade,

        # Component scores (for transparency)
        'scores': {
            'mean_reversion': round(mean_reversion_score, 2),
            'oscillation': round(oscillation_score, 2),
            'anti_trend': round(anti_trend_score, 2),
            'range_stability': round(stability_score, 2),
            'cost': round(cost_score, 2),
        },

        # Raw metrics
        'metrics': {
            'hurst_exponent': round(hurst, 4),
            'mean_cross_rate_24h': round(cross_rate, 2),
            'autocorrelation_1': round(autocorr_1, 4),
            'autocorrelation_3': round(autocorr_3, 4),
            'adx': round(current_adx, 2),
            'atr_pct': round(current_atr_pct, 4),
            'range_stability': round(range_stability, 4),
            'oscillation_intensity': round(osc_intensity, 2),
            'avg_funding_rate': round(avg_funding, 6),
            'avg_volume_usd_3d': round(avg_volume_usd, 0),
            'median_move_pct': round(median_move * 100, 4),
            'p75_move_pct': round(p75_move * 100, 4),
        },

        # Recommendations
        'recommendation': {
            'grid_spacing_pct': grid_spacing_pct,
            'max_levels': max_levels,
            'preferred_direction': 'neutral',  # martingale is direction-agnostic
        },

        'data_points': len(ohlcv),
    }

    return result


async def screen_martingale_candidates(
    symbols: List[str] = None,
    top_n: int = 10,
    min_volume_usd: float = 30_000_000,
) -> Dict[str, Any]:
    """
    2-stage martingale fitness screening.
    Stage 1 (fast): Binance ticker → high volume + low change + high trade count
                     = "활발한 횡보" 종목 50개 선별
    Stage 2 (deep): DB OHLCV → Hurst, oscillation, ADX, range stability 정밀 분석
    """
    global _latest_result

    # Stage 1: Fast ticker-based pre-screening
    if symbols:
        # User-provided list → skip stage 1, just volume filter
        stage1 = await _stage1_ticker_screen(min_volume_usd, override_symbols=symbols)
    else:
        stage1 = await _stage1_ticker_screen(min_volume_usd)

    logger.info(f'[Martingale] Stage 1: {len(stage1)} candidates from ticker screen')

    # Stage 2: Deep analysis with DB data
    rankings = []
    for entry in stage1:
        sym = entry['symbol']
        try:
            result = analyze_symbol(sym)
            if result:
                # Carry over stage1 ticker metrics
                result['ticker'] = {
                    'quote_volume_24h': entry['quoteVolume'],
                    'trade_count_24h': entry['count'],
                    'price_change_pct': entry['priceChangePercent'],
                    'choppiness': entry.get('choppiness', 0),
                }
                rankings.append(result)
        except Exception as e:
            logger.error(f'[Martingale] {sym} analysis error: {e}')

    # Sort by fitness (descending)
    rankings.sort(key=lambda x: x['fitness'], reverse=True)

    for i, r in enumerate(rankings):
        r['rank'] = i + 1

    top = rankings[:top_n]

    _latest_result = _sanitize_for_json({
        'scanned_at': datetime.utcnow().isoformat(),
        'stage1_candidates': len(stage1),
        'stage2_analyzed': len(rankings),
        'top_n': top_n,
        'min_volume_usd': min_volume_usd,
        'candidates': top,
        'all_rankings': rankings,
    })

    logger.info(
        f'[Martingale] Stage 1→{len(stage1)}, Stage 2→{len(rankings)} analyzed. '
        f'Top 3: {[(r["symbol"], r["fitness"], r["grade"]) for r in top[:3]]}'
    )

    return _latest_result


# ========== Stage 1: Fast ticker pre-screen ==========

STAGE1_TOP_N = 50
EXCLUDED_SUFFIXES = {'BUSD', 'TUSD', 'USDCUSDT', 'DAIUSDT', 'FDUSDUSDT'}
EXCLUDED_CONTAINS = {'UP', 'DOWN', 'BEAR', 'BULL', '1000000'}


async def _stage1_ticker_screen(
    min_volume_usd: float,
    override_symbols: List[str] = None,
) -> List[Dict]:
    """
    Stage 1: Binance 24hr ticker → 마틴게일 전용 사전 스크리닝.
    Scoring: 높은 거래량 + 높은 체결수 + 낮은 변동률 + 레인지 내 체결 밀도.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr")
            resp.raise_for_status()
            tickers = resp.json()
    except Exception as e:
        logger.error(f'[Martingale] Stage 1 ticker fetch failed: {e}')
        return []

    candidates = []
    for t in tickers:
        symbol = t.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        if symbol in EXCLUDED_SUFFIXES:
            continue
        if any(x in symbol for x in EXCLUDED_CONTAINS):
            continue

        # If override list given, only consider those symbols
        if override_symbols and symbol not in override_symbols:
            continue

        quote_vol = float(t.get('quoteVolume', 0))
        if quote_vol < min_volume_usd:
            continue

        high = float(t.get('highPrice', 0))
        low = float(t.get('lowPrice', 0))
        last = float(t.get('lastPrice', 0))
        count = int(t.get('count', 0))
        price_change = abs(float(t.get('priceChangePercent', 0)))

        if low <= 0 or last <= 0:
            continue

        range_pct = (high - low) / low * 100

        # === Martingale-specific metrics ===

        # 1. Choppiness: trade count per % of range
        #    High = many trades packed in small range = active sideways
        choppiness = count / max(range_pct, 0.01)

        # 2. Volume per trade (small avg = retail activity = more oscillation)
        avg_trade_size = quote_vol / max(count, 1)

        # 3. Low directional bias (|price_change| close to 0)
        #    price_change near 0 = no clear trend today
        sideways_score = max(0, 1.0 - price_change / 5.0)  # 0%→1.0, 5%→0.0

        candidates.append({
            'symbol': symbol,
            'quoteVolume': quote_vol,
            'count': count,
            'priceChangePercent': float(t.get('priceChangePercent', 0)),
            'lastPrice': last,
            'highPrice': high,
            'lowPrice': low,
            'range_pct': round(range_pct, 4),
            'choppiness': round(choppiness, 2),
            'avg_trade_size': round(avg_trade_size, 2),
            'sideways_score': round(sideways_score, 4),
        })

    if not candidates:
        return []

    # Normalize and score
    max_chop = max(c['choppiness'] for c in candidates)
    max_vol = max(c['quoteVolume'] for c in candidates)
    max_count = max(c['count'] for c in candidates)

    for c in candidates:
        chop_norm = c['choppiness'] / max_chop if max_chop > 0 else 0
        vol_norm = c['quoteVolume'] / max_vol if max_vol > 0 else 0
        count_norm = c['count'] / max_count if max_count > 0 else 0
        sw = c['sideways_score']

        # Martingale stage1 score:
        # Choppiness 35% + Sideways 25% + Volume 20% + Trade count 20%
        c['stage1_score'] = round(
            chop_norm * 35 + sw * 25 + vol_norm * 20 + count_norm * 20,
        2)

    candidates.sort(key=lambda x: x['stage1_score'], reverse=True)

    if override_symbols:
        return candidates  # return all if user-specified

    return candidates[:STAGE1_TOP_N]


def get_latest_result() -> Dict[str, Any]:
    """Return cached screening result."""
    return _latest_result


def get_candidates(top_n: int = 10) -> List[Dict]:
    """Return top N candidates from latest result."""
    if not _latest_result:
        return []
    return _latest_result.get('candidates', [])[:top_n]


async def run_martingale_scheduler():
    """Run martingale screening every SCREEN_INTERVAL_HOURS."""
    logger.info(f'[Martingale] Scheduler started: every {SCREEN_INTERVAL_HOURS}h')

    # Initial delay: let collector gather some data first
    await asyncio.sleep(120)

    while True:
        try:
            logger.info('[Martingale] Running scheduled screening...')
            result = await screen_martingale_candidates(top_n=15)
            n_analyzed = result.get('stage2_analyzed', 0)
            candidates = result.get('candidates', [])
            top3 = [(c['symbol'], c['fitness'], c['grade']) for c in candidates[:3]]
            logger.info(
                f'[Martingale] Scheduled screen done: '
                f'{n_analyzed} analyzed, top 3: {top3}'
            )
        except Exception as e:
            logger.error(f'[Martingale] Scheduler error: {e}', exc_info=True)

        await asyncio.sleep(SCREEN_INTERVAL_HOURS * 3600)
