from __future__ import annotations

import logging
import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from ..config import Settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Abstraction for vector store CRUD operations."""

    async def upsert(self, documents: list[Document], embedder: Embeddings) -> None:
        raise NotImplementedError

    async def delete_by_source(self, source_filename: str) -> int:
        raise NotImplementedError

    async def delete_by_ids(self, ids: list[str]) -> int:
        raise NotImplementedError

    async def search(
        self, query: str, embedder: Embeddings, top_k: int = 4
    ) -> list[Document]:
        raise NotImplementedError

    def get_document_info(self) -> list[dict]:
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    """ChromaDB-backed vector store with persistent storage."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()
        self._client = chromadb.PersistentClient(path=self._settings.chroma_persist_dir)
        self._collection_name = self._settings.chroma_collection
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(self, documents: list[Document], embedder: Embeddings) -> None:
        """Insert or update documents in the collection."""
        try:
            store = Chroma(
                client=self._client,
                collection_name=self._collection_name,
                embedding_function=embedder,
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

    async def delete_by_ids(self, ids: list[str]) -> int:
        """Delete specific chunks by their IDs."""
        self._collection.delete(ids=ids)
        return len(ids)

    async def search(
        self, query: str, embedder: Embeddings, top_k: int = 4
    ) -> list[Document]:
        """Similarity search returning top-k most relevant chunks."""
        store = Chroma(
            client=self._client,
            collection_name=self._collection_name,
            embedding_function=embedder,
        )
        results = store.similarity_search_with_score(query, k=top_k)
        return [doc for doc, _score in results]

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
                }
            sources[src]["chunk_count"] += 1
        return list(sources.values())
