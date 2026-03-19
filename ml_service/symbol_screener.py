"""
Dynamic Symbol Screener — Compression-based.
Finds symbols that are quiet but building energy (about to have big moves),
NOT symbols already moving. Two-stage: fast ticker filter → 7-day kline analysis.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

import httpx

from config import BINANCE_FUTURES_BASE, COLLECT_SYMBOLS
from db import SessionLocal, OHLCVHourly

logger = logging.getLogger(__name__)

# Core symbols always included
CORE_SYMBOLS = set(COLLECT_SYMBOLS)

# Settings
SCREENER_TOP_N = 30
MIN_QUOTE_VOLUME_24H = 30_000_000  # $30M (lowered to catch quiet symbols)
STAGE1_CANDIDATES = 60  # Stage 1 output size

# Exclude stablecoins and leverage tokens
EXCLUDED_SUFFIXES = {'BUSD', 'TUSD', 'USDCUSDT', 'DAIUSDT', 'FDUSDUSDT'}
EXCLUDED_CONTAINS = {'UP', 'DOWN', 'BEAR', 'BULL', '1000000'}

# Cache
_screened_symbols: List[str] = []
_last_screen_time: str = ''
_screen_details: List[Dict] = []


async def screen_volume_spikes() -> List[Dict[str, Any]]:
    """
    2-stage compression screening.
    Stage 1: All tickers → find high volume + low range (compression).
    Stage 2: Top candidates → 7-day kline comparison for range squeeze.
    """
    global _screened_symbols, _last_screen_time, _screen_details

    async with httpx.AsyncClient(timeout=15.0) as client:
        # ===== Stage 1: Fast ticker filter =====
        resp = await client.get(f"{BINANCE_FUTURES_BASE}/fapi/v1/ticker/24hr")
        resp.raise_for_status()
        tickers = resp.json()

    candidates = []
    for t in tickers:
        symbol = t.get('symbol', '')
        if not symbol.endswith('USDT'):
            continue
        if symbol in EXCLUDED_SUFFIXES:
            continue
        if any(x in symbol for x in EXCLUDED_CONTAINS):
            continue

        quote_vol = float(t.get('quoteVolume', 0))
        if quote_vol < MIN_QUOTE_VOLUME_24H:
            continue

        high = float(t.get('highPrice', 0))
        low = float(t.get('lowPrice', 0))
        last = float(t.get('lastPrice', 0))
        count = int(t.get('count', 0))
        price_change = float(t.get('priceChangePercent', 0))

        if low <= 0 or last <= 0:
            continue

        # Range as percentage
        range_pct = (high - low) / low * 100

        # Compression signal: high volume + low range = energy building
        # volume_density = volume per % of range (higher = more compressed)
        volume_density = quote_vol / max(range_pct, 0.01)

        # Trade intensity: many small trades = position building
        trade_intensity = count / max(quote_vol / 1_000_000, 0.01)

        candidates.append({
            'symbol': symbol,
            'quoteVolume': quote_vol,
            'priceChangePercent': price_change,
            'lastPrice': last,
            'highPrice': high,
            'lowPrice': low,
            'count': count,
            'range_pct': round(range_pct, 4),
            'volume_density': round(volume_density, 2),
            'trade_intensity': round(trade_intensity, 2),
        })

    if not candidates:
        logger.warning('[Screener] No candidates found')
        return []

    # Normalize and score Stage 1
    max_vd = max(c['volume_density'] for c in candidates)
    max_ti = max(c['trade_intensity'] for c in candidates)

    for c in candidates:
        vd_norm = c['volume_density'] / max_vd if max_vd > 0 else 0
        ti_norm = c['trade_intensity'] / max_ti if max_ti > 0 else 0
        # Low range_pct is good (compressed), but need min volume
        range_inv = 1.0 / max(c['range_pct'], 0.1)  # inverse: lower range = higher score
        max_range_inv = 1.0 / 0.1  # theoretical max
        ri_norm = min(range_inv / max_range_inv, 1.0)

        c['stage1_score'] = round(vd_norm * 40 + ri_norm * 35 + ti_norm * 25, 2)

    # Sort by compression score
    candidates.sort(key=lambda x: x['stage1_score'], reverse=True)

    # Take top STAGE1_CANDIDATES for Stage 2 + always include core symbols
    stage2_symbols = set()
    stage2_candidates = []

    # Core symbols first
    for c in candidates:
        if c['symbol'] in CORE_SYMBOLS:
            stage2_symbols.add(c['symbol'])
            stage2_candidates.append(c)

    # Fill from top stage1 scores
    for c in candidates:
        if len(stage2_symbols) >= STAGE1_CANDIDATES:
            break
        if c['symbol'] not in stage2_symbols:
            stage2_symbols.add(c['symbol'])
            stage2_candidates.append(c)

    # ===== Stage 2: 7-day kline analysis =====
    stage2_candidates = await _enrich_with_klines(stage2_candidates)

    # Final scoring
    for c in stage2_candidates:
        s1 = c.get('stage1_score', 0)
        range_comp = c.get('range_compression', 1.0)  # <1 = today narrower than avg
        vol_surge = c.get('volume_ratio_7d', 1.0)     # >1 = volume above avg
        is_narrowest = c.get('is_narrowest_day', False)

        # Compression score: low range + high volume = about to explode
        # range_compression < 1 means today is quieter than usual
        compression_bonus = max(0, (1.0 - range_comp) * 50)  # 0-50 points
        volume_bonus = min(vol_surge, 3.0) * 10               # 0-30 points
        narrowest_bonus = 15 if is_narrowest else 0            # 0-15 points

        c['compressionScore'] = round(s1 * 0.3 + compression_bonus + volume_bonus + narrowest_bonus, 2)

    # Sort by final compression score
    stage2_candidates.sort(key=lambda x: x.get('compressionScore', 0), reverse=True)

    # Select top N
    selected_symbols = set()
    result = []

    for c in stage2_candidates:
        if len(selected_symbols) >= SCREENER_TOP_N:
            break
        selected_symbols.add(c['symbol'])
        result.append(c)

    # Ensure core symbols are included
    for sym in CORE_SYMBOLS:
        if sym not in selected_symbols:
            selected_symbols.add(sym)
            # Find from stage2 or create placeholder
            found = next((c for c in stage2_candidates if c['symbol'] == sym), None)
            if found:
                result.append(found)
            else:
                result.append({
                    'symbol': sym, 'quoteVolume': 0, 'compressionScore': 0,
                    'note': 'core_symbol_forced',
                })

    result.sort(key=lambda x: x.get('compressionScore', 0), reverse=True)

    _screened_symbols = [r['symbol'] for r in result]
    _last_screen_time = datetime.utcnow().isoformat()
    _screen_details = result

    logger.info(f'[Screener] Selected {len(result)} symbols (compression-based). '
                f'Top 5: {[r["symbol"] for r in result[:5]]}')
    return result


async def _enrich_with_klines(candidates: List[Dict]) -> List[Dict]:
    """Stage 2: Fetch 7-day daily klines for each candidate, compute compression metrics."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = []
        for c in candidates:
            tasks.append(_fetch_kline_stats(client, c))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched = []
    for c, result in zip(candidates, results):
        if isinstance(result, Exception):
            logger.debug(f'[Screener] {c["symbol"]} kline error: {result}')
            c['range_compression'] = 1.0
            c['volume_ratio_7d'] = 1.0
            c['is_narrowest_day'] = False
        else:
            c.update(result)
        enriched.append(c)

    return enriched


