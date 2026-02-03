from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db.session import get_db
from ..models.account import ExchangeAccount
from ..models.user import User
from ..core import security
from ..core.trading_env import TradingEnvironment, get_env_config
from .auth import get_current_user

router = APIRouter()


class AccountCreate(BaseModel):
    exchange_name: str
    account_name: str
    access_key: str
    secret_key: str
    account_number: Optional[str] = None
    environment: str = TradingEnvironment.REAL.value  # "real", "virtual", "paper"


class AccountOut(BaseModel):
    id: int
    exchange_name: str
    account_name: str
    account_number: Optional[str] = None
    is_active: bool = False
    is_disabled: bool = False
    environment: str  # "real", "virtual", "paper"
    # Computed properties for backward compatibility
    is_virtual: bool = False
    api_url: Optional[str] = None
    display_name: str = ""

    class Config:
        from_attributes = True


class AccountUpdate(BaseModel):
    account_name: Optional[str] = None
    is_disabled: Optional[bool] = None


@router.get("/", response_model=List[AccountOut])
def get_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    accounts = db.query(ExchangeAccount).filter(ExchangeAccount.user_id == current_user.id).all()
    # Convert to response with computed properties
    result = []
    for acc in accounts:
        result.append(AccountOut(
            id=acc.id,
            exchange_name=acc.exchange_name,
            account_name=acc.account_name,
            account_number=acc.account_number,
            is_active=acc.is_active,
            is_disabled=acc.is_disabled,
            environment=acc.environment or TradingEnvironment.REAL.value,
            is_virtual=acc.is_virtual,
            api_url=acc.api_url,
            display_name=acc.display_name
        ))
    return result


@router.post("/", response_model=AccountOut)
def create_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Validate environment value
    try:
        env = TradingEnvironment(account_in.environment)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid environment: {account_in.environment}")

    # Encrypt keys
    encrypted_access = security.encrypt_key(account_in.access_key)
    encrypted_secret = security.encrypt_key(account_in.secret_key)

    new_account = ExchangeAccount(
        user_id=current_user.id,
        exchange_name=account_in.exchange_name,
        account_name=account_in.account_name,
        encrypted_access_key=encrypted_access,
        encrypted_secret_key=encrypted_secret,
        account_number=account_in.account_number,
        environment=env.value
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)

    return AccountOut(
        id=new_account.id,
        exchange_name=new_account.exchange_name,
        account_name=new_account.account_name,
        account_number=new_account.account_number,
        is_active=new_account.is_active,
        is_disabled=new_account.is_disabled,
        environment=new_account.environment,
        is_virtual=new_account.is_virtual,
        api_url=new_account.api_url,
        display_name=new_account.display_name
    )


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Block if live sessions are running
    from ..core.live_manager import LiveManager
    live_manager = LiveManager.get_instance()
    active_count = live_manager.get_active_sessions_count()

    if active_count > 0:
        session_ids = live_manager.get_active_session_ids()
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Live 세션 {active_count}개 실행 중입니다. 계정 삭제 전 먼저 중지해주세요.",
                "active_sessions": session_ids
            }
        )

    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    db.delete(account)
    db.commit()

    # Invalidate Cache
    from ..core.account_cache import AccountCache
    AccountCache.get_instance().invalidate(current_user.id)

    return {"status": "success"}


@router.put("/{account_id}/activate")
async def activate_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 0. Block if live sessions are running
    from ..core.live_manager import LiveManager
    live_manager = LiveManager.get_instance()
    active_count = live_manager.get_active_sessions_count()

    if active_count > 0:
        session_ids = live_manager.get_active_session_ids()
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Live 세션 {active_count}개 실행 중입니다. 계정 전환 전 먼저 중지해주세요.",
                "active_sessions": session_ids
            }
        )

    # 1. Verify account ownership
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # 2. Deactivate all other accounts for this user
    db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id
    ).update({"is_active": False})

    # 3. Activate target account
    account.is_active = True
    db.commit()

    # 4. 캐시를 새 계좌 정보로 즉시 업데이트 (invalidate 대신 직접 설정)
    from ..core.account_cache import AccountCache
    from ..core.trading_env import TradingEnvironment

    try:
        decrypted_app = security.decrypt_key(account.encrypted_access_key)
        decrypted_secret = security.decrypt_key(account.encrypted_secret_key)

        new_config = {
            'app_key': decrypted_app,
            'secret_key': decrypted_secret,
            'account_no': account.account_number,
            'account_name': account.account_name,
            'environment': account.environment or TradingEnvironment.REAL.value
        }

        # 캐시에 새 값 직접 설정 (race condition 방지)
        AccountCache.get_instance().set_active_account_config(current_user.id, new_config)
    except Exception as e:
        # 복호화 실패 시 캐시 무효화 (fallback)
        AccountCache.get_instance().invalidate(current_user.id)
        print(f"[Activate] Cache update failed, invalidated instead: {e}")

    # 5. Notify LiveManager to reinitialize adapter with new account
    from ..core.live_manager import LiveManager
    live_manager = LiveManager.get_instance()
    adapter_result = await live_manager.on_account_changed()

    return {
        "status": "success",
        "message": f"Account {account.account_name} activated",
        "adapter": adapter_result
    }


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(
    account_id: int,
    account_update: AccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.id == account_id,
        ExchangeAccount.user_id == current_user.id
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update fields if provided
    if account_update.account_name is not None:
        account.account_name = account_update.account_name

    if account_update.is_disabled is not None:
        account.is_disabled = account_update.is_disabled
        # If disabling, also deactivate
        if account_update.is_disabled and account.is_active:
            account.is_active = False

    db.commit()
    db.refresh(account)

    # Invalidate Cache
    from ..core.account_cache import AccountCache
    AccountCache.get_instance().invalidate(current_user.id)

    return AccountOut(
        id=account.id,
        exchange_name=account.exchange_name,
        account_name=account.account_name,
        account_number=account.account_number,
        is_active=account.is_active,
        is_disabled=account.is_disabled,
        environment=account.environment or TradingEnvironment.REAL.value,
        is_virtual=account.is_virtual,
        api_url=account.api_url,
        display_name=account.display_name
    )


class AccountPreferencesOut(BaseModel):
    """계좌별 환경설정"""
    last_selected_strategy_id: Optional[str] = None
    saved_symbols: Optional[List] = None


class UpdateLastStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None


@router.get("/preferences", response_model=AccountPreferencesOut)
def get_account_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current active account's preferences (last selected strategy, saved symbols, etc.)
    계좌 중심으로 환경설정 조회
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    return AccountPreferencesOut(
        last_selected_strategy_id=account.last_selected_strategy_id,
        saved_symbols=account.saved_symbols if hasattr(account, 'saved_symbols') else None
    )


@router.put("/preferences/strategy")
def update_last_selected_strategy(
    request: UpdateLastStrategyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update last selected strategy for current active account
    계좌별로 마지막 선택 전략 저장
    """
    # Get active account
    account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == current_user.id,
        ExchangeAccount.is_active == True
    ).first()

    if not account:
        raise HTTPException(status_code=404, detail="No active account found")

    # Update last selected strategy
    account.last_selected_strategy_id = request.strategy_id
    db.commit()

    return {"status": "success", "last_selected_strategy_id": request.strategy_id}
