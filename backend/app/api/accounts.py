from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db.session import get_db
from ..models.account import ExchangeAccount
from ..models.user import User
from ..core import security
from .auth import get_current_user

router = APIRouter()

class AccountCreate(BaseModel):
    exchange_name: str
    account_name: str
    access_key: str
    secret_key: str
    account_number: Optional[str] = None
    is_virtual: bool = False  # 가상 계좌 (모의투자 서버 사용 여부)
    api_url: Optional[str] = None  # Custom API URL (None = use default)

class AccountOut(BaseModel):
    id: int
    exchange_name: str
    account_name: str
    account_number: Optional[str] = None
    is_active: bool = False
    is_virtual: bool = False  # 가상 계좌 여부
    is_disabled: bool = False  # 사용 안함 상태
    api_url: Optional[str] = None

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
    return db.query(ExchangeAccount).filter(ExchangeAccount.user_id == current_user.id).all()

@router.post("/", response_model=AccountOut)
def create_account(
    account_in: AccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Encrypt keys
    encrypted_access = security.encrypt_key(account_in.access_key)
    encrypted_secret = security.encrypt_key(account_in.secret_key)
    
    # Set api_url based on is_virtual flag if not explicitly provided
    api_url = account_in.api_url
    if api_url is None and account_in.is_virtual:
        # Default to Kiwoom mock server for virtual accounts
        api_url = "https://mockapi.kiwoom.com"

    new_account = ExchangeAccount(
        user_id=current_user.id,
        exchange_name=account_in.exchange_name,
        account_name=account_in.account_name,
        encrypted_access_key=encrypted_access,
        encrypted_secret_key=encrypted_secret,
        account_number=account_in.account_number,
        is_virtual=account_in.is_virtual,
        api_url=api_url
    )
    db.add(new_account)
    db.commit()
    db.refresh(new_account)
    return new_account

@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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

    # 4. Invalidate Cache
    from ..core.account_cache import AccountCache
    AccountCache.get_instance().invalidate(current_user.id)

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

    return account