async def _fetch_kline_stats(client: httpx.AsyncClient, candidate: Dict) -> Dict:
    """Fetch 7-day daily klines and compute compression stats."""
    symbol = candidate['symbol']
    resp = await client.get(
        f"{BINANCE_FUTURES_BASE}/fapi/v1/klines",
        params={'symbol': symbol, 'interval': '1d', 'limit': 7})
    resp.raise_for_status()
    klines = resp.json()

    if not klines or len(klines) < 3:
        return {'range_compression': 1.0, 'volume_ratio_7d': 1.0, 'is_narrowest_day': False}

    # Each kline: [open_time, open, high, low, close, volume, close_time, quote_vol, ...]
    ranges = []
    volumes = []
    for k in klines:
        h = float(k[2])
        l = float(k[3])
        qv = float(k[7])  # quote volume
        rng = (h - l) / l * 100 if l > 0 else 0
        ranges.append(rng)
        volumes.append(qv)

    today_range = ranges[-1]
    today_vol = volumes[-1]
    avg_range = sum(ranges[:-1]) / max(len(ranges) - 1, 1)
    avg_vol = sum(volumes[:-1]) / max(len(volumes) - 1, 1)

    range_compression = today_range / avg_range if avg_range > 0 else 1.0
    volume_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0
    is_narrowest = today_range <= min(ranges)

    return {
        'range_compression': round(range_compression, 4),
        'volume_ratio_7d': round(volume_ratio, 4),
        'is_narrowest_day': is_narrowest,
        'today_range_pct': round(today_range, 4),
        'avg_range_7d_pct': round(avg_range, 4),
    }


def get_screened_symbols() -> List[str]:
    """Return current screened symbol list. Falls back to CORE_SYMBOLS."""
    return _screened_symbols if _screened_symbols else list(CORE_SYMBOLS)


def get_screen_status() -> Dict[str, Any]:
    """Return screening status and details."""
    return {
        'last_screen_time': _last_screen_time,
        'total_symbols': len(_screened_symbols),
        'core_symbols': list(CORE_SYMBOLS),
        'symbols': _screened_symbols,
        'details': _screen_details[:SCREENER_TOP_N],
    }


async def ensure_data_for_symbols(symbols: List[str], min_candles: int = 500):
    """
    Check which symbols have enough data for training.
    Trigger collection for those that don't.
    Returns (ready_symbols, collecting_symbols).
    """
    from collector import add_symbol, collect_symbol, collect_funding, collect_oi

    db = SessionLocal()
    try:
        from sqlalchemy import func
        counts = dict(
            db.query(OHLCVHourly.symbol, func.count(OHLCVHourly.id))
            .filter(OHLCVHourly.symbol.in_(symbols))
            .group_by(OHLCVHourly.symbol)
            .all()
        )
    finally:
        db.close()

    ready = []
    collecting = []

    for sym in symbols:
        count = counts.get(sym, 0)
        if count >= min_candles:
            ready.append(sym)
        else:
            collecting.append(sym)
            add_symbol(sym)
            logger.info(f'[Screener] {sym}: {count} candles, need {min_candles}. Starting collection...')
            try:
                await collect_symbol(sym)
                await collect_funding(sym)
                await collect_oi(sym)
                db = SessionLocal()
                try:
                    from sqlalchemy import func
                    new_count = db.query(func.count(OHLCVHourly.id)).filter(
                        OHLCVHourly.symbol == sym).scalar()
                    if new_count >= min_candles:
                        ready.append(sym)
                        logger.info(f'[Screener] {sym}: now has {new_count} candles. Ready.')
                    else:
                        logger.info(f'[Screener] {sym}: only {new_count} candles after collection. Skipping.')
                finally:
                    db.close()
            except Exception as e:
                logger.error(f'[Screener] {sym} collection failed: {e}')

    return ready, collecting
