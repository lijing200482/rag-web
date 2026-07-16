from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.messages import HumanMessage, AIMessage

from ..core.config import Settings
from .dependencies import get_embedder, get_settings, get_vector_store, rate_limit
from ..db import get_db
from ..vectorstore.milvus_store import VectorStore
from ..schema.query import QueryRequest, QueryResponse
from ..retrieval.retriever import Retriever
from ..retrieval.generator import Generator, assemble_context
from ..retrieval.prompt_templates import PROMPT_TEMPLATE, PROMPT_TEMPLATE_WITH_HISTORY
from ..retrieval.llm_factory import get_llm
from ..service.chat import get_session, get_active_kb_ids
from ..memory import MySQLBackedRedisHistory, ConversationWindow

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    embedder=Depends(get_embedder),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(rate_limit(max_calls=10, window_seconds=60)),
):
    """非流式问答（兼容旧客户端 / 测试用）。推荐使用 /query/stream（SSE）。"""
    logger.info(f"Received query: {request.question[:50]}... session_id={request.session_id}")

    if request.session_id is not None and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required for session mode")

    try:
        retriever = Retriever(store, embedder, top_k=request.top_k or settings.top_k)

        # V2: 若指定了 session，按对话关联的知识库检索（隔离）
        kb_ids: list[int] | None = None
        if request.session_id is not None and current_user is not None:
            kb_ids = await get_active_kb_ids(request.session_id, current_user.id, db)
            if not kb_ids:
                kb_ids = None

        docs = await retriever.retrieve(request.question, kb_ids=kb_ids)
        logger.info(f"Retrieved {len(docs)} relevant documents (kb_ids={kb_ids})")

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

            history = MySQLBackedRedisHistory(
                request.session_id, current_user.id
            )
            await history.aget_messages()

            window = ConversationWindow(history, k=settings.memory_window)
            conversation_history = await window.get_history_string()
            use_history = True

        template = PROMPT_TEMPLATE_WITH_HISTORY if use_history else PROMPT_TEMPLATE
        llm = get_llm(settings)
        generator = Generator(llm, template)
        answer = await generator.generate(
            question=request.question,
            context=context,
            conversation_history=conversation_history,
        )

        sources = None
        if request.include_sources:
            all_sources = [
                {
                    "source": d.metadata.get("source"),
                    "page": d.metadata.get("page_number"),
                    "content": d.page_content[:200],
                }
                for d in docs
            ]
            # 只保留 LLM 实际引用的来源（source 文件名在回答中出现）
            cited = [s for s in all_sources if s.get("source") and s["source"] in answer]
            sources = cited if cited else all_sources

        if use_history:
            # 把 sources 注入 AIMessage 一起持久化（刷新后仍可渲染引用卡片）
            ai_msg = AIMessage(content=answer)
            if sources:
                ai_msg.additional_kwargs["sources"] = sources
            await history.aadd_messages([
                HumanMessage(content=request.question),
                ai_msg,
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
        raise HTTPException(status_code=500, detail="查询服务暂时不可用，请稍后再试")
