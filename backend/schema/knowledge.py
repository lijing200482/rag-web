"""知识库相关 API 数据格式。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ==================== 知识库 ====================

class KnowledgeBaseCreate(BaseModel):
    """创建知识库请求。"""
    name: str = Field(..., min_length=1, max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, description="知识库描述")


class KnowledgeBaseUpdate(BaseModel):
    """更新知识库请求。"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class KnowledgeBaseResponse(BaseModel):
    """知识库响应。"""
    id: int
    name: str
    description: Optional[str] = None
    user_id: int
    created_at: datetime
    updated_at: datetime
    # 文档数 / 分块数（list 接口聚合返回；单查接口默认 0）
    doc_count: int = 0
    chunk_count: int = 0

    model_config = {"from_attributes": True}


# ==================== 文档 ====================

class DocumentResponse(BaseModel):
    """文档响应。"""
    id: int
    knowledge_base_id: int
    file_path: str
    file_name: str
    file_size: int
    content_type: str
    file_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== Chunk ====================

class DocumentChunkResponse(BaseModel):
    """文档块响应。"""
    id: str
    kb_id: int
    document_id: int
    file_name: str
    chunk_metadata: Optional[dict[str, Any]] = None
    hash: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== 上传记录 ====================

class DocumentUploadResponse(BaseModel):
    """上传记录响应。"""
    id: int
    knowledge_base_id: int
    file_name: str
    file_hash: str
    file_size: int
    content_type: str
    temp_path: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== 处理任务 ====================

class ProcessingTaskResponse(BaseModel):
    """处理任务响应。"""
    id: int
    knowledge_base_id: int
    document_id: Optional[int] = None
    document_upload_id: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== 上传响应（202 Accepted） ====================

class UploadAcceptedResponse(BaseModel):
    """文档上传受理响应。"""
    upload_id: int
    task_id: int
    status: str = "pending"


# ==================== 通用分页 ====================

class PageResponse(BaseModel):
    """通用列表响应（带 has_more 标记）。"""
    items: list[Any]
    has_more: bool = False


# ==================== 对话-知识库关联 ====================

class ChatKnowledgeBasesUpdate(BaseModel):
    """设置对话关联的知识库列表。"""
    kb_ids: list[int] = Field(..., description="知识库 ID 列表")
