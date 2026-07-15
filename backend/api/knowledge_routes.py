from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import require_user
from ..core.config import Settings, get_settings
from ..db import get_db
from ..ingestion.pipeline import ingest_document
from ..schema.knowledge import (
    ChatKnowledgeBasesUpdate,
    DocumentChunkResponse,
    DocumentResponse,
    DocumentUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    PageResponse,
    ProcessingTaskResponse,
    UploadAcceptedResponse,
)
from ..service import knowledge as knowledge_service
from ..vectorstore.chroma_store import VectorStore
from .dependencies import get_embedder, get_vector_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ==================== 知识库 CRUD ====================

@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_route(
    payload: KnowledgeBaseCreate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """创建知识库。"""
    kb = await knowledge_service.create_knowledge(
        payload.name, payload.description, current_user.id, db
    )
    return KnowledgeBaseResponse.model_validate(kb, from_attributes=True)


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_route(
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出我的知识库（含每个 KB 的文档数和分块数，单条 SQL 聚合）。"""
    items = await knowledge_service.list_knowledge(current_user.id, db)
    responses = []
    for kb, doc_count, chunk_count in items:
        resp = KnowledgeBaseResponse.model_validate(kb, from_attributes=True)
        resp.doc_count = doc_count
        resp.chunk_count = chunk_count
        responses.append(resp)
    return responses


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_route(
    kb_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取知识库详情。"""
    kb = await knowledge_service.get_knowledge(kb_id, current_user.id, db)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return KnowledgeBaseResponse.model_validate(kb, from_attributes=True)


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_route(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """更新知识库信息。"""
    kb = await knowledge_service.update_knowledge(
        kb_id, current_user.id, payload.model_dump(exclude_unset=True), db
    )
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return KnowledgeBaseResponse.model_validate(kb, from_attributes=True)


@router.delete("/{kb_id}")
async def delete_knowledge_route(
    kb_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
    store: VectorStore = Depends(get_vector_store),
):
    """删除知识库及其全部关联数据 + 清理 ChromaDB 向量。"""
    # 先获取 KB 信息（用于 ChromaDB 清理）
    kb = await knowledge_service.get_knowledge(kb_id, current_user.id, db)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")

    # 清理 ChromaDB 中该 KB 的全部 chunk
    try:
        deleted_count = await store.delete_by_kb_id(kb_id)
        logger.info(f"Cleaned {deleted_count} chunks in vector store for kb_id={kb_id}")
    except Exception as e:
        logger.warning(f"Failed to clean vector store for kb_id={kb_id}: {e}")

    # 删除数据库记录
    await knowledge_service.delete_knowledge(kb_id, current_user.id, db)
    return {"deleted": True, "kb_id": kb_id}


# ==================== 文档管理 ====================

@router.get(
    "/{kb_id}/documents",
    response_model=PageResponse,
)
async def list_documents_route(
    kb_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出知识库中的文档。"""
    docs, has_more = await knowledge_service.list_documents(
        kb_id, current_user.id, page, limit, db
    )
    if not docs and not await knowledge_service.get_knowledge(kb_id, current_user.id, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return PageResponse(
        items=[DocumentResponse.model_validate(d, from_attributes=True) for d in docs],
        has_more=has_more,
    )


@router.post(
    "/{kb_id}/documents",
    response_model=UploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_route(
    kb_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    embedder=Depends(get_embedder),
):
    """上传文档到知识库。

    流程：
        1. 校验 KB 归属权
        2. 接收文件 → 计算 SHA-256
        3. 查重：相同 hash → 拒绝；同名文件 → 拒绝
        4. 创建 document_uploads (pending) + processing_tasks (pending)
        5. 异步执行 pipeline：
            - 切片 + 生成 embedding + 写入 ChromaDB
            - 写入 documents + document_chunks
            - 更新 task/upload 状态为 completed
        6. 返回 202 + upload_id + task_id
    """
    # 1) 校验 KB 归属权
    kb = await knowledge_service.get_knowledge(kb_id, current_user.id, db)
    if kb is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")

    # 2) 接收文件并保存
    upload_dir = Path(settings.documents_dir) / f"kb_{kb_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = Path(file.filename or "unnamed").name
    upload_path = upload_dir / safe_filename
    content = await file.read()
    upload_path.write_bytes(content)
    logger.info(f"Saved upload: {upload_path} ({len(content)} bytes)")

    # 3) 计算 hash + 查重
    file_hash = knowledge_service.compute_file_hash(upload_path)
    file_size = len(content)
    content_type = file.content_type or "application/octet-stream"

    # 3a) hash 查重
    existing_hash = await knowledge_service.find_document_by_hash(kb_id, file_hash, db)
    if existing_hash is not None:
        # 同文件已上传，清理临时文件并拒绝
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"相同内容文件已存在: {existing_hash.file_name}",
        )

    # 3b) 同名查重
    existing_name = await knowledge_service.find_document_by_name(kb_id, safe_filename, db)
    if existing_name is not None:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"同名文件已存在: {safe_filename}",
        )

    # 4) 创建 upload + task 记录
    upload = await knowledge_service.create_upload(
        kb_id=kb_id,
        file_name=safe_filename,
        file_hash=file_hash,
        file_size=file_size,
        content_type=content_type,
        temp_path=str(upload_path),
        db=db,
    )
    task = await knowledge_service.create_task(
        kb_id=kb_id,
        document_upload_id=upload.id,
        document_id=None,
        db=db,
    )

    # 5) 异步执行 pipeline
    async def run_pipeline():
        # 使用新的独立 DB session（避免与请求 session 冲突）
        from ..db.database import async_session as session_factory
        async with session_factory() as pipeline_db:
            await ingest_document(
                kb_id=kb_id,
                upload_id=upload.id,
                task_id=task.id,
                file_path=upload_path,
                file_name=safe_filename,
                file_hash=file_hash,
                file_size=file_size,
                content_type=content_type,
                settings=settings,
                store=store,
                embedder=embedder,
                db=pipeline_db,
            )

    background_tasks.add_task(run_pipeline)

    return UploadAcceptedResponse(upload_id=upload.id, task_id=task.id, status="pending")


# ==================== Chunk ====================

@router.get("/{kb_id}/chunks", response_model=PageResponse)
async def list_chunks_route(
    kb_id: int,
    document_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出知识库的全部 chunk。"""
    chunks, has_more = await knowledge_service.list_chunks(
        kb_id, current_user.id, document_id, page, limit, db
    )
    if not chunks and not await knowledge_service.get_knowledge(kb_id, current_user.id, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return PageResponse(
        items=[DocumentChunkResponse.model_validate(c, from_attributes=True) for c in chunks],
        has_more=has_more,
    )


# ==================== Uploads ====================

@router.get("/{kb_id}/uploads", response_model=PageResponse)
async def list_uploads_route(
    kb_id: int,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出上传记录。"""
    uploads, has_more = await knowledge_service.list_uploads(
        kb_id, current_user.id, status_filter, page, limit, db
    )
    if not uploads and not await knowledge_service.get_knowledge(kb_id, current_user.id, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return PageResponse(
        items=[DocumentUploadResponse.model_validate(u, from_attributes=True) for u in uploads],
        has_more=has_more,
    )


@router.get("/uploads/{upload_id}", response_model=DocumentUploadResponse)
async def get_upload_route(
    upload_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取上传详情。"""
    upload = await knowledge_service.get_upload(upload_id, current_user.id, db)
    if upload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "上传记录不存在")
    return DocumentUploadResponse.model_validate(upload, from_attributes=True)


# ==================== Tasks ====================

@router.get("/{kb_id}/tasks", response_model=PageResponse)
async def list_tasks_route(
    kb_id: int,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """列出处理任务。"""
    tasks, has_more = await knowledge_service.list_tasks(
        kb_id, current_user.id, status_filter, page, limit, db
    )
    if not tasks and not await knowledge_service.get_knowledge(kb_id, current_user.id, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    return PageResponse(
        items=[ProcessingTaskResponse.model_validate(t, from_attributes=True) for t in tasks],
        has_more=has_more,
    )


@router.get("/tasks/{task_id}", response_model=ProcessingTaskResponse)
async def get_task_route(
    task_id: int,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """获取任务详情。"""
    task = await knowledge_service.get_task(task_id, current_user.id, db)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")
    return ProcessingTaskResponse.model_validate(task, from_attributes=True)


@router.post("/tasks/{task_id}/retry", response_model=UploadAcceptedResponse)
async def retry_task_route(
    task_id: int,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    store: VectorStore = Depends(get_vector_store),
    embedder=Depends(get_embedder),
):
    """重试失败的任务。

    流程：
        1. 校验 task 状态 = failed，且关联 upload 存在
        2. 重置 task/upload 为 pending
        3. 异步重跑 pipeline（基于 upload 记录中的 file 信息）
    """
    try:
        result = await knowledge_service.reset_task_for_retry(
            task_id, current_user.id, db
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "任务不存在")

    task, upload = result

    # 重建 pipeline 所需的文件路径
    file_path = Path(upload.temp_path) if upload.temp_path else None
    if file_path is None or not file_path.exists():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"原始文件不存在: {upload.temp_path}",
        )

    # 异步重跑 pipeline
    async def run_pipeline():
        from ..db.database import async_session as session_factory
        async with session_factory() as pipeline_db:
            await ingest_document(
                kb_id=task.knowledge_base_id,
                upload_id=upload.id,
                task_id=task.id,
                file_path=file_path,
                file_name=upload.file_name,
                file_hash=upload.file_hash,
                file_size=upload.file_size,
                content_type=upload.content_type,
                settings=settings,
                store=store,
                embedder=embedder,
                db=pipeline_db,
            )

    background_tasks.add_task(run_pipeline)

    return UploadAcceptedResponse(
        upload_id=upload.id, task_id=task.id, status="pending"
    )
