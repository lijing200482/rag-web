"""ORM 表结构定义包。

所有数据库表的 SQLAlchemy 模型都在此包中定义。
sql/init.sql 中的 DDL 与此处的 ORM 模型一一对应。
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


# 导入所有模型，确保 Base.metadata 能收集到所有表
from .user import User  # noqa: E402, F401
from .chat_session import ChatSession, ChatMessage  # noqa: E402, F401

__all__ = ["Base", "User", "ChatSession", "ChatMessage"]
