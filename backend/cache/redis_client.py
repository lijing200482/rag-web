"""Redis 连接池管理 + 异步客户端。

模块级单例：连接池和客户端全局共享，避免每个请求新建连接。
应用关闭时调用 close_redis() 释放资源。

健壮性策略:
  - 连接失败时返回 None，不抛异常
  - 调用方需检查返回值，None 时降级到 MySQL
"""
from __future__ import annotations

import logging
from typing import Optional
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError
from ..core.config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None
_available: bool = False  # 标记 Redis 是否可用


async def get_redis() -> Optional[Redis]:
    """获取 Redis 异步客户端（懒加载 + 单例）。

    连接失败时返回 None（不抛异常），调用方需判空处理。
    """
    global _pool, _client, _available
    if _client is not None:
        return _client if _available else None

    settings = get_settings()
    try:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        _client = Redis(connection_pool=_pool)
        # 验证连接
        await _client.ping()
        _available = True
        logger.info(f"Redis 连接已建立: {settings.redis_url}")
        return _client
    except RedisError as e:
        _available = False
        logger.warning(
            f"Redis 不可用，将降级到 MySQL 直查。错误: {e}"
        )
        # 清理半成品
        if _client:
            try:
                await _client.aclose()
            except Exception:
                pass
        _client = None
        if _pool:
            try:
                await _pool.disconnect()
            except Exception:
                pass
            _pool = None
        return None
    except Exception as e:
        _available = False
        logger.warning(f"Redis 初始化失败: {e}")
        return None


async def close_redis() -> None:
    """应用关闭时释放连接池。"""
    global _client, _pool
    if _client:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None
    if _pool:
        try:
            await _pool.disconnect()
        except Exception:
            pass
        _pool = None
    logger.info("Redis 连接已关闭")


def is_redis_available() -> bool:
    """检查 Redis 是否已初始化且可用。"""
    return _available and _client is not None
