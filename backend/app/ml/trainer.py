"""
ML Model Training Pipeline.
Walk-forward training with LightGBM for trend prediction.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd
import joblib
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

from .feature_engine import compute_features, get_feature_columns, add_target

logger = logging.getLogger(__name__)

MODEL_DIR = os.environ.get('ML_MODEL_DIR', '/mnt/data/ml/models')


class TrendTrainer:
    def __init__(self, symbol: str, timeframe: str = '5m',
                 horizon: int = 12, threshold: float = 0.002):
        self.symbol = symbol
        self.timeframe = timeframe
        self.horizon = horizon          # predict N candles ahead
        self.threshold = threshold      # min return to count as 'up' (0.2%)
        self.model = None
        self.feature_columns = []
        self.metadata = {}

    def _load_ohlcv(self, days: int = 90) -> pd.DataFrame:
        from ..db.session import SessionLocal
        from ..models.ohlcv import OHLCV
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)

            # Try exact timeframe first
            rows = db.query(OHLCV).filter(
                OHLCV.symbol == self.symbol,
                OHLCV.time_frame == self.timeframe,
                OHLCV.timestamp >= since
            ).order_by(OHLCV.timestamp).all()

            if rows:
                data = [{
                    'timestamp': r.timestamp,
                    'open': r.open, 'high': r.high,
                    'low': r.low, 'close': r.close,
                    'volume': r.volume
                } for r in rows]
                return pd.DataFrame(data)

            # Fallback: load 1m data and resample to target timeframe
            logger.info(f'[ML] No {self.timeframe} data, resampling from 1m')
            rows_1m = db.query(OHLCV).filter(
                OHLCV.symbol == self.symbol,
                OHLCV.time_frame == '1m',
                OHLCV.timestamp >= since
            ).order_by(OHLCV.timestamp).all()

            if not rows_1m:
                return pd.DataFrame()

            data = [{
                'timestamp': r.timestamp,
                'open': r.open, 'high': r.high,
                'low': r.low, 'close': r.close,
                'volume': r.volume
            } for r in rows_1m]
            df = pd.DataFrame(data)
            return self._resample(df, self.timeframe)
        finally:
            db.close()

    @staticmethod
    def _resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        tf_map = {'3m': '3min', '5m': '5min', '15m': '15min',
                  '30m': '30min', '1h': '1h', '4h': '4h', '1d': '1D'}
        rule = tf_map.get(timeframe)
        if not rule:
            return df
        df = df.set_index('timestamp')
        resampled = df.resample(rule).agg({
            'open': 'first', 'high': 'max',
            'low': 'min', 'close': 'last',
            'volume': 'sum'
        }).dropna()
        resampled.reset_index(inplace=True)
        return resampled

    def train(self, days: int = 90) -> Dict[str, Any]:
        logger.info(f'[ML] Training {self.symbol} ({self.timeframe}, horizon={self.horizon})')

        # 1. Load data
        df = self._load_ohlcv(days)
        if len(df) < 500:
            return {'error': f'Not enough data: {len(df)} rows (need 500+)'}

        # 2. Feature engineering
        df = compute_features(df)
        df = add_target(df, horizon=self.horizon, threshold=self.threshold)
        df.dropna(subset=['target'], inplace=True)

        # 3. Get feature columns and clean
        self.feature_columns = get_feature_columns(df)
        df_clean = df[self.feature_columns + ['target']].dropna()

        if len(df_clean) < 300:
            return {'error': f'Not enough clean data: {len(df_clean)} rows'}

        X = df_clean[self.feature_columns].values
        y = df_clean['target'].values

        # 4. Walk-forward split (80/20)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # 5. Train LightGBM
        train_set = lgb.Dataset(X_train, label=y_train)
        val_set = lgb.Dataset(X_test, label=y_test, reference=train_set)

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

        # 6. Evaluate
        y_pred_proba = self.model.predict(X_test)
        y_pred = (y_pred_proba > 0.5).astype(int)

        metrics = {
            'accuracy': round(accuracy_score(y_test, y_pred), 4),
            'precision': round(precision_score(y_test, y_pred, zero_division=0), 4),
            'recall': round(recall_score(y_test, y_pred, zero_division=0), 4),
            'f1': round(f1_score(y_test, y_pred, zero_division=0), 4),
            'auc': round(roc_auc_score(y_test, y_pred_proba), 4),
            'test_samples': len(y_test),
            'train_samples': len(y_train),
            'total_rows': len(df),
            'features_count': len(self.feature_columns),
            'positive_ratio': round(y.mean(), 4),
            'best_iteration': self.model.best_iteration,
        }

        # 7. Feature importance
        importance = dict(zip(
            self.feature_columns,
            self.model.feature_importance(importance_type='gain').tolist()
        ))
        top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:15]

        # 8. Save model
        self._save_model(metrics, top_features)

        result = {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'horizon': self.horizon,
            'threshold': self.threshold,
            'metrics': metrics,
            'top_features': top_features,
            'trained_at': datetime.utcnow().isoformat(),
        }
        logger.info(f'[ML] Training complete: acc={metrics["accuracy"]}, auc={metrics["auc"]}')
        return result

    def _save_model(self, metrics: dict, top_features: list):
        os.makedirs(MODEL_DIR, exist_ok=True)
        prefix = f'{self.symbol}_{self.timeframe}'

        # Save model
        model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
        self.model.save_model(model_path)

        # Save metadata
        self.metadata = {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'horizon': self.horizon,
            'threshold': self.threshold,
            'feature_columns': self.feature_columns,
            'metrics': metrics,
            'top_features': top_features,
            'trained_at': datetime.utcnow().isoformat(),
        }
        meta_path = os.path.join(MODEL_DIR, f'{prefix}_meta.json')
        with open(meta_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        logger.info(f'[ML] Model saved: {model_path}')

    @staticmethod
    def load_model(symbol: str, timeframe: str = '5m'):
        prefix = f'{symbol}_{timeframe}'
        model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
        meta_path = os.path.join(MODEL_DIR, f'{prefix}_meta.json')

        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None, None

        model = lgb.Booster(model_file=model_path)
        with open(meta_path, 'r') as f:
            metadata = json.load(f)

        return model, metadata
