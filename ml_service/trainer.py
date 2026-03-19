"""
ML Model Training Pipeline.
Walk-forward training with LightGBM for trend prediction.
Includes hyperparameter tuning and multi-horizon ensemble.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd
import joblib
import lightgbm as lgb
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

from feature_engine import compute_features, get_feature_columns, add_target
from config import MODEL_DIR
from db import SessionLocal, OHLCVHourly, FundingRate, OpenInterest

logger = logging.getLogger(__name__)


class TrendTrainer:
    def __init__(self, symbol: str, timeframe: str = "1h",
                 horizon: int = 12, threshold: float = 0.002,
                 auto_weight: bool = True):
        self.symbol = symbol
        self.timeframe = timeframe
        self.horizon = horizon
        self.threshold = threshold
        self.auto_weight = auto_weight
        self.model = None
        self.feature_columns = []
        self.metadata = {}

    def _load_ohlcv(self, days: int = 90) -> pd.DataFrame:
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows = db.query(OHLCVHourly).filter(
                OHLCVHourly.symbol == self.symbol,
                OHLCVHourly.timestamp >= since
            ).order_by(OHLCVHourly.timestamp).all()
            if not rows:
                return pd.DataFrame()
            data = [{'timestamp': r.timestamp, 'open': r.open, 'high': r.high,
                     'low': r.low, 'close': r.close, 'volume': r.volume} for r in rows]
            return pd.DataFrame(data)
        finally:
            db.close()

    def _load_funding(self, days: int = 90) -> pd.DataFrame:
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows = db.query(FundingRate).filter(
                FundingRate.symbol == self.symbol,
                FundingRate.timestamp >= since
            ).order_by(FundingRate.timestamp).all()
            if not rows:
                return pd.DataFrame()
            data = [{'timestamp': r.timestamp, 'funding_rate': r.funding_rate} for r in rows]
            return pd.DataFrame(data)
        finally:
            db.close()

    def _load_oi(self, days: int = 90) -> pd.DataFrame:
        db = SessionLocal()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            rows = db.query(OpenInterest).filter(
                OpenInterest.symbol == self.symbol,
                OpenInterest.timestamp >= since
            ).order_by(OpenInterest.timestamp).all()
            if not rows:
                return pd.DataFrame()
            data = [{'timestamp': r.timestamp, 'open_interest': r.open_interest,
                     'open_interest_value': r.open_interest_value} for r in rows]
            return pd.DataFrame(data)
        finally:
            db.close()

    def train(self, days: int = 90, params_override: dict = None) -> Dict[str, Any]:
        logger.info(f'[ML] Training {self.symbol} ({self.timeframe}, '
                     f'horizon={self.horizon}, threshold={self.threshold})')

        # 1. Load data
        df = self._load_ohlcv(days)
        if len(df) < 500:
            return {'error': f'Not enough data: {len(df)} rows (need 500+)'}

        funding_df = self._load_funding(days)
        oi_df = self._load_oi(days)

        # 2. Feature engineering
        df = compute_features(df, funding_df=funding_df, oi_df=oi_df)
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

        # Auto class balancing
        spw = 1.0
        if self.auto_weight:
            n_pos = y_train.sum()
            n_neg = len(y_train) - n_pos
            if n_pos > 0:
                spw = n_neg / n_pos
                logger.info(f'[ML] scale_pos_weight={spw:.3f} '
                           f'(pos={int(n_pos)}, neg={int(n_neg)})')

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
        if params_override:
            params.update(params_override)

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
        top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]

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
        logger.info(f'[ML] Training complete: acc={metrics["accuracy"]}, '
                    f'auc={metrics["auc"]}, best_iter={metrics["best_iteration"]}')
        return result

    def _save_model(self, metrics: dict, top_features: list):
        os.makedirs(MODEL_DIR, exist_ok=True)
        prefix = f'{self.symbol}_{self.timeframe}'

        model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
        self.model.save_model(model_path)

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
    def load_model(symbol: str, timeframe: str = "1h"):
        prefix = f'{symbol}_{timeframe}'
        model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
        meta_path = os.path.join(MODEL_DIR, f'{prefix}_meta.json')

        if not os.path.exists(model_path) or not os.path.exists(meta_path):
            return None, None

        model = lgb.Booster(model_file=model_path)
        with open(meta_path, 'r') as f:
            metadata = json.load(f)

        return model, metadata


# ============ Hyperparameter Tuning ============

def tune_hyperparams(symbol: str, days: int = 365) -> Dict[str, Any]:
    """Grid search over key hyperparameters. Returns best config and all results."""
    logger.info(f'[ML] Starting hyperparameter tuning for {symbol}')

    horizons = [6, 12, 24]
    thresholds = [0.005, 0.007, 0.01, 0.015]
    param_sets = [
        {'num_leaves': 15, 'learning_rate': 0.005, 'min_child_samples': 30},
        {'num_leaves': 31, 'learning_rate': 0.01, 'min_child_samples': 20},
        {'num_leaves': 63, 'learning_rate': 0.01, 'min_child_samples': 15},
        {'num_leaves': 31, 'learning_rate': 0.02, 'min_child_samples': 20},
        {'num_leaves': 31, 'learning_rate': 0.005, 'min_child_samples': 40},
    ]

    results = []
    best_score = 0
    best_config = None

    for horizon in horizons:
        for threshold in thresholds:
            for params in param_sets:
                try:
                    trainer = TrendTrainer(
                        symbol, horizon=horizon, threshold=threshold)
                    result = trainer.train(days=days, params_override=params)

                    if 'error' in result:
                        continue

                    auc = result['metrics']['auc']
                    f1 = result['metrics']['f1']
                    acc = result['metrics']['accuracy']
                    best_iter = result['metrics']['best_iteration']

                    entry = {
                        'horizon': horizon,
                        'threshold': threshold,
                        'params': params,
                        'auc': auc,
                        'f1': f1,
                        'accuracy': acc,
                        'best_iteration': best_iter,
                        'positive_ratio': result['metrics']['positive_ratio'],
                    }
                    results.append(entry)

                    # Score: weighted AUC + F1 (only if model actually learned)
                    score = auc * 0.6 + f1 * 0.4
                    if score > best_score and best_iter > 3:
                        best_score = score
                        best_config = entry

                    logger.info(
                        f'[ML] Tune {symbol}: h={horizon} t={threshold} '
                        f'nl={params["num_leaves"]} lr={params["learning_rate"]} '
                        f'-> AUC={auc:.4f} F1={f1:.4f} iter={best_iter}')

                except Exception as e:
                    logger.error(f'[ML] Tune error: {e}')

    results.sort(key=lambda x: x['auc'] * 0.6 + x['f1'] * 0.4, reverse=True)

    # Re-train with best config and save as the default model
    if best_config:
        logger.info(f'[ML] Best config for {symbol}: {best_config}')
        trainer = TrendTrainer(
            symbol, horizon=best_config['horizon'],
            threshold=best_config['threshold'])
        trainer.train(days=days, params_override=best_config['params'])

    return {
        'symbol': symbol,
        'best_config': best_config,
        'top_10': results[:10],
        'total_tried': len(results),
    }


# ============ Multi-Horizon Ensemble ============

def train_ensemble(symbol: str, days: int = 365,
                   horizons: List[int] = None,
                   threshold: float = 0.003) -> Dict[str, Any]:
    """Train models for multiple horizons and save ensemble metadata."""
    if horizons is None:
        horizons = [6, 12, 24]

    logger.info(f'[ML] Training ensemble for {symbol}: horizons={horizons}')

    ensemble_results = []
    for h in horizons:
        trainer = TrendTrainer(symbol, horizon=h, threshold=threshold)
        result = trainer.train(days=days)
        if 'error' not in result:
            os.makedirs(MODEL_DIR, exist_ok=True)
            prefix = f'{symbol}_1h_h{h}'
            model_path = os.path.join(MODEL_DIR, f'{prefix}_model.txt')
            trainer.model.save_model(model_path)
            meta = {
                'symbol': symbol, 'timeframe': '1h', 'horizon': h,
                'threshold': threshold,
                'feature_columns': trainer.feature_columns,
                'metrics': result['metrics'],
                'trained_at': datetime.utcnow().isoformat(),
            }
            meta_path = os.path.join(MODEL_DIR, f'{prefix}_meta.json')
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            ensemble_results.append({
                'horizon': h, 'auc': result['metrics']['auc'],
                'f1': result['metrics']['f1'],
                'accuracy': result['metrics']['accuracy'],
                'best_iteration': result['metrics']['best_iteration'],
            })
        else:
            ensemble_results.append({'horizon': h, 'error': result['error']})

    ensemble_meta = {
        'symbol': symbol,
        'horizons': horizons,
        'threshold': threshold,
        'models': ensemble_results,
        'trained_at': datetime.utcnow().isoformat(),
    }
    ens_path = os.path.join(MODEL_DIR, f'{symbol}_ensemble_meta.json')
    with open(ens_path, 'w') as f:
        json.dump(ensemble_meta, f, indent=2)

    logger.info(f'[ML] Ensemble training complete for {symbol}')
    return ensemble_meta
