"""LangChain BaseChatMessageHistory 自定义实现。

封装 Redis (热缓存) + MySQL (持久层) 双层存储，供 ConversationBufferWindowMemory 使用。

核心行为：
  messages 读取 → LRANGE Redis → hit: 返回 → miss: MySQL 查询 → RPUSH Redis → 返回
  add_message → INSERT MySQL → LPUSH Redis + LTRIM + EXPIRE
  clear       → DELETE MySQL → DEL Redis key

与 Java 等价代码对照：
  Java:  chatHistoryList.query(appId, maxCount) → chatMemory.add()
  Py:    history.messages → Memory 自动管理窗口
"""
from __future__ import annotations

import json
import logging
from typing import List, Sequence

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from redis.exceptions import RedisError

from ..core.config import get_settings
from ..cache.redis_client import get_redis as _get_global_redis

logger = logging.getLogger(__name__)

# Redis Key 前缀
_KEY_PREFIX = "conversation"


def _msg_to_dict(msg: BaseMessage) -> dict:
    role = "user" if isinstance(msg, HumanMessage) else "assistant"
    d = {"role": role, "content": msg.content}
    # 透传 sources（仅 assistant 消息携带，刷新后仍可渲染引用卡片）
    sources = getattr(msg, "additional_kwargs", {}).get("sources")
    if sources:
        d["sources"] = sources
    return d


def _dict_to_msg(d: dict) -> BaseMessage:
    if d["role"] == "user":
        return HumanMessage(content=d["content"])
    msg = AIMessage(content=d["content"])
    # 恢复 sources 到 additional_kwargs
    if d.get("sources"):
        msg.additional_kwargs["sources"] = d["sources"]
    return msg


