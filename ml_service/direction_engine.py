"""
Direction Engine — Rule-based direction prediction using market microstructure data.
Replaces ML direction model (AUC ~0.54) with Binance on-chain/order flow signals.

Data sources:
  1. Funding Rate (already in DB) — extreme funding = crowded positioning
  2. Long/Short Account Ratio — retail sentiment (contrarian signal)
  3. Top Trader Long/Short Ratio — smart money positioning
  4. Taker Buy/Sell Volume Ratio — actual aggression in market
  5. Price momentum (from OHLCV) — trend confirmation

Logic: contrarian on crowd + aligned with smart money + confirmed by order flow
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import httpx

from config import BINANCE_FUTURES_BASE
from db import SessionLocal, FundingRate, OHLCVHourly

logger = logging.getLogger(__name__)

# Cache: symbol -> {data, fetched_at}
_direction_cache: Dict[str, Dict] = {}
CACHE_TTL_SECONDS = 300  # 5 min


async def fetch_direction_data(symbol: str) -> Dict[str, Any]:
    """Fetch all direction-relevant data from Binance for a symbol."""
    # Check cache
    cached = _direction_cache.get(symbol)
    if cached:
        age = (datetime.utcnow() - cached['fetched_at']).total_seconds()
        if age < CACHE_TTL_SECONDS:
            return cached['data']

    data = {
        'symbol': symbol,
        'fetched_at': datetime.utcnow().isoformat(),
        'funding': None,
        'global_long_short': None,
        'top_trader_long_short': None,
        'top_trader_position': None,
        'taker_buy_sell': None,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Global Long/Short Account Ratio (last 4 periods of 1h)
        try:
            resp = await client.get(
                f"{BINANCE_FUTURES_BASE}/futures/data/globalLongShortAccountRatio",
                params={"symbol": symbol, "period": "1h", "limit": 4})
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                data['global_long_short'] = [
                    {'timestamp': r['timestamp'], 'longAccount': float(r['longAccount']),
                     'shortAccount': float(r['shortAccount']),
                     'longShortRatio': float(r['longShortRatio'])}
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f'[Direction] {symbol} global L/S error: {e}')

        # 2. Top Trader Long/Short Account Ratio
        try:
            resp = await client.get(
                f"{BINANCE_FUTURES_BASE}/futures/data/topLongShortAccountRatio",
                params={"symbol": symbol, "period": "1h", "limit": 4})
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                data['top_trader_long_short'] = [
                    {'timestamp': r['timestamp'], 'longAccount': float(r['longAccount']),
                     'shortAccount': float(r['shortAccount']),
                     'longShortRatio': float(r['longShortRatio'])}
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f'[Direction] {symbol} top trader L/S error: {e}')

        # 3. Top Trader Long/Short Position Ratio
        try:
            resp = await client.get(
                f"{BINANCE_FUTURES_BASE}/futures/data/topLongShortPositionRatio",
                params={"symbol": symbol, "period": "1h", "limit": 4})
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                data['top_trader_position'] = [
                    {'timestamp': r['timestamp'], 'longAccount': float(r['longAccount']),
                     'shortAccount': float(r['shortAccount']),
                     'longShortRatio': float(r['longShortRatio'])}
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f'[Direction] {symbol} top position error: {e}')

        # 4. Taker Buy/Sell Volume Ratio
        try:
            resp = await client.get(
                f"{BINANCE_FUTURES_BASE}/futures/data/takerlongshortRatio",
                params={"symbol": symbol, "period": "1h", "limit": 4})
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                data['taker_buy_sell'] = [
                    {'timestamp': r['timestamp'],
                     'buyVol': float(r['buyVol']), 'sellVol': float(r['sellVol']),
                     'buySellRatio': float(r['buySellRatio'])}
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f'[Direction] {symbol} taker B/S error: {e}')

    # 5. Funding Rate (from local DB — last 3 records = last 24h)
    db = SessionLocal()
    try:
        fr_rows = db.query(FundingRate).filter(
            FundingRate.symbol == symbol
        ).order_by(FundingRate.timestamp.desc()).limit(3).all()
        if fr_rows:
            data['funding'] = [
                {'timestamp': r.timestamp.isoformat(), 'funding_rate': r.funding_rate}
                for r in fr_rows
            ]
    finally:
        db.close()

    # Cache
    _direction_cache[symbol] = {'data': data, 'fetched_at': datetime.utcnow()}
    return data


def compute_direction(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute direction signal from raw market microstructure data.

    Score range: -100 (strong DOWN) to +100 (strong UP)
    Composed of 5 sub-signals, each -20 to +20.
    """
    symbol = raw_data['symbol']
    scores = {}
    details = {}

    # ===== 1. Funding Rate Signal (contrarian) =====
    # Extreme positive funding → longs pay shorts → too many longs → DOWN
    # Extreme negative funding → shorts pay longs → too many shorts → UP
    fr_score = 0
    if raw_data.get('funding'):
        rates = [f['funding_rate'] for f in raw_data['funding']]
        avg_rate = sum(rates) / len(rates)
        latest_rate = rates[0]

        if abs(latest_rate) > 0.001:  # extreme (>0.1%)
            fr_score = -20 if latest_rate > 0 else 20
        elif abs(latest_rate) > 0.0005:  # elevated
            fr_score = -12 if latest_rate > 0 else 12
        elif abs(latest_rate) > 0.0002:  # mildly elevated
            fr_score = -5 if latest_rate > 0 else 5

        # Trend: funding increasing = more crowded
        if len(rates) >= 2:
            trend = latest_rate - rates[-1]
            if abs(trend) > 0.0001:
                fr_score += -3 if trend > 0 else 3

        details['funding'] = {
            'latest': round(latest_rate, 6),
            'avg_24h': round(avg_rate, 6),
            'interpretation': 'longs_crowded' if latest_rate > 0.0003 else
                              'shorts_crowded' if latest_rate < -0.0003 else 'neutral',
        }
    scores['funding'] = max(-20, min(20, fr_score))

    # ===== 2. Global Long/Short Ratio (contrarian) =====
    # > 1.0 = more long accounts → contrarian DOWN
    # < 1.0 = more short accounts → contrarian UP
    gls_score = 0
    if raw_data.get('global_long_short'):
        latest = raw_data['global_long_short'][0]
        ratio = latest['longShortRatio']

        deviation = ratio - 1.0  # how far from neutral
        if abs(deviation) > 0.5:
            gls_score = -20 if deviation > 0 else 20
        elif abs(deviation) > 0.2:
            gls_score = -12 if deviation > 0 else 12
        elif abs(deviation) > 0.1:
            gls_score = -5 if deviation > 0 else 5

        # Trend over 4 periods
        if len(raw_data['global_long_short']) >= 2:
            oldest = raw_data['global_long_short'][-1]
            trend = latest['longShortRatio'] - oldest['longShortRatio']
            if abs(trend) > 0.05:
                gls_score += -3 if trend > 0 else 3  # longs increasing = bearish

        details['global_long_short'] = {
            'ratio': round(ratio, 4),
            'long_pct': round(latest['longAccount'] * 100, 1),
            'interpretation': 'retail_long_heavy' if ratio > 1.2 else
                              'retail_short_heavy' if ratio < 0.8 else 'balanced',
        }
    scores['global_long_short'] = max(-20, min(20, gls_score))

    # ===== 3. Top Trader Long/Short (aligned — smart money) =====
    # > 1.0 = top traders are long → follow them → UP
    # < 1.0 = top traders are short → follow them → DOWN
    ttls_score = 0
    if raw_data.get('top_trader_long_short'):
        latest = raw_data['top_trader_long_short'][0]
        ratio = latest['longShortRatio']

        deviation = ratio - 1.0
        if abs(deviation) > 0.5:
            ttls_score = 20 if deviation > 0 else -20  # follow smart money
        elif abs(deviation) > 0.2:
            ttls_score = 12 if deviation > 0 else -12
        elif abs(deviation) > 0.1:
            ttls_score = 5 if deviation > 0 else -5

        details['top_trader'] = {
            'ratio': round(ratio, 4),
            'long_pct': round(latest['longAccount'] * 100, 1),
            'interpretation': 'smart_money_long' if ratio > 1.2 else
                              'smart_money_short' if ratio < 0.8 else 'balanced',
        }
    scores['top_trader'] = max(-20, min(20, ttls_score))

    # ===== 4. Top Trader Position Ratio (aligned — capital weighted) =====
    ttp_score = 0
    if raw_data.get('top_trader_position'):
        latest = raw_data['top_trader_position'][0]
        ratio = latest['longShortRatio']

        deviation = ratio - 1.0
        if abs(deviation) > 0.5:
            ttp_score = 20 if deviation > 0 else -20
        elif abs(deviation) > 0.2:
            ttp_score = 12 if deviation > 0 else -12
        elif abs(deviation) > 0.1:
            ttp_score = 5 if deviation > 0 else -5

        details['top_position'] = {
            'ratio': round(ratio, 4),
            'long_pct': round(latest['longAccount'] * 100, 1),
            'interpretation': 'big_money_long' if ratio > 1.2 else
                              'big_money_short' if ratio < 0.8 else 'balanced',
        }
    scores['top_position'] = max(-20, min(20, ttp_score))

    # ===== 5. Taker Buy/Sell Ratio (order flow — direct) =====
    # > 1.0 = more aggressive buyers → UP
    # < 1.0 = more aggressive sellers → DOWN
    taker_score = 0
    if raw_data.get('taker_buy_sell'):
        latest = raw_data['taker_buy_sell'][0]
        ratio = latest['buySellRatio']

        deviation = ratio - 1.0
        if abs(deviation) > 0.3:
            taker_score = 20 if deviation > 0 else -20
        elif abs(deviation) > 0.1:
            taker_score = 12 if deviation > 0 else -12
        elif abs(deviation) > 0.03:
            taker_score = 5 if deviation > 0 else -5

        # Trend: increasing buy ratio
        if len(raw_data['taker_buy_sell']) >= 2:
            oldest = raw_data['taker_buy_sell'][-1]
            trend = latest['buySellRatio'] - oldest['buySellRatio']
            if abs(trend) > 0.05:
                taker_score += 3 if trend > 0 else -3

        details['taker_flow'] = {
            'ratio': round(ratio, 4),
            'buy_vol': round(latest['buyVol'], 2),
            'sell_vol': round(latest['sellVol'], 2),
            'interpretation': 'buyers_aggressive' if ratio > 1.1 else
                              'sellers_aggressive' if ratio < 0.9 else 'balanced',
        }
    scores['taker_flow'] = max(-20, min(20, taker_score))

    # ===== Composite Score =====
    total_score = sum(scores.values())  # range: -100 to +100

    # Convert to direction
    if total_score >= 25:
        direction = 'UP'
        confidence = min(abs(total_score) / 100, 1.0)
    elif total_score <= -25:
        direction = 'DOWN'
        confidence = min(abs(total_score) / 100, 1.0)
    else:
        direction = 'NEUTRAL'
        confidence = 0.0

    # Strength classification
    abs_score = abs(total_score)
    if abs_score >= 60:
        strength = 'STRONG'
    elif abs_score >= 40:
        strength = 'MODERATE'
    elif abs_score >= 25:
        strength = 'WEAK'
    else:
        strength = 'NONE'

    return {
        'symbol': symbol,
        'direction': direction,
        'strength': strength,
        'total_score': total_score,
        'confidence': round(confidence, 4),
        'sub_scores': scores,
        'details': details,
        'computed_at': datetime.utcnow().isoformat(),
    }


async def get_direction(symbol: str) -> Dict[str, Any]:
    """Full pipeline: fetch data → compute direction."""
    raw = await fetch_direction_data(symbol)
    return compute_direction(raw)


async def get_directions_batch(symbols: List[str]) -> Dict[str, Dict]:
    """Get direction for multiple symbols."""
    results = {}
    for sym in symbols:
        try:
            results[sym] = await get_direction(sym)
        except Exception as e:
            logger.error(f'[Direction] {sym} error: {e}')
            results[sym] = {
                'symbol': sym, 'direction': 'NEUTRAL', 'strength': 'NONE',
                'total_score': 0, 'confidence': 0.0, 'error': str(e),
            }
    return results
