from __future__ import annotations

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.messages import HumanMessage, AIMessage

from ..core.config import Settings
from .dependencies import get_settings
from ..db import get_db
from ..vectorstore.chroma_store import ChromaVectorStore, VectorStore
from ..ingestion.embedder import get_embedding_provider
from ..ingestion.pipeline import ingest_file
from ..schema.document import DocumentInfo
from ..schema.query import QueryRequest, QueryResponse
from ..retrieval.retriever import Retriever
from ..retrieval.generator import Generator, assemble_context
from ..retrieval.prompt_templates import PROMPT_TEMPLATE, PROMPT_TEMPLATE_WITH_HISTORY
from ..retrieval.llm_factory import get_llm
from ..auth.dependencies import get_current_user
from ..service.chat import get_session
from ..memory import MySQLBackedRedisHistory, ConversationWindow

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
        try:
            upload_path.unlink(missing_ok=True)
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
    embedder=Depends(get_embedder),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(f"Received query: {request.question[:50]}... session_id={request.session_id}")

    if request.session_id is not None and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required for session mode")

    try:
        retriever = Retriever(store, embedder, top_k=request.top_k or settings.top_k)
        docs = await retriever.retrieve(request.question)
        logger.info(f"Retrieved {len(docs)} relevant documents")

        context = assemble_context(docs)

        # ===== 对话记忆（LangChain Memory + Redis/MySQL 双层） =====
        conversation_history = ""
        use_history = False

        if request.session_id is not None and current_user is not None:
            sess = await get_session(request.session_id, current_user.id, db)
            if sess is None:
                raise HTTPException(
                    status_code=404, detail="Session not found"
                )

            # 创建一个带双层存储的 LangChain 对话历史
            history = MySQLBackedRedisHistory(
                request.session_id, current_user.id
            )
            # 预加载：触发 Redis 读取或 MySQL→Redis 回源，填充内部缓存
            await history.aget_messages()

            window = ConversationWindow(history, k=settings.memory_window)
            conversation_history = await window.get_history_string()
            use_history = True

        # 选择 prompt 模板并生成
        template = PROMPT_TEMPLATE_WITH_HISTORY if use_history else PROMPT_TEMPLATE
        llm = get_llm(settings)
        generator = Generator(llm, template)
        answer = await generator.generate(
            question=request.question,
            context=context,
            conversation_history=conversation_history,
        )

        # 整理来源
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

        # ===== 写入记忆（MySQL 持久 + Redis 双写） =====
        if use_history:
            await history.aadd_messages([
                HumanMessage(content=request.question),
                AIMessage(content=answer),
            ])

            if not sess.title:
                from ..service.chat import update_session_title
                auto_title = request.question.strip().replace("\n", " ")[:200]
                await update_session_title(
                    request.session_id, current_user.id, auto_title, db
                )

        logger.info("Query completed successfully")
        return QueryResponse(
            answer=answer,
            sources=sources,
            session_id=request.session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
