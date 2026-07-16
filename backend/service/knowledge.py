"""知识库业务层 —— KnowledgeBase / Document / DocumentChunk / DocumentUpload / ProcessingTask 的 CRUD。

数据流：
    创建知识库  → INSERT knowledge_bases
    上传文档    → INSERT document_uploads (pending) + processing_tasks (pending)
                → 异步 pipeline 处理：切片/向量化/写入 documents+chunks/更新状态
    检索        → 按 kb_ids 在向量存储中过滤检索

权限：所有操作校验 knowledge_bases.user_id == current_user.id
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.models import (
    Document,
    DocumentChunk,
    DocumentUpload,
    KnowledgeBase,
    ProcessingTask,
)

logger = logging.getLogger(__name__)


# ==================== KnowledgeBase CRUD ====================

async def create_knowledge(
    name: str,
    description: Optional[str],
    user_id: int,
    db: AsyncSession,
) -> KnowledgeBase:
    """创建知识库。"""
    kb = KnowledgeBase(name=name, description=description, user_id=user_id)
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    logger.info(f"KnowledgeBase created: id={kb.id}, user_id={user_id}")
    return kb


async def list_knowledge(
    user_id: int, db: AsyncSession
) -> list[tuple[KnowledgeBase, int, int]]:
    """列出某用户的全部知识库，并一次性聚合每个 KB 的文档数和分块数。

    用两条相关子查询在单条 SQL 中完成计数，避免 N+1 查询。

    Returns:
        [(knowledge_base, doc_count, chunk_count), ...]
    """
    doc_count_subq = (
        select(func.count())
        .select_from(Document)
        .where(Document.knowledge_base_id == KnowledgeBase.id)
        .correlate(KnowledgeBase)
        .scalar_subquery()
        .label("doc_count")
    )
    chunk_count_subq = (
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.kb_id == KnowledgeBase.id)
        .correlate(KnowledgeBase)
        .scalar_subquery()
        .label("chunk_count")
    )
    result = await db.execute(
        select(KnowledgeBase, doc_count_subq, chunk_count_subq)
        .where(KnowledgeBase.user_id == user_id)
        .order_by(KnowledgeBase.updated_at.desc())
    )
    rows = result.all()
    return [(kb, int(doc_count or 0), int(chunk_count or 0)) for kb, doc_count, chunk_count in rows]


async def get_knowledge(
    kb_id: int, user_id: int, db: AsyncSession
) -> KnowledgeBase | None:
    """获取单个知识库（校验归属权）。"""
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_knowledge(
    kb_id: int,
    user_id: int,
    data: dict[str, Any],
    db: AsyncSession,
) -> KnowledgeBase | None:
    """更新知识库名称或描述。"""
    values = {k: v for k, v in data.items() if v is not None}
    if not values:
        return await get_knowledge(kb_id, user_id, db)

    await db.execute(
        update(KnowledgeBase)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
        .values(**values)
    )
    await db.commit()
    return await get_knowledge(kb_id, user_id, db)


async def delete_knowledge(
    kb_id: int, user_id: int, db: AsyncSession
) -> bool:
    """删除知识库及其全部关联数据。

    按显式顺序删除以避免外键约束问题（与 delete_session 同思路）：
        chunks → uploads → tasks → documents → knowledge_base
    向量存储中的向量数据由调用方（路由层）单独清理。
    """
    kb = await get_knowledge(kb_id, user_id, db)
    if kb is None:
        return False

    # 按依赖顺序删除子表（叶子 → 根，避免外键约束 1451）
    # 依赖关系：
    #   document_chunks      → documents, knowledge_bases
    #   processing_tasks     → documents, document_uploads, knowledge_bases  ← 必须先于 uploads/documents 删除
    #   document_uploads     → knowledge_bases
    #   documents            → knowledge_bases
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.kb_id == kb_id)
    )
    await db.execute(
        delete(ProcessingTask).where(ProcessingTask.knowledge_base_id == kb_id)
    )
    await db.execute(
        delete(DocumentUpload).where(DocumentUpload.knowledge_base_id == kb_id)
    )
    await db.execute(
        delete(Document).where(Document.knowledge_base_id == kb_id)
    )
    await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    await db.commit()
    logger.info(f"KnowledgeBase deleted: id={kb_id}, user_id={user_id}")
    return True


# ==================== Document 管理 ====================

async def create_document_record(
    kb_id: int,
    file_path: str,
    file_name: str,
    file_size: int,
    content_type: str,
    file_hash: str,
    db: AsyncSession,
) -> Document:
    """插入 documents 记录。"""
    doc = Document(
        knowledge_base_id=kb_id,
        file_path=file_path,
        file_name=file_name,
        file_size=file_size,
        content_type=content_type,
        file_hash=file_hash,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def list_documents(
    kb_id: int,
    user_id: int,
    page: int,
    limit: int,
    db: AsyncSession,
) -> tuple[list[Document], bool]:
    """分页列出知识库中的文档。

    Returns:
        (documents, has_more)
    """
    # 先校验 KB 归属
    kb = await get_knowledge(kb_id, user_id, db)
    if kb is None:
        return [], False

    offset = max(page - 1, 0) * limit
    result = await db.execute(
        select(Document)
        .where(Document.knowledge_base_id == kb_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return rows, has_more


async def get_document(
    doc_id: int, user_id: int, db: AsyncSession
) -> Document | None:
    """获取文档详情（校验所属 KB 的归属权）。"""
    result = await db.execute(
        select(Document)
        .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
        .where(Document.id == doc_id, KnowledgeBase.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_document(
    doc_id: int,
    user_id: int,
    db: AsyncSession,
    store: Optional[Any] = None,
) -> bool:
    """删除文档及其 chunks、processing_tasks，并清理向量存储。

    Args:
        store: 可选的向量存储实例。传入时按 (kb_id, file_name) 精确清理
               该文档在向量存储中的全部 chunk；None 时跳过向量清理
               （向后兼容，但会留下孤儿向量，建议始终传入）。

    Returns:
        是否真的删除了一行。
    """
    doc = await get_document(doc_id, user_id, db)
    if doc is None:
        return False

    # 1) 清理向量存储中的向量：按 (kb_id, file_name) 精确定位
    if store is not None:
        try:
            deleted_count = await store.delete_by_kb_id_and_source(
                doc.knowledge_base_id, doc.file_name
            )
            if deleted_count > 0:
                logger.info(
                    f"Cleaned {deleted_count} chunks in vector store "
                    f"for doc_id={doc_id} (kb_id={doc.knowledge_base_id}, "
                    f"file_name={doc.file_name})"
                )
        except Exception as e:
            # 向量清理失败不阻断 DB 删除流程，仅记录警告
            logger.warning(
                f"Failed to clean vector store for doc_id={doc_id}: {e}"
            )

    # 2) 删除子表（chunks 必须先于 documents，避免外键约束）
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == doc_id)
    )
    await db.execute(
        delete(ProcessingTask).where(ProcessingTask.document_id == doc_id)
    )
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()
    logger.info(f"Document deleted: id={doc_id}, user_id={user_id}")
    return True


async def find_document_by_hash(
    kb_id: int, file_hash: str, db: AsyncSession
) -> Document | None:
    """按 hash 查重 —— 同一 KB 中是否已存在相同 hash 的文档。"""
    result = await db.execute(
        select(Document)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.file_hash == file_hash,
        )
    )
    return result.scalar_one_or_none()


async def find_document_by_name(
    kb_id: int, file_name: str, db: AsyncSession
) -> Document | None:
    """按文件名查重 —— 同一 KB 中是否已存在同名文档。"""
    result = await db.execute(
        select(Document)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.file_name == file_name,
        )
    )
    return result.scalar_one_or_none()


# ==================== Chunk 管理 ====================

async def list_chunks(
    kb_id: int,
    user_id: int,
    document_id: Optional[int],
    page: int,
    limit: int,
    db: AsyncSession,
) -> tuple[list[DocumentChunk], bool]:
    """分页列出 chunk。可按 document_id 过滤。"""
    kb = await get_knowledge(kb_id, user_id, db)
    if kb is None:
        return [], False

    offset = max(page - 1, 0) * limit
    stmt = (
        select(DocumentChunk)
        .where(DocumentChunk.kb_id == kb_id)
        .order_by(DocumentChunk.id.asc())
    )
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    stmt = stmt.offset(offset).limit(limit + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return rows, has_more


# ==================== DocumentUpload ====================

async def create_upload(
    kb_id: int,
    file_name: str,
    file_hash: str,
    file_size: int,
    content_type: str,
    temp_path: Optional[str],
    db: AsyncSession,
) -> DocumentUpload:
    """创建上传记录（status=pending）。"""
    upload = DocumentUpload(
        knowledge_base_id=kb_id,
        file_name=file_name,
        file_hash=file_hash,
        file_size=file_size,
        content_type=content_type,
        temp_path=temp_path,
        status="pending",
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)
    return upload


async def list_uploads(
    kb_id: int,
    user_id: int,
    status_filter: Optional[str],
    page: int,
    limit: int,
    db: AsyncSession,
) -> tuple[list[DocumentUpload], bool]:
    """分页列出上传记录，可按 status 过滤。"""
    kb = await get_knowledge(kb_id, user_id, db)
    if kb is None:
        return [], False

    offset = max(page - 1, 0) * limit
    stmt = (
        select(DocumentUpload)
        .where(DocumentUpload.knowledge_base_id == kb_id)
        .order_by(DocumentUpload.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(DocumentUpload.status == status_filter)
    stmt = stmt.offset(offset).limit(limit + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return rows, has_more


async def get_upload(
    upload_id: int, user_id: int, db: AsyncSession
) -> DocumentUpload | None:
    """获取上传详情（校验归属权）。"""
    result = await db.execute(
        select(DocumentUpload)
        .join(KnowledgeBase, DocumentUpload.knowledge_base_id == KnowledgeBase.id)
        .where(DocumentUpload.id == upload_id, KnowledgeBase.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_upload_status(
    upload_id: int,
    status: str,
    error_message: Optional[str],
    db: AsyncSession,
) -> None:
    """更新上传记录状态。"""
    await db.execute(
        update(DocumentUpload)
        .where(DocumentUpload.id == upload_id)
        .values(status=status, error_message=error_message)
    )
    await db.commit()


# ==================== ProcessingTask ====================

async def create_task(
    kb_id: int,
    document_upload_id: Optional[int],
    document_id: Optional[int],
    db: AsyncSession,
) -> ProcessingTask:
    """创建处理任务（status=pending）。"""
    task = ProcessingTask(
        knowledge_base_id=kb_id,
        document_upload_id=document_upload_id,
        document_id=document_id,
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def list_tasks(
    kb_id: int,
    user_id: int,
    status_filter: Optional[str],
    page: int,
    limit: int,
    db: AsyncSession,
) -> tuple[list[ProcessingTask], bool]:
    """分页列出处理任务，可按 status 过滤。"""
    kb = await get_knowledge(kb_id, user_id, db)
    if kb is None:
        return [], False

    offset = max(page - 1, 0) * limit
    stmt = (
        select(ProcessingTask)
        .where(ProcessingTask.knowledge_base_id == kb_id)
        .order_by(ProcessingTask.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(ProcessingTask.status == status_filter)
    stmt = stmt.offset(offset).limit(limit + 1)

    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return rows, has_more


async def get_task(
    task_id: int, user_id: int, db: AsyncSession
) -> ProcessingTask | None:
    """获取任务详情（校验归属权）。"""
    result = await db.execute(
        select(ProcessingTask)
        .join(KnowledgeBase, ProcessingTask.knowledge_base_id == KnowledgeBase.id)
        .where(ProcessingTask.id == task_id, KnowledgeBase.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_task_status(
    task_id: int,
    status: str,
    error_message: Optional[str],
    db: AsyncSession,
) -> None:
    """更新任务状态。"""
    await db.execute(
        update(ProcessingTask)
        .where(ProcessingTask.id == task_id)
        .values(status=status, error_message=error_message)
    )
    await db.commit()


async def reset_task_for_retry(
    task_id: int, user_id: int, db: AsyncSession
) -> tuple[ProcessingTask, DocumentUpload] | None:
    """重置失败任务为 pending 状态，返回 (task, upload) 供 pipeline 重跑。

    校验：
        - task 必须存在且属于当前用户
        - task 当前状态必须为 failed（防止重试进行中任务）
        - task 必须关联 document_upload_id
    """
    task = await get_task(task_id, user_id, db)
    if task is None:
        return None
    if task.status != "failed":
        raise ValueError(f"任务当前状态为 {task.status}，只有 failed 状态可重试")
    if not task.document_upload_id:
        raise ValueError("任务未关联上传记录，无法重试")

    # 查询关联的上传记录
    result = await db.execute(
        select(DocumentUpload).where(DocumentUpload.id == task.document_upload_id)
    )
    upload = result.scalar_one_or_none()
    if upload is None:
        raise ValueError("关联的上传记录不存在")

    # 重置状态
    await db.execute(
        update(ProcessingTask)
        .where(ProcessingTask.id == task_id)
        .values(status="pending", error_message=None)
    )
    await db.execute(
        update(DocumentUpload)
        .where(DocumentUpload.id == upload.id)
        .values(status="pending", error_message=None)
    )
    await db.commit()
    return task, upload


# ==================== DocumentChunk 批量写入 ====================

async def bulk_insert_chunks(
    chunks_data: list[dict[str, Any]], db: AsyncSession
) -> int:
    """批量插入文档块记录。

    chunk_id 基于 (kb_id, file_name, content) 的 SHA-256，相同内容 → 相同 ID。
    若数据库中已存在相同 ID（例如历史上传残留或部分失败重试），跳过这些 chunk，
    符合"内容去重"设计语义，避免主键冲突 (IntegrityError 1062)。

    Args:
        chunks_data: 每项包含 id, kb_id, document_id, file_name, chunk_metadata, hash

    Returns:
        实际插入条数（已存在的会被跳过）
    """
    if not chunks_data:
        return 0

    # 1) 同批次内部按 chunk_id 去重（文档中可能有完全相同内容的段落 → 相同 chunk_id）
    seen_ids: set[str] = set()
    deduped_data: list[dict[str, Any]] = []
    internal_dupes = 0
    for c in chunks_data:
        cid = c["id"]
        if cid in seen_ids:
            internal_dupes += 1
            continue
        seen_ids.add(cid)
        deduped_data.append(c)
    if internal_dupes > 0:
        logger.info(
            f"Bulk insert: removed {internal_dupes} internal duplicate(s) within batch"
        )

    # 2) 过滤数据库中已存在的 chunk_id（历史上传残留 / 重试场景）
    chunk_ids = [c["id"] for c in deduped_data]
    result = await db.execute(
        select(DocumentChunk.id).where(DocumentChunk.id.in_(chunk_ids))
    )
    existing_ids = set(result.scalars().all())

    new_chunks_data = [c for c in deduped_data if c["id"] not in existing_ids]
    db_skipped = len(deduped_data) - len(new_chunks_data)
    if db_skipped > 0:
        logger.info(
            f"Bulk insert: skipped {db_skipped} chunk(s) already in DB"
        )

    skipped = internal_dupes + db_skipped
    if not new_chunks_data:
        return 0

    objects = [
        DocumentChunk(
            id=c["id"],
            kb_id=c["kb_id"],
            document_id=c["document_id"],
            file_name=c["file_name"],
            chunk_metadata=c.get("chunk_metadata"),
            hash=c["hash"],
        )
        for c in new_chunks_data
    ]
    db.add_all(objects)
    await db.commit()
    logger.info(f"Bulk inserted {len(objects)} chunks (skipped {skipped} duplicates)")
    return len(objects)
