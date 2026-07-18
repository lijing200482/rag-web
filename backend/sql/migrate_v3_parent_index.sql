-- ============================================================
-- RAG 系统 V3 迁移脚本 —— Small-to-Big 父子索引
--
-- 目标：
--   为 document_chunks 表新增两个字段，支持 V4 的 Small-to-Big 父子索引策略：
--     - is_parent (TINYINT(1)): 标记是父块(1)还是子块(0)
--     - parent_id (VARCHAR(64)): 子块指向父块的 chunk_id;父块本身为 NULL
--
-- 配套改动：
--   - backend/ingestion/splitter.py: 两级切分（父块800 + 子块200）
--   - backend/vectorstore/milvus_store.py: Milvus collection schema 同步加字段
--   - backend/app/models/knowledge.py: ORM 模型同步加字段
--
-- 注意：
--   1. 现有 V2 数据（无父子标记）is_parent 默认 0、parent_id 默认 NULL，
--      检索时按"V2 旧数据"分支处理（子块 parent_id 为空 → 直接返回子块自身）。
--   2. Milvus collection 因为 schema 变更必须 drop 重建，现有向量数据需重新入库。
--      重建步骤见 docs 中相关说明或调用：
--          from pymilvus import MilvusClient
--          c = MilvusClient(MILVUS_URI)
--          c.drop_collection("rag_collection")
--          # 重启服务后 _ensure_collection() 会按新 schema 自动重建
--
-- 使用：mysql -u root -p rag < backend/sql/migrate_v3_parent_index.sql
-- ============================================================

-- 1. 新增 is_parent 字段（默认 0 = 子块）
ALTER TABLE document_chunks
    ADD COLUMN is_parent TINYINT(1) NOT NULL DEFAULT 0
    COMMENT 'V4父子索引: 1=父块(用于生成), 0=子块(用于检索)'
    AFTER hash;

-- 2. 新增 parent_id 字段（父块为 NULL，子块指向父块 chunk_id）
ALTER TABLE document_chunks
    ADD COLUMN parent_id VARCHAR(64) NULL
    COMMENT 'V4父子索引: 子块指向父块chunk_id;父块为NULL'
    AFTER is_parent;

-- 3. 为父子字段建索引（加速过滤查询和父块回查）
CREATE INDEX idx_chunk_is_parent ON document_chunks(is_parent);
CREATE INDEX idx_chunk_parent_id ON document_chunks(parent_id);

-- ============================================================
-- 4. V4-B: 新增 page_content 字段（父块全文回查数据源）
--    父块不再存 Milvus,全文存本字段,检索时子块命中后从本字段回查父块
--    旧数据 page_content 设为空串(旧 chunk 全文在 Milvus,无需回查)
-- ============================================================
ALTER TABLE document_chunks
    ADD COLUMN page_content LONGTEXT NULL
    COMMENT 'V4-B: 块全文(父块回查数据源;子块也存便于排错)。MySQL不允许TEXT有DEFAULT,故nullable,应用层保证非空'
    AFTER parent_id;

-- ============================================================
-- 完成
-- ============================================================
SELECT 'V3 parent-index migration completed successfully' AS status;
