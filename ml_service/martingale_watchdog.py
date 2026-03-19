"""
Martingale Watchdog — Emergency Stop Monitor.
Watches registered symbols for conditions that break martingale assumptions:
  - Big move incoming (volatility spike)
  - Trend breakout (ADX surge, Hurst shift)
  - Range expansion (ATR blow-up)
  - Abnormal volume (liquidation cascade risk)
  - Funding rate extreme (holding cost explosion)

External systems register/deregister symbols.
Watchdog checks every CHECK_INTERVAL and flags ALERT / WARNING / OK.
"""
import asyncio
import logging
import math
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

import numpy as np
import pandas as pd
import httpx

from config import BINANCE_FUTURES_BASE
from db import SessionLocal, OHLCVHourly, FundingRate, OpenInterest

logger = logging.getLogger(__name__)

# ========== State ==========
_watched_symbols: Dict[str, Dict[str, Any]] = {}  # symbol → registration info
_alert_status: Dict[str, Dict[str, Any]] = {}      # symbol → latest check result
_watchdog_running = False

# ========== Settings ==========
CHECK_INTERVAL_SECONDS = 300  # 5 minutes


# ========== Alert Thresholds ==========
class Thresholds:
    # ALERT (긴급 중단 권고)
    ADX_ALERT = 40              # ADX > 40 = strong trend forming
    ATR_EXPANSION_ALERT = 2.0   # ATR가 평균의 2배 이상 = range blow-up
    VOLUME_SPIKE_ALERT = 4.0    # 거래량이 평균의 4배 = 이상 급등
    HURST_ALERT = 0.70          # Hurst > 0.70 = strong trending
    PRICE_BREAK_ALERT = 0.03    # 최근 1시간 가격 변동 > 3%
    FUNDING_ALERT = 0.001       # |funding| > 0.1% = extreme positioning

    # WARNING (주의)
    ADX_WARNING = 30
    ATR_EXPANSION_WARNING = 1.5
    VOLUME_SPIKE_WARNING = 2.5
    HURST_WARNING = 0.63
    PRICE_BREAK_WARNING = 0.02
    FUNDING_WARNING = 0.0005


