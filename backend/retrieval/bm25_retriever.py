"""BM25 关键词检索器 —— Hybrid 检索的关键词召回分支。

设计目标：
    解决纯向量检索在中文场景下的召回盲区（如"缓存穿透"查询，nomic-embed-text
    会把字面含"缓存"但语义无关的标题子块排到 top_k 内，把真正讲解决方案的子块挤出）。

    V5 起已切换为 bge-m3（中文 SOTA），纯向量召回能力显著提升，
    但 BM25 仍保留作为关键词命中兜底（V5 后可考虑关闭或降权）。

    BM25 基于词频统计，对"查询词字面命中"敏感，与向量检索的"语义相似"互补。

架构选择：
    - 用 rank_bm25 库（纯 Python，无外部依赖）
    - 用 jieba 做中文分词（rank_bm25 默认按空格切分，对中文无效）
    - 索引在内存中构建，按 kb_id 维度缓存（每个知识库一个 BM25Okapi 实例）
    - V4-C：从 MySQL document_chunks 表加载子块（is_parent=0）的 page_content
      构建索引。子块 page_content 在 V4-B+ 改造时已存（不再为 NULL），
      BM25 在子块粒度索引，与向量检索路径对称。

V4-C 改造关键决策（为什么索引子块而非父块）：
    ① 与向量检索路径对称：两边都返回子块 → 按子块排名做 RRF 融合 → 统一回查父块
    ② 召回粒度精确：BM25 命中"缓存穿透"子块，而非整个讲 5 个知识点的父块
    ③ top_k 对称：向量 top_k=20 子块 vs BM25 top_k=20 子块，RRF rank 含义一致
    ④ 代码统一：复用 _expand_to_parents，无需独立的 _expand_parents_by_ids

缓存策略：
    - 首次查询时按 kb_id 集合加载子块并构建 BM25 索引
    - 缓存 key = tuple(sorted(kb_ids))，避免顺序差异导致重复构建
    - TTL 失效：文档新增/删除时需手动调 invalidate(kb_id) 清缓存
    - 内存占用估算：1 万个子块 × 平均 100 词 ≈ 10MB，可接受
"""
from __future__ import annotations

import logging
import time
from typing import Any

import jieba
import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from ..app.models.knowledge import DocumentChunk

logger = logging.getLogger(__name__)


def _tokenize_zh(text: str) -> list[str]:
    """中文分词：jieba 切词 + 过滤停用词和单字符噪声。

    rank_bm25 默认按空格切分，对中文无效，故用 jieba。
    过滤策略：
        - 去除纯标点和空白
        - 保留长度 >=2 的词（中文单字歧义大，但保留英文单字如 "RDB"）
        - 去除常见停用词（虚词、代词、连词）
        - **保留否定词**（不、没、没有、非）——否定词在中文语义中高度区分性，
          "不是缓存穿透" vs "是缓存穿透" 语义完全相反，去掉会损害 BM25 召回能力
    """
    if not text:
        return []
    tokens = jieba.lcut(text)
    # 停用词表：高频虚词/代词/连词，对 BM25 打分贡献低
    # 注意：否定词（不/没/没有/非）刻意保留，避免语义反转
    stop_words = {
        "的", "是", "了", "在", "和", "与", "也", "都", "而", "及",
        "但", "如果", "因为", "所以", "因此", "由于", "为了",
        "这", "那", "这个", "那个", "这些", "那些", "什么", "怎么", "如何",
        "可以", "能够", "应该", "需要", "必须",
        "一", "二", "三", "一个", "一些",
        "我", "你", "他", "她", "它", "我们", "你们", "他们",
        ":", "：", ",", "，", ".", "。", "!", "?", "！", "？",
        "(", ")", "（", "）", "[", "]", "【", "】",
        "-", "=", "+", "*", "/", "\\", "|", "&", "#", "@",
        "``", "`", "```", "---",
    }
    return [
        t for t in tokens
        if t.strip() and t not in stop_words and len(t.strip()) >= 2
        and not t.isspace()
    ]


