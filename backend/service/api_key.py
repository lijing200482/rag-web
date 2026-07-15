"""API 密钥业务层 —— APIKey CRUD。

密钥生成规则：secrets.token_urlsafe(32)
存储规则：仅存 SHA-256 hash 到 `key_hash` 列，不存 raw key；
         `key_prefix` 列存前 8 字符用于展示
显示规则：响应中仅返回 key_prefix（前 8 字符 + ...），创建时返回一次完整 key
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.models import APIKey

logger = logging.getLogger(__name__)

_KEY_PREFIX_LEN = 8


def _generate_api_key() -> str:
    """生成随机 API 密钥。"""
    return secrets.token_urlsafe(32)


def _mask_key(key: str) -> str:
    """返回脱敏后的 key 前缀用于显示。"""
    if len(key) <= _KEY_PREFIX_LEN:
        return key
    return key[:_KEY_PREFIX_LEN] + "..."


async def create_api_key(
    name: str, user_id: int, db: AsyncSession
) -> tuple[APIKey, str]:
    """创建 API 密钥。

    Returns:
        (api_key_obj, raw_key): raw_key 仅此一次返回给调用方
    """
    raw_key = _generate_api_key()
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:_KEY_PREFIX_LEN]
    api_key = APIKey(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=user_id,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    logger.info(f"APIKey created: id={api_key.id}, user_id={user_id}, name={name!r}")
    return api_key, raw_key


async def list_api_keys(
    user_id: int, db: AsyncSession
) -> list[APIKey]:
    """列出某用户的全部 API 密钥。"""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.user_id == user_id)
        .order_by(APIKey.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_api_key(
    key_id: int, user_id: int, db: AsyncSession
) -> bool:
    """删除 API 密钥（校验归属权）。"""
    result = await db.execute(
        delete(APIKey)
        .where(APIKey.id == key_id, APIKey.user_id == user_id)
    )
    await db.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info(f"APIKey deleted: id={key_id}, user_id={user_id}")
    return deleted > 0


async def get_api_key_by_value(
    key_value: str, db: AsyncSession
) -> Optional[APIKey]:
    """按 key 值查询密钥（用于 API 鉴权场景）。

    入参 key_value 为 raw key，此处计算 SHA-256 后比对 `key_hash` 列。
    若查到则同步更新 last_used_at。
    """
    key_hash = hashlib.sha256(key_value.encode()).hexdigest()
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return None

    # 更新最后使用时间
    from datetime import datetime, timezone
    await db.execute(
        update(APIKey)
        .where(APIKey.id == api_key.id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return api_key


def mask_key(key: str) -> str:
    """对外暴露的脱敏函数。"""
    return _mask_key(key)
