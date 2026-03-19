"""
Independent ML Prediction Service.
Runs on port 8002, separate from main backend.
Includes own data collector (Binance Futures 1h OHLCV + Funding + OI).
"""
import asyncio
import logging
import uvicorn
from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, BackgroundTasks

from config import ML_PORT

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

_scheduler_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task
    from collector import run_scheduler
    from scanner import run_scan_scheduler
    from martingale_screener import run_martingale_scheduler
    _scheduler_task = asyncio.create_task(run_scheduler())
    _scan_task = asyncio.create_task(run_scan_scheduler())
    _martingale_task = asyncio.create_task(run_martingale_scheduler())
    logger.info('[ML] Collector + Scanner + Martingale schedulers launched')
    yield
    if _scheduler_task:
        _scheduler_task.cancel()
    if _scan_task:
        _scan_task.cancel()
    if _martingale_task:
        _martingale_task.cancel()
    logger.info('[ML] Schedulers stopped')


app = FastAPI(title='ML Trend Prediction Service', version='2.0.0', lifespan=lifespan)


@app.get('/health')
async def health():
    return {'status': 'ok', 'service': 'ml-prediction', 'version': '2.0.0'}


# ========== Collector endpoints ==========

@app.get('/collector/status')
async def collector_status():
    from collector import get_status
    return get_status()


@app.post('/collector/run')
async def collector_run():
    from collector import collect_all
    asyncio.create_task(collect_all())
    return {'status': 'collection_started'}


@app.post('/collector/run-sync')
async def collector_run_sync():
    from collector import collect_all
    total = await collect_all()
    return {'status': 'done', 'total_inserted': total}


@app.post('/collector/add-symbol')
async def collector_add_symbol(symbol: str = Query(...)):
    from collector import add_symbol, collect_symbol
    symbols = add_symbol(symbol)
    n = await collect_symbol(symbol)
    return {'symbols': symbols, 'inserted': n}


# ========== Training endpoints ==========

@app.post('/train/{symbol}')
async def train_model(
    symbol: str,
    background_tasks: BackgroundTasks,
    timeframe: str = Query('1h'),
    horizon: int = Query(12),
    threshold: float = Query(0.003),
    days: int = Query(365),
    sync: bool = Query(False),
    auto_weight: bool = Query(True),
):
    from trainer import TrendTrainer
    trainer = TrendTrainer(symbol, timeframe, horizon, threshold, auto_weight)

    if sync:
        result = trainer.train(days)
        return result
    else:
        def _train():
            try:
                result = trainer.train(days)
                logger.info(f'[ML] Background training done for {symbol}: '
                           f'auc={result.get("metrics", {}).get("auc")}')
            except Exception as e:
                logger.error(f'[ML] Background training failed for {symbol}: {e}',
                           exc_info=True)
        background_tasks.add_task(_train)
        return {'status': 'training_started', 'symbol': symbol, 'timeframe': timeframe}


@app.post('/train-batch')
async def train_batch(
    symbols: str = Query(..., description='Comma-separated symbols'),
    background_tasks: BackgroundTasks = None,
    timeframe: str = Query('1h'),
    horizon: int = Query(12),
    threshold: float = Query(0.003),
    days: int = Query(365),
    auto_weight: bool = Query(True),
):
    from trainer import TrendTrainer
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

    def _train_all():
        results = {}
        for sym in symbol_list:
            try:
                trainer = TrendTrainer(sym, timeframe, horizon, threshold, auto_weight)
                result = trainer.train(days)
                results[sym] = result.get('metrics', {}).get('auc', 'error')
                logger.info(f'[ML] Batch: {sym} done - auc={results[sym]}')
            except Exception as e:
                results[sym] = f'error: {str(e)[:100]}'
                logger.error(f'[ML] Batch: {sym} failed: {e}')
        logger.info(f'[ML] Batch training complete: {results}')

    background_tasks.add_task(_train_all)
    return {'status': 'batch_training_started', 'symbols': symbol_list}


# ========== Tuning endpoints ==========

