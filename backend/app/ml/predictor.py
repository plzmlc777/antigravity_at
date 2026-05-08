"""
ML Trend Predictor.
Loads trained model and makes real-time predictions.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd

from .feature_engine import compute_features, get_feature_columns
from .trainer import TrendTrainer, MODEL_DIR

logger = logging.getLogger(__name__)


class TrendPredictor:
    _cache: Dict[str, Any] = {}  # {symbol_tf: {model, metadata, loaded_at}}

    @classmethod
    def get_prediction(cls, symbol: str, timeframe: str = '5m') -> Dict[str, Any]:
        key = f'{symbol}_{timeframe}'

        # Load or cache model
        if key not in cls._cache:
            model, metadata = TrendTrainer.load_model(symbol, timeframe)
            if model is None:
                return {'error': f'No trained model for {symbol} ({timeframe})'}
            cls._cache[key] = {
                'model': model,
                'metadata': metadata,
                'loaded_at': datetime.utcnow(),
            }

        cached = cls._cache[key]
        model = cached['model']
        metadata = cached['metadata']
        feature_columns = metadata['feature_columns']

        # Fetch recent OHLCV data (need ~150 candles for feature calculation)
        df = cls._fetch_recent(symbol, timeframe, limit=200)
        if df is None or len(df) < 100:
            return {'error': f'Not enough recent data for {symbol}'}

        # Compute features
        df = compute_features(df)

        # Get last row features
        last_row = df.iloc[-1:]
        missing = [c for c in feature_columns if c not in last_row.columns]
        if missing:
            return {'error': f'Missing features: {missing[:5]}'}

        X = last_row[feature_columns].values
        if np.isnan(X).any():
            # Try second-to-last row
            last_row = df.iloc[-2:-1]
            X = last_row[feature_columns].values
            if np.isnan(X).any():
                return {'error': 'Features contain NaN values'}

        # Predict
        proba = model.predict(X)[0]
        prediction = 'UP' if proba > 0.5 else 'DOWN'
        confidence = proba if proba > 0.5 else 1 - proba

        horizon = metadata.get('horizon', 12)
        tf_minutes = cls._tf_to_minutes(timeframe)
        predict_minutes = horizon * tf_minutes

        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'prediction': prediction,
            'probability': round(float(proba), 4),
            'confidence': round(float(confidence), 4),
            'horizon_candles': horizon,
            'horizon_minutes': predict_minutes,
            'current_price': float(df.iloc[-1]['close']),
            'model_accuracy': metadata.get('metrics', {}).get('accuracy'),
            'model_auc': metadata.get('metrics', {}).get('auc'),
            'trained_at': metadata.get('trained_at'),
            'predicted_at': datetime.utcnow().isoformat(),
        }

    @classmethod
    def get_batch_predictions(cls, symbols: list, timeframe: str = '5m') -> list:
        results = []
        for symbol in symbols:
            try:
                pred = cls.get_prediction(symbol, timeframe)
                results.append(pred)
            except Exception as e:
                results.append({'symbol': symbol, 'error': str(e)})
        return results

    @classmethod
    def reload_model(cls, symbol: str, timeframe: str = '5m'):
        key = f'{symbol}_{timeframe}'
        cls._cache.pop(key, None)

    @classmethod
    def list_models(cls) -> list:
        import os, json
        models = []
        if not os.path.exists(MODEL_DIR):
            return models
        for f in os.listdir(MODEL_DIR):
            if f.endswith('_meta.json'):
                path = os.path.join(MODEL_DIR, f)
                try:
                    with open(path, 'r') as fh:
                        meta = json.load(fh)
                    models.append({
                        'symbol': meta['symbol'],
                        'timeframe': meta['timeframe'],
                        'accuracy': meta.get('metrics', {}).get('accuracy'),
                        'auc': meta.get('metrics', {}).get('auc'),
                        'trained_at': meta.get('trained_at'),
                        'features_count': meta.get('metrics', {}).get('features_count'),
                    })
                except Exception:
                    pass
        return models

    @staticmethod
    def _fetch_recent(symbol: str, timeframe: str, limit: int = 200) -> Optional[pd.DataFrame]:
        from ..db.session import db_scope
        from ..models.ohlcv import OHLCV
        with db_scope() as db:
            # Try exact timeframe first
            rows = db.query(OHLCV).filter(
                OHLCV.symbol == symbol,
                OHLCV.time_frame == timeframe,
            ).order_by(OHLCV.timestamp.desc()).limit(limit).all()

            if not rows:
                # Fallback: load 1m and resample
                tf_minutes = {'3m': 3, '5m': 5, '15m': 15, '30m': 30,
                              '1h': 60, '4h': 240}.get(timeframe, 5)
                need_1m = limit * tf_minutes + 100
                rows = db.query(OHLCV).filter(
                    OHLCV.symbol == symbol,
                    OHLCV.time_frame == '1m',
                ).order_by(OHLCV.timestamp.desc()).limit(need_1m).all()

                if not rows:
                    return None

                data = [{'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
                         'low': r.low, 'close': r.close, 'volume': r.volume} for r in rows]
                df = pd.DataFrame(data).sort_values('timestamp').reset_index(drop=True)

                from .trainer import TrendTrainer
                return TrendTrainer._resample(df, timeframe)

            data = [{'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
                     'low': r.low, 'close': r.close, 'volume': r.volume} for r in rows]
            df = pd.DataFrame(data)
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)
            return df

    @staticmethod
    def _tf_to_minutes(tf: str) -> int:
        mapping = {'1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
                   '1h': 60, '4h': 240, '1d': 1440}
        return mapping.get(tf, 5)
