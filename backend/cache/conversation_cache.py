"""对话记忆 Redis 缓存层（已废弃）。

⚠️ 自 LangChain Memory 重构后不再使用。
已迁移到 backend/memory/custom_history.py（MySQLBackedRedisHistory）。

保留此文件仅供向后兼容，所有新代码应使用 ConversationBufferWindowMemory +
MySQLBackedRedisHistory。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..core.config import get_settings
from ..retrieval.generator import format_history

logger = logging.getLogger(__name__)

# Redis Key 前缀
_MESSAGE_KEY_PREFIX = "conversation"
_WARM_LOCK_SUFFIX = "warm_lock"
_EMPTY_FLAG_SUFFIX = "empty"


def _msg_key(session_id: int) -> str:
    return f"{_MESSAGE_KEY_PREFIX}:{session_id}:messages"


def _lock_key(session_id: int) -> str:
    return f"{_MESSAGE_KEY_PREFIX}:{session_id}:{_WARM_LOCK_SUFFIX}"


def _empty_key(session_id: int) -> str:
    return f"{_MESSAGE_KEY_PREFIX}:{session_id}:{_EMPTY_FLAG_SUFFIX}"


# ==================== 公共 API ====================


async def get_history(
    session_id: int,
    redis: Optional[Redis],
    memory_window: int | None = None,
) -> str:
    """获取对话历史字符串（Read-Through 缓存）。

    1) 读 Redis List
    2) Miss → 加分布式锁 → 从 MySQL 回填 → 释放锁 → 返回
    3) Redis 异常或 None → 降级查 MySQL

    Returns:
        格式化后的历史文本，无历史时返回 ""。
    """
    if memory_window is None:
        memory_window = get_settings().memory_window

    # Redis 不可用 → 直接走 MySQL 降级路径
    if redis is None:
        return await _load_from_mysql_directly(session_id, memory_window)

    key = _msg_key(session_id)

    try:
        # 1) 读缓存
        raw_list = await redis.lrange(key, 0, memory_window - 1)
        if raw_list:
            dicts = [json.loads(item) for item in raw_list]
            history = _dicts_to_history(dicts)
            logger.debug(f"缓存命中: session={session_id}, 条数={len(dicts)}")
            return history

        # 2) 检查空会话标记（防止空会话反复穿透）
        is_empty = await redis.exists(_empty_key(session_id))
        if is_empty:
            logger.debug(f"空会话标记命中: session={session_id}, 跳过回源")
            return ""

    except RedisError as e:
        logger.warning(f"Redis 读异常，降级查 MySQL: session={session_id}, error={e}")
        return await _load_from_mysql_directly(session_id, memory_window)

    # 3) 缓存未命中 → 加锁回源
    return await _warm_from_db(session_id, redis, memory_window)


async def push_message(
    session_id: int,
    role: str,
    content: str,
    redis: Optional[Redis],
) -> None:
    """Write-Through：新消息追加到 Redis List。

    在 MySQL 写入成功后调用，保持缓存热度。

    Args:
        session_id: 会话 ID
        role: "user" 或 "assistant"
        content: 消息文本
        redis: Redis 客户端（None 时跳过缓存写入）
    """
    if redis is None:
        return  # Redis 不可用，跳过

    try:
        key = _msg_key(session_id)
        exists = await redis.exists(key)
        if not exists:
            return  # 未被缓存的会话无需写 Redis

        settings = get_settings()
        item = json.dumps({"role": role, "content": content}, ensure_ascii=False)

        async with redis.pipeline() as pipe:
            pipe.lpush(key, item)
            pipe.ltrim(key, 0, settings.redis_conversation_max_messages - 1)
            pipe.expire(key, settings.redis_conversation_ttl)
            await pipe.execute()

        logger.debug(f"缓存追加: session={session_id}, role={role}")
    except RedisError as e:
        logger.warning(f"Redis 写异常（已降级）: session={session_id}, error={e}")


async def warm_session(session_id: int, redis: Optional[Redis]) -> None:
    """预热：用户打开会话时主动缓存最近消息。

    Args:
        session_id: 会话 ID
        redis: Redis 客户端（None 时跳过）
    """
    if redis is None:
        return

    key = _msg_key(session_id)
    try:
        exists = await redis.exists(key)
        if exists:
            return
    except RedisError:
        return  # Redis 不可用，跳过预热

    settings = get_settings()
    await _warm_from_db(session_id, redis, settings.memory_window)


async def invalidate_session(session_id: int, redis: Optional[Redis]) -> None:
    """删除会话时清除 Redis 缓存。

    Args:
        session_id: 会话 ID
        redis: Redis 客户端（None 时跳过）
    """
    if redis is None:
        return

    try:
        keys = [_msg_key(session_id), _empty_key(session_id)]
        await redis.delete(*keys)
        logger.info(f"缓存清除: session={session_id}")
    except RedisError as e:
        logger.warning(f"Redis 删异常（已降级）: session={session_id}, error={e}")


# ==================== 内部实现 ====================


def _dicts_to_history(dicts: list[dict]) -> str:
    """将消息字典列表格式化为 prompt-ready 历史字符串。

    Redis List 是 LPUSH 的（新在前），format_history 需要旧在前。
    """
    class _Msg:
        __slots__ = ("role", "content")
        def __init__(self, d: dict):
            self.role = d["role"]
            self.content = d["content"]

    msgs = [_Msg(d) for d in reversed(dicts)]
    return format_history(msgs)


async def _warm_from_db(
    session_id: int,
    redis: Redis,
    memory_window: int,
) -> str:
    """加分布式锁，查 MySQL，回填 Redis。"""
    lock_key = _lock_key(session_id)
    msg_key = _msg_key(session_id)

    try:
        acquired = await redis.set(lock_key, "1", nx=True, ex=5)
    except RedisError:
        acquired = False

    if not acquired:
        # 没抢到锁 → 短暂等待后重试读缓存
        await asyncio.sleep(0.1)
        try:
            raw_list = await redis.lrange(msg_key, 0, memory_window - 1)
            if raw_list:
                dicts = [json.loads(item) for item in raw_list]
                return _dicts_to_history(dicts)
        except RedisError:
            pass
        # 降级：直接查 MySQL
        logger.info(f"缓存回源冲突，降级直查 MySQL: session={session_id}")
        return await _load_from_mysql_directly(session_id, memory_window)

    try:
        return await _load_and_cache(session_id, redis, memory_window)
    finally:
        try:
            await redis.delete(lock_key)
        except RedisError:
            pass


async def _load_and_cache(
    session_id: int,
    redis: Redis,
    memory_window: int,
) -> str:
    """从 MySQL 加载消息并写入 Redis。"""
    from sqlalchemy import select
    from ..db.database import async_session as session_factory
    from ..model.chat_session import ChatMessage

    async with session_factory() as db:
        try:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(memory_window)
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()
        except Exception as e:
            logger.error(f"MySQL 查询失败: session={session_id}, error={e}")
            raise

    settings = get_settings()

    if not messages:
        # 空会话：设标记防止反复穿透
        try:
            await redis.set(_empty_key(session_id), "1", ex=60)
        except RedisError:
            pass
        return ""

    dicts = []
    for m in messages:
        dicts.append({"role": m.role, "content": m.content})

    try:
        async with redis.pipeline() as pipe:
            for d in dicts:
                pipe.lpush(_msg_key(session_id), json.dumps(d, ensure_ascii=False))
            pipe.ltrim(_msg_key(session_id), 0, settings.redis_conversation_max_messages - 1)
            pipe.expire(_msg_key(session_id), settings.redis_conversation_ttl)
            await pipe.execute()
    except RedisError as e:
        logger.warning(f"Redis 回填失败，但不影响查询结果: session={session_id}, error={e}")

    logger.info(f"缓存回填完成: session={session_id}, 写入 {len(dicts)} 条消息")
    return _dicts_to_history(dicts)


async def _load_from_mysql_directly(
    session_id: int,
    memory_window: int,
) -> str:
    """Redis 不可用时降级——直接查 MySQL。"""
    from sqlalchemy import select
    from ..db.database import async_session as session_factory
    from ..model.chat_session import ChatMessage

    async with session_factory() as db:
        try:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(memory_window)
            )
            result = await db.execute(stmt)
            messages = result.scalars().all()
        except Exception as e:
            logger.error(f"MySQL 降级查询失败: session={session_id}, error={e}")
            return ""

    msgs = list(messages)
    msgs.reverse()  # id 升序
    return format_history(msgs)
