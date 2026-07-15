"""聊天服务层 —— 会话与消息的 CRUD。

基于新的数据模型层 (backend/app/models)：
    Chat     —— 对话表 (原 ChatSession)
    Message  —— 消息表 (原 ChatMessage，去除 user_id/sources，增加 updated_at)
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.models import Chat, Message, KnowledgeBase, chat_knowledge_bases

logger = logging.getLogger(__name__)


# ==================== Chat (会话) ====================

async def create_session(
    user_id: int, title: str, db: AsyncSession
) -> Chat:
    """新建会话。"""
    chat = Chat(user_id=user_id, title=title)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    logger.info(f"Chat created: id={chat.id}, user_id={user_id}")
    return chat


async def list_sessions(user_id: int, db: AsyncSession) -> list[Chat]:
    """列出某用户的全部会话，按更新时间倒序。"""
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == user_id)
        .order_by(Chat.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_session(
    session_id: int, user_id: int, db: AsyncSession
) -> Chat | None:
    """获取单个会话（需校验 user_id 所属）。

    不再预加载 messages：会话元信息由本接口返回，
    消息列表由独立的 /chat/sessions/{id}/messages 游标分页端点拉取，
    避免获取会话时一次性加载全部消息。
    """
    result = await db.execute(
        select(Chat)
        .where(Chat.id == session_id, Chat.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_session_title(
    session_id: int, user_id: int, title: str, db: AsyncSession
) -> Chat | None:
    """重命名会话标题。返回更新后的会话，不存在或不属于该用户则返回 None。"""
    await db.execute(
        update(Chat)
        .where(Chat.id == session_id, Chat.user_id == user_id)
        .values(title=title)
    )
    await db.commit()
    return await get_session(session_id, user_id, db)


async def delete_session(
    session_id: int, user_id: int, db: AsyncSession
) -> bool:
    """删除会话及其全部消息和知识库关联。

    显式按依赖顺序删除，不依赖数据库外键 ON DELETE CASCADE。
    原因：现有数据库的外键可能没有级联约束（旧 schema 遗留），
    用 Core DELETE 语句也不触发 ORM 的 cascade="all, delete-orphan"。

    删除顺序（叶子 → 根）：
        1. messages             → 引用 chats
        2. chat_knowledge_bases  → 引用 chats（多对多中间表）
        3. chats                → 自身

    返回是否真的删除了一行。
    """
    # 先校验会话归属，避免误删他人消息
    sess = await db.execute(
        select(Chat.id).where(Chat.id == session_id, Chat.user_id == user_id)
    )
    if sess.first() is None:
        return False

    # 1) 先删消息（引用 chats，避免外键约束阻止删除 chats）
    await db.execute(
        delete(Message).where(Message.chat_id == session_id)
    )
    # 2) 删除知识库关联（中间表也引用 chats，不删会触发 1451）
    await db.execute(
        delete(chat_knowledge_bases).where(
            chat_knowledge_bases.c.chat_id == session_id
        )
    )
    # 3) 再删会话本身
    result = await db.execute(
        delete(Chat)
        .where(Chat.id == session_id, Chat.user_id == user_id)
    )
    await db.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info(f"Chat deleted: id={session_id}, user_id={user_id}")
    return deleted > 0


# ==================== Message (消息) ====================

async def add_message(
    session_id: int,
    role: str,
    content: str,
    db: AsyncSession,
    sources: list[dict] | None = None,
) -> Message:
    """向会话追加一条消息。

    sources 仅对 assistant 角色有意义，记录检索引用的来源（刷新后仍可渲染引用卡片）。
    """
    message = Message(
        chat_id=session_id,
        role=role,
        content=content,
        sources=sources if role == "assistant" else None,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_recent_messages(
    session_id: int, user_id: int, limit: int, db: AsyncSession
) -> list[Message]:
    """获取指定会话最近 limit 条消息（按 id 升序返回，便于直接拼接成历史）。

    会校验会话是否属于该用户，不属于则返回空列表。
    """
    # 先校验会话归属
    sess = await db.execute(
        select(Chat.id)
        .where(Chat.id == session_id, Chat.user_id == user_id)
    )
    if sess.first() is None:
        return []

    # 取最近 limit 条，再按 id 升序返回
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == session_id)
        .order_by(Message.id.desc())
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
) -> tuple[list[Message], bool]:
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
            select(Chat.id)
            .where(Chat.id == session_id, Chat.user_id == user_id)
        )
        if sess.first() is None:
            return [], False

        stmt = select(Message).where(Message.chat_id == session_id)
        if cursor is not None:
            stmt = stmt.where(Message.id < cursor)
        stmt = stmt.order_by(Message.id.desc()).limit(limit + 1)  # 多取一条判断 has_more

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


# ==================== Chat ↔ KnowledgeBase 关联 ====================

async def _verify_chat_owner(
    chat_id: int, user_id: int, db: AsyncSession
) -> bool:
    """校验对话归属权。"""
    result = await db.execute(
        select(Chat.id).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    return result.first() is not None


async def link_knowledge_bases(
    chat_id: int, kb_ids: list[int], user_id: int, db: AsyncSession
) -> None:
    """设置对话关联的知识库列表（整体替换）。

    1. 校验对话归属权
    2. 清空现有关联
    3. 插入新关联（仅关联属于该用户的知识库）
    """
    if not await _verify_chat_owner(chat_id, user_id, db):
        return

    # 清空现有关联
    await db.execute(
        delete(chat_knowledge_bases).where(
            chat_knowledge_bases.c.chat_id == chat_id
        )
    )

    # 插入新关联（仅该用户拥有的 KB）
    if kb_ids:
        # 过滤出真正属于该用户的 KB ID
        result = await db.execute(
            select(KnowledgeBase.id)
            .where(
                KnowledgeBase.id.in_(kb_ids),
                KnowledgeBase.user_id == user_id,
            )
        )
        valid_ids = [row[0] for row in result.all()]

        if valid_ids:
            await db.execute(
                chat_knowledge_bases.insert(),
                [{"chat_id": chat_id, "knowledge_base_id": kid} for kid in valid_ids],
            )

    await db.commit()
    logger.info(f"Linked {len(kb_ids)} KBs to chat_id={chat_id}, user_id={user_id}")


async def get_linked_knowledge_bases(
    chat_id: int, user_id: int, db: AsyncSession
) -> list[KnowledgeBase]:
    """列出对话关联的知识库。"""
    if not await _verify_chat_owner(chat_id, user_id, db):
        return []

    result = await db.execute(
        select(KnowledgeBase)
        .join(chat_knowledge_bases, KnowledgeBase.id == chat_knowledge_bases.c.knowledge_base_id)
        .where(chat_knowledge_bases.c.chat_id == chat_id)
        .order_by(KnowledgeBase.id.asc())
    )
    return list(result.scalars().all())


async def add_knowledge_base(
    chat_id: int, kb_id: int, user_id: int, db: AsyncSession
) -> bool:
    """添加单个知识库关联。

    Returns:
        True 表示成功添加；False 表示对话或知识库不存在/不属于该用户。
    """
    if not await _verify_chat_owner(chat_id, user_id, db):
        return False

    # 校验 KB 归属权
    kb_result = await db.execute(
        select(KnowledgeBase.id)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
    )
    if kb_result.first() is None:
        return False

    # 检查是否已关联（避免重复插入）
    existing = await db.execute(
        select(chat_knowledge_bases)
        .where(
            chat_knowledge_bases.c.chat_id == chat_id,
            chat_knowledge_bases.c.knowledge_base_id == kb_id,
        )
    )
    if existing.first() is not None:
        return True  # 已存在视为成功

    await db.execute(
        chat_knowledge_bases.insert(),
        {"chat_id": chat_id, "knowledge_base_id": kb_id},
    )
    await db.commit()
    logger.info(f"Added KB {kb_id} to chat_id={chat_id}")
    return True


async def remove_knowledge_base(
    chat_id: int, kb_id: int, user_id: int, db: AsyncSession
) -> bool:
    """移除单个知识库关联。"""
    if not await _verify_chat_owner(chat_id, user_id, db):
        return False

    result = await db.execute(
        delete(chat_knowledge_bases).where(
            chat_knowledge_bases.c.chat_id == chat_id,
            chat_knowledge_bases.c.knowledge_base_id == kb_id,
        )
    )
    await db.commit()
    deleted = result.rowcount or 0
    if deleted:
        logger.info(f"Removed KB {kb_id} from chat_id={chat_id}")
    return deleted > 0


async def get_active_kb_ids(
    chat_id: int, user_id: int, db: AsyncSession
) -> list[int]:
    """获取对话关联的知识库 ID 列表（用于检索时过滤）。

    若对话没有关联任何知识库，返回空列表（检索层据此决定是否过滤）。
    """
    if not await _verify_chat_owner(chat_id, user_id, db):
        return []

    result = await db.execute(
        select(chat_knowledge_bases.c.knowledge_base_id)
        .where(chat_knowledge_bases.c.chat_id == chat_id)
    )
    return [row[0] for row in result.all()]
