"""SSE 流式问答端点。

使用自定义 MySQLBackedRedisHistory + ConversationWindow，
封装 Redis 热缓存 + MySQL 持久双层存储。

SSE 事件格式:
  event: token     → data: {"content": "部分文本"}
  event: sources   → data: [来源数组]
  event: error     → data: {"detail": "错误信息"}
  event: done      → data: {"session_id": 3}
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage

from ..core.config import Settings
from ..db import get_db
from ..vectorstore.chroma_store import ChromaVectorStore, VectorStore
from ..ingestion.embedder import get_embedding_provider
from ..retrieval.retriever import Retriever
from ..retrieval.generator import Generator, assemble_context
from ..retrieval.llm_factory import get_llm
from ..retrieval.prompt_templates import PROMPT_TEMPLATE, PROMPT_TEMPLATE_WITH_HISTORY
from ..schema.query import QueryRequest
from ..auth.dependencies import get_current_user
from ..service.chat import get_session
from ..memory import MySQLBackedRedisHistory, ConversationWindow
from .dependencies import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def get_vector_store(settings: Settings = Depends(get_settings)) -> ChromaVectorStore:
    return ChromaVectorStore(settings)


def get_embedder(settings: Settings = Depends(get_settings)):
    return get_embedding_provider(settings).get_embedder()


@router.post("/query/stream")
async def query_stream(
    request: QueryRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    embedder=Depends(get_embedder),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """SSE 流式问答：逐 token 推送 LLM 生成结果。"""
    logger.info(f"SSE query: {request.question[:50]}... session_id={request.session_id}")

    if request.session_id is not None and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required for session mode")

    # ===== 1) 检索 =====
    try:
        top_k = request.top_k or settings.top_k
        retriever = Retriever(store, embedder, top_k=top_k)
        docs = await retriever.retrieve(request.question)
        logger.info(f"SSE retrieved {len(docs)} documents")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

    context = assemble_context(docs)

    # ===== 2) 会话校验 & 获取历史（LangChain Memory） =====
    conversation_history = ""
    use_history = False
    sess = None
    history: MySQLBackedRedisHistory | None = None

    if request.session_id is not None and current_user is not None:
        sess = await get_session(request.session_id, current_user.id, db)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found")

        history = MySQLBackedRedisHistory(request.session_id, current_user.id)
        # 预加载：触发 Redis 读取或 MySQL→Redis 回源
        await history.aget_messages()

        window = ConversationWindow(history, k=settings.memory_window)
        conversation_history = await window.get_history_string()
        use_history = True

    # ===== 3) 整理 sources =====
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

    # ===== 4) 构建 SSE 生成器 =====
    template = PROMPT_TEMPLATE_WITH_HISTORY if use_history else PROMPT_TEMPLATE
    llm = get_llm(settings)
    generator = Generator(llm, template)

    async def event_generator():
        full_answer = ""

        try:
            # 发送 sources 事件
            if sources:
                yield _sse_event("sources", sources)

            # 逐 token 流式推送
            async for token in generator.generate_stream(
                question=request.question,
                context=context,
                conversation_history=conversation_history,
            ):
                if token:
                    full_answer += token
                    yield _sse_event("token", {"content": token})

        except Exception as e:
            logger.error(f"SSE generation failed: {str(e)}", exc_info=True)
            yield _sse_event("error", {"detail": f"Generation failed: {str(e)}"})

            disconnect = "disconnect" in str(e).lower()
            if not disconnect:
                logger.warning(f"SSE stream interrupted: {str(e)}")
            return

        # ===== 5) 写入记忆（LangChain Memory 管理 MySQL + Redis 双写） =====
        if use_history and full_answer and history is not None:
            try:
                await history.aadd_messages([
                    HumanMessage(content=request.question),
                    AIMessage(content=full_answer),
                ])

                if not sess.title:
                    from ..service.chat import update_session_title
                    auto_title = request.question.strip().replace("\n", " ")[:200]
                    await update_session_title(
                        request.session_id, current_user.id, auto_title, db
                    )
            except Exception as e:
                logger.error(f"SSE post-write failed: {str(e)}", exc_info=True)
                yield _sse_event("error", {"detail": "Answer generated but failed to save"})
                return

        # ===== 6) 结束事件 =====
        yield _sse_event("done", {"session_id": request.session_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event: str, data: object) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
