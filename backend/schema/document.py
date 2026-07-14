"""文档相关 API 数据格式。"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DocumentInfo(BaseModel):
    """文档列表项响应。"""
    source: str
    document_type: str
    chunk_count: int
    uploaded_at: Optional[datetime] = None


class DeleteRequest(BaseModel):
    """批量删除请求。"""
    ids: list[str]
