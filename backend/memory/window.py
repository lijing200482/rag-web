"""对话记忆窗口管理器。

LangChain 0.3.x 移除了 ConversationBufferWindowMemory，
这里提供一个极简替代：窗口裁剪 + LLM 对话格式字符串。
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from .custom_history import MySQLBackedRedisHistory


class ConversationWindow:
    """管理对话历史窗口：只保留最近 K 轮，格式化输出。"""

    def __init__(
        self,
        history: MySQLBackedRedisHistory,
        k: int = 10,
    ) -> None:
        self._history = history
        self._k = k

    async def get_history_string(self) -> str:
        """异步加载历史，裁剪最近 K 轮，返回 "Human/AI: xxx\n..." 格式。"""
        messages = await self._history.aget_messages()
        # 取最近 k*2 条（k 个 user + k 个 assistant）
        window = messages[-(self._k * 2):]

        lines = []
        for msg in window:
            role = "Human" if isinstance(msg, HumanMessage) else "AI"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)
