"""数据库连接管理 —— SQLAlchemy 异步引擎 + 会话工厂。"""
import logging
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from ..core.config import Settings, get_settings
from ..model import Base

logger = logging.getLogger(__name__)

# 全局引擎与会话工厂（按 settings.database_url 构建）
_settings = get_settings()
engine = create_async_engine(_settings.database_url, pool_pre_ping=True, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI 依赖：注入一个异步数据库会话。"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """启动时创建表（若已存在则跳过）。

    生产环境建议先执行 backend/sql/init.sql 创建库与表，
    此处作为开发环境的兜底建表逻辑。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized (tables ensured)")
