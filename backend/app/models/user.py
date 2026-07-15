"""用户 + API 密钥 ORM 模型。

User ──1:N──→ KnowledgeBase
User ──1:N──→ Chat
User ──1:N──→ APIKey
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """用户表。

    注：hashed_password 属性映射到数据库中的 hashed_pwd 列，
    以兼容已存在的 users 表结构。
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column("hashed_pwd", String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)

    # 关系
    knowledge_bases = relationship("KnowledgeBase", back_populates="user")
    chats = relationship("Chat", back_populates="user")
    api_keys = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class APIKey(Base, TimestampMixin):
    """API 密钥表。"""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(64), nullable=False)
    key_prefix = Column(String(8), nullable=False)
    name = Column(String(255), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<APIKey id={self.id} name={self.name!r} user_id={self.user_id}>"
