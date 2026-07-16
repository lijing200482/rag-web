"""文档管理路由 —— 独立于 /knowledge 的文档级操作。

当前端点：
    DELETE /documents/{doc_id}  删除单个文档（含 chunks + 向量存储）

设计说明：
    文档详情查询走 /knowledge/{kb_id}/documents（分页）；
    文档删除需要向量存储清理，故单独成路由以注入 VectorStore。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_user
from ..db import get_db
from ..service import knowledge as knowledge_service
from ..vectorstore.milvus_store import VectorStore
from .dependencies import get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.delete("/{doc_id}")
async def delete_document_route(
    doc_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
):
    """删除单个文档及其全部关联数据。

    清理顺序：
        1. 向量存储中的向量（按 kb_id + file_name 精确定位）
        2. document_chunks 表
        3. processing_tasks 表（引用 document_id 的记录）
        4. documents 表本身
    """
    deleted = await knowledge_service.delete_document(
        doc_id=doc_id,
        user_id=current_user.id,
        db=db,
        store=store,
    )
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在或无权访问")
    return {"deleted": True, "doc_id": doc_id}
