"""API 密钥管理路由。

按 V2 业务层设计方案：
    /api-keys       POST → 创建密钥
    /api-keys       GET  → 列出我的密钥
    /api-keys/{id}  DELETE → 删除密钥
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_user
from ..db import get_db
from ..schema.api_key import APIKeyCreatedResponse, APIKeyCreate, APIKeyResponse
from ..service import api_key as api_key_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.post(
    "",
    response_model=APIKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key_route(
    payload: APIKeyCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """创建 API 密钥 —— 仅此一次返回完整 key。"""
    api_key, raw_key = await api_key_service.create_api_key(
        payload.name, current_user.id, db
    )
    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=api_key_service.mask_key(raw_key),
        is_active=api_key.is_active,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys_route(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出我的 API 密钥。"""
    keys = await api_key_service.list_api_keys(current_user.id, db)
    return [
        APIKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
            updated_at=k.updated_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}")
async def delete_api_key_route(
    key_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """删除 API 密钥。"""
    deleted = await api_key_service.delete_api_key(key_id, current_user.id, db)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API 密钥不存在")
    return {"deleted": True, "key_id": key_id}
