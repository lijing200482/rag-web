"""模型基类 —— Base + TimestampMixin。

所有 ORM 模型继承 Base，通过混入 TimestampMixin 自动获得 created_at / updated_at 时间戳。
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    """返回当前 UTC 时间（带时区），替代已弃用的 datetime.utcnow()。"""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """混入类，提供 created_at / updated_at 时间戳。"""

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
