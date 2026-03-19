"""
Binance Futures 1h OHLCV + Funding Rate + Open Interest Collector.
Fetches data directly from Binance API and stores in local SQLite.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import httpx

from config import BINANCE_FUTURES_BASE, COLLECT_SYMBOLS, COLLECT_INTERVAL_MINUTES, COLLECT_INITIAL_DAYS
from db import SessionLocal, OHLCVHourly, FundingRate, OpenInterest

logger = logging.getLogger(__name__)

_active_symbols = list(COLLECT_SYMBOLS)
_running = False
_last_collect = {}


def get_active_symbols():
    return list(_active_symbols)


def add_symbol(symbol: str):
    s = symbol.strip().upper()
    if s not in _active_symbols:
        _active_symbols.append(s)
    return _active_symbols


# ============ OHLCV ============

async def fetch_klines(client, symbol, start_ms, end_ms=None, limit=1500):
    params = {"symbol": symbol, "interval": "1h", "startTime": start_ms, "limit": limit}
    if end_ms:
        params["endTime"] = end_ms
    resp = await client.get(f"{BINANCE_FUTURES_BASE}/fapi/v1/klines", params=params)
    resp.raise_for_status()
    return resp.json()


async def collect_symbol(symbol, days=None):
    db = SessionLocal()
    try:
        from sqlalchemy import func
        latest = db.query(func.max(OHLCVHourly.timestamp)).filter(
            OHLCVHourly.symbol == symbol).scalar()
        if latest:
            start_ms = int(latest.timestamp() * 1000) + 3600000
        else:
            d = days or COLLECT_INITIAL_DAYS
            start_ms = int((datetime.utcnow() - timedelta(days=d)).timestamp() * 1000)

        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if start_ms >= now_ms:
            return 0

        total = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = start_ms
            while cursor < now_ms:
                try:
                    klines = await fetch_klines(client, symbol, cursor)
                except Exception as e:
                    logger.error(f"[Collector] {symbol} OHLCV error: {e}")
                    break
                if not klines:
                    break
                for k in klines:
                    ts = datetime.utcfromtimestamp(k[0] / 1000)
                    ex = db.query(OHLCVHourly).filter(
                        OHLCVHourly.symbol == symbol,
                        OHLCVHourly.timestamp == ts).first()
                    if ex:
                        ex.open, ex.high, ex.low, ex.close, ex.volume = (
                            float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
                    else:
                        db.add(OHLCVHourly(symbol=symbol, timestamp=ts,
                            open=float(k[1]), high=float(k[2]), low=float(k[3]),
                            close=float(k[4]), volume=float(k[5])))
                        total += 1
                db.commit()
                cursor = klines[-1][0] + 3600000
                if len(klines) < 1500:
                    break
                await asyncio.sleep(0.2)

        _last_collect[symbol] = datetime.utcnow().isoformat()
        if total > 0:
            logger.info(f"[Collector] {symbol} OHLCV: +{total} candles")
        return total
    except Exception as e:
        db.rollback()
        logger.error(f"[Collector] {symbol} OHLCV error: {e}", exc_info=True)
        return 0
    finally:
        db.close()


# ============ Funding Rate ============

async def collect_funding(symbol, days=None):
    db = SessionLocal()
    try:
        from sqlalchemy import func
        latest = db.query(func.max(FundingRate.timestamp)).filter(
            FundingRate.symbol == symbol).scalar()
        if latest:
            start_ms = int(latest.timestamp() * 1000) + 1000
        else:
            d = days or COLLECT_INITIAL_DAYS
            start_ms = int((datetime.utcnow() - timedelta(days=d)).timestamp() * 1000)

        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if start_ms >= now_ms:
            return 0

        total = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = start_ms
            while cursor < now_ms:
                params = {"symbol": symbol, "startTime": cursor, "limit": 1000}
                try:
                    resp = await client.get(
                        f"{BINANCE_FUTURES_BASE}/fapi/v1/fundingRate", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"[Collector] {symbol} funding error: {e}")
                    break
                if not data:
                    break
                for item in data:
                    ts = datetime.utcfromtimestamp(item["fundingTime"] / 1000)
                    rate = float(item["fundingRate"])
                    ex = db.query(FundingRate).filter(
                        FundingRate.symbol == symbol,
                        FundingRate.timestamp == ts).first()
                    if not ex:
                        db.add(FundingRate(
                            symbol=symbol, timestamp=ts, funding_rate=rate))
                        total += 1
                db.commit()
                cursor = data[-1]["fundingTime"] + 1000
                if len(data) < 1000:
                    break
                await asyncio.sleep(0.2)

        if total > 0:
            logger.info(f"[Collector] {symbol} funding: +{total} records")
        return total
    except Exception as e:
        db.rollback()
        logger.error(f"[Collector] {symbol} funding error: {e}", exc_info=True)
        return 0
    finally:
        db.close()


# ============ Open Interest ============

async def collect_oi(symbol, days=None):
    db = SessionLocal()
    try:
        from sqlalchemy import func
        latest = db.query(func.max(OpenInterest.timestamp)).filter(
            OpenInterest.symbol == symbol).scalar()
        if latest:
            start_ms = int(latest.timestamp() * 1000) + 1000
        else:
            d = min(days or COLLECT_INITIAL_DAYS, 30)
            start_ms = int((datetime.utcnow() - timedelta(days=d)).timestamp() * 1000)

        now_ms = int(datetime.utcnow().timestamp() * 1000)
        if start_ms >= now_ms:
            return 0

        total = 0
        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = start_ms
            while cursor < now_ms:
                params = {
                    "symbol": symbol, "period": "1h",
                    "startTime": cursor, "limit": 500,
                }
                try:
                    resp = await client.get(
                        f"{BINANCE_FUTURES_BASE}/futures/data/openInterestHist",
                        params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"[Collector] {symbol} OI error: {e}")
                    break
                if not data:
                    break
                for item in data:
                    ts = datetime.utcfromtimestamp(item["timestamp"] / 1000)
                    oi = float(item["sumOpenInterest"])
                    oi_val = float(item.get("sumOpenInterestValue", 0))
                    ex = db.query(OpenInterest).filter(
                        OpenInterest.symbol == symbol,
                        OpenInterest.timestamp == ts).first()
                    if not ex:
                        db.add(OpenInterest(
                            symbol=symbol, timestamp=ts,
                            open_interest=oi, open_interest_value=oi_val))
                        total += 1
                db.commit()
                cursor = data[-1]["timestamp"] + 1000
                if len(data) < 500:
                    break
                await asyncio.sleep(0.3)

        if total > 0:
            logger.info(f"[Collector] {symbol} OI: +{total} records")
        return total
    except Exception as e:
        db.rollback()
        logger.error(f"[Collector] {symbol} OI error: {e}", exc_info=True)
        return 0
    finally:
        db.close()


# ============ Orchestration ============

async def collect_all(days=None):
    global _running
    _running = True
    total = 0
    for symbol in _active_symbols:
        try:
            n = await collect_symbol(symbol, days)
            total += n
            await collect_funding(symbol, days)
            await collect_oi(symbol, days)
        except Exception as e:
            logger.error(f"[Collector] {symbol} failed: {e}")
    _running = False
    return total


async def run_scheduler():
    logger.info(
        f"[Collector] Scheduler started: {len(_active_symbols)} symbols, "
        f"every {COLLECT_INTERVAL_MINUTES}m")
    await collect_all()
    logger.info("[Collector] Initial collection complete")
    while True:
        await asyncio.sleep(COLLECT_INTERVAL_MINUTES * 60)
        try:
            await collect_all()
        except Exception as e:
            logger.error(f"[Collector] Scheduler error: {e}", exc_info=True)


def get_status():
    db = SessionLocal()
    try:
        from sqlalchemy import func
        ohlcv_stats = db.query(
            OHLCVHourly.symbol, func.count(OHLCVHourly.id),
            func.min(OHLCVHourly.timestamp), func.max(OHLCVHourly.timestamp),
        ).group_by(OHLCVHourly.symbol).all()
        funding_map = {r[0]: r[1] for r in db.query(
            FundingRate.symbol, func.count(FundingRate.id)
        ).group_by(FundingRate.symbol).all()}
        oi_map = {r[0]: r[1] for r in db.query(
            OpenInterest.symbol, func.count(OpenInterest.id)
        ).group_by(OpenInterest.symbol).all()}
        return {
            "running": _running,
            "interval_minutes": COLLECT_INTERVAL_MINUTES,
            "active_symbols": _active_symbols,
            "last_collect": _last_collect,
            "symbols": {
                row[0]: {
                    "ohlcv_count": row[1],
                    "oldest": row[2].isoformat() if row[2] else None,
                    "newest": row[3].isoformat() if row[3] else None,
                    "funding_count": funding_map.get(row[0], 0),
                    "oi_count": oi_map.get(row[0], 0),
                } for row in ohlcv_stats
            },
        }
    finally:
        db.close()
