from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..crud.crud_strategy_config import strategy_config
from ..schemas.strategy_config import StrategyConfig, StrategyConfigCreate
from ..models.account import ExchangeAccount

router = APIRouter()

def get_active_account_id(db: Session) -> Optional[int]:
    """Get the ID of the currently active account."""
    active = db.query(ExchangeAccount).filter(ExchangeAccount.is_active == True).first()
    return active.id if active else None

@router.get("/{strategy_id}", response_model=List[StrategyConfig])
def read_strategy_configs(
    strategy_id: str,
    db: Session = Depends(get_db),
    account_id: Optional[int] = Query(None, description="Filter by account ID. If not provided, uses active account."),
    skip: int = 0,
    limit: int = 100
):
    """
    Retrieve strategy configurations for a specific strategy and account.
    """
    # Use provided account_id or fallback to active account
    effective_account_id = account_id if account_id is not None else get_active_account_id(db)
    return strategy_config.get_multi(db, strategy_id=strategy_id, account_id=effective_account_id, skip=skip, limit=limit)

@router.post("/{strategy_id}/sync", response_model=List[StrategyConfig])
def sync_strategy_configs(
    *,
    strategy_id: str,
    db: Session = Depends(get_db),
    configs: List[StrategyConfigCreate],
    account_id: Optional[int] = Query(None, description="Account ID. If not provided, uses active account.")
):
    """
    Sync strategy configurations for a specific strategy and account.
    Replaces all existing configurations for this strategy/account with the new list.
    """
    # Use provided account_id or fallback to active account
    effective_account_id = account_id if account_id is not None else get_active_account_id(db)

    # Ensure strategy_id in config objects matches path
    for c in configs:
        c.strategy_id = strategy_id
        c.account_id = effective_account_id

    return strategy_config.replace_all(db, strategy_id=strategy_id, configs=configs, account_id=effective_account_id)

@router.post("/{strategy_id}/sync-selective", response_model=List[StrategyConfig])
def sync_strategy_configs_selective(
    *,
    strategy_id: str,
    db: Session = Depends(get_db),
    configs: List[StrategyConfigCreate],
    preserve_inactive: bool = True,
    account_id: Optional[int] = Query(None, description="Account ID. If not provided, uses active account.")
):
    """
    Selectively sync strategy configurations for a specific strategy and account.
    Preserves inactive (Draft) tabs while synchronizing active tabs.

    Parameters:
    - strategy_id: Strategy identifier
    - configs: List of configurations to sync
    - preserve_inactive: If True, keep is_active=False tabs (default: True)
    - account_id: Account ID. If not provided, uses active account.

    Returns:
    - List of all configurations for this strategy/account (including preserved inactive tabs)
    """
    # Use provided account_id or fallback to active account
    effective_account_id = account_id if account_id is not None else get_active_account_id(db)

    # Ensure strategy_id and account_id in config objects matches
    for c in configs:
        c.strategy_id = strategy_id
        c.account_id = effective_account_id

    return strategy_config.sync_selective(db, strategy_id=strategy_id, configs=configs, preserve_inactive=preserve_inactive, account_id=effective_account_id)