@app.post('/tune/{symbol}')
async def tune_symbol(
    symbol: str,
    background_tasks: BackgroundTasks,
    days: int = Query(365),
    sync: bool = Query(False),
):
    """Hyperparameter grid search for a symbol."""
    from trainer import tune_hyperparams

    if sync:
        result = tune_hyperparams(symbol, days)
        return result
    else:
        def _tune():
            try:
                result = tune_hyperparams(symbol, days)
                best = result.get('best_config', {})
                logger.info(f'[ML] Tuning done for {symbol}: best={best}')
            except Exception as e:
                logger.error(f'[ML] Tuning failed for {symbol}: {e}', exc_info=True)
        background_tasks.add_task(_tune)
        return {'status': 'tuning_started', 'symbol': symbol}


@app.post('/tune-batch')
async def tune_batch(
    symbols: str = Query(..., description='Comma-separated symbols'),
    background_tasks: BackgroundTasks = None,
    days: int = Query(365),
):
    """Tune all symbols sequentially in background."""
    from trainer import tune_hyperparams
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

    def _tune_all():
        for sym in symbol_list:
            try:
                result = tune_hyperparams(sym, days)
                best = result.get('best_config', {})
                logger.info(f'[ML] Tune batch: {sym} done - best AUC={best.get("auc") if best else "N/A"}')
            except Exception as e:
                logger.error(f'[ML] Tune batch: {sym} failed: {e}')

    background_tasks.add_task(_tune_all)
    return {'status': 'tune_batch_started', 'symbols': symbol_list}


# ========== Ensemble endpoints ==========

@app.post('/ensemble/train/{symbol}')
async def train_ensemble_model(
    symbol: str,
    background_tasks: BackgroundTasks,
    days: int = Query(365),
    threshold: float = Query(0.003),
    sync: bool = Query(False),
):
    """Train multi-horizon ensemble (h6, h12, h24)."""
    from trainer import train_ensemble

    if sync:
        result = train_ensemble(symbol, days=days, threshold=threshold)
        return result
    else:
        def _train():
            try:
                result = train_ensemble(symbol, days=days, threshold=threshold)
                logger.info(f'[ML] Ensemble training done for {symbol}')
            except Exception as e:
                logger.error(f'[ML] Ensemble training failed for {symbol}: {e}', exc_info=True)
        background_tasks.add_task(_train)
        return {'status': 'ensemble_training_started', 'symbol': symbol}


@app.get('/ensemble/predict/{symbol}')
async def ensemble_predict(symbol: str):
    """Get ensemble prediction (average of multiple horizons)."""
    from predictor import TrendPredictor
    return TrendPredictor.get_ensemble_prediction(symbol)


# ========== Signal endpoints (핵심 API) ==========

@app.get('/signal/top-movers')
async def signal_top_movers(n: int = Query(20)):
    """빅무브 확률 상위 N개 종목 반환. 다른 프로그램에서 호출하는 메인 API."""
    from scanner import get_top_movers
    return get_top_movers(n)


@app.get('/signal/{symbol}')
async def signal_symbol(symbol: str):
    """특정 종목의 시그널 (BIG_MOVE_UP/DOWN, SMALL_MOVE, UNCERTAIN)."""
    from scanner import get_signal
    return get_signal(symbol)


@app.get('/signal')
async def signal_all():
    """최신 전체 스캔 결과."""
    from scanner import get_latest_scan
    return get_latest_scan()


@app.post('/signal/scan')
async def signal_scan_now():
    """즉시 빅무브 스캔 실행."""
    from scanner import scan_all_async
    return await scan_all_async()


@app.post('/signal/train')
async def signal_train_now(background_tasks: BackgroundTasks):
    """즉시 변동성 모델 재학습 + 빅무브 스캔."""
    from scanner import train_all_models, scan_all_async
    from symbol_screener import get_screened_symbols

    symbols = get_screened_symbols()

    async def _train_and_scan():
        try:
            train_all_models(symbols=symbols)
            await scan_all_async(symbols=symbols)
            logger.info(f'[Scanner] Manual train + scan complete: {len(symbols)} symbols')
        except Exception as e:
            logger.error(f'[Scanner] Manual train error: {e}', exc_info=True)

    asyncio.create_task(_train_and_scan())
    return {'status': 'training_and_scanning_started', 'symbols_count': len(symbols)}


