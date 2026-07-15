from __future__ import annotations

import logging
import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from ..core.config import Settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Abstraction for vector store CRUD operations."""

    async def upsert(self, documents: list[Document], embedder: Embeddings) -> None:
        raise NotImplementedError

    async def delete_by_source(self, source_filename: str) -> int:
        raise NotImplementedError

    async def delete_by_ids(self, ids: list[str]) -> int:
        raise NotImplementedError

    async def delete_by_kb_id(self, kb_id: int) -> int:
        raise NotImplementedError

    async def search(
        self,
        query: str,
        embedder: Embeddings,
        top_k: int = 4,
        kb_ids: list[int] | None = None,
    ) -> list[Document]:
        raise NotImplementedError

    def get_document_info(self) -> list[dict]:
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    """ChromaDB-backed vector store with persistent storage.

    V2 关键改动：每个 chunk 的 metadata 持久化 kb_id，
    检索时可按 kb_ids 过滤实现知识库隔离。
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()
        self._client = chromadb.PersistentClient(path=self._settings.chroma_persist_dir)
        self._collection_name = self._settings.chroma_collection
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(self, documents: list[Document], embedder: Embeddings) -> None:
        """Insert or update documents in the collection.

        每个 document 的 metadata 必须包含 kb_id（用于检索时按知识库过滤）。
        """
        try:
            store = Chroma(
                client=self._client,
                collection_name=self._collection_name,
                embedding_function=embedder,
            )
            # 确保 chunk metadata 中带 kb_id（用于检索时过滤）
            for doc in documents:
                if "kb_id" not in doc.metadata:
                    logger.warning(
                        f"Document missing kb_id in metadata: source={doc.metadata.get('source', '?')}"
                    )
            store.add_documents(documents)
            logger.info(f"Upserted {len(documents)} documents to collection '{self._collection_name}'")
        except Exception as e:
            logger.error(f"Failed to upsert {len(documents)} documents: {str(e)}")
            raise RuntimeError(f"Vector store upsert failed: {str(e)}") from e

    async def delete_by_source(self, source_filename: str) -> int:
        """Delete all chunks belonging to a specific source file."""
        results = self._collection.get(where={"source": source_filename})
        if results and results["ids"]:
            self._collection.delete(ids=results["ids"])
            return len(results["ids"])
        return 0

    async def delete_by_kb_id(self, kb_id: int) -> int:
        """删除某知识库的全部 chunk（用于删除知识库时清理向量）。"""
        results = self._collection.get(where={"kb_id": kb_id})
        if results and results["ids"]:
            self._collection.delete(ids=results["ids"])
            return len(results["ids"])
        return 0

    async def delete_by_ids(self, ids: list[str]) -> int:
        """Delete specific chunks by their IDs."""
        self._collection.delete(ids=ids)
        return len(ids)

    async def search(
        self,
        query: str,
        embedder: Embeddings,
        top_k: int = 4,
        kb_ids: list[int] | None = None,
    ) -> list[Document]:
        """Similarity search returning top-k most relevant chunks.

        V2 关键：当 kb_ids 非空时，使用 ChromaDB 原生 metadata filter
        where={"kb_id": {"$in": [1, 3]}} 只在指定知识库范围内检索。
        kb_ids=None 或空列表表示不限制（搜索全部，向后兼容）。

        使用 similarity_search_with_score 获取 cosine distance 分数，
        然后按 settings.similarity_threshold 过滤掉不相关的文档。
        """
        store = Chroma(
            client=self._client,
            collection_name=self._collection_name,
            embedding_function=embedder,
        )

        # 构造 filter
        filter_dict = None
        if kb_ids:
            filter_dict = {"kb_id": {"$in": kb_ids}}
            logger.info(f"Search with kb_id filter: {kb_ids}")

        # 带过滤的相似度搜索
        if filter_dict is not None:
            results = store.similarity_search_with_score(
                query, k=top_k, filter=filter_dict
            )
        else:
            results = store.similarity_search_with_score(query, k=top_k)

        threshold = self._settings.similarity_threshold
        filtered: list[Document] = []
        for doc, score in results:
            if threshold is not None and score > threshold:
                logger.debug(
                    f"Filtered out chunk (score={score:.4f} > threshold={threshold}): "
                    f"source={doc.metadata.get('source', '?')}, kb_id={doc.metadata.get('kb_id', '?')}"
                )
                continue
            filtered.append(doc)

        if not filtered and results:
            logger.warning(
                f"All {len(results)} chunks filtered by score threshold "
                f"(threshold={threshold}). Best score={results[0][1]:.4f}. "
                "Returning empty list; upstream prompt will handle no-context branch."
            )

        logger.info(
            f"Search: query='{query[:30]}...', retrieved={len(results)}, "
            f"after_filter={len(filtered)}, kb_ids={kb_ids}"
        )
        return filtered

    def get_document_info(self) -> list[dict]:
        """Return summary info about all stored sources grouped by document."""
        results = self._collection.get(include=["metadatas"])
        sources: dict[str, dict] = {}
        for meta in (results["metadatas"] or []):
            src = meta.get("source", "unknown")
            if src not in sources:
                sources[src] = {
                    "source": src,
                    "document_type": meta.get("document_type", ""),
                    "chunk_count": 0,
                    "uploaded_at": meta.get("uploaded_at"),
                    "kb_id": meta.get("kb_id"),
                }
            sources[src]["chunk_count"] += 1
        return list(sources.values())
