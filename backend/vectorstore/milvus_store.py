"""向量存储 —— Milvus 实现（V3）。

V3 起由 Milvus 取代 ChromaDB：
    - 先使用 Milvus Lite（pip install pymilvus，零外部依赖，本地文件持久化）
    - 后续可无缝升级至 Milvus Standalone（Docker）
    - 保留 VectorStore 抽象基类，便于切换实现

Collection Schema 严格遵循 docs/V3-向量数据库升级-Milvus方案.md 第二节：
    - 主键 id (VarChar 64) = chunk_id（SHA-256）
    - embedding (FloatVector 768) = nomic-embed-text 输出维度
    - 必选标量: text / source / kb_id（建索引）
    - 可选标量: document_type / page_number / chunk_index
    - JSON 元数据: metadata_json（放 hash / uploaded_at 等零散字段）

索引：
    - 向量: HNSW + COSINE（与原 ChromaDB cosine 距离一致）
    - 标量: kb_id / source 建 INVERTED 索引（加速过滤查询）
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pymilvus import DataType, MilvusClient

from ..core.config import Settings

logger = logging.getLogger(__name__)

# nomic-embed-text 输出 768 维
_DIMENSION = 768


def _escape_filter_string(value: str) -> str:
    """转义 Milvus filter 表达式中的字符串字面量。

    Milvus filter 表达式用双引号包裹字符串字面量，
    若 value 含双引号会破坏表达式结构甚至注入。
    通过将 " 替换为 \" 实现安全转义。

    例：
        a"b → "a\\"b"
        中文文档.md → "中文文档.md"
    """
    if value is None:
        return ""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')

# ── Windows 兼容性 patch ──────────────────────────────────────────────
# milvus-lite 的 manifest.save() 用 os.rename(tmp, target) 做原子提交，
# 但 Python 的 os.rename 在 Windows上当 target 已存在时会抛 WinError 183，
# 导致第二次及后续 create_index / upsert 失败。
# os.replace 才是跨平台原子覆盖的正确 API，这里 patch milvus_lite 内部使用
# 的 os.rename 指向 os.replace，消除 Windows 上的 manifest.json 冲突。
# patch 只执行一次，幂等。
_patch_applied = False


def _apply_windows_rename_patch() -> None:
    global _patch_applied
    if _patch_applied:
        return
    try:
        import milvus_lite.storage.manifest as _m  # type: ignore[import-not-found]

        # manifest.save 内部直接调用 os.rename，把模块级 os.rename 替换为 os.replace
        _m.os.rename = os.replace  # type: ignore[attr-defined]
        _patch_applied = True
        logger.info("[Milvus] Applied Windows os.rename→os.replace patch for milvus-lite")
    except ImportError:
        # 非 Lite 模式（Standalone）不需要 patch
        pass


class VectorStore:
    """向量存储 CRUD 抽象基类。

    V3 新增 delete_by_kb_id_and_source 用于 pipeline 失败回滚
    （按 kb_id + source 精确定位刚写入的向量，避免孤儿数据）。
    """

    async def upsert(self, documents: list[Document], embedder: Embeddings) -> None:
        raise NotImplementedError

    async def delete_by_kb_id(self, kb_id: int) -> int:
        raise NotImplementedError

    async def delete_by_kb_id_and_source(self, kb_id: int, source_filename: str) -> int:
        """按 (kb_id, source) 精确删除。用于 pipeline 失败回滚。"""
        raise NotImplementedError

    async def search(
        self,
        query: str,
        embedder: Embeddings,
        top_k: int = 4,
        kb_ids: list[int] | None = None,
    ) -> list[Document]:
        raise NotImplementedError

    def close(self) -> None:
        """释放底层连接资源。默认空实现，子类按需覆盖。"""
        # 默认无操作，MilvusVectorStore 等持有连接的实现覆盖此方法
        return None


def _build_schema():
    """构建 Collection Schema（严格按文档 2.2 节）。"""
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    # 主键
    schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
    # 向量
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=_DIMENSION)
    # 必选标量
    schema.add_field("text", DataType.VARCHAR, max_length=65535)
    schema.add_field("source", DataType.VARCHAR, max_length=255)
    schema.add_field("kb_id", DataType.INT64)
    # 可选标量
    schema.add_field("document_type", DataType.VARCHAR, max_length=20)
    schema.add_field("page_number", DataType.INT64, nullable=True)
    schema.add_field("chunk_index", DataType.INT64, nullable=True)
    # JSON 元数据
    schema.add_field("metadata_json", DataType.JSON)
    return schema


def _build_index_params():
    """构建索引参数（严格按文档 2.3 节）。"""
    index_params = MilvusClient.prepare_index_params()
    # 向量索引：HNSW + COSINE
    index_params.add_index(
        field_name="embedding",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )
    # 标量索引：加速过滤
    index_params.add_index(field_name="kb_id", index_type="INVERTED")
    index_params.add_index(field_name="source", index_type="INVERTED")
    return index_params


class MilvusVectorStore(VectorStore):
    """Milvus-backed vector store.

    先使用 Milvus Lite（本地文件），后续可升级至 Standalone（Docker）。
    pymilvus 的 MilvusClient 是同步客户端，本类用 asyncio.to_thread 包装
    所有阻塞调用，避免阻塞 FastAPI 事件循环。
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()
        # Windows 兼容：patch milvus-lite 的 os.rename 为 os.replace
        _apply_windows_rename_patch()
        self._client = MilvusClient(self._settings.milvus_uri)
        self._collection_name = self._settings.milvus_collection
        self._ensure_collection()

    def close(self) -> None:
        """关闭底层 MilvusClient 连接，释放资源。

        在 FastAPI lifespan shutdown 时调用。
        幂等：重复调用不会报错。
        """
        try:
            self._client.close()
        except Exception as e:
            logger.debug(f"[Milvus] close skipped: {e}")

    def _ensure_collection(self) -> None:
        """若 Collection 不存在则创建（按文档 3.1 节），并加载到内存。

        Milvus 要求 collection 必须 load 到内存后才能 search/query。
        Lite 模式会自动 load，Standalone 模式需显式调用 load_collection。
        此处统一在创建后调用 load，保证搜索可用。

        注意：milvus-lite 在 Windows 上 create_index 时会用 os.rename
        做原子提交，而 Python 的 os.rename 在 target 已存在时抛 WinError 183。
        本类的模块级 _apply_windows_rename_patch() 已将 os.rename 替换为
        os.replace 解决此问题，故可按标准方式一次性传入 index_params。
        """
        if not self._client.has_collection(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                schema=_build_schema(),
                index_params=_build_index_params(),
            )
            logger.info(
                f"[Milvus] Created collection '{self._collection_name}' "
                f"(dim={_DIMENSION}, HNSW+COSINE)"
            )
        # 确保 collection 已加载到内存（search 前必需）
        try:
            self._client.load_collection(self._collection_name)
        except Exception as e:
            # 已加载的情况下重复 load 会报错，忽略即可
            logger.debug(f"[Milvus] load_collection skipped: {e}")

    # ------------------------------------------------------------------
    # 内部工具：把 LangChain Document 转为 Milvus 行
    # ------------------------------------------------------------------
    @staticmethod
    def _doc_to_row(doc: Document, embedding: list[float]) -> dict:
        """把 LangChain Document 转为 Milvus 行（按 schema 字段映射）。

        metadata 中提取：chunk_id→id, source, kb_id, document_type,
        page_number, chunk_index, hash, uploaded_at 等。
        """
        meta = doc.metadata or {}
        chunk_id = meta.get("chunk_id")
        if not chunk_id:
            raise ValueError("Document missing 'chunk_id' in metadata (required as Milvus primary key)")

        # metadata_json 收纳零散字段（保留 hash / uploaded_at / 原始 meta）
        reserved = {
            "chunk_id", "source", "kb_id", "document_type",
            "page_number", "chunk_index",
        }
        extra_meta: dict[str, Any] = {
            k: v for k, v in meta.items() if k not in reserved
        }
        # 确保文档要求的 hash / uploaded_at 进入 metadata_json
        if "hash" in meta:
            extra_meta["hash"] = meta["hash"]
        if "uploaded_at" in meta:
            extra_meta["uploaded_at"] = meta["uploaded_at"]
        elif "timestamp" in meta:
            # splitter 生成的是 timestamp 字段，统一映射为 uploaded_at
            extra_meta["uploaded_at"] = meta["timestamp"]

        # page_number / chunk_index 可能为 None 或不存在
        page_number = meta.get("page_number")
        chunk_index = meta.get("chunk_index")

        return {
            "id": str(chunk_id),
            "embedding": embedding,
            "text": doc.page_content,
            "source": str(meta.get("source", "")),
            "kb_id": int(meta.get("kb_id", 0)),
            "document_type": str(meta.get("document_type", "")),
            "page_number": int(page_number) if page_number is not None else None,
            "chunk_index": int(chunk_index) if chunk_index is not None else None,
            "metadata_json": extra_meta,
        }

    @staticmethod
    def _hits_to_documents(results) -> list[Document]:
        """把 Milvus 搜索结果转为 LangChain Document 列表（按文档 3.2 节）。

        results 是 MilvusClient.search 返回的 list[list[hit]]，
        每个 hit 含 id/distance/entity。
        """
        docs: list[Document] = []
        for hits in results:  # results[i] 对应 query[i]
            for hit in hits:
                entity = hit.get("entity", {}) or {}
                # 从 metadata_json 恢复零散字段
                metadata: dict[str, Any] = dict(entity.get("metadata_json", {}) or {})
                # 再补充标量字段到 metadata（保持与 ChromaDB 版本兼容）
                metadata["source"] = entity.get("source", "")
                metadata["kb_id"] = entity.get("kb_id")
                metadata["document_type"] = entity.get("document_type", "")
                metadata["page_number"] = entity.get("page_number")
                metadata["chunk_index"] = entity.get("chunk_index")
                metadata["chunk_id"] = hit.get("id", "")

                docs.append(Document(
                    page_content=entity.get("text", ""),
                    metadata=metadata,
                ))
        return docs

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    async def upsert(self, documents: list[Document], embedder: Embeddings) -> None:
        """批量写入：逐条计算 embedding 后 upsert（按文档 3.1 节）。

        Milvus upsert 会按主键 id 自动覆盖已有记录，天然支持去重 / 重试。
        """
        if not documents:
            return

        # 校验 metadata
        for doc in documents:
            if "kb_id" not in (doc.metadata or {}):
                logger.warning(
                    f"Document missing kb_id in metadata: source={doc.metadata.get('source', '?')}"
                )
            if not doc.metadata.get("chunk_id"):
                raise RuntimeError(
                    f"Vector store upsert failed: chunk missing 'chunk_id' (source={doc.metadata.get('source', '?')})"
                )

        try:
            # 逐条计算 embedding（LangChain embed_documents 接口）
            texts = [doc.page_content for doc in documents]
            embeddings = await asyncio.to_thread(embedder.embed_documents, texts)

            rows = [
                self._doc_to_row(doc, emb)
                for doc, emb in zip(documents, embeddings)
            ]

            # 同步 API 放入线程池
            await asyncio.to_thread(
                self._client.upsert,
                collection_name=self._collection_name,
                data=rows,
            )
            # flush 确保数据写入段文件并刷新 row_count 统计
            await asyncio.to_thread(self._client.flush, self._collection_name)
            logger.info(
                f"[Milvus] Upserted {len(rows)} chunks to collection '{self._collection_name}'"
            )
        except Exception as e:
            logger.error(f"[Milvus] Failed to upsert {len(documents)} documents: {e}")
            raise RuntimeError(f"Vector store upsert failed: {e}") from e

    async def search(
        self,
        query: str,
        embedder: Embeddings,
        top_k: int = 4,
        kb_ids: list[int] | None = None,
    ) -> list[Document]:
        """相似度搜索（按文档 3.1 节）。

        - kb_ids 非空时用布尔表达式过滤 kb_id
        - 用 similarity_threshold 过滤 cosine distance 过大的结果
          （Milvus COSINE metric 返回的 distance 越小越相似）
        """
        # 构建 filter_expr
        filter_expr = None
        if kb_ids:
            ids_str = ", ".join(str(k) for k in kb_ids)
            filter_expr = f"kb_id in [{ids_str}]"
            logger.info(f"[Milvus] Search with kb_id filter: {kb_ids}")

        query_vector = await asyncio.to_thread(embedder.embed_query, query)

        output_fields = [
            "text", "source", "kb_id", "document_type",
            "page_number", "chunk_index", "metadata_json",
        ]
        results = await asyncio.to_thread(
            self._client.search,
            collection_name=self._collection_name,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=output_fields,
        )

        # results 是 list[list[hit]]，单 query 只有 results[0]
        hits = results[0] if results else []

        # 过滤相似度阈值
        # Milvus COSINE metric 返回的 distance 越小越相似（与 ChromaDB 一致）
        threshold = self._settings.similarity_threshold
        filtered_docs: list[Document] = []
        for hit in hits:
            distance = hit.get("distance", 0.0)
            if threshold is not None and distance > threshold:
                logger.debug(
                    f"[Milvus] Filtered out chunk (distance={distance:.4f} > "
                    f"threshold={threshold}): source="
                    f"{(hit.get('entity', {}) or {}).get('source', '?')}"
                )
                continue
            filtered_docs.append(hit)

        # 把过滤后的 hits 转为 LangChain Document
        docs = self._hits_to_documents([filtered_docs]) if filtered_docs else []

        if not docs and hits:
            best = hits[0].get("distance", 0.0) if hits else 0.0
            logger.warning(
                f"[Milvus] All {len(hits)} chunks filtered by distance threshold "
                f"(threshold={threshold}). Best distance={best:.4f}. "
                "Returning empty list; upstream prompt will handle no-context branch."
            )

        logger.info(
            f"[Milvus] Search: query='{query[:30]}...', retrieved="
            f"{len(hits)}, after_filter={len(docs)}, kb_ids={kb_ids}"
        )
        return docs

    async def delete_by_kb_id(self, kb_id: int) -> int:
        """删除某知识库的全部 chunk（按文档 3.1 节）。"""
        try:
            filter_expr = f"kb_id == {int(kb_id)}"
            count_result = await asyncio.to_thread(
                self._client.query,
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["id"],
            )
            count = len(count_result) if count_result else 0
            await asyncio.to_thread(
                self._client.delete,
                collection_name=self._collection_name,
                filter=filter_expr,
            )
            await asyncio.to_thread(self._client.flush, self._collection_name)
            logger.info(f"[Milvus] Deleted {count} chunks by kb_id={kb_id}")
            return count
        except Exception as e:
            logger.error(f"[Milvus] delete_by_kb_id failed: {e}")
            return 0

    async def delete_by_kb_id_and_source(self, kb_id: int, source_filename: str) -> int:
        """按 (kb_id, source) 精确删除。用于 pipeline 失败回滚。"""
        try:
            safe_source = _escape_filter_string(source_filename)
            filter_expr = f'kb_id == {int(kb_id)} && source == "{safe_source}"'
            count_result = await asyncio.to_thread(
                self._client.query,
                collection_name=self._collection_name,
                filter=filter_expr,
                output_fields=["id"],
            )
            count = len(count_result) if count_result else 0
            await asyncio.to_thread(
                self._client.delete,
                collection_name=self._collection_name,
                filter=filter_expr,
            )
            await asyncio.to_thread(self._client.flush, self._collection_name)
            logger.info(
                f"[Milvus] Deleted {count} chunks by kb_id={kb_id}, source='{source_filename}'"
            )
            return count
        except Exception as e:
            logger.error(f"[Milvus] delete_by_kb_id_and_source failed: {e}")
            return 0
