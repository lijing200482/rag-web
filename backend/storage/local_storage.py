"""LocalStorage —— 本地文件系统存储后端（向后兼容实现）。

封装当前已有的文件系统逻辑为 StorageBackend 实现：
    - 用于 storage_backend=local 配置
    - 用于单元测试（不依赖外部 MinIO 服务）
    - 对象 key 即本地文件路径（documents/kb_{id}/{file_name}）

参见文档：docs/V3-对象存储升级-MinIO方案.md 第 3.4 节
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .base import StorageBackend


class LocalStorage(StorageBackend):
    def __init__(self, settings):
        self._base_dir = Path(settings.documents_dir)  # "documents"

    def _path(self, kb_id: int, file_name: str) -> Path:
        """本地存储路径：{base_dir}/kb_{kb_id}/{file_name}"""
        return self._base_dir / f"kb_{kb_id}" / file_name

    async def upload(
        self,
        *,
        kb_id: int,
        file_name: str,
        content: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> str:
        """写入本地文件，返回本地路径（作为 key）。

        metadata 在本地存储下不持久化（本地文件系统无对象级元数据能力），
        仅保留参数以兼容接口。
        """
        path = self._path(kb_id, file_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    async def download_to_path(self, key: str, local_path: Path) -> Path:
        """本地文件直接复制到临时路径（供 LangChain loaders 使用）。"""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(key), local_path)
        return local_path

    async def delete_by_prefix(self, prefix: str) -> int:
        """删除 kb_{id}/ 目录（prefix 形如 "kb_1/" 或 "1/"）。

        本地文件不精确计数，返回 0。
        """
        kb_dir = self._base_dir / prefix.rstrip("/")
        if kb_dir.exists() and kb_dir.is_dir():
            shutil.rmtree(kb_dir)
        return 0  # 本地文件不精确计数
