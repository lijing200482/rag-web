"""文件存储后端抽象基类。

将文件操作抽象为 StorageBackend 接口，当前有 LocalStorage 实现（向后兼容）
和 MinIOStorage 实现（S3 兼容对象存储）。通过 core/config.py 的 storage_backend
配置项切换，路由层与 pipeline 层无需感知具体实现。

参见文档：docs/V3-对象存储升级-MinIO方案.md 第三节
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """文件存储后端抽象。

    所有方法均为异步。MinIO 实现用 aioboto3 提供异步支持；
    LocalStorage 实现做同步 I/O 但保持 async 签名以兼容接口。
    """

    @abstractmethod
    async def upload(
        self,
        *,
        kb_id: int,
        file_name: str,
        content: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> str:
        """上传文件，返回存储路径/对象 key。"""
        ...

    @abstractmethod
    async def download_to_path(self, key: str, local_path: Path) -> Path:
        """下载到本地临时文件（供 LangChain loaders 使用），返回本地路径。"""
        ...

    @abstractmethod
    async def delete_by_prefix(self, prefix: str) -> int:
        """按前缀批量删除（用于删除整个知识库）。返回删除数量。"""
        ...
