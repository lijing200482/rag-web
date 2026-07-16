from collections import defaultdict
from functools import lru_cache
from time import time

from fastapi import Depends, HTTPException, Request

from ..auth.dependencies import get_current_user
from ..core.config import Settings, get_settings as _get_settings
from ..ingestion.embedder import get_embedding_provider
from ..vectorstore.milvus_store import MilvusVectorStore


@lru_cache
def get_settings() -> Settings:
    """Cached singleton for settings — reads .env once at startup."""
    return _get_settings()


@lru_cache(maxsize=1)
def get_vector_store() -> MilvusVectorStore:
    """Cached singleton for MilvusVectorStore.

    V3 起由 Milvus 取代 ChromaDB。MilvusClient + Collection 创建较重，
    使用 lru_cache 单例化避免每次请求重建。
    """
    settings = get_settings()
    return MilvusVectorStore(settings)


@lru_cache(maxsize=1)
def get_embedder():
    """Cached singleton for the configured embedder."""
    settings = get_settings()
    return get_embedding_provider(settings).get_embedder()


# 简单的内存滑动窗口限流（per-user / per-IP）
_rate_limit_store: defaultdict = defaultdict(list)


def rate_limit(max_calls: int = 10, window_seconds: int = 60):
    """Per-user 速率限制依赖。

    已登录用户按 user.id 限流；匿名用户按客户端 IP 限流。
    超过 max_calls/window_seconds 时抛 429。
    """

    async def _check(
        request: Request,
        user=Depends(get_current_user),
    ):
        now = time()
        if user is not None:
            key = f"user:{user.id}"
        else:
            client_host = request.client.host if request.client else "unknown"
            key = f"anon:{client_host}"
        # 清理过期记录
        _rate_limit_store[key] = [
            t for t in _rate_limit_store[key] if t > now - window_seconds
        ]
        if len(_rate_limit_store[key]) >= max_calls:
            raise HTTPException(429, "请求过于频繁，请稍后再试")
        _rate_limit_store[key].append(now)
        return user

    return _check
