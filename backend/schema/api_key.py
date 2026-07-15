"""API 密钥相关 API 数据格式。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """创建 API 密钥请求。"""
    name: str = Field(..., min_length=1, max_length=255, description="密钥名称")


class APIKeyResponse(BaseModel):
    """API 密钥响应（不含完整 key 值，仅返回前缀用于识别）。"""
    id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreatedResponse(APIKeyResponse):
    """创建后响应 —— 仅此一次返回完整 key。"""
    key: str
