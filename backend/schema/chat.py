"""聊天会话相关 API 数据格式。

基于新的数据模型层：
    Chat    —— 对话表 (id, title, user_id, created_at, updated_at)
    Message —— 消息表 (id, content, role, chat_id, created_at, updated_at)

Message 模型不再持久化 sources 字段；sources 在 /query 响应中直接返回。
MessageResponse 保留 sources 可选字段以兼容前端历史消息渲染。
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """新建会话请求。"""
    title: str = Field(default="", max_length=500, description="会话标题，默认空字符串")


class SessionUpdate(BaseModel):
    """重命名会话请求。"""
    title: str = Field(..., min_length=1, max_length=500, description="新标题")


class MessageResponse(BaseModel):
    """单条消息响应。"""
    id: int
    chat_id: int
    role: str
    content: str
    sources: Optional[list[dict[str, Any]]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    """会话响应（不含消息列表）。"""
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    """会话响应（仅元信息，不含消息列表）。

    消息通过独立的 /chat/sessions/{id}/messages 游标分页端点拉取，
    避免获取会话时预加载全部消息。
    """
    id: int
    user_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== 游标分页 ====================

class MessagePage(BaseModel):
    """游标分页的消息列表。"""
    messages: list[MessageResponse]
    next_cursor: Optional[int] = None  # 本批最小 id，null 表示到底了
    has_more: bool = False
