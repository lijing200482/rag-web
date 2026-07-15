"""文档处理流水线 —— V2 完整异步流程。

V2 改造：
    - 新增 ingest_document() 接收完整的上传上下文（kb_id, upload_id, task_id 等）
    - 异步执行：加载 → 切片 → 向量化 → 写 ChromaDB
    - 同步写入 DB 表：documents + document_chunks
    - 更新 processing_tasks / document_uploads 状态
    - 每个 chunk metadata 持久化 kb_id（用于检索时按知识库过滤）
    - chunk_id 基于 SHA-256 → 相同内容自动去重

保留 ingest_file() 兼容旧的 /documents/upload 端点。
"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langchain_core.documents import Document
from sqlalchemy import select as sa_select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from .loaders import load_document
from .splitter import chunk_documents
from ..vectorstore.chroma_store import VectorStore
from .embedder import get_embedding_provider
from ..core.config import Settings
from ..service import knowledge as knowledge_service

logger = logging.getLogger(__name__)


# ============================================================
# V2: 完整异步流水线
# ============================================================

async def ingest_document(
    kb_id: int,
    upload_id: int,
    task_id: int,
    file_path: Path,
    file_name: str,
    file_hash: str,
    file_size: int,
    content_type: str,
    settings: Settings,
    store: VectorStore,
    embedder,
    db: AsyncSession,
) -> None:
    """V2 完整文档处理流水线。

    流程：
        ① 更新 task 状态 = processing（独立提交，便于上层观察）
        ② 加载文档（asyncio.to_thread 包装同步 I/O，避免阻塞事件循环）
        ③ 切片（带 kb_id + file_name → 生成稳定 chunk_id）
        ④ 向量化 + 写入 ChromaDB（metadata 带 kb_id，事务外执行）
        ⑤⑥⑦ 单一 DB 事务：写入 documents + document_chunks + 更新状态

    任一步失败 → 回滚：
        - DB 事务自动回滚（db.begin() 上下文管理）
        - ④ 已执行 → 按 (kb_id, file_name) 清理 ChromaDB 中刚写入的向量
        - 标记 task = failed, upload = failed（含 error_message）
    """
    vector_written = False  # ④ 已写入 ChromaDB

    try:
        # ① task → processing（独立提交，便于上层轮询观察处理中状态）
        await db.execute(
            sa_update(knowledge_service.ProcessingTask)
            .where(knowledge_service.ProcessingTask.id == task_id)
            .values(status="processing", error_message=None)
        )
        await db.commit()

        # ② 加载文档（同步 I/O 放入线程池，避免阻塞事件循环）
        docs = await asyncio.to_thread(load_document, file_path)
        logger.info(
            f"[Pipeline] Loaded {len(docs)} page(s) from {file_name} (kb_id={kb_id})"
        )

        # ③ 切片（V2: 传入 kb_id 和 file_name 生成稳定 chunk_id）
        chunks = chunk_documents(
            docs,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            kb_id=kb_id,
            file_name=file_name,
        )

        # 补充 chunk metadata：source / document_type / uploaded_at
        uploaded_at = datetime.now(timezone.utc).isoformat()
        for chunk in chunks:
            chunk.metadata["source"] = file_name
            chunk.metadata["document_type"] = file_path.suffix.lstrip(".")
            chunk.metadata["uploaded_at"] = uploaded_at

        logger.info(
            f"[Pipeline] Split into {len(chunks)} chunks "
            f"(chunk_size={settings.chunk_size}, overlap={settings.chunk_overlap})"
        )

        # ④ 向量化 + 写入 ChromaDB（事务外执行，DB 事务失败时在 except 中清理）
        await store.upsert(chunks, embedder)
        vector_written = True
        logger.info(f"[Pipeline] Upserted {len(chunks)} chunks to vector store")

        # ⑤⑥⑦ 单一 DB 事务：document + chunks + 状态更新，全部成功或全部回滚
        async with db.begin():
            # ⑤ 写入 documents 表
            doc = knowledge_service.Document(
                knowledge_base_id=kb_id,
                file_path=str(file_path),
                file_name=file_name,
                file_size=file_size,
                content_type=content_type,
                file_hash=file_hash,
            )
            db.add(doc)
            await db.flush()  # 获取自增主键 doc.id，不提交
            logger.info(f"[Pipeline] Document record staged: id={doc.id}")

            # ⑥ 写入 document_chunks 表（批量，带去重逻辑）
            chunks_data = []
            for chunk in chunks:
                chunk_id = chunk.metadata.get("chunk_id")
                chunk_hash = chunk.metadata.get("hash")
                if not chunk_id or not chunk_hash:
                    logger.warning(f"[Pipeline] Chunk missing chunk_id/hash: {chunk.metadata}")
                    continue

                # chunk_metadata 保留 page_number、offset 等信息（剔除内部字段）
                chunk_meta = {
                    k: v
                    for k, v in chunk.metadata.items()
                    if k not in {"chunk_id", "hash", "timestamp", "kb_id", "source",
                                 "document_type", "uploaded_at"}
                }

                chunks_data.append({
                    "id": chunk_id,
                    "kb_id": kb_id,
                    "document_id": doc.id,
                    "file_name": file_name,
                    "chunk_metadata": chunk_meta or None,
                    "hash": chunk_hash,
                })

            # 同批次内部按 chunk_id 去重
            seen_ids: set[str] = set()
            deduped_data: list[dict] = []
            for c in chunks_data:
                if c["id"] not in seen_ids:
                    seen_ids.add(c["id"])
                    deduped_data.append(c)

            # 过滤数据库中已存在的 chunk_id（历史残留 / 重试场景）
            inserted = 0
            if deduped_data:
                chunk_ids = [c["id"] for c in deduped_data]
                result = await db.execute(
                    sa_select(knowledge_service.DocumentChunk.id).where(
                        knowledge_service.DocumentChunk.id.in_(chunk_ids)
                    )
                )
                existing_ids = set(result.scalars().all())
                new_chunks_data = [
                    c for c in deduped_data if c["id"] not in existing_ids
                ]

                objects = [
                    knowledge_service.DocumentChunk(
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
                inserted = len(objects)

            logger.info(f"[Pipeline] Inserted {inserted} chunk records to DB")

            # ⑦ task → completed, upload → completed
            await db.execute(
                sa_update(knowledge_service.ProcessingTask)
                .where(knowledge_service.ProcessingTask.id == task_id)
                .values(status="completed", error_message=None)
            )
            await db.execute(
                sa_update(knowledge_service.DocumentUpload)
                .where(knowledge_service.DocumentUpload.id == upload_id)
                .values(status="completed", error_message=None)
            )
            logger.info(
                f"[Pipeline] Completed: kb_id={kb_id}, doc_id={doc.id}, "
                f"task_id={task_id}, upload_id={upload_id}"
            )

    except Exception as e:
        logger.error(
            f"[Pipeline] Failed: kb_id={kb_id}, task_id={task_id}, error={e}",
            exc_info=True,
        )

        # 回滚 ChromaDB 中刚写入的向量（DB 事务已由 db.begin() 自动回滚）
        if vector_written:
            await _rollback_pipeline(
                kb_id=kb_id,
                file_name=file_name,
                store=store,
            )

        # 标记失败（新事务）
        try:
            await db.execute(
                sa_update(knowledge_service.ProcessingTask)
                .where(knowledge_service.ProcessingTask.id == task_id)
                .values(status="failed", error_message=str(e))
            )
            await db.execute(
                sa_update(knowledge_service.DocumentUpload)
                .where(knowledge_service.DocumentUpload.id == upload_id)
                .values(status="failed", error_message=str(e))
            )
            await db.commit()
        except Exception as update_err:
            logger.error(f"[Pipeline] Failed to update failure status: {update_err}")
            await db.rollback()
        raise


async def _rollback_pipeline(
    kb_id: int,
    file_name: str,
    store: VectorStore,
) -> None:
    """失败后回滚 ChromaDB 中已写入的向量，避免孤儿向量。

    DB 记录由 db.begin() 事务自动回滚，无需手动清理。
    ChromaDB 是外部系统，不在 DB 事务内，需要按 (kb_id, file_name) 手动清理。
    清理失败仅记录 warning，不阻断异常重新抛出。
    """
    try:
        collection = getattr(store, "_collection", None)
        if collection is not None:
            results = collection.get(
                where={"kb_id": kb_id, "source": file_name}
            )
            if results and results.get("ids"):
                collection.delete(ids=results["ids"])
                logger.info(
                    f"[Pipeline] Rollback: cleaned {len(results['ids'])} chunks "
                    f"in vector store (kb_id={kb_id}, file_name={file_name})"
                )
    except Exception as rollback_err:
        logger.warning(
            f"[Pipeline] Rollback: failed to clean vector store "
            f"(kb_id={kb_id}, file_name={file_name}): {rollback_err}"
        )


# ============================================================
# 兼容旧接口：ingest_file()
# ============================================================

async def ingest_file(file_path: Path, settings: Settings, store: VectorStore) -> str:
    """One-shot ingestion pipeline（旧接口兼容）。

    旧 /documents/upload 端点使用，不写 DB 表，不更新 task 状态。
    新代码请使用 ingest_document()。
    """
    # Step 1: Load document
    try:
        docs = load_document(file_path)
        logger.info(f"[Step 1/4] Loaded {len(docs)} page(s) from {file_path.name}")
    except Exception as e:
        logger.error(f"[Step 1/4] Failed to load document: {str(e)}")
        raise

    # Step 2: Chunk document（无 kb_id，回退到 uuid chunk_id）
    try:
        chunks = chunk_documents(docs, settings.chunk_size, settings.chunk_overlap)
        logger.info(
            f"[Step 2/4] Split into {len(chunks)} chunks "
            f"(chunk_size={settings.chunk_size}, overlap={settings.chunk_overlap})"
        )
    except Exception as e:
        logger.error(f"[Step 2/4] Failed to chunk document: {str(e)}")
        raise

    # Add document-level metadata to every chunk
    uploaded_at = datetime.now(timezone.utc).isoformat()
    for chunk in chunks:
        chunk.metadata["source"] = file_path.name
        chunk.metadata["document_type"] = file_path.suffix.lstrip(".")
        chunk.metadata["uploaded_at"] = uploaded_at

    # Step 3: Get embedder
    try:
        embedder = get_embedding_provider(settings).get_embedder()
        logger.info(
            f"[Step 3/4] Embedder ready "
            f"(provider={settings.embedding_provider}, model={settings.embedding_model})"
        )
    except Exception as e:
        logger.error(f"[Step 3/4] Failed to initialize embedder: {str(e)}")
        raise

    # Step 4: Upsert to vector store
    try:
        await store.upsert(chunks, embedder)
        logger.info(f"[Step 4/4] Upserted {len(chunks)} chunks to vector store")
    except Exception as e:
        logger.error(f"[Step 4/4] Failed to upsert to vector store: {str(e)}")
        raise

    return str(file_path)
