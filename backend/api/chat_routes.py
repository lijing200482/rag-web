"""聊天会话管理路由。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..auth.dependencies import require_user
from ..schema.chat import (
    SessionCreate,
    SessionUpdate,
    SessionResponse,
    ConversationResponse,
    MessagePage,
)
from ..service.chat import (
    create_session,
    list_sessions,
    get_session,
    update_session_title,
    delete_session,
    get_messages_cursor,
    link_knowledge_bases,
    get_linked_knowledge_bases,
    add_knowledge_base,
    remove_knowledge_base,
)
from ..memory import MySQLBackedRedisHistory
from ..schema.knowledge import (
    ChatKnowledgeBasesUpdate,
    KnowledgeBaseResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session_route(
    payload: SessionCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """新建会话。"""
    session = await create_session(current_user.id, payload.title, db)
    return SessionResponse.model_validate(session, from_attributes=True)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions_route(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的所有会话。"""
    sessions = await list_sessions(current_user.id, db)
    return [SessionResponse.model_validate(s, from_attributes=True) for s in sessions]


@router.get("/sessions/{session_id}", response_model=ConversationResponse)
async def get_session_route(
    session_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取会话及其全部消息，同时预热 Redis 缓存。"""
    session = await get_session(session_id, current_user.id, db)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # 预热：首次访问自动从 MySQL 灌入 Redis
    history = MySQLBackedRedisHistory(session_id, current_user.id)
    await history.aget_messages()

    return ConversationResponse.model_validate(session, from_attributes=True)


@router.get("/sessions/{session_id}/messages", response_model=MessagePage)
async def get_messages_route(
    session_id: int,
    cursor: int | None = None,
    limit: int = 20,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """游标分页获取会话消息。

    - cursor=None: 取最新的 limit 条
    - cursor=N:   取 id < N 的更早消息
    """
    from ..schema.chat import MessageResponse

    msgs, has_more = await get_messages_cursor(
        session_id, current_user.id, cursor, limit, db
    )
    if not msgs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or empty"
        )

    return MessagePage(
        messages=[MessageResponse.model_validate(m, from_attributes=True) for m in msgs],
        next_cursor=msgs[0].id if has_more else None,
        has_more=has_more,
    )


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
async def rename_session_route(
    session_id: int,
    payload: SessionUpdate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """重命名会话。"""
    session = await update_session_title(session_id, current_user.id, payload.title, db)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return SessionResponse.model_validate(session, from_attributes=True)


@router.delete("/sessions/{session_id}")
async def delete_session_route(
    session_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """删除会话（MySQL 显式删消息 + Redis 缓存清除）。"""
    deleted = await delete_session(session_id, current_user.id, db)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    # 清除 Redis 缓存（MySQL 消息已由 delete_session 显式删除）
    history = MySQLBackedRedisHistory(session_id, current_user.id)
    await history.aclear()

    return {"deleted": True, "session_id": session_id}


# ==================== 对话 ↔ 知识库关联 ====================

@router.get("/sessions/{session_id}/knowledge", response_model=list[KnowledgeBaseResponse])
async def list_chat_knowledge_route(
    session_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出对话关联的知识库。"""
    kbs = await get_linked_knowledge_bases(session_id, current_user.id, db)
    if not kbs and not await get_session(session_id, current_user.id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return [KnowledgeBaseResponse.model_validate(k, from_attributes=True) for k in kbs]


@router.put("/sessions/{session_id}/knowledge")
async def set_chat_knowledge_route(
    session_id: int,
    payload: ChatKnowledgeBasesUpdate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """设置对话关联的知识库列表（整体替换）。"""
    if not await get_session(session_id, current_user.id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    await link_knowledge_bases(session_id, payload.kb_ids, current_user.id, db)
    return {"chat_id": session_id, "kb_ids": payload.kb_ids}


@router.post("/sessions/{session_id}/knowledge/{kb_id}")
async def add_chat_knowledge_route(
    session_id: int,
    kb_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """添加单个知识库关联。"""
    ok = await add_knowledge_base(session_id, kb_id, current_user.id, db)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session or knowledge base not found or not owned by user",
        )
    return {"chat_id": session_id, "kb_id": kb_id, "added": True}


@router.delete("/sessions/{session_id}/knowledge/{kb_id}")
async def remove_chat_knowledge_route(
    session_id: int,
    kb_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """移除单个知识库关联。"""
    if not await get_session(session_id, current_user.id, db):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    removed = await remove_knowledge_base(session_id, kb_id, current_user.id, db)
    return {"chat_id": session_id, "kb_id": kb_id, "removed": removed}
