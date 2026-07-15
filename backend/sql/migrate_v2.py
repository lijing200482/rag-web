"""V2 数据模型迁移脚本 —— 用 SQLAlchemy 自动建表 + 手动迁移旧数据。"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text as sa_text

from backend.app.models import Base
from backend.db.database import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_migration():
    logger.info("=== 开始 V2 数据模型迁移 ===")

    # Step 1: 创建新表（create_all 只创建不存在的表）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("[Step 1] 新表创建完成 (create_all)")

    # Step 2: 迁移 chat_sessions → chats
    async with engine.begin() as conn:
        has_old = (await conn.execute(
            sa_text("SELECT COUNT(*) FROM information_schema.TABLES "
                     "WHERE TABLE_SCHEMA = 'rag' AND TABLE_NAME = 'chat_sessions'")
        )).scalar() > 0

        if has_old:
            has_new = (await conn.execute(
                sa_text("SELECT COUNT(*) FROM information_schema.TABLES "
                         "WHERE TABLE_SCHEMA = 'rag' AND TABLE_NAME = 'chats'")
            )).scalar() > 0

            if not has_new:
                await conn.execute(sa_text("RENAME TABLE chat_sessions TO chats"))
                logger.info("[Step 2] chat_sessions → chats (RENAME OK)")
            else:
                try:
                    await conn.execute(
                        sa_text("INSERT IGNORE INTO chats (id, title, user_id, created_at, updated_at) "
                                "SELECT id, title, user_id, created_at, updated_at FROM chat_sessions")
                    )
                    logger.info("[Step 2] 数据已复制到 chats")
                except Exception as e:
                    logger.warning(f"[Step 2] 复制跳过: {e}")
        else:
            logger.info("[Step 2] chat_sessions 不存在，跳过")

    # Step 3: 迁移 chat_messages → messages
    async with engine.begin() as conn:
        has_old = (await conn.execute(
            sa_text("SELECT COUNT(*) FROM information_schema.TABLES "
                     "WHERE TABLE_SCHEMA = 'rag' AND TABLE_NAME = 'chat_messages'")
        )).scalar() > 0

        if has_old:
            msg_count = (await conn.execute(
                sa_text("SELECT COUNT(*) FROM messages")
            )).scalar()

            if msg_count == 0:
                old_count = (await conn.execute(
                    sa_text("SELECT COUNT(*) FROM chat_messages")
                )).scalar()
                if old_count > 0:
                    await conn.execute(
                        sa_text(
                            "INSERT INTO messages (id, content, role, chat_id, created_at, updated_at) "
                            "SELECT id, content, role, session_id, created_at, NOW() FROM chat_messages"
                        )
                    )
                    logger.info(f"[Step 3] 迁移 {old_count} 条消息到 messages")
                else:
                    logger.info("[Step 3] chat_messages 为空，跳过数据迁移")

            await conn.execute(sa_text("DROP TABLE IF EXISTS chat_messages"))
            logger.info("[Step 3] 旧表 chat_messages 已删除")
        else:
            logger.info("[Step 3] chat_messages 不存在，跳过")

    # Step 4: 校验
    async with engine.begin() as conn:
        result = await conn.execute(
            sa_text("SELECT TABLE_NAME FROM information_schema.TABLES "
                     "WHERE TABLE_SCHEMA = 'rag' ORDER BY TABLE_NAME")
        )
        rows = result.fetchall()
        tables = [r[0] for r in rows]
        logger.info(f"最终表: {', '.join(tables)}")

    logger.info("=== V2 迁移完成 ===")


if __name__ == "__main__":
    asyncio.run(run_migration())
