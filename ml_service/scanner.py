"""
Big Move Scanner.
Periodically scans all symbols, ranks by big-move probability.
Provides simple API: "which symbols are most likely to move big?"
"""
import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd
import lightgbm as lgb

from config import MODEL_DIR, COLLECT_SYMBOLS
from db import SessionLocal, OHLCVHourly, FundingRate, OpenInterest
from feature_engine import compute_features, get_feature_columns, add_volatility_target

logger = logging.getLogger(__name__)


def _sanitize_for_json(obj):
    """Replace NaN/Inf floats with None for JSON serialization."""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    return obj

# In-memory scan results
_latest_scan: Dict[str, Any] = {}
_scan_history: List[Dict] = []  # last N scans

SCAN_INTERVAL_HOURS = 6
BIG_MOVE_THRESHOLD_DEFAULT = 0.015  # fallback 1.5%
HORIZON = 12  # 12 hours


class VolatilityTrainer:
    """Trains a BIG_MOVE / SMALL_MOVE binary classifier."""

    def __init__(self, symbol: str, horizon: int = 12,
                 threshold: float = 0.015):
        self.symbol = symbol
        self.horizon = horizon
        self.threshold = threshold
        self.model = None
        self.feature_columns = []

    def _load_data(self, days: int = 365):
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows = db.query(OHLCVHourly).filter(
                OHLCVHourly.symbol == self.symbol,
                OHLCVHourly.timestamp >= since
            ).order_by(OHLCVHourly.timestamp).all()
            if not rows:
                return None, None, None
            ohlcv = pd.DataFrame([{
                'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
                'low': r.low, 'close': r.close, 'volume': r.volume
            } for r in rows])

            fr = db.query(FundingRate).filter(
                FundingRate.symbol == self.symbol,
                FundingRate.timestamp >= since
            ).order_by(FundingRate.timestamp).all()
            funding = pd.DataFrame([{
                'timestamp': r.timestamp, 'funding_rate': r.funding_rate
            } for r in fr]) if fr else pd.DataFrame()

            oi = db.query(OpenInterest).filter(
                OpenInterest.symbol == self.symbol,
                OpenInterest.timestamp >= since
            ).order_by(OpenInterest.timestamp).all()
            oi_df = pd.DataFrame([{
                'timestamp': r.timestamp, 'open_interest': r.open_interest,
                'open_interest_value': r.open_interest_value
            } for r in oi]) if oi else pd.DataFrame()

            return ohlcv, funding, oi_df
        finally:
            db.close()

    def train(self, days: int = 365, model_type: str = 'volatility'):
        ohlcv, funding, oi_df = self._load_data(days)
        if ohlcv is None or len(ohlcv) < 500:
            return {'error': f'Not enough data for {self.symbol}'}

        df = compute_features(ohlcv, funding_df=funding, oi_df=oi_df)
        df = add_volatility_target(df, self.horizon, self.threshold)

        df.dropna(subset=['target'], inplace=True)
        self.feature_columns = get_feature_columns(df)
        df_clean = df[self.feature_columns + ['target']].dropna()

        if len(df_clean) < 300:
            return {'error': f'Not enough clean data: {len(df_clean)}'}

        X = df_clean[self.feature_columns].values
        y = df_clean['target'].values

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        train_set = lgb.Dataset(X_train, label=y_train)
        val_set = lgb.Dataset(X_test, label=y_test, reference=train_set)

        n_pos = y_train.sum()
        n_neg = len(y_train) - n_pos
        spw = n_neg / n_pos if n_pos > 0 else 1.0

        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.01,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'min_child_samples': 20,
            'scale_pos_weight': spw,
            'verbose': -1,
            'seed': 42,
        }

        callbacks = [lgb.early_stopping(50, verbose=False), lgb.log_evaluation(0)]
        self.model = lgb.train(
            params, train_set,
            num_boost_round=1000,
            valid_sets=[val_set],
            callbacks=callbacks,
        )

        y_proba = self.model.predict(X_test)
        y_pred = (y_proba > 0.5).astype(int)

        from sklearn.metrics import (accuracy_score, roc_auc_score, f1_score,
                                     precision_score, recall_score)

        # Check for single class in test set
        unique_classes = len(set(y_test))
        if unique_classes < 2:
            return {'error': f'Single class in test set for {self.symbol}'}

        # Precision by probability bucket: "모델이 X% 이상이라 했을 때 실제 비율"
        precision_by_bucket = {}
        for threshold_val in [0.4, 0.5, 0.6, 0.7, 0.8]:
            mask = y_proba >= threshold_val
            if mask.sum() > 0:
                precision_by_bucket[str(threshold_val)] = round(
                    float(y_test[mask].mean()), 4)

        metrics = {
            'accuracy': round(accuracy_score(y_test, y_pred), 4),
            'auc': round(roc_auc_score(y_test, y_proba), 4),
            'f1': round(f1_score(y_test, y_pred, zero_division=0), 4),
            'precision': round(precision_score(y_test, y_pred, zero_division=0), 4),
            'recall': round(recall_score(y_test, y_pred, zero_division=0), 4),
            'positive_ratio': round(float(y.mean()), 4),
            'best_iteration': self.model.best_iteration,
            'precision_by_bucket': precision_by_bucket,
        }

        self._last_metrics = metrics

        return {
            'symbol': self.symbol,
            'model_type': model_type,
            'horizon': self.horizon,
            'threshold': self.threshold,
            'metrics': metrics,
            'features_count': len(self.feature_columns),
        }

    def save(self, model_type: str = 'volatility'):
        os.makedirs(MODEL_DIR, exist_ok=True)
        prefix = f'{self.symbol}_vol' if model_type == 'volatility' else f'{self.symbol}_dir'
        self.model.save_model(os.path.join(MODEL_DIR, f'{prefix}_model.txt'))
        meta = {
            'symbol': self.symbol,
            'model_type': model_type,
            'horizon': self.horizon,
            'threshold': self.threshold,
            'feature_columns': self.feature_columns,
            'metrics': getattr(self, '_last_metrics', {}),
            'trained_at': datetime.utcnow().isoformat(),
        }
        with open(os.path.join(MODEL_DIR, f'{prefix}_meta.json'), 'w') as f:
            json.dump(meta, f, indent=2)

    @staticmethod
    def load(symbol: str, model_type: str = 'volatility'):
        prefix = f'{symbol}_vol' if model_type == 'volatility' else f'{symbol}_dir'
        model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
        meta_path = os.path.join(MODEL_DIR, f'{prefix}_meta.json')
        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None, None
        model = lgb.Booster(model_file=model_path)
        with open(meta_path, 'r') as f:
            meta = json.load(f)
        return model, meta


