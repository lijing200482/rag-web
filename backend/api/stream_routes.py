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
from ..db.database import async_session
from ..vectorstore.milvus_store import VectorStore
from ..retrieval.retriever import Retriever
from ..retrieval.generator import Generator, assemble_context
from ..retrieval.llm_factory import get_llm
from ..retrieval.prompt_templates import PROMPT_TEMPLATE, PROMPT_TEMPLATE_WITH_HISTORY
from ..schema.query import QueryRequest
from ..service.chat import get_session, get_active_kb_ids
from ..memory import MySQLBackedRedisHistory, ConversationWindow
from .dependencies import get_embedder, get_settings, get_vector_store, rate_limit

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query/stream")
async def query_stream(
    request: QueryRequest,
    req: Request,
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    embedder=Depends(get_embedder),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(rate_limit(max_calls=10, window_seconds=60)),
):
    """SSE 流式问答：逐 token 推送 LLM 生成结果。"""
    logger.info(f"SSE query: {request.question[:50]}... session_id={request.session_id}")

    if request.session_id is not None and current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required for session mode")

    # ===== 1) 检索 =====
    try:
        top_k = request.top_k or settings.top_k
        retriever = Retriever(store, embedder, top_k=top_k)

        # V2: 若指定了 session，按对话关联的知识库检索（隔离）
        kb_ids: list[int] | None = None
        if request.session_id is not None and current_user is not None:
            kb_ids = await get_active_kb_ids(request.session_id, current_user.id, db)
            # 若对话未关联任何知识库，则 kb_ids=[] → 不过滤（向后兼容）
            if not kb_ids:
                kb_ids = None

        docs = await retriever.retrieve(request.question, kb_ids=kb_ids)
        logger.info(f"SSE retrieved {len(docs)} documents (kb_ids={kb_ids})")
    except Exception as e:
        # 内部异常细节不抛给客户端，仅记录日志（避免泄露 DB 错误、路径等敏感信息）
        logger.error(f"SSE retrieval failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="检索服务暂时不可用，请稍后再试")

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

    # ===== 3) 整理候选 sources =====
    all_sources = None
    if request.include_sources:
        all_sources = [
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
            # 逐 token 流式推送（不在开始前发 sources，避免显示未引用的候选）
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

        # ===== 5) 过滤 sources：只保留 LLM 实际引用的来源 =====
        # 检索返回 top_k 个候选，但 LLM 可能只引用了其中部分。
        # 解析 full_answer 中出现的 source 文件名，过滤后再发送。
        cited_sources = None
        if all_sources and full_answer:
            cited_sources = [
                s for s in all_sources
                if s.get("source") and s["source"] in full_answer
            ]
            # 如果全部被引用或全部没被引用（LLM 未按格式引用），用原始列表
            if not cited_sources:
                cited_sources = all_sources
            yield _sse_event("sources", cited_sources)

        # ===== 6) 写入记忆（LangChain Memory 管理 MySQL + Redis 双写） =====
        if use_history and full_answer and history is not None:
            try:
                # 持久化的是过滤后的 cited_sources，保证刷新后数量一致
                ai_msg = AIMessage(content=full_answer)
                if cited_sources:
                    ai_msg.additional_kwargs["sources"] = cited_sources
                await history.aadd_messages([
                    HumanMessage(content=request.question),
                    ai_msg,
                ])

                if not sess.title:
                    from ..service.chat import update_session_title
                    auto_title = request.question.strip().replace("\n", " ")[:200]
                    # 生成器内不持有请求级 session，用短生命周期 session 写标题
                    async with async_session() as title_db:
                        await update_session_title(
                            request.session_id, current_user.id, auto_title, title_db
                        )
            except Exception as e:
                logger.error(f"SSE post-write failed: {str(e)}", exc_info=True)
                yield _sse_event("error", {"detail": "Answer generated but failed to save"})
                return

        # ===== 7) 结束事件 =====
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
