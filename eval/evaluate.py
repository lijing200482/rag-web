# -*- coding: utf-8 -*-
"""RAG 检索层 MVP 评估脚本。

评估指标：
    - Hit@K:     top_k 内是否有至少 1 个相关父块（0/1）
    - MRR@K:     1 / 第一个相关父块排名（无相关=0）
    - Recall@K:  命中相关父块数 / MySQL 中总相关父块数
    - Precision@K: 命中相关父块数 / K

相关性判定：
    父块 page_content 包含所有 expected_keywords 即视为相关（AND 逻辑）
    反例 case（keywords=["__none__"]）：不应召回任何"相关"文档

用法：
    # 跑当前方案（V5-b: Hybrid + Reranker）默认
    .venv\\Scripts\\python.exe eval\\evaluate.py

    # 关闭 Reranker 跑 V5-a
    .venv\\Scripts\\python.exe eval\\evaluate.py --no-rerank

    # 关闭 Hybrid 跑纯向量
    .venv\\Scripts\\python.exe eval\\evaluate.py --no-hybrid

    # 自定义 top_k
    .venv\\Scripts\\python.exe eval\\evaluate.py --top-k 6
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from backend.db.database import async_session
from backend.core.config import get_settings
from backend.vectorstore.milvus_store import MilvusVectorStore
from backend.ingestion.embedder import get_embedding_provider
from backend.retrieval.retriever import Retriever
from backend.retrieval.bm25_retriever import BM25Retriever
from backend.retrieval.reranker import Reranker

KB_ID = 1
EVAL_SET_PATH = Path(__file__).parent / "eval_set.jsonl"


def load_eval_set() -> list[dict]:
    cases = []
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def is_relevant(doc, keywords: list[str]) -> bool:
    """判定父块是否相关：page_content 包含所有 expected_keywords（AND）。"""
    if keywords == ["__none__"]:
        return False
    content = (doc.page_content or "").lower()
    return all(kw.lower() in content for kw in keywords)


async def count_relevant_in_db(db, keywords: list[str]) -> int:
    """查 MySQL 中包含所有 keywords 的父块数（ground truth 总数）。"""
    if keywords == ["__none__"]:
        return 0
    sql = "SELECT COUNT(*) FROM document_chunks WHERE is_parent = 1"
    for kw in keywords:
        # 转义单引号防注入（keywords 是我们自己标的，但仍保险）
        safe_kw = kw.replace("'", "''")
        sql += f" AND LOWER(page_content) LIKE '%{safe_kw.lower()}%'"
    r = await db.execute(text(sql))
    return r.scalar() or 0


async def eval_one(retriever, case: dict, db, top_k: int) -> dict:
    query = case["query"]
    keywords = case["expected_keywords"]
    is_negative = keywords == ["__none__"]

    docs = await retriever.retrieve(query, top_k=top_k, kb_ids=[KB_ID])

    hits = [is_relevant(d, keywords) for d in docs]
    hit_at_k = 1 if any(hits) else 0
    mrr = 0.0
    for i, h in enumerate(hits, 1):
        if h:
            mrr = 1.0 / i
            break

    total_relevant = await count_relevant_in_db(db, keywords)
    hits_count = sum(hits)
    recall = hits_count / total_relevant if total_relevant > 0 else 0.0
    precision = hits_count / len(docs) if docs else 0.0

    return {
        "query": query,
        "is_negative": is_negative,
        "hit_at_k": hit_at_k,
        "mrr": mrr,
        "recall": recall,
        "precision": precision,
        "total_relevant_in_db": total_relevant,
        "hits_count": hits_count,
        "retrieved_count": len(docs),
        "retrieved_previews": [
            {
                "rank": i + 1,
                "relevant": h,
                "preview": (d.page_content or "")[:60].replace("\n", " "),
                "rrf_score": d.metadata.get("rrf_score"),
                "rerank_score": d.metadata.get("rerank_score"),
                "hit_source": d.metadata.get("hit_source"),
            }
            for i, (d, h) in enumerate(zip(docs, hits))
        ],
    }


def print_case_result(case_result: dict):
    q = case_result["query"]
    if case_result["is_negative"]:
        # 反例：hit_at_k=1 是坏的（误召回）
        status = "❌ 误召回" if case_result["hit_at_k"] else "✅ 正确不召回"
        print(f"  [反例] {q}")
        print(f"         {status} (retrieved={case_result['retrieved_count']})")
        return
    print(f"  {q}")
    print(
        f"    Hit@K={case_result['hit_at_k']} "
        f"MRR={case_result['mrr']:.3f} "
        f"Recall={case_result['recall']:.3f} "
        f"({case_result['hits_count']}/{case_result['total_relevant_in_db']}) "
        f"Precision={case_result['precision']:.3f}"
    )
    for p in case_result["retrieved_previews"][:3]:
        mark = "✓" if p["relevant"] else " "
        rrf = f"{p['rrf_score']:.4f}" if p["rrf_score"] else "-"
        rerank = f"{p['rerank_score']:.2f}" if p.get("rerank_score") else "-"
        src = p["hit_source"] or "-"
        print(f"      [{p['rank']}] {mark} rrf={rrf} rerank={rerank} src={src}")
        print(f"          {p['preview']}...")


def print_summary(results: list[dict], tag: str):
    # 正向 case
    pos = [r for r in results if not r["is_negative"]]
    neg = [r for r in results if r["is_negative"]]

    if pos:
        avg_hit = sum(r["hit_at_k"] for r in pos) / len(pos)
        avg_mrr = sum(r["mrr"] for r in pos) / len(pos)
        avg_recall = sum(r["recall"] for r in pos) / len(pos)
        avg_precision = sum(r["precision"] for r in pos) / len(pos)
    else:
        avg_hit = avg_mrr = avg_recall = avg_precision = 0

    # 反例：误召回率（hit_at_k=1 算误召回）
    false_recall_rate = sum(r["hit_at_k"] for r in neg) / len(neg) if neg else 0

    print(f"\n{'='*70}")
    print(f"【汇总：{tag}】")
    print(f"{'='*70}")
    print(f"正向 case 数: {len(pos)}")
    print(f"  Hit@K        = {avg_hit:.3f}  (top_k 内至少命中 1 个相关)")
    print(f"  MRR@K        = {avg_mrr:.3f}  (第一个相关父块的排名倒数)")
    print(f"  Recall@K     = {avg_recall:.3f}  (命中相关 / 总相关)")
    print(f"  Precision@K  = {avg_precision:.3f}  (命中相关 / K)")
    if neg:
        print(f"反例 case 数: {len(neg)}")
        print(f"  误召回率     = {false_recall_rate:.3f}  (越低越好，0=不误召回)")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-hybrid", action="store_true", help="关闭 Hybrid（跑纯向量）")
    parser.add_argument("--no-rerank", action="store_true", help="关闭 Reranker")
    parser.add_argument("--top-k", type=int, default=4, help="top_k (默认 4)")
    args = parser.parse_args()

    hybrid = not args.no_hybrid
    rerank = not args.no_rerank
    top_k = args.top_k

    # 方案标签
    parts = []
    parts.append("Hybrid" if hybrid else "PureVector")
    parts.append("+Rerank" if rerank else "")
    tag = " + ".join(p for p in parts if p) + f" (top_k={top_k})"

    print("=" * 70)
    print(f"【RAG 检索评估 MVP】方案：{tag}")
    print("=" * 70)

    settings = get_settings()
    store = MilvusVectorStore(settings)
    embedder = get_embedding_provider(settings).get_embedder()
    reranker = Reranker(
        model_name=settings.rerank_model,
        max_length=settings.rerank_max_length,
    ) if (rerank and settings.rerank_enabled) else None

    cases = load_eval_set()
    print(f"加载评测集: {len(cases)} 条\n")

    results = []
    async with async_session() as db:
        retriever = Retriever(
            store, embedder,
            top_k=top_k,
            db=db,
            max_parent_chars=settings.max_parent_chars,
            bm25_retriever=BM25Retriever(db) if hybrid else None,
            hybrid_search_enabled=hybrid,
            hybrid_rrf_k=settings.hybrid_rrf_k,
            hybrid_vector_top_k=settings.hybrid_vector_top_k,
            hybrid_bm25_top_k=settings.hybrid_bm25_top_k,
            reranker=reranker,
            rerank_enabled=reranker is not None,
            rerank_top_k=settings.rerank_top_k,
        )

        print("【逐条结果】")
        for i, case in enumerate(cases, 1):
            print(f"\n[{i}/{len(cases)}]")
            r = await eval_one(retriever, case, db, top_k)
            results.append(r)
            print_case_result(r)

    store.close()
    print_summary(results, tag)


if __name__ == "__main__":
    asyncio.run(main())
