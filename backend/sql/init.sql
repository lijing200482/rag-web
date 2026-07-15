-- ============================================================
-- RAG 系统数据库初始化脚本
-- 数据库名: rag
-- 执行方式: mysql -u root -p < backend/sql/init.sql
-- 或在 MySQL 客户端中直接 source 本文件
--
-- 表结构对应 backend/app/models/ 中的 ORM 模型定义。
-- ============================================================

CREATE DATABASE IF NOT EXISTS rag
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE rag;

-- ------------------------------------------------------------
-- 用户表 (对应 User 模型)
-- 注：列名 hashed_pwd，ORM 属性 hashed_password 映射到此列
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    email        VARCHAR(255) UNIQUE NOT NULL,
    username     VARCHAR(255) UNIQUE NOT NULL,
    hashed_pwd   VARCHAR(255) NOT NULL,
    is_active    TINYINT(1) DEFAULT 1,
    is_superuser TINYINT(1) DEFAULT 0,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_users_email (email),
    INDEX idx_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- API 密钥表 (对应 APIKey 模型)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    `key`        VARCHAR(255) NOT NULL,
    name         VARCHAR(255) NOT NULL,
    user_id      INT NOT NULL,
    is_active    TINYINT(1) DEFAULT 1,
    last_used_at DATETIME NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_api_keys_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 知识库表 (对应 KnowledgeBase 模型)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description LONGTEXT NULL,
    user_id     INT NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_kb_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 文档表 (对应 Document 模型)
-- 联合唯一约束：(knowledge_base_id, file_name) → 同一知识库内文件名不重复
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    file_path         VARCHAR(255) NOT NULL,
    file_name         VARCHAR(255) NOT NULL,
    file_size         BIGINT NOT NULL,
    content_type      VARCHAR(100) NOT NULL,
    file_hash         VARCHAR(64) NULL,
    knowledge_base_id INT NOT NULL,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_documents_file_hash (file_hash),
    INDEX idx_documents_kb_id (knowledge_base_id),
    UNIQUE INDEX uq_kb_file_name (knowledge_base_id, file_name),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 文档块表 (对应 DocumentChunk 模型)
-- id = SHA-256(kb_id:file_name:chunk_content)，相同内容自动去重
-- hash 用于增量更新时判断块是否变化
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_chunks (
    id              VARCHAR(64) PRIMARY KEY,
    kb_id           INT NOT NULL,
    document_id     INT NOT NULL,
    file_name       VARCHAR(255) NOT NULL,
    chunk_metadata  JSON NULL,
    hash            VARCHAR(64) NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chunks_hash (hash),
    INDEX idx_chunks_kb_id (kb_id),
    INDEX idx_chunks_document_id (document_id),
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 文档上传记录表 (对应 DocumentUpload 模型)
-- 状态机：pending → completed / failed
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_uploads (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id INT NOT NULL,
    file_name         VARCHAR(255) NOT NULL,
    file_hash         VARCHAR(64) NOT NULL,
    file_size         BIGINT NOT NULL,
    content_type      VARCHAR(100) NOT NULL,
    temp_path         VARCHAR(255) NULL,
    status            VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message     TEXT NULL,
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_uploads_kb_id (knowledge_base_id),
    INDEX idx_uploads_status (status),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 文档处理任务表 (对应 ProcessingTask 模型)
-- 状态机：pending → processing → completed / failed
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processing_tasks (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id  INT NOT NULL,
    document_id        INT NULL,
    document_upload_id INT NULL,
    status             VARCHAR(50) NOT NULL DEFAULT 'pending',
    error_message      TEXT NULL,
    created_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_tasks_kb_id (knowledge_base_id),
    INDEX idx_tasks_document_id (document_id),
    INDEX idx_tasks_status (status),
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL,
    FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 对话表 (对应 Chat 模型)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chats (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    title      VARCHAR(255) NOT NULL,
    user_id    INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chats_user_id (user_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 消息表 (对应 Message 模型)
-- LONGTEXT 容纳可能很长的 AI 回复
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    content    LONGTEXT NOT NULL,
    role       VARCHAR(50) NOT NULL,          -- user / assistant
    chat_id    INT NOT NULL,
    sources    JSON NULL,                     -- assistant 消息的引用来源
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_messages_chat_id (chat_id),
    -- 复合索引：游标分页/最近 N 条查询按 chat_id 过滤 + id DESC 排序
    INDEX idx_msg_chat_id_desc (chat_id, id DESC),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- 对话-知识库多对多中间表 (对应 chat_knowledge_bases Table)
-- 一个对话可选多个知识库，灵活组合
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_knowledge_bases (
    chat_id           INT NOT NULL,
    knowledge_base_id INT NOT NULL,
    PRIMARY KEY (chat_id, knowledge_base_id),
    INDEX idx_ckb_kb_id (knowledge_base_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- API Key 表：重命名 key 列为 key_hash，新增 key_prefix
ALTER TABLE api_keys CHANGE COLUMN `key` key_hash VARCHAR(64) NOT NULL;
ALTER TABLE api_keys ADD COLUMN key_prefix VARCHAR(8) AFTER key_hash;

-- messages 表：复合索引
CREATE INDEX idx_msg_chat_id_desc ON messages (chat_id, id DESC);

ALTER TABLE messages ADD COLUMN sources JSON NULL AFTER chat_id;