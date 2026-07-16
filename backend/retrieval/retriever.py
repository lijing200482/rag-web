from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from ..vectorstore.milvus_store import VectorStore


class Retriever:
    """Thin wrapper around vector store search with configurable top_k.

    V2: 支持 kb_ids 参数实现知识库隔离检索。
    """

    def __init__(self, store: VectorStore, embedder: Embeddings, top_k: int = 4):
        self._store = store
        self._embedder = embedder
        self._top_k = top_k

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        kb_ids: list[int] | None = None,
    ) -> list[Document]:
        """检索相关文档。

        Args:
            query: 用户问题
            top_k: 覆盖默认 top_k
            kb_ids: 知识库 ID 列表，非空时只在这些知识库范围内检索
        """
        k = top_k if top_k is not None else self._top_k
        return await self._store.search(query, self._embedder, top_k=k, kb_ids=kb_ids)
