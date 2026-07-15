"""对话 + 消息 ORM 模型。

Chat ↔ KnowledgeBase 通过中间表 chat_knowledge_bases 实现多对多关系。
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Table,
    JSON,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


# 多对多中间表：Chat ↔ KnowledgeBase
chat_knowledge_bases = Table(
    "chat_knowledge_bases",
    Base.metadata,
    Column(
        "chat_id",
        Integer,
        ForeignKey("chats.id"),
        primary_key=True,
    ),
    Column(
        "knowledge_base_id",
        Integer,
        ForeignKey("knowledge_bases.id"),
        primary_key=True,
    ),
)


class Chat(Base, TimestampMixin):
    """对话表 —— 一个对话可选多个知识库，灵活组合。"""

    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
    )
    user = relationship("User", back_populates="chats")
    knowledge_bases = relationship(
        "KnowledgeBase",
        secondary=chat_knowledge_bases,
        backref="chats",
    )

    def __repr__(self) -> str:
        return f"<Chat id={self.id} title={self.title!r}>"


class Message(Base, TimestampMixin):
    """消息表 —— LONGTEXT 容纳可能很长的 AI 回复。"""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(LONGTEXT, nullable=False)
    role = Column(String(50), nullable=False)  # user / assistant
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    sources = Column(JSON, nullable=True)  # assistant 消息的引用来源，user 消息为 None

    chat = relationship("Chat", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role!r} chat_id={self.chat_id}>"
