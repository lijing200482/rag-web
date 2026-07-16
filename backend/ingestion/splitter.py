"""文档分块器 —— V2 增强 hash + chunk_id。

V2 改动：
    - chunk_id 改为基于 (kb_id, file_name, content) 的 SHA-256
      → 相同内容自动去重，与 DocumentChunk 表的 id 主键对齐
    - 每个 chunk 的 hash 字段记录内容 hash（增量更新时判断是否变化）
    - metadata 中带 kb_id（用于向量存储检索时按知识库过滤）
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    kb_id: int | None = None,
    file_name: str | None = None,
) -> list[Document]:
    """Split documents into chunks with semantic boundary awareness.

    Args:
        kb_id: 知识库 ID（写入 chunk.metadata，用于检索时过滤）
        file_name: 文件名（与 kb_id 一起用于生成稳定的 chunk_id）

    V2: 若提供 kb_id 和 file_name，则 chunk_id 基于 (kb_id, file_name, content) 的
    SHA-256 → 相同内容自动去重。否则回退到 uuid4（向后兼容）。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    # Enrich each chunk with V2 metadata
    for chunk in chunks:
        content = chunk.page_content

        # V2: 稳定的 chunk_id（基于内容 hash）
        if kb_id is not None and file_name is not None:
            chunk_id = _compute_chunk_id(kb_id, file_name, content)
        else:
            chunk_id = str(uuid.uuid4())

        chunk.metadata["chunk_id"] = chunk_id
        chunk.metadata["hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk.metadata["timestamp"] = datetime.now(timezone.utc).isoformat()

        # 持久化 kb_id 到 metadata（用于检索时按知识库过滤）
        if kb_id is not None:
            chunk.metadata["kb_id"] = kb_id

    return chunks


def _compute_chunk_id(kb_id: int, file_name: str, content: str) -> str:
    """计算 chunk 的稳定 ID：基于 (kb_id, file_name, content) 的 SHA-256。

    相同内容 → 相同 ID，与 DocumentChunk 表的主键设计一致 → 自动去重。
    """
    raw = f"{kb_id}:{file_name}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