class MySQLBackedRedisHistory(BaseChatMessageHistory):
    """LangChain 对话历史，底层 MySQL 持久 + Redis 热缓存。

    用法：
        history = MySQLBackedRedisHistory(session_id=3)
        memory = ConversationBufferWindowMemory(
            chat_memory=history, k=10, memory_key="conversation_history"
        )
        vars = await memory.aload_memory_variables({})
        # vars["conversation_history"] → "Human: xxx\nAI: yyy\n..."
    """

    def __init__(
        self,
        session_id: int,
        user_id: int = 0,
        redis_url: str | None = None,
    ) -> None:
        """初始化。

        Args:
            session_id: MySQL 中 chat_sessions.id
            user_id: 用于归属校验和写入
            redis_url: 可选的 Redis 连接地址（默认读 settings）
        """
        self.session_id = session_id
        self.user_id = user_id
        self._redis_url = redis_url

        # 懒加载引用（首次使用时通过 _ensure_redis 建立）
        self._redis = None
        self._redis_available: bool | None = None  # None=未探测, True/False=已探测

        # 消息缓存：aget_messages 后填充，避免重复读 Redis
        self._cached: List[BaseMessage] | None = None

    # ==================== 同步接口（langchain 可能调用） ====================

    @property
    def messages(self) -> List[BaseMessage]:
        """同步读取 —— 返回最近一次 async 加载的缓存。"""
        if self._cached is not None:
            return self._cached
        logger.debug(f"同步 messages 返回空（首次请用 aget_messages）: session={self.session_id}")
        return []

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        """同步写 —— 异步场景请用 aadd_messages。"""
        logger.warning("同步 add_messages 不支持，请使用 aadd_messages")

    def clear(self) -> None:
        """同步清空 —— 异步场景请用 aclear。"""
        logger.warning("同步 clear 不支持，请使用 aclear")

    # ==================== 异步接口（FastAPI 主路径） ====================

    async def aget_messages(self) -> List[BaseMessage]:
        """异步获取消息列表 —— Redis 优先，Miss 时回源 MySQL。"""
        if self._cached is not None:
            return self._cached

        redis = await self._ensure_redis()
        key = _msg_key(self.session_id)

        # 尝试 Redis
        if redis is not None:
            try:
                raw = await redis.lrange(key, 0, -1)
                if raw:
                    msgs = [_dict_to_msg(json.loads(item)) for item in reversed(raw)]
                    self._cached = msgs
                    logger.debug(f"Redis 命中: session={self.session_id}, {len(msgs)} 条")
                    return msgs
            except RedisError as e:
                logger.warning(f"Redis 读失败: {e}")
                self._redis_available = False

        # 回源 MySQL
        msgs = await _load_from_mysql(self.session_id, self.user_id)
        self._cached = msgs

        # 回填 Redis
        if redis is not None and self._redis_available is not False:
            try:
                settings = get_settings()
                async with redis.pipeline() as pipe:
                    for m in msgs:
                        pipe.lpush(
                            key,
                            json.dumps(_msg_to_dict(m), ensure_ascii=False),
                        )
                    pipe.ltrim(key, 0, settings.redis_conversation_max_messages - 1)
                    pipe.expire(key, settings.redis_conversation_ttl)
                    await pipe.execute()
                logger.info(f"Redis 回填: session={self.session_id}, {len(msgs)} 条")
            except RedisError as e:
                logger.warning(f"Redis 回填失败: {e}")

        return msgs

    async def aadd_messages(self, messages: Sequence[BaseMessage]) -> None:
        """异步写入消息 —— MySQL 持久 + Redis 双写。"""
        from ..service.chat import add_message as db_add_message
        from ..db.database import async_session as session_factory

        redis = await self._ensure_redis()

        async with session_factory() as db:
            for msg in messages:
                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                # 从 additional_kwargs 取出 sources 一起持久化
                sources = getattr(msg, "additional_kwargs", {}).get("sources")
                await db_add_message(
                    session_id=self.session_id,
                    role=role,
                    content=msg.content,
                    db=db,
                    sources=sources,
                )

                # Write-Through Redis
                if redis is not None and self._redis_available is not False:
                    try:
                        settings = get_settings()
                        key = _msg_key(self.session_id)
                        item = json.dumps(_msg_to_dict(msg), ensure_ascii=False)
                        async with redis.pipeline() as pipe:
                            pipe.lpush(key, item)
                            pipe.ltrim(key, 0, settings.redis_conversation_max_messages - 1)
                            pipe.expire(key, settings.redis_conversation_ttl)
                            await pipe.execute()
                    except RedisError as e:
                        logger.warning(f"Redis 写失败: {e}")

                # 更新内存缓存
                if self._cached is not None:
                    self._cached.append(msg)

        logger.debug(f"写入 {len(messages)} 条消息: session={self.session_id}")

    async def aclear(self) -> None:
        """清空该会话的全部消息（MySQL + Redis）。"""
        from sqlalchemy import delete
        from ..db.database import async_session as session_factory
        from ..app.models import Message

        # 清 MySQL
        async with session_factory() as db:
            await db.execute(
                delete(Message).where(Message.chat_id == self.session_id)
            )
            await db.commit()

        # 清 Redis
        redis = await self._ensure_redis()
        if redis is not None:
            try:
                await redis.delete(_msg_key(self.session_id))
            except RedisError:
                pass

        # 清缓存
        self._cached = None
        logger.info(f"会话消息已清空: session={self.session_id}")

    # ==================== 内部工具 ====================

    async def _ensure_redis(self):
        """懒加载 Redis 客户端（容错：不可用时返回 None）。"""
        if self._redis is not None:
            return self._redis
        if self._redis_available is False:
            return None

        try:
            self._redis = await _get_global_redis()
            self._redis_available = self._redis is not None
            return self._redis
        except Exception as e:
            logger.warning(f"Redis 初始化失败: {e}")
            self._redis_available = False
            self._redis = None
            return None


# ==================== 辅助函数 ====================

def _msg_key(session_id: int) -> str:
    return f"{_KEY_PREFIX}:{session_id}:messages"


async def _load_from_mysql(session_id: int, user_id: int = 0) -> List[BaseMessage]:
    """从 MySQL 加载对话历史（回源路径）。

    只取最近 N 条（N = settings.redis_conversation_max_messages），
    避免千条消息全量加载后再裁剪。ORDER BY id DESC + LIMIT N 取最近 N 条，
    再 reverse() 恢复时间升序。
    """
    from sqlalchemy import select
    from ..db.database import async_session as session_factory
    from ..app.models import Message

    settings = get_settings()
    limit = settings.redis_conversation_max_messages

    async with session_factory() as db:
        stmt = (
            select(Message)
            .where(Message.chat_id == session_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())

    rows.reverse()  # 恢复时间升序，便于直接拼接成历史

    msgs = []
    for row in rows:
        if row.role == "user":
            msgs.append(HumanMessage(content=row.content))
        else:
            msg = AIMessage(content=row.content)
            # 恢复 sources 到 additional_kwargs
            if row.sources:
                msg.additional_kwargs["sources"] = row.sources
            msgs.append(msg)

    logger.info(f"MySQL 加载: session={session_id}, {len(msgs)} 条")
    return msgs