class BM25Retriever:
    """基于子块文本的 BM25 关键词检索器。

    索引单位：子块（is_parent=0）的 page_content。
    返回单位：child_chunk_id 列表（按 BM25 分数降序）。

    为什么索引子块（V4-C 改造）：
        ① 与向量检索路径对称：两边都返回子块 → 按子块排名做 RRF 融合 → 统一回查父块
        ② 召回粒度精确：BM25 命中"缓存穿透"子块，而非整个讲 5 个知识点的父块
        ③ top_k 对称：向量 top_k=20 子块 vs BM25 top_k=20 子块，RRF rank 含义一致
        ④ 代码统一：复用 _expand_to_parents，无需独立的 _expand_parents_by_ids

    缓存策略：
        - 缓存为类级共享（_cache），跨请求/跨实例复用，避免每次请求重建索引
        - BM25Retriever 每次请求创建新实例（注入新 db session），但缓存不丢失
        - 文档新增/删除/更新时调 invalidate(kb_id) 清缓存
    """

    # 类级缓存：跨请求/跨实例共享
    # key=(kb_ids tuple) → (bm25_index, child_ids_list, parent_ids_list, file_names_list)
    _cache: dict[tuple[int, ...], tuple[BM25Okapi, list[str], list[str], list[str]]] = {}

    def __init__(self, db: AsyncSession):
        self._db = db

    async def _load_and_build(
        self, kb_ids: list[int] | None
    ) -> tuple[BM25Okapi, list[str], list[str], list[str]] | None:
        """从 MySQL 加载子块文本并构建 BM25 索引。

        Args:
            kb_ids: 知识库 ID 列表，None 表示全库（谨慎使用，可能很大）

        Returns:
            (bm25_index, child_ids, parent_ids, file_names) 或 None（无数据）
            child_ids[i] 对应的子块的父块 ID 是 parent_ids[i]，来源文件是 file_names[i]
        """
        # 查询子块的 id、parent_id、page_content、file_name
        # file_name 用于 BM25-only 命中时构造伪 Document 的 source 元数据，
        # 与向量命中路径保持一致（向量子块 metadata.source 就是 file_name）
        stmt = sa_select(
            DocumentChunk.id,
            DocumentChunk.parent_id,
            DocumentChunk.page_content,
            DocumentChunk.file_name,
        ).where(
            DocumentChunk.is_parent == False  # noqa: E712
        )
        if kb_ids:
            stmt = stmt.where(DocumentChunk.kb_id.in_(kb_ids))

        result = await self._db.execute(stmt)
        rows = result.all()

        if not rows:
            logger.info(f"[BM25] No child chunks found for kb_ids={kb_ids}")
            return None

        # 过滤掉 page_content 为空的记录
        valid_rows = [
            (r.id, r.parent_id, r.page_content, r.file_name)
            for r in rows if r.page_content
        ]
        if not valid_rows:
            logger.warning(f"[BM25] All child chunks have NULL page_content")
            return None

        child_ids = [r[0] for r in valid_rows]
        parent_ids = [r[1] for r in valid_rows]
        file_names = [r[3] for r in valid_rows]
        # 分词
        corpus_tokens = [_tokenize_zh(r[2]) for r in valid_rows]

        t0 = time.perf_counter()
        bm25 = BM25Okapi(corpus_tokens)
        build_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[BM25] Index built: {len(child_ids)} children, "
            f"kb_ids={kb_ids}, build_time={build_ms:.1f}ms"
        )
        return bm25, child_ids, parent_ids, file_names

    def _cache_key(self, kb_ids: list[int] | None) -> tuple[int, ...]:
        """生成缓存 key：排序后的 kb_ids 元组。None 表示全库。"""
        if kb_ids is None:
            return (-1,)  # 用 -1 表示全库
        return tuple(sorted(kb_ids))

    async def _get_index(
        self, kb_ids: list[int] | None
    ) -> tuple[BM25Okapi, list[str], list[str], list[str]] | None:
        """获取或构建 BM25 索引（带缓存）。"""
        key = self._cache_key(kb_ids)
        if key in self._cache:
            return self._cache[key]
        index_data = await self._load_and_build(kb_ids)
        if index_data is not None:
            self._cache[key] = index_data
        return index_data

    @classmethod
    def invalidate(cls, kb_id: int | None = None) -> None:
        """失效缓存。文档新增/删除/更新时调用。

        Args:
            kb_id: 指定知识库失效；None 表示清空所有缓存
        """
        if kb_id is None:
            n = len(cls._cache)
            cls._cache.clear()
            if n:
                logger.info(f"[BM25] Cache cleared: {n} entries removed")
        else:
            # 清除包含该 kb_id 的缓存条目
            keys_to_remove = [
                k for k in cls._cache
                if kb_id in k or k == (-1,)
            ]
            for k in keys_to_remove:
                del cls._cache[k]
            if keys_to_remove:
                logger.info(
                    f"[BM25] Cache invalidated for kb_id={kb_id}: "
                    f"{len(keys_to_remove)} entries removed"
                )

    async def search(
        self,
        query: str,
        top_k: int = 10,
        kb_ids: list[int] | None = None,
    ) -> list[tuple[str, str, float, str]]:
        """BM25 关键词检索。

        Args:
            query: 用户问题
            top_k: 返回前 K 个结果
            kb_ids: 知识库 ID 列表

        Returns:
            [(child_chunk_id, parent_chunk_id, bm25_score, file_name), ...]
            按 bm25_score 降序。file_name 用于 BM25-only 命中时构造伪 Document
            的 source 元数据，与向量命中路径保持一致。
        """
        t0 = time.perf_counter()
        index_data = await self._get_index(kb_ids)
        if index_data is None:
            logger.info(f"[BM25] No index available, returning empty")
            return []

        bm25, child_ids, parent_ids, file_names = index_data
        query_tokens = _tokenize_zh(query)
        if not query_tokens:
            logger.info(f"[BM25] Query tokenized to empty, returning empty")
            return []

        scores = bm25.get_scores(query_tokens)
        # 取 top_k：argsort 降序
        top_indices = np.argsort(scores)[::-1][:top_k]

        results: list[tuple[str, str, float, str]] = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:
                continue  # 过滤 0 分（完全不匹配）
            results.append((child_ids[idx], parent_ids[idx], score, file_names[idx]))

        search_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[BM25] Search done: query={query!r}, "
            f"tokens={query_tokens}, top_k={top_k}, "
            f"results={len(results)}, time={search_ms:.1f}ms"
        )
        if logger.isEnabledFor(logging.DEBUG):
            for i, (cid, pid, score, fname) in enumerate(results[:5]):
                logger.debug(
                    f"[BM25]   hit[{i}] score={score:.4f} "
                    f"child_id={cid[:12]}... parent_id={pid[:12]}... "
                    f"file={fname}"
                )
        return results
