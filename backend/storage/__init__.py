"""存储后端工厂模块。

通过 get_storage(settings) 按 storage_backend 配置返回对应实现：
    - "local" → LocalStorage（本地文件系统，向后兼容）
    - "minio" → MinIOStorage（S3 兼容对象存储）

路由层与 pipeline 层统一通过 get_storage() 获取实例，不感知具体实现。

参见文档：docs/V3-对象存储升级-MinIO方案.md 第七节
"""
from __future__ import annotations

from ..core.config import Settings
from .base import StorageBackend
from .local_storage import LocalStorage
from .minio_storage import MinIOStorage

# 模块级缓存：按 backend 名称缓存实例（Settings 不可哈希，不能用 lru_cache）
# Settings 本身由 get_settings() 缓存，配置在运行期不变，故实例只需构造一次
_storage_cache: dict[str, StorageBackend] = {}


def get_storage(settings: Settings) -> StorageBackend:
    """根据 settings.storage_backend 返回对应的存储后端实例。

    首次调用时构造实例并缓存，后续调用直接返回缓存实例（避免重复创建
    aioboto3 Session 等资源）。Settings 不可哈希，故按 backend 名称做 key。

    Raises:
        ValueError: 未知的 storage_backend 值。
    """
    backend = settings.storage_backend
    if backend in _storage_cache:
        return _storage_cache[backend]

    if backend == "local":
        instance: StorageBackend = LocalStorage(settings)
    elif backend == "minio":
        instance = MinIOStorage(settings)
    else:
        raise ValueError(
            f"未知的存储后端: {backend}（支持: 'local' | 'minio'）"
        )

    _storage_cache[backend] = instance
    return instance


__all__ = ["StorageBackend", "LocalStorage", "MinIOStorage", "get_storage"]
