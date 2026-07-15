"""Redis 连接池管理 + 异步客户端。

模块级单例：连接池和客户端全局共享，避免每个请求新建连接。
应用关闭时调用 close_redis() 释放资源。

健壮性策略:
  - 连接失败时返回 None，不抛异常
  - 调用方需检查返回值，None 时降级到 MySQL
  - 失败后不会永久放弃：距上次失败超过 _RETRY_INTERVAL 秒后会自动重试
"""
from __future__ import annotations

import logging
import time
from typing import Optional
from redis.asyncio import Redis, ConnectionPool
from redis.exceptions import RedisError
from ..core.config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None
_client: Optional[Redis] = None
_available: bool = False  # 标记 Redis 是否可用
_last_fail_time: float = 0.0  # 上次失败的时间戳（秒）
_RETRY_INTERVAL = 30  # 秒：失败后再次重试的最小间隔


async def get_redis() -> Optional[Redis]:
    """获取 Redis 异步客户端（懒加载 + 单例 + 失败重试）。

    连接失败时返回 None（不抛异常），调用方需判空处理。
    首次连接失败后会标记不可用，但距上次失败超过 _RETRY_INTERVAL 秒后
    会自动尝试重连，避免单例一旦失败永不恢复。
    """
    global _pool, _client, _available, _last_fail_time

    # 已有可用客户端，直接复用
    if _available and _client is not None:
        return _client

    # 之前失败过：未到重试间隔则直接返回 None，超过则尝试重连
    if not _available:
        now = time.time()
        if now - _last_fail_time < _RETRY_INTERVAL:
            return None
        logger.info(
            f"Redis 重试：距上次失败 {int(now - _last_fail_time)}s，超过重试间隔 {_RETRY_INTERVAL}s，尝试重新连接"
        )

    settings = get_settings()
    try:
        # 清理上一次失败的半成品连接，避免连接泄漏
        if _client is not None:
            try:
                await _client.aclose()
            except Exception:
                pass
            _client = None
        if _pool is not None:
            try:
                await _pool.disconnect()
            except Exception:
                pass
            _pool = None

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
        _last_fail_time = time.time()
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
        _last_fail_time = time.time()
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
