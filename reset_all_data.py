"""开发环境清空脚本：清空所有 RAG 业务数据，保留用户账号。

清理范围：
    1. MySQL   → TRUNCATE 业务表（保留 users / api_keys）
    2. Milvus  → drop collection（下次启动服务自动重建空 collection）
    3. MinIO   → 清空 bucket 所有对象
    4. Redis   → FLUSHDB 清空对话缓存

使用方式：
    python reset_all_data.py           # 交互式确认
    python reset_all_data.py --force   # 跳过确认（CI/脚本调用）

幂等：可重复执行，已空的数据不会报错。
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.core.config import get_settings
from backend.storage.minio_storage import MinIOStorage
from backend.cache.redis_client import get_redis


# MySQL 业务表清单（按外键依赖叶子→根排序，TRUNCATE 顺序）
# 保留：users, api_keys
BUSINESS_TABLES = [
    "messages",                # → chats
    "chat_knowledge_bases",    # → chats, knowledge_bases（中间表）
    "document_chunks",         # → documents, knowledge_bases
    "processing_tasks",        # → documents, document_uploads, knowledge_bases
    "document_uploads",        # → knowledge_bases
    "documents",               # → knowledge_bases
    "chats",                   # → users
    "knowledge_bases",         # → users
]


async def clear_mysql(settings) -> None:
    """禁用外键检查 → TRUNCATE 业务表 → 重新启用外键检查。"""
    print("\n[1/4] 清空 MySQL 业务表（保留 users / api_keys）...")
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.begin() as conn:
            # 禁用外键检查，避免 TRUNCATE 顺序问题
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            for table in BUSINESS_TABLES:
                result = await conn.execute(text(f"TRUNCATE TABLE `{table}`"))
                print(f"  ✓ TRUNCATE {table}")
            await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        # 校验
        async with engine.connect() as conn:
            for table in BUSINESS_TABLES:
                r = await conn.execute(text(f"SELECT COUNT(*) FROM `{table}`"))
                count = r.scalar()
                if count != 0:
                    print(f"  ⚠ {table} 仍有 {count} 行（外键约束未禁用？）")
        print("  ✓ MySQL 清空完成")
    finally:
        await engine.dispose()


async def clear_milvus(settings) -> None:
    """drop collection（下次启动服务时 _ensure_collection 会自动重建空表）。"""
    print("\n[2/4] 清空 Milvus collection...")
    from pymilvus import MilvusClient

    client = MilvusClient(settings.milvus_uri)
    collection = settings.milvus_collection
    try:
        if client.has_collection(collection):
            # 先查行数
            stats = client.get_collection_stats(collection)
            row_count = stats.get("row_count", 0) if isinstance(stats, dict) else 0
            client.drop_collection(collection)
            print(f"  ✓ Dropped collection '{collection}' (had ~{row_count} rows)")
        else:
            print(f"  ✓ Collection '{collection}' not exists (already clean)")
    finally:
        client.close()


async def clear_minio(settings) -> None:
    """清空 MinIO bucket 所有对象（bucket 本身保留）。"""
    print("\n[3/4] 清空 MinIO bucket...")
    storage = MinIOStorage(settings)
    try:
        # delete_by_prefix("") 会匹配所有对象
        deleted = await storage.delete_by_prefix("")
        print(f"  ✓ Deleted {deleted} objects from bucket '{settings.minio_bucket}'")
    except Exception as e:
        print(f"  ⚠ MinIO 清空失败: {e}")
        print("    （可手动用 mc rm --recursive minio/rag-documents 清理）")


async def clear_redis(settings) -> None:
    """FLUSHDB 清空当前 Redis db（对话缓存）。"""
    print("\n[4/4] 清空 Redis 对话缓存...")
    try:
        redis = await get_redis()
        if redis is None:
            print("  ⚠ Redis 未连接（跳过）")
            return
        await redis.flushdb()
        print(f"  ✓ FLUSHDB executed (db=0)")
    except Exception as e:
        print(f"  ⚠ Redis 清空失败: {e}")


async def main(force: bool = False) -> None:
    settings = get_settings()
    print("=" * 60)
    print("RAG 开发环境数据清空脚本")
    print("=" * 60)
    print(f"MySQL:   {settings.database_url}")
    print(f"Milvus:  {settings.milvus_uri} (collection={settings.milvus_collection})")
    print(f"MinIO:   {settings.minio_endpoint} (bucket={settings.minio_bucket})")
    print(f"Redis:   {settings.redis_url}")
    print("-" * 60)
    print("将清空: messages, chat_knowledge_bases, document_chunks, ")
    print("        processing_tasks, document_uploads, documents, chats, knowledge_bases")
    print("保留:   users, api_keys")
    print("=" * 60)

    if not force:
        confirm = input("\n确认清空所有业务数据？输入 'yes' 继续: ").strip().lower()
        if confirm != "yes":
            print("已取消")
            return

    await clear_mysql(settings)
    await clear_milvus(settings)
    await clear_minio(settings)
    await clear_redis(settings)

    print("\n" + "=" * 60)
    print("✓ 全部清空完成")
    print("=" * 60)
    print("下一步：重启 uvicorn 服务，Milvus collection 会自动重建")
    print("       然后重新上传文档测试")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清空 RAG 开发环境数据")
    parser.add_argument("--force", action="store_true", help="跳过确认提示")
    args = parser.parse_args()

    try:
        asyncio.run(main(force=args.force))
    except KeyboardInterrupt:
        print("\n已中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 执行失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
