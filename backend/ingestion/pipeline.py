import logging
from pathlib import Path
from datetime import datetime, timezone
from langchain_core.documents import Document
from .loaders import load_document
from .splitter import chunk_documents
from ..vectorstore.chroma_store import VectorStore
from .embedder import get_embedding_provider
from ..core.config import Settings

logger = logging.getLogger(__name__)


async def ingest_file(file_path: Path, settings: Settings, store: VectorStore) -> str:
    """One-shot ingestion pipeline: load -> chunk -> embed -> upsert."""
    
    # Step 1: Load document
    try:
        docs = load_document(file_path)
        logger.info(f"[Step 1/4] Loaded {len(docs)} page(s) from {file_path.name}")
    except Exception as e:
        logger.error(f"[Step 1/4] Failed to load document: {str(e)}")
        raise
    
    # Step 2: Chunk document
    try:
        chunks = chunk_documents(docs, settings.chunk_size, settings.chunk_overlap)
        logger.info(f"[Step 2/4] Split into {len(chunks)} chunks (chunk_size={settings.chunk_size}, overlap={settings.chunk_overlap})")
    except Exception as e:
        logger.error(f"[Step 2/4] Failed to chunk document: {str(e)}")
        raise
    
    # Add document-level metadata to every chunk
    uploaded_at = datetime.now(timezone.utc).isoformat()
    for chunk in chunks:
        chunk.metadata["source"] = file_path.name
        chunk.metadata["document_type"] = file_path.suffix.lstrip(".")
        chunk.metadata["uploaded_at"] = uploaded_at
    
    # Step 3: Get embedder
    try:
        embedder = get_embedding_provider(settings).get_embedder()
        logger.info(f"[Step 3/4] Embedder ready (provider={settings.embedding_provider}, model={settings.embedding_model})")
    except Exception as e:
        logger.error(f"[Step 3/4] Failed to initialize embedder: {str(e)}")
        raise
    
    # Step 4: Upsert to vector store
    try:
        await store.upsert(chunks, embedder)
        logger.info(f"[Step 4/4] Upserted {len(chunks)} chunks to vector store")
    except Exception as e:
        logger.error(f"[Step 4/4] Failed to upsert to vector store: {str(e)}")
        raise
    
    return str(file_path)