# ============ Train All ============

def _calc_dynamic_threshold(symbol: str, days: int = 90) -> float:
    """Calculate per-symbol threshold based on recent ATR.
    Target: positive_ratio ~30-40% (meaningful big moves, not daily noise)."""
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        rows = db.query(OHLCVHourly).filter(
            OHLCVHourly.symbol == symbol,
            OHLCVHourly.timestamp >= since
        ).order_by(OHLCVHourly.timestamp).all()
        if not rows or len(rows) < 100:
            return BIG_MOVE_THRESHOLD_DEFAULT

        df = pd.DataFrame([{
            'close': r.close, 'high': r.high, 'low': r.low
        } for r in rows])

        # HORIZON 기간 동안의 실제 수익률 분포
        returns = df['close'].pct_change(HORIZON).abs().dropna()
        if len(returns) < 50:
            return BIG_MOVE_THRESHOLD_DEFAULT

        # 상위 30%에 해당하는 수익률 = "평소보다 큰 움직임"의 기준선
        threshold = float(returns.quantile(0.70))
        # 최소 1%, 최대 30%로 제한
        threshold = max(0.01, min(threshold, 0.30))
        return round(threshold, 4)
    finally:
        db.close()


def train_all_models(symbols: list = None, days: int = 365):
    """Train volatility models with per-symbol dynamic threshold."""
    symbols = symbols or list(COLLECT_SYMBOLS)
    results = {}

    for sym in symbols:
        threshold = _calc_dynamic_threshold(sym)
        trainer = VolatilityTrainer(sym, horizon=HORIZON, threshold=threshold)
        result = trainer.train(days=days, model_type='volatility')
        if 'error' not in result:
            trainer.save(model_type='volatility')
            pos_ratio = result['metrics'].get('positive_ratio', 0)
            results[sym] = {'volatility': result['metrics'], 'threshold': threshold}
            logger.info(f'[Scanner] {sym} TH={threshold*100:.1f}% pos_ratio={pos_ratio:.1%} AUC={result["metrics"]["auc"]}')
        else:
            results[sym] = {'volatility': {'error': result['error']}}
            logger.warning(f'[Scanner] {sym}: {result["error"]}')

    return _sanitize_for_json(results)


