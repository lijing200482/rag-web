"""文档处理流水线 —— V2 完整异步流程。

V2 改造：
    - 新增 ingest_document() 接收完整的上传上下文（kb_id, upload_id, task_id 等）
    - 异步执行：加载 → 切片 → 向量化 → 写入向量存储
    - 同步写入 DB 表：documents + document_chunks
    - 更新 processing_tasks / document_uploads 状态
    - 每个 chunk metadata 持久化 kb_id（用于检索时按知识库过滤）
    - chunk_id 基于 SHA-256 → 相同内容自动去重
"""
import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select as sa_select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from .loaders import load_document
from .splitter import chunk_documents
from ..vectorstore.milvus_store import VectorStore
from ..core.config import Settings
from ..service import knowledge as knowledge_service
from ..storage import get_storage

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
    storage_key: str = "",
) -> None:
    """V2 完整文档处理流水线。

    流程：
        ① 更新 task 状态 = processing（独立提交，便于上层观察）
        ② 加载文档（asyncio.to_thread 包装同步 I/O，避免阻塞事件循环）
        ③ 切片（带 kb_id + file_name → 生成稳定 chunk_id）
        ④ 向量化 + 写入向量存储（metadata 带 kb_id，事务外执行）
        ⑤⑥⑦ 单一 DB 事务：写入 documents + document_chunks + 更新状态

    远端文件加载（storage_key 非空时）：
        - 通过 storage.download_to_path() 将 MinIO 对象下载到临时文件
        - load_document 读取临时文件（LangChain loaders 需要本地路径）
        - 处理完成后（无论成功失败）清理临时文件

    任一步失败 → 回滚：
        - DB 事务自动回滚（db.begin() 上下文管理）
        - ④ 已执行 → 按 (kb_id, file_name) 清理向量存储中刚写入的向量
        - 标记 task = failed, upload = failed（含 error_message）
    """
    vector_written = False  # ④ 已写入向量存储

    # 远端文件加载：如果提供了 storage_key（MinIO 对象 key），则从远端下载到临时文件
    # storage_key 为空 → 使用本地 file_path（LocalStorage 向后兼容）
    if storage_key:
        storage = get_storage(settings)
        temp_path = Path(tempfile.gettempdir()) / f"rag_ingest_{file_hash[:8]}_{file_name}"
        await storage.download_to_path(storage_key, temp_path)
        actual_path = temp_path
        _cleanup = True
    else:
        actual_path = file_path
        _cleanup = False

    try:
        # ① task → processing（独立提交，便于上层轮询观察处理中状态）
        await db.execute(
            sa_update(knowledge_service.ProcessingTask)
            .where(knowledge_service.ProcessingTask.id == task_id)
            .values(status="processing", error_message=None)
        )
        await db.commit()

        # ② 加载文档（同步 I/O 放入线程池，避免阻塞事件循环）
        docs = await asyncio.to_thread(load_document, actual_path)
        logger.info(
            f"[Pipeline] Loaded {len(docs)} page(s) from {file_name} (kb_id={kb_id})"
        )

        # ③ 切片（V4: Small-to-Big 两级切分 → 父块+子块混合列表）
        # V4-B+: 按 token 计数（from_tiktoken_encoder），与 LLM 计费单位一致
        chunks = chunk_documents(
            docs,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            kb_id=kb_id,
            file_name=file_name,
            parent_chunk_size=settings.parent_chunk_size,
            child_chunk_size=settings.child_chunk_size,
            child_chunk_overlap=settings.child_chunk_overlap,
            encoding_name=settings.tiktoken_encoding,
        )

        # 补充 chunk metadata：source / document_type / uploaded_at
        uploaded_at = datetime.now(timezone.utc).isoformat()
        for chunk in chunks:
            chunk.metadata["source"] = file_name
            chunk.metadata["document_type"] = file_path.suffix.lstrip(".")
            chunk.metadata["uploaded_at"] = uploaded_at

        # V4-B: 拆分父子块 —— 父块只写 MySQL,子块写 MySQL + Milvus
        # 父块永远不会参与向量检索(search 时 filter is_parent==false),无需算 embedding
        parent_chunks = [c for c in chunks if c.metadata.get("is_parent")]
        child_chunks = [c for c in chunks if not c.metadata.get("is_parent")]
        logger.info(
            f"[Pipeline] Split into {len(chunks)} chunks "
            f"(parents={len(parent_chunks)} → MySQL only, "
            f"children={len(child_chunks)} → MySQL + Milvus, "
            f"parent_size={settings.parent_chunk_size}, child_size={settings.child_chunk_size})"
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[Pipeline] === Parent chunks preview (max 2) ===")
            for i, c in enumerate(parent_chunks[:2]):
                logger.debug(
                    f"[Pipeline]   parent[{i}] chunk_id={c.metadata['chunk_id'][:12]}... "
                    f"len={len(c.page_content)} content={c.page_content[:100]!r}..."
                )
            logger.debug(f"[Pipeline] === Child chunks preview (max 3) ===")
            for i, c in enumerate(child_chunks[:3]):
                logger.debug(
                    f"[Pipeline]   child[{i}] chunk_id={c.metadata['chunk_id'][:12]}... "
                    f"parent_id={c.metadata.get('parent_id', '?')[:12]}... "
                    f"len={len(c.page_content)} content={c.page_content[:80]!r}..."
                )

        # ④ 向量化 + 写入向量存储：只处理子块（父块跳过,节省 embed 调用 + 存储）
        # V2 兼容:若 child_chunks 为空(未启用父子切分),回退到全量 upsert
        chunks_to_embed = child_chunks if child_chunks else chunks
        # 收集本次实际写入 Milvus 的 chunk_id 集合
        # 失败回滚时按此集合精确删除,避免误删同文件名下已成功入库的旧 chunk
        written_chunk_ids: list[str] = [
            c.metadata["chunk_id"] for c in chunks_to_embed
            if c.metadata.get("chunk_id")
        ]
        await store.upsert(chunks_to_embed, embedder)
        vector_written = True
        logger.info(f"[Pipeline] Upserted {len(chunks_to_embed)} chunks to vector store")

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
            # V4: 同时写入父块和子块，通过 is_parent / parent_id 区分
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
                                 "document_type", "uploaded_at",
                                 "is_parent", "parent_id"}
                }

                chunks_data.append({
                    "id": chunk_id,
                    "kb_id": kb_id,
                    "document_id": doc.id,
                    "file_name": file_name,
                    "chunk_metadata": chunk_meta or None,
                    "hash": chunk_hash,
                    # V4: 父子索引字段
                    "is_parent": bool(chunk.metadata.get("is_parent", False)),
                    "parent_id": chunk.metadata.get("parent_id"),
                    # V4-B+: 父块和子块都存 page_content
                    # 父块：用于 RAG 检索时回查完整语义单元
                    # 子块：用于 BM25 关键词检索（Hybrid 检索的关键词召回分支）
                    # 代价：子块多存 ~200-400 字，但换来 BM25 与向量检索路径对称
                    "page_content": chunk.page_content,
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
                        # V4: 父子索引字段
                        is_parent=c["is_parent"],
                        parent_id=c["parent_id"],
                        # V4-B: 块全文
                        page_content=c["page_content"],
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

            # V4-B+: 文档新增后清 BM25 缓存，下次查询时按新数据重建索引
            try:
                from ..retrieval.bm25_retriever import BM25Retriever
                BM25Retriever.invalidate(kb_id=kb_id)
            except Exception as cache_err:
                logger.warning(
                    f"[Pipeline] BM25 cache invalidation failed (non-fatal): {cache_err}"
                )

    except Exception as e:
        logger.error(
            f"[Pipeline] Failed: kb_id={kb_id}, task_id={task_id}, error={e}",
            exc_info=True,
        )

        # 回滚向量存储中刚写入的向量（DB 事务已由 db.begin() 自动回滚）
        if vector_written:
            await _rollback_pipeline(
                kb_id=kb_id,
                file_name=file_name,
                store=store,
                written_chunk_ids=written_chunk_ids,
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
    finally:
        # 清理远端下载到本地的临时文件（storage_key 模式下才会产生）
        if _cleanup:
            try:
                actual_path.unlink(missing_ok=True)
            except Exception as cleanup_err:
                logger.warning(
                    f"[Pipeline] Temp file cleanup failed: {cleanup_err}"
                )


async def _rollback_pipeline(
    kb_id: int,
    file_name: str,
    store: VectorStore,
    written_chunk_ids: list[str] | None = None,
) -> None:
    """失败后回滚向量存储中已写入的向量，避免孤儿向量。

    DB 记录由 db.begin() 事务自动回滚，无需手动清理。
    向量存储是外部系统，不在 DB 事务内，需要手动清理。

    V4-B+ 起改为按 chunk_id 集合精确删除：
        - written_chunk_ids 非空 → 调 delete_by_ids 只删本次新写入的向量
        - written_chunk_ids 为空（V3 旧路径或收集失败）→ 降级用 delete_by_kb_id_and_source
          按 (kb_id, file_name) 全删（会误删同文件名旧 chunk，但有兜底总比留孤儿好）

    精确回滚的必要性：重试场景下同一文件名可能已有上次成功入库的 chunk，
    按 (kb_id, file_name) 全删会误伤这些旧 chunk，导致 Milvus 有记录而 MySQL 无记录
    的孤儿数据（或反之）。按 chunk_id 删除只影响本次写入，保证跨系统最终一致性。

    清理失败仅记录 warning，不阻断异常重新抛出。
    """
    try:
        if written_chunk_ids:
            # 优先路径：按本次新写的 chunk_id 精确删除
            count = await store.delete_by_ids(written_chunk_ids)
            logger.info(
                f"[Pipeline] Rollback: cleaned {count}/{len(written_chunk_ids)} chunks "
                f"by chunk_ids (kb_id={kb_id}, file_name={file_name})"
            )
        else:
            # 降级路径：无 chunk_id 集合（不应发生，防御性兜底）
            count = await store.delete_by_kb_id_and_source(kb_id, file_name)
            logger.warning(
                f"[Pipeline] Rollback: fallback to delete_by_kb_id_and_source "
                f"(no written_chunk_ids), cleaned {count} chunks "
                f"(kb_id={kb_id}, file_name={file_name}) - may affect old chunks of same file"
            )
    except Exception as rollback_err:
        logger.warning(
            f"[Pipeline] Rollback: failed to clean vector store "
            f"(kb_id={kb_id}, file_name={file_name}): {rollback_err}"
        )
