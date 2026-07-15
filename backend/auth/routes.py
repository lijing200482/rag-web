import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import Settings, get_settings
from ..db import get_db
from ..schema.auth import UserRegister, UserLogin, UserResponse, TokenResponse
from .security import hash_password, verify_password, create_access_token
from .service import create_user, get_user_by_credential, user_exists, list_users, update_user_status, get_user_by_id
from .dependencies import require_user, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(
    data: UserRegister,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    exists, field = await user_exists(data.email, data.username, db)
    if exists:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{field} already registered",
        )
    hashed = hash_password(data.password)
    user = await create_user(data.email, data.username, hashed, db)
    token = create_access_token(user.id, settings)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_credential(data.credential, db)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been disabled",
        )
    token = create_access_token(user.id, settings)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user, from_attributes=True),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user=Depends(require_user)):
    return UserResponse.model_validate(current_user, from_attributes=True)


# ============ 管理员接口 ============

@router.get("/users", response_model=list[UserResponse])
async def get_users(
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """获取所有用户列表（仅管理员）。"""
    users = await list_users(db)
    return [UserResponse.model_validate(u, from_attributes=True) for u in users]


@router.patch("/users/{user_id}/status", response_model=UserResponse)
async def toggle_user_status(
    user_id: int,
    is_active: bool,
    admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用用户（仅管理员）。

    保护规则：
        1. 不能禁用自己（避免误锁）
        2. 不能禁用其他超级管理员（防止管理员互相封禁导致无管理员）
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own status",
        )
    target = await get_user_by_id(user_id, db)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if target.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify superuser status",
        )
    user = await update_user_status(user_id, is_active, db)
    return UserResponse.model_validate(user, from_attributes=True)
