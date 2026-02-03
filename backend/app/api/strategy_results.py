from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from ..db.session import get_db
from ..models.strategy_result import StrategyAnalysisResult
from ..schemas.strategy_result import StrategyResultCreate
from ..core.user_context import UserAccountContext, get_user_context

router = APIRouter()

@router.post("/{tab_id}/{result_type}")
def save_strategy_result(
    tab_id: str,
    result_type: str,
    result_in: StrategyResultCreate,
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context)
):
    account_id = ctx.account_id

    # Upsert Logic - filter by account_id as well
    db_obj = db.query(StrategyAnalysisResult).filter(
        StrategyAnalysisResult.tab_id == tab_id,
        StrategyAnalysisResult.result_type == result_type,
        StrategyAnalysisResult.account_id == account_id
    ).first()

    if db_obj:
        db_obj.data = result_in.data
    else:
        db_obj = StrategyAnalysisResult(
            tab_id=tab_id,
            result_type=result_type,
            account_id=account_id,
            data=result_in.data
        )
        db.add(db_obj)

    db.commit()
    db.refresh(db_obj)
    return {"status": "ok"}

# Fields to exclude from response (large graphics data)
GRAPHICS_FIELDS = {'chart_data', 'ohlcv_data', 'multi_ohlcv_data', 'trades', 'matched_trades', 'logs', 'equity_curve'}

def _strip_graphics_data(data):
    """Remove large graphics fields from backtest result recursively, keep only stats."""
    if data is None:
        return data
    if isinstance(data, dict):
        return {k: _strip_graphics_data(v) for k, v in data.items() if k not in GRAPHICS_FIELDS}
    if isinstance(data, list):
        return [_strip_graphics_data(item) for item in data]
    return data


@router.get("/{tab_id}")
def get_strategy_results(
    tab_id: str,
    db: Session = Depends(get_db),
    ctx: UserAccountContext = Depends(get_user_context),
    include_graphics: bool = False
):
    import logging
    logger = logging.getLogger(__name__)

    try:
        account_id = ctx.account_id

        logger.info(f"[StrategyResults] Fetching results for tab_id: {tab_id}, account_id: {account_id}, include_graphics: {include_graphics}")

        results = db.query(StrategyAnalysisResult).filter(
            StrategyAnalysisResult.tab_id == tab_id,
            StrategyAnalysisResult.account_id == account_id
        ).all()

        logger.info(f"[StrategyResults] Found {len(results)} results for tab_id: {tab_id}")

        response = {
            "backtest": None,
            "optimization": None
        }

        for r in results:
            if r.result_type == 'backtest':
                # Strip graphics data unless explicitly requested
                response['backtest'] = r.data if include_graphics else _strip_graphics_data(r.data)
                logger.info(f"[StrategyResults] Loaded backtest data, keys: {list(response['backtest'].keys()) if response['backtest'] else 'None'}")
            elif r.result_type == 'optimization':
                response['optimization'] = r.data

        return response
    except Exception as e:
        logger.error(f"[StrategyResults] Error fetching results for tab_id {tab_id}: {str(e)}")
        import traceback
        logger.error(f"[StrategyResults] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