# ============ Scan (Predict) ============

async def scan_all_async(symbols: list = None) -> Dict[str, Any]:
    """Predict big-move probability for all symbols. Direction is separate (via /direction API)."""
    global _latest_scan
    symbols = symbols or list(COLLECT_SYMBOLS)

    rankings = []
    for sym in symbols:
        try:
            entry = _predict_symbol_vol(sym)
            if entry:
                # Signal based on big_move_prob only
                big_prob = entry['big_move_prob']

                if big_prob >= 0.6:
                    entry['signal'] = 'BIG_MOVE'
                    entry['confidence'] = round(big_prob, 4)
                elif big_prob >= 0.5 and entry.get('is_squeezing'):
                    entry['signal'] = 'SQUEEZE_ALERT'
                    entry['confidence'] = round(big_prob, 4)
                elif big_prob >= 0.5:
                    entry['signal'] = 'WARMING_UP'
                    entry['confidence'] = round(big_prob, 4)
                elif big_prob <= 0.35:
                    entry['signal'] = 'SMALL_MOVE'
                    entry['confidence'] = round(1 - big_prob, 4)
                else:
                    entry['signal'] = 'UNCERTAIN'
                    entry['confidence'] = 0.0

                entry['recommendation'] = _build_recommendation(entry)
                rankings.append(entry)
        except Exception as e:
            logger.error(f'[Scanner] {sym} predict error: {e}')

    # Sort by big_move_prob descending
    rankings.sort(key=lambda x: x['big_move_prob'], reverse=True)

    for i, r in enumerate(rankings):
        r['rank'] = i + 1

    _latest_scan = _sanitize_for_json({
        'scanned_at': datetime.utcnow().isoformat(),
        'horizon_hours': HORIZON,
        'big_move_threshold': f'{BIG_MOVE_THRESHOLD_DEFAULT*100:.1f}%',
        'total_symbols': len(rankings),
        'rankings': rankings,
    })

    _scan_history.append(_latest_scan)
    if len(_scan_history) > 20:
        _scan_history.pop(0)

    logger.info(f'[Scanner] Scan complete: {len(rankings)} symbols')
    return _latest_scan


