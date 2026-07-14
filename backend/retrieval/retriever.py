from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from ..vectorstore.chroma_store import VectorStore


class Retriever:
    """Thin wrapper around vector store search with configurable top_k."""

    def __init__(self, store: VectorStore, embedder: Embeddings, top_k: int = 4):
        self._store = store
        self._embedder = embedder
        self._top_k = top_k

    async def retrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        k = top_k if top_k is not None else self._top_k
        return await self._store.search(query, self._embedder, top_k=k)
