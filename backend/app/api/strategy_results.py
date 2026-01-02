from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any

from ..db.session import get_db
from ..models.strategy_result import StrategyAnalysisResult
from ..schemas.strategy_result import StrategyResultCreate

router = APIRouter()

@router.post("/{tab_id}/{result_type}")
def save_strategy_result(
    tab_id: str, 
    result_type: str, 
    result_in: StrategyResultCreate, 
    db: Session = Depends(get_db)
):
    # Upsert Logic
    db_obj = db.query(StrategyAnalysisResult).filter(
        StrategyAnalysisResult.tab_id == tab_id,
        StrategyAnalysisResult.result_type == result_type
    ).first()

    if db_obj:
        db_obj.data = result_in.data
    else:
        db_obj = StrategyAnalysisResult(
            tab_id=tab_id,
            result_type=result_type,
            data=result_in.data
        )
        db.add(db_obj)
    
    db.commit()
    db.refresh(db_obj)
    return {"status": "ok"}

@router.get("/{tab_id}")
def get_strategy_results(tab_id: str, db: Session = Depends(get_db)):
    results = db.query(StrategyAnalysisResult).filter(
        StrategyAnalysisResult.tab_id == tab_id
    ).all()
    
    response = {
        "backtest": None,
        "optimization": None
    }
    
    for r in results:
        if r.result_type == 'backtest':
            response['backtest'] = r.data
        elif r.result_type == 'optimization':
            response['optimization'] = r.data
            
    return response
