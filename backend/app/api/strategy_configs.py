from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..crud.crud_strategy_config import strategy_config
from ..schemas.strategy_config import StrategyConfig, StrategyConfigCreate

router = APIRouter()

@router.get("/", response_model=List[StrategyConfig])
def read_strategy_configs(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """
    Retrieve strategy configurations.
    """
    return strategy_config.get_multi(db, skip=skip, limit=limit)

@router.post("/", response_model=List[StrategyConfig])
def sync_strategy_configs(
    *,
    db: Session = Depends(get_db),
    configs: List[StrategyConfigCreate]
):
    """
    Sync strategy configurations.
    Replaces all existing configurations with the new list.
    """
    return strategy_config.replace_all(db, configs=configs)
