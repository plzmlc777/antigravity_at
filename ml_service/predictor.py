"""
ML Trend Predictor.
Loads trained model and makes real-time predictions.
Uses local SQLite OHLCVHourly + FundingRate + OpenInterest data.
Supports single model and multi-horizon ensemble predictions.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd

from feature_engine import compute_features, get_feature_columns
from trainer import TrendTrainer, MODEL_DIR
from db import SessionLocal, OHLCVHourly, FundingRate, OpenInterest

logger = logging.getLogger(__name__)


class TrendPredictor:
    _cache: Dict[str, Any] = {}

    @classmethod
    def get_prediction(cls, symbol: str, timeframe: str = '1h') -> Dict[str, Any]:
        key = f'{symbol}_{timeframe}'

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

        # Fetch recent data
        df, funding_df, oi_df = cls._fetch_all_recent(symbol, limit=300)
        if df is None or len(df) < 100:
            return {'error': f'Not enough recent data for {symbol}'}

        # Compute features with funding + OI
        df = compute_features(df, funding_df=funding_df, oi_df=oi_df)

        # Get last row features
        last_row = df.iloc[-1:]
        missing = [c for c in feature_columns if c not in last_row.columns]
        if missing:
            return {'error': f'Missing features: {missing[:5]}'}

        X = last_row[feature_columns].values
        if np.isnan(X).any():
            last_row = df.iloc[-2:-1]
            X = last_row[feature_columns].values
            if np.isnan(X).any():
                return {'error': 'Features contain NaN values'}

        proba = model.predict(X)[0]
        prediction = 'UP' if proba > 0.5 else 'DOWN'
        confidence = proba if proba > 0.5 else 1 - proba

        horizon = metadata.get('horizon', 12)
        predict_minutes = horizon * 60

        return {
            'symbol': symbol,
            'timeframe': '1h',
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
    def get_ensemble_prediction(cls, symbol: str) -> Dict[str, Any]:
        """Predict using multi-horizon ensemble (average of h6, h12, h24)."""
        ens_path = os.path.join(MODEL_DIR, f'{symbol}_ensemble_meta.json')
        if not os.path.exists(ens_path):
            return {'error': f'No ensemble model for {symbol}'}

        with open(ens_path, 'r') as f:
            ens_meta = json.load(f)

        horizons = ens_meta.get('horizons', [6, 12, 24])

        # Fetch data once
        df, funding_df, oi_df = cls._fetch_all_recent(symbol, limit=300)
        if df is None or len(df) < 100:
            return {'error': f'Not enough recent data for {symbol}'}

        df_feat = compute_features(df, funding_df=funding_df, oi_df=oi_df)

        predictions = []
        details = []
        for h in horizons:
            prefix = f'{symbol}_1h_h{h}'
            model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
            meta_path = os.path.join(MODEL_DIR, f'{prefix}_meta.json')
            if not os.path.exists(model_path) or not os.path.exists(meta_path):
                continue

            import lightgbm as lgb
            model = lgb.Booster(model_file=model_path)
            with open(meta_path, 'r') as f:
                meta = json.load(f)

            feature_cols = meta['feature_columns']
            available = [c for c in feature_cols if c in df_feat.columns]
            if len(available) != len(feature_cols):
                continue

            last_row = df_feat.iloc[-1:]
            X = last_row[feature_cols].values
            if np.isnan(X).any():
                last_row = df_feat.iloc[-2:-1]
                X = last_row[feature_cols].values
                if np.isnan(X).any():
                    continue

            proba = model.predict(X)[0]
            predictions.append(proba)
            details.append({
                'horizon': h,
                'probability': round(float(proba), 4),
                'prediction': 'UP' if proba > 0.5 else 'DOWN',
                'auc': meta.get('metrics', {}).get('auc'),
            })

        if not predictions:
            return {'error': 'No valid ensemble models'}

        avg_proba = float(np.mean(predictions))
        prediction = 'UP' if avg_proba > 0.5 else 'DOWN'
        confidence = avg_proba if avg_proba > 0.5 else 1 - avg_proba

        return {
            'symbol': symbol,
            'method': 'ensemble',
            'prediction': prediction,
            'probability': round(avg_proba, 4),
            'confidence': round(confidence, 4),
            'current_price': float(df.iloc[-1]['close']),
            'models_used': len(predictions),
            'details': details,
            'predicted_at': datetime.utcnow().isoformat(),
        }

    @classmethod
    def get_batch_predictions(cls, symbols: list, timeframe: str = '1h') -> list:
        results = []
        for symbol in symbols:
            try:
                pred = cls.get_prediction(symbol, timeframe)
                results.append(pred)
            except Exception as e:
                results.append({'symbol': symbol, 'error': str(e)})
        return results

    @classmethod
    def reload_model(cls, symbol: str, timeframe: str = '1h'):
        key = f'{symbol}_{timeframe}'
        cls._cache.pop(key, None)

    @classmethod
    def list_models(cls) -> list:
        models = []
        if not os.path.exists(MODEL_DIR):
            return models
        for f in os.listdir(MODEL_DIR):
            if f.endswith('_meta.json') and 'ensemble' not in f:
                path = os.path.join(MODEL_DIR, f)
                try:
                    with open(path, 'r') as fh:
                        meta = json.load(fh)
                    models.append({
                        'symbol': meta['symbol'],
                        'timeframe': meta.get('timeframe', '1h'),
                        'horizon': meta.get('horizon'),
                        'accuracy': meta.get('metrics', {}).get('accuracy'),
                        'auc': meta.get('metrics', {}).get('auc'),
                        'f1': meta.get('metrics', {}).get('f1'),
                        'trained_at': meta.get('trained_at'),
                        'features_count': meta.get('metrics', {}).get('features_count'),
                    })
                except Exception:
                    pass
        return models

    @staticmethod
    def _fetch_all_recent(symbol: str, limit: int = 300):
        """Fetch recent OHLCV, funding, and OI data from SQLite."""
        db = SessionLocal()
        try:
            # OHLCV
            rows = db.query(OHLCVHourly).filter(
                OHLCVHourly.symbol == symbol,
            ).order_by(OHLCVHourly.timestamp.desc()).limit(limit).all()

            if not rows:
                return None, None, None

            data = [{'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
                     'low': r.low, 'close': r.close, 'volume': r.volume} for r in rows]
            df = pd.DataFrame(data)
            df.sort_values('timestamp', inplace=True)
            df.reset_index(drop=True, inplace=True)

            earliest = df['timestamp'].min()

            # Funding rates
            fr_rows = db.query(FundingRate).filter(
                FundingRate.symbol == symbol,
                FundingRate.timestamp >= earliest,
            ).order_by(FundingRate.timestamp).all()
            funding_df = pd.DataFrame(
                [{'timestamp': r.timestamp, 'funding_rate': r.funding_rate}
                 for r in fr_rows]) if fr_rows else pd.DataFrame()

            # Open interest
            oi_rows = db.query(OpenInterest).filter(
                OpenInterest.symbol == symbol,
                OpenInterest.timestamp >= earliest,
            ).order_by(OpenInterest.timestamp).all()
            oi_df = pd.DataFrame(
                [{'timestamp': r.timestamp, 'open_interest': r.open_interest,
                  'open_interest_value': r.open_interest_value}
                 for r in oi_rows]) if oi_rows else pd.DataFrame()

            return df, funding_df, oi_df
        finally:
            db.close()