def scan_all(symbols: list = None) -> Dict[str, Any]:
    """Sync wrapper for scan_all_async (for use in sync contexts like train-sync)."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        # Already in async context — create a task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, scan_all_async(symbols))
            return future.result()
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        return asyncio.run(scan_all_async(symbols))


def _predict_symbol_vol(symbol: str) -> Optional[Dict]:
    """Predict big-move probability only (volatility model). Direction handled separately."""
    db = SessionLocal()
    try:
        rows = db.query(OHLCVHourly).filter(
            OHLCVHourly.symbol == symbol,
        ).order_by(OHLCVHourly.timestamp.desc()).limit(300).all()
        if not rows or len(rows) < 100:
            return None

        ohlcv = pd.DataFrame([{
            'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
            'low': r.low, 'close': r.close, 'volume': r.volume
        } for r in rows]).sort_values('timestamp').reset_index(drop=True)

        earliest = ohlcv['timestamp'].min()

        fr = db.query(FundingRate).filter(
            FundingRate.symbol == symbol,
            FundingRate.timestamp >= earliest,
        ).order_by(FundingRate.timestamp).all()
        funding = pd.DataFrame([{
            'timestamp': r.timestamp, 'funding_rate': r.funding_rate
        } for r in fr]) if fr else pd.DataFrame()

        oi = db.query(OpenInterest).filter(
            OpenInterest.symbol == symbol,
            OpenInterest.timestamp >= earliest,
        ).order_by(OpenInterest.timestamp).all()
        oi_df = pd.DataFrame([{
            'timestamp': r.timestamp, 'open_interest': r.open_interest,
            'open_interest_value': r.open_interest_value
        } for r in oi]) if oi else pd.DataFrame()

    finally:
        db.close()

    df = compute_features(ohlcv, funding_df=funding, oi_df=oi_df)
    last = df.iloc[-1]
    current_price = float(last['close'])

    # ATR-based recommended threshold
    atr_pct = float(last.get('atr_pct_14', 0))
    recommended_threshold = round(max(atr_pct * 1.5, 0.005), 4)  # 1.5x ATR or min 0.5%

    # Volatility state (squeeze detection)
    bb_squeeze = float(last.get('bb_squeeze_20', 1.0)) if 'bb_squeeze_20' in df.columns else 1.0
    atr_contraction = float(last.get('atr_contraction', 1.0)) if 'atr_contraction' in df.columns else 1.0
    vol_regime = float(last.get('vol_regime', 1.0)) if 'vol_regime' in df.columns else 1.0

    # Squeeze score: lower = more compressed = higher breakout potential
    squeeze_score = round((bb_squeeze + atr_contraction + vol_regime) / 3, 4)
    is_squeezing = squeeze_score < 0.85

    result = {
        'symbol': symbol,
        'current_price': current_price,
        'big_move_prob': 0.0,
        'signal': 'NO_SIGNAL',
        'confidence': 0.0,
        'recommended_threshold': recommended_threshold,
        'atr_pct_14': round(atr_pct, 4),
        'squeeze_score': squeeze_score,
        'is_squeezing': is_squeezing,
        'big_move_threshold': None,  # 학습 시 사용된 threshold
        'model_auc': None,
        'model_accuracy': None,
        'expected_win_rate': None,
    }

    vol_model, vol_meta = VolatilityTrainer.load(symbol, 'volatility')
    if vol_model and vol_meta:
        result['big_move_threshold'] = vol_meta.get('threshold')
        feat_cols = vol_meta['feature_columns']
        X = _get_features(df, feat_cols)
        if X is not None:
            big_prob = float(vol_model.predict(X)[0])
            result['big_move_prob'] = round(big_prob, 4)

        # Model quality metrics
        metrics = vol_meta.get('metrics', {})
        result['model_auc'] = metrics.get('auc')
        result['model_accuracy'] = metrics.get('accuracy')
        result['model_precision'] = metrics.get('precision')
        result['model_recall'] = metrics.get('recall')
        result['precision_by_bucket'] = metrics.get('precision_by_bucket', {})

        # Expected win rate: 모델 출력 확률 구간에 해당하는 실제 precision 사용
        # "모델이 big_prob=0.65라 했을 때, 과거 테스트셋에서 0.6 이상이라 한 것 중 실제 BIG_MOVE 비율"
        buckets = metrics.get('precision_by_bucket', {})
        if buckets and big_prob > 0.35:
            # 현재 big_prob에 가장 가까운 하한 bucket 찾기
            bucket_keys = sorted([float(k) for k in buckets.keys()])
            matched_bucket = None
            for bk in reversed(bucket_keys):
                if big_prob >= bk:
                    matched_bucket = str(bk)
                    break
            if matched_bucket:
                result['expected_win_rate'] = buckets[matched_bucket]
                result['win_rate_bucket'] = matched_bucket
            else:
                # big_prob < 최소 bucket → base rate 사용
                result['expected_win_rate'] = metrics.get('positive_ratio', 0.5)
                result['win_rate_bucket'] = 'base_rate'
        else:
            # 모델 없거나 bucket 없음 → positive_ratio fallback
            result['expected_win_rate'] = metrics.get('positive_ratio', 0.5)
            result['win_rate_bucket'] = 'base_rate'

    return result


def _get_features(df: pd.DataFrame, feature_columns: list):
    """Extract feature vector from last row of df."""
    last_row = df.iloc[-1:]
    missing = [c for c in feature_columns if c not in last_row.columns]
    if missing:
        return None
    X = last_row[feature_columns].values
    if np.isnan(X).any():
        last_row = df.iloc[-2:-1]
        X = last_row[feature_columns].values
        if np.isnan(X).any():
            return None
    return X


def _build_recommendation(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Build recommendation summary. Big-move prediction only, no direction."""
    signal = entry.get('signal', 'UNCERTAIN')
    big_prob = entry.get('big_move_prob', 0)
    squeeze = entry.get('is_squeezing', False)
    squeeze_score = entry.get('squeeze_score', 1.0)
    threshold = entry.get('recommended_threshold', 0.015)
    win_rate = entry.get('expected_win_rate')
    atr_pct = entry.get('atr_pct_14', 0)
    bm_threshold = entry.get('big_move_threshold')  # 학습 시 사용된 threshold

    # TP/SL based on ATR
    tp_pct = round(threshold * 100, 2)
    sl_pct = round(atr_pct * 100, 2)
    bm_th_pct = round(bm_threshold * 100, 2) if bm_threshold else None

    # Summary
    parts = []
    if signal == 'BIG_MOVE':
        parts.append(f'빅무브 {big_prob*100:.0f}%')
    elif signal == 'SQUEEZE_ALERT':
        parts.append(f'스퀴즈 감지 (압축 {squeeze_score:.2f})')
        parts.append(f'확률 {big_prob*100:.0f}%')
    elif signal == 'WARMING_UP':
        parts.append(f'빅무브 준비 {big_prob*100:.0f}%')
    elif signal == 'SMALL_MOVE':
        parts.append('소폭 움직임 예상')
    else:
        parts.append(f'확률 {big_prob*100:.0f}%')

    if squeeze and signal != 'SQUEEZE_ALERT':
        parts.append(f'스퀴즈 중')

    if win_rate:
        parts.append(f'승률 {win_rate*100:.0f}%')

    if bm_th_pct:
        parts.append(f'기준 ±{bm_th_pct}%')
    parts.append(f'TH {tp_pct}% / SL {sl_pct}%')

    summary = ' | '.join(parts) if parts else '시그널 없음'

    return {
        'signal': signal,
        'big_move_probability': round(big_prob, 4),
        'expected_win_rate': win_rate,
        'big_move_threshold_pct': bm_th_pct,
        'recommended_threshold_pct': tp_pct,
        'stop_loss_pct': sl_pct,
        'is_squeezing': squeeze,
        'squeeze_score': squeeze_score,
        'summary': summary,
    }


