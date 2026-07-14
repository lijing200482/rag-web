"""users 表 ORM 模型 —— 用户表完整定义。"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from . import Base


class User(Base):
    """用户表。

    字段与 backend/sql/init.sql 中 users 表的 DDL 完全对应：
        id           INT AUTO_INCREMENT PRIMARY KEY
        email        VARCHAR(255) UNIQUE NOT NULL
        username     VARCHAR(100) UNIQUE NOT NULL
        hashed_pwd   VARCHAR(255) NOT NULL
        is_active    TINYINT(1) DEFAULT 1   (1=启用, 0=禁用)
        is_superuser TINYINT(1) DEFAULT 0   (1=管理员, 0=普通用户)
        created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP

    注：MySQL 的 BOOLEAN 即 TINYINT(1)，TRUE/FALSE 即 1/0。
    SQLAlchemy 读取时自动转换为 Python bool，0→False，1→True。
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hashed_pwd: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
