"""问答相关 API 数据格式。"""
from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    """提问请求。

    session_id 可选：
        - 不传或为 None：保持原无状态行为，不入库。
        - 传值：从该会话拉取最近 memory_window 条消息作为对话历史，
          并将本次 user 消息与 assistant 回答写入数据库。
    """
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: Optional[int] = None
    include_sources: bool = True
    session_id: Optional[int] = None


class QueryResponse(BaseModel):
    """提问响应。"""
    answer: str
    sources: Optional[list[dict]] = None
    session_id: Optional[int] = None