@app.post('/signal/train-sync')
async def signal_train_sync():
    """동기 변동성 모델 재학습 + 빅무브 스캔."""
    from scanner import train_all_models, scan_all_async
    from symbol_screener import get_screened_symbols

    symbols = get_screened_symbols()
    train_results = train_all_models(symbols=symbols)
    scan_result = await scan_all_async(symbols=symbols)
    return {
        'train_results': train_results,
        'scan': scan_result,
    }


# ========== Direction endpoints ==========

@app.get('/direction/{symbol}')
async def direction_symbol(symbol: str):
    """규칙 기반 방향 예측 (funding + L/S ratio + taker flow)."""
    from direction_engine import get_direction
    return await get_direction(symbol)


@app.get('/direction')
async def direction_batch(symbols: str = Query(..., description='Comma-separated symbols')):
    """여러 종목 방향 예측."""
    from direction_engine import get_directions_batch
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
    return await get_directions_batch(symbol_list)


# ========== Screener endpoints ==========

@app.get('/screener/status')
async def screener_status():
    """Current screened symbols and details."""
    from symbol_screener import get_screen_status
    return get_screen_status()


@app.post('/screener/run')
async def screener_run():
    """Manually trigger symbol screening."""
    from symbol_screener import screen_volume_spikes
    results = await screen_volume_spikes()
    return {'total': len(results), 'symbols': [r['symbol'] for r in results], 'details': results}


# ========== Martingale Screener endpoints ==========

@app.post('/martingale/screen')
async def martingale_screen(
    top_n: int = Query(10),
    min_volume: float = Query(10_000_000, description='Min 24h volume USD'),
    symbols: Optional[str] = Query(None, description='Comma-separated symbols (optional)'),
):
    """마틴게일 전략에 최적인 종목 스크리닝."""
    from martingale_screener import screen_martingale_candidates
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()] if symbols else None
    return await screen_martingale_candidates(symbol_list, top_n, min_volume)


@app.get('/martingale/candidates')
async def martingale_candidates(top_n: int = Query(10)):
    """최신 마틴게일 스크리닝 결과 (캐시)."""
    from martingale_screener import get_latest_result
    result = get_latest_result()
    if not result:
        return {'error': 'No screening result yet. Run POST /martingale/screen first.'}
    return result


@app.get('/martingale/analyze/{symbol}')
async def martingale_analyze(symbol: str):
    """단일 종목 마틴게일 적합도 분석."""
    from martingale_screener import analyze_symbol, _sanitize_for_json
    result = analyze_symbol(symbol)
    if not result:
        return {'error': f'Not enough data for {symbol}'}
    return _sanitize_for_json(result)


# ========== Prediction endpoints (legacy) ==========

@app.get('/predict/{symbol}')
async def predict_symbol(
    symbol: str,
    timeframe: str = Query('1h'),
):
    from predictor import TrendPredictor
    return TrendPredictor.get_prediction(symbol, timeframe)


@app.get('/predict-batch')
async def predict_batch(
    symbols: str = Query(..., description='Comma-separated symbols'),
    timeframe: str = Query('1h'),
):
    from predictor import TrendPredictor
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
    return TrendPredictor.get_batch_predictions(symbol_list, timeframe)


@app.get('/models')
async def list_models():
    from predictor import TrendPredictor
    return TrendPredictor.list_models()


@app.post('/reload/{symbol}')
async def reload_model(symbol: str, timeframe: str = Query('1h')):
    from predictor import TrendPredictor
    TrendPredictor.reload_model(symbol, timeframe)
    return {'status': 'reloaded', 'symbol': symbol, 'timeframe': timeframe}


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=ML_PORT, reload=True)
