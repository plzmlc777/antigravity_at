import uuid
from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..core import security
from ..models.user import User
from ..core.config import settings
from pydantic import BaseModel

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")

class UserCreate(BaseModel):
    email: str
    password: str

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    is_admin: bool = False
    has_active_account: bool = False

# Dependency to get current user
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        token_session_id: str = payload.get("sid")
        if email is None:
            raise credentials_exception
    except security.jwt.JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception

    # Single session enforcement: reject if session_id doesn't match
    # If DB has active_session_id set, token MUST have matching sid (legacy tokens without sid are also rejected)
    if user.active_session_id and token_session_id != user.active_session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired: logged in from another device",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user

# Optional auth: returns user if token present, None otherwise
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token", auto_error=False)

async def get_optional_user(token: str = Depends(oauth2_scheme_optional), db: Session = Depends(get_db)):
    if not token:
        return None
    try:
        payload = security.jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        user = db.query(User).filter(User.email == email).first()
        return user
    except Exception:
        return None

async def get_current_active_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges",
        )
    return current_user

@router.post("/register", response_model=Token)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = security.get_password_hash(user_in.password)
    session_id = str(uuid.uuid4())
    new_user = User(email=user_in.email, hashed_password=hashed_password, active_session_id=session_id)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = security.create_access_token(subject=new_user.email, session_id=session_id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/token", response_model=Token)
def login_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    from ..models.account import ExchangeAccount

    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    # Check if user has any non-disabled account
    active_account = db.query(ExchangeAccount).filter(
        ExchangeAccount.user_id == user.id,
        ExchangeAccount.is_disabled == False
    ).first()

    # Generate new session_id and invalidate previous session
    session_id = str(uuid.uuid4())
    user.active_session_id = session_id
    db.commit()

    access_token = security.create_access_token(subject=user.email, session_id=session_id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "is_admin": user.is_admin,
        "has_active_account": active_account is not None
    }

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout endpoint - cleans up all user state.
    Blocks logout if live trading sessions are running.
    """
    from ..core.live_manager import LiveManager

    live_manager = LiveManager.get_instance()
    active_count = live_manager.get_active_sessions_count()

    # Block logout if live sessions are running
    if active_count > 0:
        session_ids = live_manager.get_active_session_ids()
        raise HTTPException(
            status_code=400,
            detail={
                "message": f"Live 세션 {active_count}개 실행 중입니다. 먼저 중지해주세요.",
                "active_sessions": session_ids
            }
        )

    # Clean up all state for this user
    await live_manager.cleanup_for_logout(current_user.id)

    return {
        "status": "success",
        "message": "로그아웃 완료. 모든 상태가 정리되었습니다."
    }


@router.put("/password")
async def change_password(
    password_data: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify current password
    if not security.verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다")

    # Validate new password
    if len(password_data.new_password) < 6:
        raise HTTPException(status_code=400, detail="새 비밀번호는 6자 이상이어야 합니다")

    # Update password
    current_user.hashed_password = security.get_password_hash(password_data.new_password)
    db.commit()

    return {"status": "success", "message": "비밀번호가 변경되었습니다"}
