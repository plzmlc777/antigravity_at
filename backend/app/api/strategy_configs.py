from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..crud.crud_strategy_config import strategy_config
from ..schemas.strategy_config import StrategyConfig, StrategyConfigCreate, ConfigScope
from ..models.account import ExchangeAccount

router = APIRouter()


def get_active_account_id(db: Session = Depends(get_db)) -> int:
    """
    현재 활성화된 계좌 ID를 반환하는 의존성
    - 활성 계좌가 없으면 404 에러
    """
    active_account = db.query(ExchangeAccount).filter(
        ExchangeAccount.is_active == True
    ).first()

    if not active_account:
        raise HTTPException(status_code=404, detail="No active account found. Please activate an account first.")

    return active_account.id


def get_config_scope(
    strategy_id: str,
    account_id: int = Depends(get_active_account_id)
) -> ConfigScope:
    """
    계좌 + 전략 컨텍스트를 반환하는 의존성
    account_id와 strategy_id를 항상 함께 묶어서 관리
    """
    return ConfigScope(account_id=account_id, strategy_id=strategy_id)


@router.get("/{strategy_id}", response_model=List[StrategyConfig])
def read_strategy_configs(
    db: Session = Depends(get_db),
    scope: ConfigScope = Depends(get_config_scope),
    skip: int = 0,
    limit: int = 100
):
    """
    Retrieve strategy configurations for the active account + strategy.
    계좌별로 분리된 설정을 조회합니다.
    """
    return strategy_config.get_multi(db, scope=scope, skip=skip, limit=limit)


@router.post("/{strategy_id}/sync", response_model=List[StrategyConfig])
def sync_strategy_configs(
    *,
    db: Session = Depends(get_db),
    scope: ConfigScope = Depends(get_config_scope),
    configs: List[StrategyConfigCreate]
):
    """
    Sync strategy configurations for the active account + strategy.
    Replaces all existing configurations.
    """
    # Ensure account_id and strategy_id in config objects match scope
    for c in configs:
        c.account_id = scope.account_id
        c.strategy_id = scope.strategy_id

    return strategy_config.replace_all(db, scope=scope, configs=configs)


@router.post("/{strategy_id}/sync-selective", response_model=List[StrategyConfig])
def sync_strategy_configs_selective(
    *,
    db: Session = Depends(get_db),
    scope: ConfigScope = Depends(get_config_scope),
    configs: List[StrategyConfigCreate],
    preserve_inactive: bool = True
):
    """
    Selectively sync strategy configurations for the active account + strategy.
    Preserves inactive (Draft) tabs while synchronizing active tabs.

    Parameters:
    - strategy_id: Strategy identifier (from URL path)
    - configs: List of configurations to sync
    - preserve_inactive: If True, keep is_active=False tabs (default: True)

    Returns:
    - List of all configurations for this account + strategy (including preserved inactive tabs)
    """
    # Ensure account_id and strategy_id in config objects match scope
    for c in configs:
        c.account_id = scope.account_id
        c.strategy_id = scope.strategy_id

    return strategy_config.sync_selective(
        db,
        scope=scope,
        configs=configs,
        preserve_inactive=preserve_inactive
    )