# ============ API Helpers ============

def get_latest_scan() -> Dict[str, Any]:
    """Return latest scan results."""
    return _latest_scan or {'error': 'No scan results yet. Wait for first scan.'}


def get_top_movers(n: int = 20) -> List[Dict]:
    """Return top N symbols by big-move probability."""
    if not _latest_scan:
        return []
    return _latest_scan.get('rankings', [])[:n]


def get_signal(symbol: str) -> Dict[str, Any]:
    """Get signal for a specific symbol from latest scan."""
    if not _latest_scan:
        return {'error': 'No scan yet'}
    for r in _latest_scan.get('rankings', []):
        if r['symbol'] == symbol:
            return r
    return {'error': f'{symbol} not in latest scan'}


# ============ Scheduler ============

async def run_scan_scheduler():
    """Run scan every SCAN_INTERVAL_HOURS. Also triggers retrain daily.
    Uses dynamic symbol screener to discover volume-spike symbols."""
    logger.info(f'[Scanner] Scheduler started: every {SCAN_INTERVAL_HOURS}h')

    _scan_count = 0

    while True:
        try:
            # Step 1: Screen for volume-spike symbols
            from symbol_screener import screen_volume_spikes, get_screened_symbols, ensure_data_for_symbols
            try:
                await screen_volume_spikes()
                dynamic_symbols = get_screened_symbols()
                logger.info(f'[Scanner] Screened {len(dynamic_symbols)} symbols')

                # Step 2: Ensure data exists for all screened symbols
                ready_symbols, _ = await ensure_data_for_symbols(dynamic_symbols)
                logger.info(f'[Scanner] {len(ready_symbols)} symbols ready for scanning')
            except Exception as e:
                logger.error(f'[Scanner] Screening failed, using defaults: {e}')
                ready_symbols = list(COLLECT_SYMBOLS)

            # Step 3: Retrain models once per day (every 4th scan if 6h interval)
            if _scan_count % 4 == 0:
                logger.info(f'[Scanner] Retraining all models for {len(ready_symbols)} symbols...')
                train_all_models(symbols=ready_symbols)
                logger.info('[Scanner] Retrain complete')

            # Step 4: Run scan on ready symbols (async for direction_engine)
            await scan_all_async(symbols=ready_symbols)
            _scan_count += 1

        except Exception as e:
            logger.error(f'[Scanner] Scheduler error: {e}', exc_info=True)

        await asyncio.sleep(SCAN_INTERVAL_HOURS * 3600)
