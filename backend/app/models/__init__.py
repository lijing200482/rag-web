"""数据模型层 —— 统一导出所有 ORM 模型。

目录结构：
    base.py       → Base 基类 + TimestampMixin
    user.py       → User + APIKey
    knowledge.py  → KnowledgeBase + Document + DocumentChunk
                    + DocumentUpload + ProcessingTask
    chat.py       → Chat + Message + chat_knowledge_bases 中间表

所有模型共享同一个 Base.metadata，由 db/database.py 的 init_db() 统一建表。
"""
from .base import Base, TimestampMixin
from .user import User, APIKey
from .knowledge import (
    KnowledgeBase,
    Document,
    DocumentChunk,
    DocumentUpload,
    ProcessingTask,
)
from .chat import Chat, Message, chat_knowledge_bases

__all__ = [
    "Base",
    "TimestampMixin",
    "User",
    "APIKey",
    "KnowledgeBase",
    "Document",
    "DocumentChunk",
    "DocumentUpload",
    "ProcessingTask",
    "Chat",
    "Message",
    "chat_knowledge_bases",
]
