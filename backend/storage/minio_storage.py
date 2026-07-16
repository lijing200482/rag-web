"""MinIOStorage —— MinIO S3 兼容对象存储后端实现。

对象路径规范：{kb_id}/{hash_prefix}/{original_filename}
    - kb_id 前缀：按知识库隔离，删除知识库时按前缀批量清理
    - hash_prefix：文件 SHA-256 前 8 位，打散目录避免单目录海量文件
    - original_filename：保留原始名便于辨识

使用 aioboto3 提供异步 S3 客户端，同一套代码可无缝切换到 AWS S3、
腾讯云 COS、阿里云 OSS（仅需修改 endpoint/credentials）。

参见文档：docs/V3-对象存储升级-MinIO方案.md 第 3.3 节、第二节
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import urllib.parse

import aioboto3
from botocore.config import Config as BotoConfig

from .base import StorageBackend

logger = logging.getLogger(__name__)


def _encode_metadata_value(value: str) -> str:
    """对 S3 元数据值做 ASCII 安全编码。

    S3 协议规定用户自定义 metadata 只能包含 ASCII 字符，
    非法字符会被 botocore 直接拒绝（ParamValidationError）。
    对含中文等非 ASCII 字符的值用 URL 百分号编码，
    读取时用 urllib.parse.unquote 解码即可还原。
    """
    if value is None:
        return ""
    s = str(value)
    # safe="" 表示所有非字母数字字符都编码，确保结果纯 ASCII
    return urllib.parse.quote(s, safe="")


def _encode_metadata(metadata: dict | None) -> dict:
    """对 metadata dict 的所有 value 做 ASCII 编码（上传时调用）。"""
    if not metadata:
        return {}
    return {k: _encode_metadata_value(v) for k, v in metadata.items()}


def _decode_metadata(metadata: dict | None) -> dict:
    """对 metadata dict 的所有 value 做 URL 解码（读取时调用）。

    与 _encode_metadata 互逆，用于从 S3 响应中还原原始中文文件名等。
    当前业务不读取 metadata，此函数供未来扩展使用。
    """
    if not metadata:
        return {}
    return {k: urllib.parse.unquote(str(v)) for k, v in metadata.items()}


class MinIOStorage(StorageBackend):
    def __init__(self, settings):
        self._bucket = settings.minio_bucket            # "rag-documents"
        self._endpoint = settings.minio_endpoint         # "localhost:9000"
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._secure = settings.minio_secure             # False（本地开发）
        self._region = settings.minio_region             # "us-east-1"
        self._session = aioboto3.Session()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _client_kwargs(self) -> dict:
        """构造 aioboto3 S3 client 参数。"""
        scheme = "https" if self._secure else "http"
        return {
            "endpoint_url": f"{scheme}://{self._endpoint}",
            "aws_access_key_id": self._access_key,
            "aws_secret_access_key": self._secret_key,
            "region_name": self._region,
            "config": BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        }

    @staticmethod
    def _compute_hash_bytes(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _build_key(self, kb_id: int, file_hash: str, file_name: str) -> str:
        """构建对象 key: {kb_id}/{hash_prefix}/{file_name}"""
        hash_prefix = file_hash[:8]
        return f"{kb_id}/{hash_prefix}/{file_name}"

    async def _ensure_bucket(self, s3) -> None:
        """确保 bucket 存在（首次上传时自动创建）。"""
        try:
            await s3.head_bucket(Bucket=self._bucket)
        except Exception:
            # bucket 不存在则创建
            try:
                await s3.create_bucket(Bucket=self._bucket)
                logger.info(f"[MinIO] Created bucket: {self._bucket}")
            except Exception as e:
                # 并发创建时可能已被其他请求创建，忽略
                logger.debug(f"[MinIO] create_bucket (ignored): {e}")

    # ------------------------------------------------------------------
    # StorageBackend 接口实现
    # ------------------------------------------------------------------

    async def upload(
        self,
        *,
        kb_id: int,
        file_name: str,
        content: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> str:
        """上传到 MinIO，返回对象 key。

        对象 key 由 (kb_id, content_hash, file_name) 决定，相同内容 → 相同 key，
        天然去重（重复上传同内容文件会覆盖同一对象，不产生新对象）。
        """
        file_hash = self._compute_hash_bytes(content)
        key = self._build_key(kb_id, file_hash, file_name)
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            await self._ensure_bucket(s3)
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata=_encode_metadata(metadata),
            )
        logger.info(
            f"[MinIO] Uploaded: bucket={self._bucket}, key={key}, "
            f"size={len(content)} bytes"
        )
        return key

    async def download_to_path(self, key: str, local_path: Path) -> Path:
        """下载到本地临时文件（LangChain loaders 需要本地文件路径）。"""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            body = await response["Body"].read()
        local_path.write_bytes(body)
        return local_path

    async def delete_by_prefix(self, prefix: str) -> int:
        """删除 {prefix}/ 下的所有对象 → 清理整个知识库的文件。

        使用 list_objects_v2 分页器枚举后批量删除（每批最多 1000 个）。
        返回实际删除的对象数量。
        """
        count = 0
        async with self._session.client("s3", **self._client_kwargs()) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self._bucket, Prefix=prefix
            ):
                objects = [
                    {"Key": obj["Key"]} for obj in page.get("Contents", [])
                ]
                if objects:
                    await s3.delete_objects(
                        Bucket=self._bucket, Delete={"Objects": objects}
                    )
                    count += len(objects)
        logger.info(
            f"[MinIO] Cleaned {count} objects under prefix={prefix}"
        )
        return count
