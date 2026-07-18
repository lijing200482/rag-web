from __future__ import annotations

import logging
import time

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.models.knowledge import DocumentChunk
from ..vectorstore.milvus_store import VectorStore
from .bm25_retriever import BM25Retriever
from .reranker import Reranker

logger = logging.getLogger(__name__)


class Retriever:
    """Thin wrapper around vector store search with configurable top_k.

    V2: 支持 kb_ids 参数实现知识库隔离检索。
    V4-B: 父块回查从 Milvus 移至本层（从 MySQL DocumentChunk 查）。
          vectorstore 只返回子块，本层负责把子块 page_content 替换为父块全文。
          - 按 parent_id 批量查 MySQL（避免循环单条查询）
          - 同一父块只回查一次并去重（避免重复父块灌入 Prompt）
          - 父块长度上限保护（防止异常父块撑爆 LLM 上下文窗口）
          - 降级场景告警日志（父块缺失/V2 旧数据时使用子块回答）
    V4-B+: Hybrid 检索（向量 + BM25 关键词融合）。
          - 向量召回子块 + BM25 召回子块（V4-C 改造，两边粒度对称）
          - 在子块 chunk_id 维度做 RRF 融合（rank 含义一致）
          - 融合后按 parent_id 聚合取 top_k 父块
          - 复用 _expand_to_parents 统一父块回查（代码路径合并）
          - BM25 索引按 kb_ids 维度缓存，文档变更时调 invalidate 清缓存
    V5: 二阶段精排（cross-encoder reranker）。
          - 在 RRF 融合 + 父块回查后，对 top_k 候选做 cross-encoder 精排
          - 用 (query, doc) 拼接 forward，弥补 bi-encoder 丢失的 query-doc 交互
          - 解决"双写一致排在缓存穿透方案前面"等 RRF 排序不准问题
          - 模型类级共享，CPU 推理放线程池避免阻塞事件循环
    """

    def __init__(
        self,
        store: VectorStore,
        embedder: Embeddings,
        top_k: int = 4,
        db: AsyncSession | None = None,
        max_parent_chars: int | None = None,
        bm25_retriever: BM25Retriever | None = None,
        hybrid_search_enabled: bool = False,
        hybrid_rrf_k: int = 60,
        hybrid_vector_top_k: int = 15,
        hybrid_bm25_top_k: int = 15,
        reranker: Reranker | None = None,
        rerank_enabled: bool = False,
        rerank_top_k: int | None = None,
    ):
        self._store = store
        self._embedder = embedder
        self._top_k = top_k
        self._db = db  # V4-B: 父块回查用,可为 None(回退到子块自身)
        # V4-B: 父块字符上限（检查清单 P0-4），None 表示不截断
        self._max_parent_chars = max_parent_chars
        # V4-B+: Hybrid 检索配置
        self._bm25 = bm25_retriever
        self._hybrid_enabled = hybrid_search_enabled and bm25_retriever is not None
        self._rrf_k = max(1, hybrid_rrf_k)
        self._hybrid_vector_top_k = hybrid_vector_top_k
        self._hybrid_bm25_top_k = hybrid_bm25_top_k
        # V5: Reranker 配置
        self._reranker = reranker
        self._rerank_enabled = rerank_enabled and reranker is not None
        self._rerank_top_k = rerank_top_k
        if self._hybrid_enabled:
            logger.info(
                f"[Retriever] Hybrid search enabled (RRF): "
                f"rrf_k={self._rrf_k}, "
                f"vector_top_k={self._hybrid_vector_top_k}, "
                f"bm25_top_k={self._hybrid_bm25_top_k}"
            )
        if self._rerank_enabled:
            logger.info(
                f"[Retriever] Rerank enabled (cross-encoder): "
                f"rerank_top_k={self._rerank_top_k or top_k}"
            )

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        kb_ids: list[int] | None = None,
    ) -> list[Document]:
        """检索相关文档。

        Args:
            query: 用户问题
            top_k: 覆盖默认 top_k
            kb_ids: 知识库 ID 列表，非空时只在这些知识库范围内检索

        V4-B+ Hybrid 流程（hybrid_search_enabled=True 时）：
            1. 向量检索：召回 hybrid_vector_top_k 个子块（按 distance 升序）
            2. BM25 检索：召回 hybrid_bm25_top_k 个子块（按 bm25_score 降序）
            3. RRF 融合：在子块 chunk_id 维度融合，rrf_score = Σ 1/(k + rank)
            4. 按 parent_id 聚合（同一父块只保留 rrf_score 最高的子块）取 top_k
            5. 复用 _expand_to_parents 批量查 MySQL 拿父块全文（与纯向量路径统一）

        V4-B 纯向量流程（hybrid_search_enabled=False 时）：
            1. vectorstore.search 返回子块（metadata 含 parent_id）
            2. 按 parent_id 去重 → 批量查 MySQL DocumentChunk 拿父块全文
            3. 拼装：page_content=父块全文, metadata=子块溯源信息
            4. 同一父块只出现一次（按 parent_chunk_id 去重）

        旧数据兼容：子块 parent_id 为空（V2 单块数据）→ 直接返回子块本身。
        """
        t0 = time.perf_counter()
        k = top_k if top_k is not None else self._top_k
        logger.info(
            f"[Retriever] Query start: query={query!r}, top_k={k}, kb_ids={kb_ids}, "
            f"hybrid={self._hybrid_enabled}"
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[Retriever] Query length: {len(query)} chars")

        # ── Hybrid 分支：向量 + BM25 RRF 融合 ──
        if self._hybrid_enabled:
            return await self._retrieve_hybrid(query, k, kb_ids, t0)

        # ── 纯向量分支（原 V4-B 路径）──
        t1 = time.perf_counter()
        child_docs = await self._store.search(query, self._embedder, top_k=k, kb_ids=kb_ids)
        t_search = (time.perf_counter() - t1) * 1000
        logger.info(
            f"[Retriever] Vector search done: {len(child_docs)} children in {t_search:.1f}ms"
        )
        if logger.isEnabledFor(logging.DEBUG):
            for i, d in enumerate(child_docs):
                dist = d.metadata.get("distance")
                logger.debug(
                    f"[Retriever]   child[{i}] distance={dist:.4f} "
                    f"source={d.metadata.get('source')} "
                    f"content={d.page_content[:80]!r}..."
                )

        if not child_docs:
            logger.info("[Retriever] No results returned (empty)")
            return []

        # 2. V4-B: 父块回查
        t2 = time.perf_counter()
        result = await self._expand_to_parents(child_docs)
        t_expand = (time.perf_counter() - t2) * 1000
        t_total = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[Retriever] Parent expansion done in {t_expand:.1f}ms, "
            f"total retrieve: {t_total:.1f}ms, final_docs={len(result)}"
        )

        # 3. V5: cross-encoder 重排序（可选）
        if self._rerank_enabled and result:
            result = await self._reranker.rerank(query, result, top_k=self._rerank_top_k)
            t_total = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[Retriever] After rerank, total retrieve: "
                f"{t_total:.1f}ms, final_docs={len(result)}"
            )
        return result

    async def _retrieve_hybrid(
        self,
        query: str,
        top_k: int,
        kb_ids: list[int] | None,
        t0: float,
    ) -> list[Document]:
        """Hybrid 检索：向量 + BM25 用 RRF 融合（V4-C 子块对称版）。

        RRF (Reciprocal Rank Fusion) 公式：
            rrf_score(d) = Σ 1/(k + rank_i(d))
        其中 rank_i(d) 是文档 d 在第 i 个检索器结果中的排名（从 1 开始），
        k 是平滑参数（默认 60），越大越鼓励多样性。

        V4-C 关键改造：两边都在子块维度做 RRF
            - 向量检索返回子块（chunk_id + parent_id）
            - BM25 检索也返回子块（chunk_id + parent_id）
            - 在 chunk_id 维度做 RRF 融合，rank 含义一致
            - 融合后按 parent_id 聚合（保留 rrf_score 最高的子块作为父块代表）
            - 复用 _expand_to_parents 统一父块回查，与纯向量路径对称
        """
        # 1. 向量检索：召回 hybrid_vector_top_k 个子块
        t1 = time.perf_counter()
        vector_children = await self._store.search(
            query, self._embedder,
            top_k=self._hybrid_vector_top_k, kb_ids=kb_ids,
        )
        t_vec = (time.perf_counter() - t1) * 1000
        logger.info(
            f"[Retriever][Hybrid] Vector search: "
            f"{len(vector_children)} children in {t_vec:.1f}ms "
            f"(top_k={self._hybrid_vector_top_k})"
        )

        # 2. BM25 检索：召回 hybrid_bm25_top_k 个子块
        t2 = time.perf_counter()
        bm25_results = await self._bm25.search(
            query, top_k=self._hybrid_bm25_top_k, kb_ids=kb_ids,
        )
        t_bm25 = (time.perf_counter() - t2) * 1000
        logger.info(
            f"[Retriever][Hybrid] BM25 search: "
            f"{len(bm25_results)} children in {t_bm25:.1f}ms "
            f"(top_k={self._hybrid_bm25_top_k})"
        )

        # 3. 在子块 chunk_id 维度构建 rank
        # 向量子块 rank：按 Milvus 返回顺序（distance 升序）
        vector_child_rank: dict[str, int] = {}  # chunk_id → rank
        vector_child_doc: dict[str, Document] = {}  # chunk_id → Document
        for child in vector_children:
            cid = child.metadata.get("chunk_id")
            if cid and cid not in vector_child_rank:
                vector_child_rank[cid] = len(vector_child_rank) + 1
                vector_child_doc[cid] = child

        # BM25 子块 rank：按 BM25 分数降序
        bm25_child_rank: dict[str, int] = {}  # chunk_id → rank
        # chunk_id → (parent_id, score, file_name)
        # file_name 用于 BM25-only 命中时构造伪 Document 的 source 元数据，
        # 与向量命中路径保持一致（向量子块 metadata.source 就是 file_name）
        bm25_child_meta: dict[str, tuple[str, float, str]] = {}
        for cid, pid, score, file_name in bm25_results:
            if cid not in bm25_child_rank:
                bm25_child_rank[cid] = len(bm25_child_rank) + 1
                bm25_child_meta[cid] = (pid, score, file_name)

        # 4. RRF 融合：在 chunk_id 维度
        all_child_ids = set(vector_child_rank) | set(bm25_child_rank)
        rrf_scores: dict[str, float] = {}  # chunk_id → rrf_score
        hit_sources: dict[str, str] = {}  # chunk_id → "vector+bm25"/"vector_only"/"bm25_only"
        for cid in all_child_ids:
            score = 0.0
            in_vector = cid in vector_child_rank
            in_bm25 = cid in bm25_child_rank
            if in_vector:
                score += 1.0 / (self._rrf_k + vector_child_rank[cid])
            if in_bm25:
                score += 1.0 / (self._rrf_k + bm25_child_rank[cid])
            rrf_scores[cid] = score
            if in_vector and in_bm25:
                hit_sources[cid] = "vector+bm25"
            elif in_vector:
                hit_sources[cid] = "vector_only"
            else:
                hit_sources[cid] = "bm25_only"

        # 5. 按 parent_id 聚合：同一父块只保留 rrf_score 最高的子块
        # parent_id → (chunk_id, rrf_score, hit_source)
        parent_best: dict[str, tuple[str, float, str]] = {}
        for cid in all_child_ids:
            rrf = rrf_scores[cid]
            source = hit_sources[cid]
            # 拿 parent_id：向量命中从向量子块取，BM25-only 从 bm25_child_meta 取
            if cid in vector_child_doc:
                pid = vector_child_doc[cid].metadata.get("parent_id")
            else:
                pid = bm25_child_meta[cid][0]
            if not pid:
                continue  # V2 旧数据无 parent_id，跳过
            # 同一父块只保留 rrf_score 最高的子块
            if pid not in parent_best or rrf > parent_best[pid][1]:
                parent_best[pid] = (cid, rrf, source)

        # 按 rrf_score 降序，取 top_k 个父块
        sorted_parents = sorted(parent_best.items(), key=lambda x: x[1][1], reverse=True)
        final_top_k = sorted_parents[:top_k]

        logger.info(
            f"[Retriever][Hybrid] RRF fusion (k={self._rrf_k}): "
            f"unique_children={len(all_child_ids)}, "
            f"unique_parents={len(parent_best)}, final={len(final_top_k)}, "
            f"both={sum(1 for s in hit_sources.values() if s == 'vector+bm25')}, "
            f"vector_only={sum(1 for s in hit_sources.values() if s == 'vector_only')}, "
            f"bm25_only={sum(1 for s in hit_sources.values() if s == 'bm25_only')}"
        )
        if logger.isEnabledFor(logging.DEBUG):
            for i, (pid, (cid, rrf, source)) in enumerate(final_top_k[:5]):
                v_rank = vector_child_rank.get(cid, "-")
                b_rank = bm25_child_rank.get(cid, "-")
                logger.debug(
                    f"[Retriever][Hybrid]   fused[{i}] rrf={rrf:.6f} "
                    f"pid={pid[:12]}... cid={cid[:12]}... "
                    f"vector_rank={v_rank} bm25_rank={b_rank} source={source}"
                )

        if not final_top_k:
            logger.info("[Retriever][Hybrid] No results after fusion")
            return []

        # 6. 构造子块列表，复用 _expand_to_parents 做父块回查
        # 顺序按 rrf_score 降序，与 _expand_to_parents 的"首次命中即最相似"假设一致
        fused_children: list[Document] = []
        for pid, (cid, rrf, source) in final_top_k:
            if cid in vector_child_doc:
                # 向量命中的子块：用原 Document（保留 page_content 作为父块缺失时的降级内容）
                child_doc = vector_child_doc[cid]
                merged_meta = dict(child_doc.metadata)
                page_content = child_doc.page_content
            else:
                # BM25-only 命中：从零构造伪 Document（无 distance 等向量元数据）
                # page_content 留空，父块回查失败时会被 _expand_to_parents 跳过
                # source/file_name 从 BM25 索引取，保持与向量命中路径一致
                bm25_score, file_name = bm25_child_meta[cid][1], bm25_child_meta[cid][2]
                merged_meta = {
                    "chunk_id": cid,
                    "parent_id": pid,
                    "source": file_name,  # 与向量子块 metadata.source 对齐
                    "bm25_score": bm25_score,
                }
                page_content = ""
            merged_meta["rrf_score"] = rrf
            merged_meta["hit_source"] = source
            fused_children.append(Document(page_content=page_content, metadata=merged_meta))

        # 7. 复用纯向量路径的 _expand_to_parents 做父块回查
        t3 = time.perf_counter()
        result = await self._expand_to_parents(fused_children)
        t_expand = (time.perf_counter() - t3) * 1000
        t_total = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[Retriever][Hybrid] Parent expansion done in {t_expand:.1f}ms, "
            f"total retrieve: {t_total:.1f}ms, final_docs={len(result)}"
        )

        # 8. V5: cross-encoder 重排序（可选）
        # 对 Hybrid 融合 + 父块回查后的 top_k 候选做精排，
        # 解决"双写一致排在缓存穿透方案前面"等 RRF 排序不准问题
        if self._rerank_enabled and result:
            result = await self._reranker.rerank(query, result, top_k=self._rerank_top_k)
            t_total = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[Retriever][Hybrid] After rerank, total retrieve: "
                f"{t_total:.1f}ms, final_docs={len(result)}"
            )
        return result

    async def _expand_to_parents(self, child_docs: list[Document]) -> list[Document]:
        """把子块 page_content 替换为父块全文（从 MySQL DocumentChunk.page_content 查）。

        - 收集子块的 parent_id（去重）
        - 批量 SELECT DocumentChunk WHERE id IN (parent_ids) → 拿父块 page_content
        - 拼装：父块内容 + 子块溯源 metadata
        - **同一父块只回查一次**：多个子块指向同一父块时，保留 distance 最小的子块
          作为溯源代表，避免重复父块灌入 Prompt（检查清单 P0-3）

        降级场景（检查清单 P0-4 告警）：
            - 无 db / 无 parent_id（V2 旧数据）→ 直接返回子块
            - 父块缺失（parent_id 在 MySQL 中查不到）→ 用子块，记 warning
            - 父块超长 → 截断到 max_parent_chars，记 warning
        """
        # 收集需要回查的 parent_id（已按 Milvus 返回顺序去重）
        parent_ids: list[str] = []
        seen: set[str] = set()
        for d in child_docs:
            pid = d.metadata.get("parent_id")
            if pid and pid not in seen:
                seen.add(pid)
                parent_ids.append(pid)

        # 无 parent_id（V2 旧数据）或无 db → 直接返回子块
        if not parent_ids or self._db is None:
            logger.info(
                f"[Retriever] No parent expansion "
                f"(parent_ids={len(parent_ids)}, db={'yes' if self._db else 'no'})"
            )
            return child_docs

        # 批量查 MySQL 拿父块全文（只取 id + page_content,避免 LONGTEXT 全字段加载）
        result = await self._db.execute(
            sa_select(DocumentChunk.id, DocumentChunk.page_content).where(
                DocumentChunk.id.in_(parent_ids)
            )
        )
        parent_map: dict[str, str] = {
            pid: content for pid, content in result.all() if content
        }
        missing_parents = [pid for pid in parent_ids if pid not in parent_map]
        logger.info(
            f"[Retriever] Parent lookup: requested={len(parent_ids)}, "
            f"found={len(parent_map)}, missing={len(missing_parents)}"
        )

        # 告警：父块回查失败比例过高（检查清单 P0-4 降级监控）
        if missing_parents:
            logger.warning(
                f"[Retriever] {len(missing_parents)}/{len(parent_ids)} parent chunks "
                f"not found in MySQL (orphans?): "
                f"{[p[:8] + '...' for p in missing_parents[:5]]}"
            )

        # 拼装最终结果：page_content=父块全文, metadata=子块溯源
        # V4-B P0-3：同一父块只回查一次，按 parent_chunk_id 去重
        # child_docs 已按 distance 升序返回，故首次命中即最相似子块
        final_docs: list[Document] = []
        used_parents: set[str] = set()
        fallback_count = 0
        truncated_count = 0

        for child in child_docs:
            pid = child.metadata.get("parent_id")
            parent_content = parent_map.get(pid) if pid else None

            if parent_content:
                # 同一父块已被更相似的子块占用 → 跳过（去重）
                if pid in used_parents:
                    continue
                used_parents.add(pid)

                # V4-B P0-4：父块长度限制（防止异常父块撑爆 LLM 上下文窗口）
                truncated_content = parent_content
                if self._max_parent_chars and len(parent_content) > self._max_parent_chars:
                    logger.warning(
                        f"[Retriever] Parent chunk {pid[:8]}... exceeds "
                        f"max_parent_chars ({len(parent_content)} > "
                        f"{self._max_parent_chars}), truncating"
                    )
                    truncated_content = parent_content[:self._max_parent_chars]
                    truncated_count += 1

                # 父块回查成功 → 用父块全文替换子块内容
                merged_meta = dict(child.metadata)
                merged_meta["parent_chunk_id"] = pid
                merged_meta["is_parent"] = False  # 标记这是回查后的检索结果
                merged_meta["parent_truncated"] = (
                    len(parent_content) > len(truncated_content)
                )
                final_docs.append(Document(
                    page_content=truncated_content,
                    metadata=merged_meta,
                ))
            else:
                # V2 旧数据（parent_id 为空）或父块缺失 → 降级用子块
                # Hybrid 模式下伪子块 page_content 为空串，跳过避免污染结果
                if not child.page_content.strip():
                    continue
                fallback_count += 1
                final_docs.append(child)

        # 降级告警（检查清单 P0-4：父块回查失败时告警，避免静默用子块产生隐性幻觉）
        if fallback_count > 0:
            logger.warning(
                f"[Retriever] {fallback_count}/{len(child_docs)} chunks fell back "
                f"to child content (parent missing or V2 legacy data) - "
                f"answers may rely on narrow context, monitor for hallucination"
            )
        if truncated_count > 0:
            logger.warning(
                f"[Retriever] {truncated_count} parent chunks truncated "
                f"due to length limit (max_parent_chars={self._max_parent_chars})"
            )

        expanded = sum(1 for d in final_docs if d.metadata.get("parent_chunk_id"))
        deduped = len(child_docs) - len(final_docs)
        logger.info(
            f"[Retriever] Expanded {expanded}/{len(final_docs)} docs to parent content "
            f"(deduped {deduped} duplicate children, fallback {fallback_count})"
        )
        return final_docs