def _sanitize(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


# ========== Registration API ==========

def register_symbol(symbol: str, meta: Dict = None) -> Dict:
    """Register a symbol for watchdog monitoring."""
    symbol = symbol.upper()
    _watched_symbols[symbol] = {
        'registered_at': datetime.utcnow().isoformat(),
        'meta': meta or {},
    }
    logger.info(f'[Watchdog] Registered: {symbol}')
    return {'symbol': symbol, 'status': 'registered', 'total_watched': len(_watched_symbols)}


def unregister_symbol(symbol: str) -> Dict:
    """Remove a symbol from watchdog monitoring."""
    symbol = symbol.upper()
    removed = _watched_symbols.pop(symbol, None)
    _alert_status.pop(symbol, None)
    if removed:
        logger.info(f'[Watchdog] Unregistered: {symbol}')
        return {'symbol': symbol, 'status': 'unregistered', 'total_watched': len(_watched_symbols)}
    return {'symbol': symbol, 'status': 'not_found', 'total_watched': len(_watched_symbols)}


def get_watched_symbols() -> Dict[str, Any]:
    """Return all watched symbols and their alert status."""
    result = {}
    for sym, info in _watched_symbols.items():
        alert = _alert_status.get(sym, {'level': 'UNKNOWN', 'message': 'Not checked yet'})
        result[sym] = {
            'registered_at': info['registered_at'],
            'meta': info['meta'],
            'alert': alert,
        }
    return result


def get_alert(symbol: str) -> Optional[Dict]:
    """Get alert status for a specific symbol."""
    return _alert_status.get(symbol.upper())


def get_alerts_summary() -> Dict[str, Any]:
    """Get summary of all alerts."""
    alerts = []
    warnings = []
    ok = []
    for sym, status in _alert_status.items():
        level = status.get('level', 'UNKNOWN')
        if level == 'ALERT':
            alerts.append(sym)
        elif level == 'WARNING':
            warnings.append(sym)
        else:
            ok.append(sym)

    return {
        'checked_at': datetime.utcnow().isoformat(),
        'total_watched': len(_watched_symbols),
        'alert_count': len(alerts),
        'warning_count': len(warnings),
        'ok_count': len(ok),
        'alerts': alerts,
        'warnings': warnings,
        'ok': ok,
        'details': _sanitize(_alert_status),
    }


# ========== Check Logic ==========

def check_symbol(symbol: str) -> Dict[str, Any]:
    """
    Check a single symbol for martingale emergency conditions.
    Returns alert level: ALERT / WARNING / OK
    """
    db = SessionLocal()
    try:
        # Recent 72h OHLCV (enough for short-term checks)
        rows = db.query(OHLCVHourly).filter(
            OHLCVHourly.symbol == symbol,
        ).order_by(OHLCVHourly.timestamp.desc()).limit(72).all()

        if not rows or len(rows) < 24:
            return {
                'level': 'UNKNOWN',
                'message': f'Insufficient data ({len(rows) if rows else 0} candles)',
                'checked_at': datetime.utcnow().isoformat(),
            }

        ohlcv = pd.DataFrame([{
            'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
            'low': r.low, 'close': r.close, 'volume': r.volume
        } for r in rows]).sort_values('timestamp').reset_index(drop=True)

        # Funding rate
        fr_rows = db.query(FundingRate).filter(
            FundingRate.symbol == symbol,
        ).order_by(FundingRate.timestamp.desc()).limit(10).all()
        latest_funding = abs(float(fr_rows[0].funding_rate)) if fr_rows else 0.0

    finally:
        db.close()

    close = ohlcv['close'].astype(float)
    high = ohlcv['high'].astype(float)
    low = ohlcv['low'].astype(float)
    volume = ohlcv['volume'].astype(float)

    if close.std() == 0:
        return {'level': 'UNKNOWN', 'message': 'No price movement',
                'checked_at': datetime.utcnow().isoformat()}

    triggers = []  # (level, reason, metric_name, value, threshold)

    # --- 1. Price break: recent 1h price change ---
    recent_change = abs(float(close.iloc[-1] / close.iloc[-2] - 1)) if len(close) >= 2 else 0
    if recent_change >= Thresholds.PRICE_BREAK_ALERT:
        triggers.append(('ALERT', f'급격한 가격 변동 {recent_change*100:.2f}%',
                        'price_change_1h', recent_change, Thresholds.PRICE_BREAK_ALERT))
    elif recent_change >= Thresholds.PRICE_BREAK_WARNING:
        triggers.append(('WARNING', f'가격 변동 주의 {recent_change*100:.2f}%',
                        'price_change_1h', recent_change, Thresholds.PRICE_BREAK_WARNING))

    # --- 2. ATR expansion ---
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    atr_recent = float(tr.tail(6).mean())  # last 6h ATR
    atr_baseline = float(tr.tail(48).mean()) if len(tr) >= 48 else atr_recent
    atr_ratio = atr_recent / max(atr_baseline, 1e-10)

    if atr_ratio >= Thresholds.ATR_EXPANSION_ALERT:
        triggers.append(('ALERT', f'ATR 급팽창 {atr_ratio:.2f}x (레인지 확대)',
                        'atr_expansion', atr_ratio, Thresholds.ATR_EXPANSION_ALERT))
    elif atr_ratio >= Thresholds.ATR_EXPANSION_WARNING:
        triggers.append(('WARNING', f'ATR 확대 중 {atr_ratio:.2f}x',
                        'atr_expansion', atr_ratio, Thresholds.ATR_EXPANSION_WARNING))

    # --- 3. Volume spike ---
    vol_recent = float(volume.tail(3).mean())  # last 3h avg
    vol_baseline = float(volume.tail(48).mean()) if len(volume) >= 48 else vol_recent
    vol_ratio = vol_recent / max(vol_baseline, 1e-10)

    if vol_ratio >= Thresholds.VOLUME_SPIKE_ALERT:
        triggers.append(('ALERT', f'거래량 폭증 {vol_ratio:.1f}x (비정상)',
                        'volume_spike', vol_ratio, Thresholds.VOLUME_SPIKE_ALERT))
    elif vol_ratio >= Thresholds.VOLUME_SPIKE_WARNING:
        triggers.append(('WARNING', f'거래량 증가 {vol_ratio:.1f}x',
                        'volume_spike', vol_ratio, Thresholds.VOLUME_SPIKE_WARNING))

    # --- 4. ADX (trend strength) ---
    if len(close) >= 28:
        plus_dm = high.diff().where(lambda x: (x > 0) & (x > -low.diff()), 0.0)
        minus_dm = (-low.diff()).where(lambda x: (x > 0) & (x > high.diff()), 0.0)
        atr_smooth = tr.rolling(14).mean().replace(0, np.nan)
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        adx = dx.rolling(14).mean()
        current_adx = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else 20.0

        if current_adx >= Thresholds.ADX_ALERT:
            triggers.append(('ALERT', f'강한 추세 형성 ADX={current_adx:.1f}',
                            'adx', current_adx, Thresholds.ADX_ALERT))
        elif current_adx >= Thresholds.ADX_WARNING:
            triggers.append(('WARNING', f'추세 강화 중 ADX={current_adx:.1f}',
                            'adx', current_adx, Thresholds.ADX_WARNING))
    else:
        current_adx = None

    # --- 5. Hurst exponent (short-term, last 48h returns) ---
    if len(close) >= 48:
        returns_48 = np.log(close.tail(48) / close.tail(48).shift(1)).dropna().values
        if len(returns_48) >= 30:
            from martingale_screener import _calc_hurst
            hurst_short = _calc_hurst(close.tail(48))
        else:
            hurst_short = 0.5
    else:
        hurst_short = 0.5

    if hurst_short >= Thresholds.HURST_ALERT:
        triggers.append(('ALERT', f'추세 전환 감지 Hurst={hurst_short:.3f}',
                        'hurst', hurst_short, Thresholds.HURST_ALERT))
    elif hurst_short >= Thresholds.HURST_WARNING:
        triggers.append(('WARNING', f'평균회귀 약화 Hurst={hurst_short:.3f}',
                        'hurst', hurst_short, Thresholds.HURST_WARNING))

    # --- 6. Funding rate extreme ---
    if latest_funding >= Thresholds.FUNDING_ALERT:
        triggers.append(('ALERT', f'펀딩비 극단 |{latest_funding*100:.3f}%|',
                        'funding_rate', latest_funding, Thresholds.FUNDING_ALERT))
    elif latest_funding >= Thresholds.FUNDING_WARNING:
        triggers.append(('WARNING', f'펀딩비 주의 |{latest_funding*100:.3f}%|',
                        'funding_rate', latest_funding, Thresholds.FUNDING_WARNING))

    # --- 7. Consecutive directional candles (momentum building) ---
    if len(close) >= 6:
        last6_dir = np.sign(close.diff().tail(6).dropna().values)
        consec_same = 0
        if len(last6_dir) >= 5:
            # Count consecutive same-direction candles from the end
            last_dir = last6_dir[-1]
            for d in reversed(last6_dir):
                if d == last_dir and d != 0:
                    consec_same += 1
                else:
                    break
        if consec_same >= 5:
            triggers.append(('ALERT', f'연속 {consec_same}봉 동일 방향 (모멘텀)',
                            'consecutive_candles', consec_same, 5))
        elif consec_same >= 4:
            triggers.append(('WARNING', f'연속 {consec_same}봉 동일 방향',
                            'consecutive_candles', consec_same, 4))

    # --- Determine overall level ---
    alert_triggers = [t for t in triggers if t[0] == 'ALERT']
    warning_triggers = [t for t in triggers if t[0] == 'WARNING']

    if alert_triggers:
        level = 'ALERT'
        action = 'STOP_RECOMMENDED'
        message = ' | '.join(t[1] for t in alert_triggers)
    elif warning_triggers:
        level = 'WARNING'
        action = 'MONITOR_CLOSELY'
        message = ' | '.join(t[1] for t in warning_triggers)
    else:
        level = 'OK'
        action = 'CONTINUE'
        message = '마틴게일 조건 정상'

    result = {
        'symbol': symbol,
        'level': level,
        'action': action,
        'message': message,
        'checked_at': datetime.utcnow().isoformat(),
        'triggers': [
            {'level': t[0], 'reason': t[1], 'metric': t[2],
             'value': round(t[3], 4) if isinstance(t[3], float) else t[3],
             'threshold': round(t[4], 4) if isinstance(t[4], float) else t[4]}
            for t in triggers
        ],
        'metrics': {
            'price_change_1h': round(recent_change, 4),
            'atr_expansion': round(atr_ratio, 4),
            'volume_spike': round(vol_ratio, 4),
            'adx': round(current_adx, 2) if current_adx is not None else None,
            'hurst_48h': round(hurst_short, 4),
            'funding_rate': round(latest_funding, 6),
        },
    }

    return result


async def check_all_watched() -> Dict[str, Any]:
    """Check all watched symbols and update alert status."""
    if not _watched_symbols:
        return {'message': 'No symbols registered', 'symbols': {}}

    results = {}
    for symbol in list(_watched_symbols.keys()):
        try:
            result = check_symbol(symbol)
            _alert_status[symbol] = result
            results[symbol] = result

            if result['level'] == 'ALERT':
                logger.warning(f'[Watchdog] ALERT {symbol}: {result["message"]}')
            elif result['level'] == 'WARNING':
                logger.info(f'[Watchdog] WARNING {symbol}: {result["message"]}')

        except Exception as e:
            logger.error(f'[Watchdog] {symbol} check error: {e}')
            _alert_status[symbol] = {
                'level': 'ERROR', 'message': str(e),
                'checked_at': datetime.utcnow().isoformat(),
            }

    return _sanitize({
        'checked_at': datetime.utcnow().isoformat(),
        'total_checked': len(results),
        'results': results,
    })


# ========== Scheduler ==========

async def run_watchdog_scheduler():
    """Periodically check all watched symbols."""
    global _watchdog_running
    _watchdog_running = True
    logger.info(f'[Watchdog] Scheduler started: every {CHECK_INTERVAL_SECONDS}s')

    while _watchdog_running:
        try:
            if _watched_symbols:
                await check_all_watched()
        except Exception as e:
            logger.error(f'[Watchdog] Scheduler error: {e}', exc_info=True)

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
