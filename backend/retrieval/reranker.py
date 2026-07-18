"""Cross-encoder 重排序器 —— RAG 二阶段精排。

设计目标：
    解决 bi-encoder（bge-m3 召回）的排序不准问题。
    bi-encoder 把 query 和 doc 分别编码后做点积，丢失了 query-doc 交互信息；
    cross-encoder 把 (query, doc) 拼接输入 transformer，做完整 attention 交互，
    精度显著高于 bi-encoder，但计算成本高（每候选一次 forward）。

    典型两阶段 RAG 架构：
        召回（bi-encoder, 快但糙, 20 候选）
            ↓
        融合（RRF, 兜底字面匹配）
            ↓
        精排（cross-encoder, 慢但准, 4 候选）  ← 本模块
            ↓
        生成（LLM）

架构选择：
    - 用 BAAI/bge-reranker-v2-m3（与 bge-m3 同源，XLMRoberta 架构，多语言 SOTA）
    - 直接用 transformers AutoModelForSequenceClassification 加载，不引入 FlagEmbedding
    - 模型类级共享（_model），避免每次请求重复加载 ~2GB 模型
    - CPU 推理（cross-encoder 没法走 Ollama），4 候选约 200-500ms

为什么不用 Ollama：
    Ollama 主要做 causal LLM 和 embedding（bi-encoder），不支持 cross-encoder 类型模型。
    Reranker 必须用 transformers 直接加载。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder 重排序器。

    使用：
        reranker = Reranker(model_name="BAAI/bge-reranker-v2-m3")
        docs = await reranker.rerank(query, docs, top_k=4)

    模型加载：
        - 首次调用 rerank() 时加载（懒加载，避免服务启动慢）
        - 类级共享 _model / _tokenizer，跨请求/跨实例复用
        - 加载失败（如离线无缓存）会被 _load_failed 标记，rerank 直接返回原顺序

    推理：
        - CPU 推理（torch.float32）
        - 同步调用包在 run_in_executor 中，避免阻塞事件循环
        - batch 化：把所有候选一次性 forward
    """

    # 类级共享：跨请求/跨实例复用模型，避免重复加载 ~2GB
    _model: Any = None
    _tokenizer: Any = None
    _loaded_model_name: str | None = None
    _load_failed: bool = False

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        max_length: int = 512,
    ):
        self._model_name = model_name
        self._max_length = max_length

    def _ensure_model(self) -> bool:
        """懒加载模型（首次调用时加载）。返回是否可用。"""
        if self._load_failed:
            return False
        if self._model is not None and self._tokenizer is not None:
            return True
        if self._loaded_model_name == self._model_name and self._load_failed:
            return False

        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            t0 = time.perf_counter()
            logger.info(f"[Reranker] Loading model: {self._model_name} ...")
            # local_files_only=True: 跳过 HF Hub 联网检查，直接用本地缓存
            # 不加这个参数，transformers 会尝试联网检查模型版本，
            # 网络不通时会重试很久（首次请求卡几分钟的元凶）
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_name, local_files_only=True,
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self._model_name,
                torch_dtype=torch.float32,  # CPU 推理用 FP32
                local_files_only=True,
            )
            self._model.eval()
            self._loaded_model_name = self._model_name
            load_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[Reranker] Model loaded: {self._model_name}, "
                f"load_time={load_ms:.0f}ms"
            )
            return True
        except Exception as e:
            logger.error(
                f"[Reranker] Failed to load model {self._model_name}: {e}",
                exc_info=True,
            )
            self._load_failed = True
            return False

    def _rerank_sync(self, query: str, docs: list[Document]) -> list[tuple[int, float]]:
        """同步重排序：返回 [(原索引, 相关性分数), ...] 按分数降序。"""
        import torch

        if not docs:
            return []

        # 构造 (query, doc) pairs
        pairs = [[query, d.page_content] for d in docs]
        with torch.no_grad():
            inputs = self._tokenizer(
                pairs,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=self._max_length,
            )
            # cross-encoder 输出 logits shape=(batch, 1)，取标量分数
            scores = self._model(**inputs, return_dict=True).logits.view(-1).float()

        # 返回 [(原索引, 分数), ...] 按分数降序
        scored = [(i, float(scores[i])) for i in range(len(docs))]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    async def rerank(
        self,
        query: str,
        docs: list[Document],
        top_k: int | None = None,
    ) -> list[Document]:
        """对候选文档做 cross-encoder 精排。

        Args:
            query: 用户问题
            docs: 召回阶段返回的候选文档（已做父块回查，page_content 为父块全文）
            top_k: 精排后保留的文档数，None 表示保留全部

        Returns:
            重排后的文档列表（按相关性降序），metadata 新增 rerank_score 字段
            若模型加载失败或 docs 为空，返回原 docs（降级为不重排）
        """
        if not docs:
            return docs

        # 模型不可用 → 降级返回原顺序
        if not self._ensure_model():
            logger.warning(
                f"[Reranker] Model unavailable, skip rerank "
                f"(returning {len(docs)} docs in original order)"
            )
            return docs

        # CPU 推理放线程池，避免阻塞事件循环
        t0 = time.perf_counter()
        loop = asyncio.get_event_loop()
        try:
            scored = await loop.run_in_executor(None, self._rerank_sync, query, docs)
        except Exception as e:
            logger.error(f"[Reranker] rerank failed: {e}", exc_info=True)
            return docs  # 失败降级

        rerank_ms = (time.perf_counter() - t0) * 1000

        # 取 top_k
        if top_k is not None and top_k > 0:
            scored = scored[:top_k]

        # 拼装结果：原 Document + rerank_score 元数据
        result: list[Document] = []
        for rank, (orig_idx, score) in enumerate(scored):
            doc = docs[orig_idx]
            merged_meta = dict(doc.metadata)
            merged_meta["rerank_score"] = score
            merged_meta["rerank_rank"] = rank  # 0-based
            result.append(Document(page_content=doc.page_content, metadata=merged_meta))

        logger.info(
            f"[Reranker] Rerank done: query={query!r}, "
            f"candidates={len(docs)}, kept={len(result)}, "
            f"time={rerank_ms:.0f}ms, "
            f"top_scores={[f'{s:.3f}' for _, s in scored[:3]]}"
        )
        if logger.isEnabledFor(logging.DEBUG):
            for rank, (orig_idx, score) in enumerate(scored[:5]):
                src = docs[orig_idx].metadata.get("source", "?")
                logger.debug(
                    f"[Reranker]   rank[{rank}] score={score:.3f} "
                    f"orig_idx={orig_idx} source={src}"
                )
        return result
