"""
ML Trend Prediction API Endpoints.
Designed to be called from remote servers (e.g., mint server).
"""
import logging
from typing import Optional
from fastapi import APIRouter, Query, BackgroundTasks

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/ml', tags=['ML Prediction'])


@router.post('/train/{symbol}')
async def train_model(
    symbol: str,
    background_tasks: BackgroundTasks,
    timeframe: str = Query('5m', description='OHLCV timeframe'),
    horizon: int = Query(12, description='Prediction horizon in candles'),
    threshold: float = Query(0.002, description='Min return threshold for UP class'),
    days: int = Query(90, description='Training data days'),
    sync: bool = Query(False, description='Run synchronously (blocking)'),
):
    """Train a trend prediction model for a symbol."""
    from ..ml.trainer import TrendTrainer

    trainer = TrendTrainer(symbol, timeframe, horizon, threshold)

    if sync:
        result = trainer.train(days)
        return result
    else:
        def _train():
            try:
                result = trainer.train(days)
                logger.info(f'[ML] Background training done for {symbol}: {result.get("metrics", {}).get("accuracy")}')
            except Exception as e:
                logger.error(f'[ML] Background training failed for {symbol}: {e}', exc_info=True)

        background_tasks.add_task(_train)
        return {'status': 'training_started', 'symbol': symbol, 'timeframe': timeframe}


@router.post('/train-batch')
async def train_batch(
    symbols: str = Query(..., description='Comma-separated symbols'),
    background_tasks: BackgroundTasks = None,
    timeframe: str = Query('5m'),
    horizon: int = Query(12),
    threshold: float = Query(0.002),
    days: int = Query(90),
):
    """Train models for multiple symbols in background."""
    from ..ml.trainer import TrendTrainer

    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

    def _train_all():
        results = {}
        for sym in symbol_list:
            try:
                trainer = TrendTrainer(sym, timeframe, horizon, threshold)
                result = trainer.train(days)
                results[sym] = result.get('metrics', {}).get('accuracy', 'error')
                logger.info(f'[ML] Batch: {sym} done - acc={results[sym]}')
            except Exception as e:
                results[sym] = f'error: {str(e)[:100]}'
                logger.error(f'[ML] Batch: {sym} failed: {e}')
        logger.info(f'[ML] Batch training complete: {results}')

    background_tasks.add_task(_train_all)
    return {'status': 'batch_training_started', 'symbols': symbol_list}


@router.get('/predict/{symbol}')
async def predict_symbol(
    symbol: str,
    timeframe: str = Query('5m', description='OHLCV timeframe'),
):
    """Get trend prediction for a symbol. Can be called from remote servers."""
    from ..ml.predictor import TrendPredictor
    return TrendPredictor.get_prediction(symbol, timeframe)


@router.get('/predict-batch')
async def predict_batch(
    symbols: str = Query(..., description='Comma-separated symbols'),
    timeframe: str = Query('5m'),
):
    """Get predictions for multiple symbols at once."""
    from ..ml.predictor import TrendPredictor
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
    return TrendPredictor.get_batch_predictions(symbol_list, timeframe)


@router.get('/models')
async def list_models():
    """List all trained models and their metrics."""
    from ..ml.predictor import TrendPredictor
    return TrendPredictor.list_models()


@router.post('/reload/{symbol}')
async def reload_model(symbol: str, timeframe: str = Query('5m')):
    """Force reload a model from disk (after retraining)."""
    from ..ml.predictor import TrendPredictor
    TrendPredictor.reload_model(symbol, timeframe)
    return {'status': 'reloaded', 'symbol': symbol, 'timeframe': timeframe}
