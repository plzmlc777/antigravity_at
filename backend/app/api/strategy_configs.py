from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..crud.crud_strategy_config import strategy_config
from ..schemas.strategy_config import StrategyConfig, StrategyConfigCreate

router = APIRouter()

@router.get("/{strategy_id}", response_model=List[StrategyConfig])
def read_strategy_configs(
    strategy_id: str,
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """
    Retrieve strategy configurations for a specific strategy.
    """
    return strategy_config.get_multi(db, strategy_id=strategy_id, skip=skip, limit=limit)

@router.post("/{strategy_id}/sync", response_model=List[StrategyConfig])
def sync_strategy_configs(
    *,
    strategy_id: str,
    db: Session = Depends(get_db),
    configs: List[StrategyConfigCreate]
):
    """
    Sync strategy configurations for a specific strategy.
    Replaces all existing configurations for this strategy with the new list.
    """
    # Ensure strategy_id in config objects matches path (optional but good for consistency)
    for c in configs:
        c.strategy_id = strategy_id

    return strategy_config.replace_all(db, strategy_id=strategy_id, configs=configs)

@router.post("/{strategy_id}/sync-selective", response_model=List[StrategyConfig])
def sync_strategy_configs_selective(
    *,
    strategy_id: str,
    db: Session = Depends(get_db),
    configs: List[StrategyConfigCreate],
    preserve_inactive: bool = True
):
    """
    Selectively sync strategy configurations for a specific strategy.
    Preserves inactive (Draft) tabs while synchronizing active tabs.

    Parameters:
    - strategy_id: Strategy identifier
    - configs: List of configurations to sync
    - preserve_inactive: If True, keep is_active=False tabs (default: True)

    Returns:
    - List of all configurations for this strategy (including preserved inactive tabs)
    """
    # Ensure strategy_id in config objects matches path
    for c in configs:
        c.strategy_id = strategy_id

    return strategy_config.sync_selective(db, strategy_id=strategy_id, configs=configs, preserve_inactive=preserve_inactive)
