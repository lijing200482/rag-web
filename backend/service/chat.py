"""聊天服务层 —— 会话与消息的 CRUD。"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..model.chat_session import ChatSession, ChatMessage

logger = logging.getLogger(__name__)


# ==================== Session ====================

async def create_session(
    user_id: int, title: str, db: AsyncSession
) -> ChatSession:
    """新建会话。"""
    session = ChatSession(user_id=user_id, title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info(f"Session created: id={session.id}, user_id={user_id}")
    return session


async def list_sessions(user_id: int, db: AsyncSession) -> list[ChatSession]:
    """列出某用户的全部会话，按更新时间倒序。"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_session(
    session_id: int, user_id: int, db: AsyncSession
) -> ChatSession | None:
    """获取单个会话（需校验 user_id 所属），并预加载消息。"""
    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_session_title(
    session_id: int, user_id: int, title: str, db: AsyncSession
) -> ChatSession | None:
    """重命名会话标题。返回更新后的会话，不存在或不属于该用户则返回 None。"""
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .values(title=title)
    )
    await db.commit()
    return await get_session(session_id, user_id, db)


async def delete_session(
    session_id: int, user_id: int, db: AsyncSession
) -> bool:
    """删除会话（消息由外键 ON DELETE CASCADE 自动清理）。

    返回是否真的删除了一行。
    """
    result = await db.execute(
        delete(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    await db.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info(f"Session deleted: id={session_id}, user_id={user_id}")
    return deleted > 0


# ==================== Message ====================

async def add_message(
    session_id: int,
    user_id: int,
    role: str,
    content: str,
    db: AsyncSession,
    sources: Optional[list[dict]] = None,
) -> ChatMessage:
    """向会话追加一条消息。"""
    message = ChatMessage(
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
        sources=sources,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_recent_messages(
    session_id: int, user_id: int, limit: int, db: AsyncSession
) -> list[ChatMessage]:
    """获取指定会话最近 limit 条消息（按 id 升序返回，便于直接拼接成历史）。

    会校验 session 是否属于该用户，不属于则返回空列表。
    """
    # 先校验会话归属
    sess = await db.execute(
        select(ChatSession.id)
        .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    if sess.first() is None:
        return []

    # 取最近 limit 条，再按 id 升序返回
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    msgs = list(result.scalars().all())
    msgs.reverse()
    return msgs


# ==================== 游标分页 ====================

async def get_messages_cursor(
    session_id: int,
    user_id: int,
    cursor: Optional[int] = None,
    limit: int = 20,
    db: AsyncSession | None = None,
) -> tuple[list[ChatMessage], bool]:
    """游标分页：取该会话最近 limit 条消息。

    Args:
        cursor: 游标 id（取 id < cursor 的更早消息），None 表示从最新开始。
        db: 外部传入的异步会话（避免连接泄漏）。

    Returns:
        (messages, has_more): messages 按 id 升序排列，has_more 表示是否还有更早消息。
    """
    own_db = db is None
    if own_db:
        from ..db.database import async_session as session_factory
        db = session_factory()

    try:
        # 校验归属
        sess = await db.execute(
            select(ChatSession.id)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        if sess.first() is None:
            return [], False

        stmt = select(ChatMessage).where(ChatMessage.session_id == session_id)
        if cursor is not None:
            stmt = stmt.where(ChatMessage.id < cursor)
        stmt = stmt.order_by(ChatMessage.id.desc()).limit(limit + 1)  # 多取一条判断 has_more

        result = await db.execute(stmt)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        rows.reverse()  # id 升序
        return rows, has_more
    finally:
        if own_db:
            await db.close()
