from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from ..db.session import get_db
from ..models.user import User
from .auth import get_current_active_admin
from pydantic import BaseModel

router = APIRouter()

class UserOut(BaseModel):
    id: int
    email: str
    is_admin: bool

    class Config:
        from_attributes = True

class RoleUpdate(BaseModel):
    is_admin: bool

@router.get("/users", response_model=List[UserOut])
def get_users(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_active_admin)
):
    """List all users (Admin only)"""
    return db.query(User).all()

@router.put("/users/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    role_update: RoleUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_active_admin)
):
    """Update user admin role (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Optional: Prevent self-demotion
    if user.id == admin_user.id and not role_update.is_admin:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")
        
    user.is_admin = role_update.is_admin
    db.commit()
    db.refresh(user)
    return user
