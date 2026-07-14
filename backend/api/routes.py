from __future__ import annotations

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pathlib import Path

from ..config import Settings
from .dependencies import get_settings
from ..vectorstore.chroma_store import ChromaVectorStore, VectorStore
from ..ingestion.embedder import get_embedding_provider
from ..ingestion.pipeline import ingest_file
from ..models.document import DocumentInfo
from ..models.query import QueryRequest, QueryResponse
from ..retrieval.retriever import Retriever
from ..retrieval.generator import Generator, assemble_context
from ..retrieval.prompt_templates import PROMPT_TEMPLATE
from ..retrieval.llm_factory import get_llm

logger = logging.getLogger(__name__)

router = APIRouter()


def get_vector_store(settings: Settings = Depends(get_settings)) -> ChromaVectorStore:
    return ChromaVectorStore(settings)


def get_embedder(settings: Settings = Depends(get_settings)):
    return get_embedding_provider(settings).get_embedder()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
):
    logger.info(f"Received upload request for file: {file.filename}, size: {file.size} bytes")

    # 保存文件到documet目录
    upload_dir = Path(settings.documents_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / file.filename
    
    content = await file.read()
    upload_path.write_bytes(content)
    logger.info(f"Saved file to: {upload_path}")
    
    try:
        await ingest_file(upload_path, settings, store)
        logger.info(f"Ingested file successfully: {file.filename}")
        return {"filename": file.filename, "status": "uploaded"}
    
    except Exception as e:
        logger.error(f"Ingestion failed for {file.filename}: {str(e)}", exc_info=True)
        # 入库失败，清理已保存的文件
        try:
            upload_path.unlink(missing_ok=True)
            logger.info(f"Cleaned up file: {upload_path}")
        except Exception as cleanup_err:
            logger.warning(f"Failed to clean up file {upload_path}: {cleanup_err}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents(store: VectorStore = Depends(get_vector_store)):
    logger.info("Fetching document list")
    infos = store.get_document_info()
    logger.info(f"Found {len(infos)} documents")
    return [DocumentInfo(**info) for info in infos]


@router.delete("/documents/{source}")
async def delete_document(
    source: str,
    store: VectorStore = Depends(get_vector_store),
):
    logger.info(f"Deleting document: {source}")
    deleted = await store.delete_by_source(source)
    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"No document found: {source}")
    logger.info(f"Deleted {deleted} chunks for {source}")
    return {"deleted_chunks": deleted, "source": source}


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    embedder = Depends(get_embedder),
):
    logger.info(f"Received query: {request.question[:50]}...")
    
    try:
        retriever = Retriever(store, embedder, top_k=request.top_k or settings.top_k)
        docs = await retriever.retrieve(request.question)
        logger.info(f"Retrieved {len(docs)} relevant documents")
        
        context = assemble_context(docs)
        llm = get_llm(settings)
        generator = Generator(llm, PROMPT_TEMPLATE)
        answer = await generator.generate(request.question, context)
        
        sources = None
        if request.include_sources:
            sources = [
                {
                    "source": d.metadata.get("source"),
                    "page": d.metadata.get("page_number"),
                    "content": d.page_content[:200],
                }
                for d in docs
            ]
        
        logger.info("Query completed successfully")
        return QueryResponse(answer=answer, sources=sources)
    
    except Exception as e:
        logger.error(f"Query failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
