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

class AccountOut(BaseModel):
    id: int
    exchange_name: str
    account_name: str
    account_number: Optional[str] = None
    is_active: bool = False
    
    class Config:
        orm_mode = True

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
    
    new_account = ExchangeAccount(
        user_id=current_user.id,
        exchange_name=account_in.exchange_name,
        account_name=account_in.account_name,
        encrypted_access_key=encrypted_access,
        encrypted_secret_key=encrypted_secret,
        account_number=account_in.account_number
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
    return {"status": "success"}

@router.put("/{account_id}/activate")
def activate_account(
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
    
    return {"status": "success", "message": f"Account {account.account_name} activated"}
