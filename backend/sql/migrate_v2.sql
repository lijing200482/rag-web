-- ============================================================
-- RAG 系统 V2 数据模型迁移脚本
-- 
-- 目标：
--   1. 新建表：knowledge_bases / documents / document_chunks
--              document_uploads / processing_tasks / api_keys
--              chat_knowledge_bases
--   2. 迁移旧表：chat_sessions → chats
--   3. 迁移旧表：chat_messages → messages（结构调整）
--
-- 使用：mysql -u root -p rag < backend/sql/migrate_v2.sql
-- ============================================================

-- ====================
-- 1. 新建知识库相关表
-- ====================

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255)    NOT NULL,
    description LONGTEXT        NULL,
    user_id     INT             NOT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_kb_user (user_id),
    CONSTRAINT fk_kb_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS documents (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    file_path       VARCHAR(255)    NOT NULL,
    file_name       VARCHAR(255)    NOT NULL,
    file_size       BIGINT          NOT NULL,
    content_type    VARCHAR(100)    NOT NULL,
    file_hash       VARCHAR(64)     NULL,
    knowledge_base_id INT           NOT NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_doc_kb (knowledge_base_id),
    INDEX idx_doc_hash (file_hash),
    CONSTRAINT fk_doc_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT uq_kb_file_name UNIQUE (knowledge_base_id, file_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_chunks (
    id              VARCHAR(64)     NOT NULL PRIMARY KEY COMMENT 'SHA-256 哈希作主键',
    kb_id           INT             NOT NULL,
    document_id     INT             NOT NULL,
    file_name       VARCHAR(255)    NOT NULL,
    chunk_metadata  JSON            NULL,
    hash            VARCHAR(64)     NOT NULL COMMENT '内容哈希，用于增量更新检测',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chunk_kb (kb_id),
    INDEX idx_chunk_doc (document_id),
    INDEX idx_chunk_hash (hash),
    CONSTRAINT fk_chunk_kb FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT fk_chunk_doc FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS document_uploads (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id INT           NOT NULL,
    file_name       VARCHAR(255)    NOT NULL,
    file_hash       VARCHAR(64)     NOT NULL,
    file_size       BIGINT          NOT NULL,
    content_type    VARCHAR(100)    NOT NULL,
    temp_path       VARCHAR(255)    NULL,
    status          VARCHAR(50)     NOT NULL DEFAULT 'pending' COMMENT 'pending / completed / failed',
    error_message   TEXT            NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_up_kb (knowledge_base_id),
    CONSTRAINT fk_up_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS processing_tasks (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    knowledge_base_id INT           NOT NULL,
    document_id     INT             NULL,
    document_upload_id INT          NULL,
    status          VARCHAR(50)     NOT NULL DEFAULT 'pending' COMMENT 'pending / processing / completed / failed',
    error_message   TEXT            NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_task_kb (knowledge_base_id),
    CONSTRAINT fk_task_kb FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    CONSTRAINT fk_task_doc FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL,
    CONSTRAINT fk_task_upload FOREIGN KEY (document_upload_id) REFERENCES document_uploads(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ====================
-- 2. 新建 API 密钥表
-- ====================

CREATE TABLE IF NOT EXISTS api_keys (
    id              INT             AUTO_INCREMENT PRIMARY KEY,
    key             VARCHAR(255)    NOT NULL,
    name            VARCHAR(255)    NOT NULL,
    user_id         INT             NOT NULL,
    is_active       TINYINT(1)      NOT NULL DEFAULT 1,
    last_used_at    DATETIME        NULL,
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ak_user (user_id),
    CONSTRAINT fk_ak_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ====================
-- 3. 迁移旧对话表 → 新结构
-- ====================

-- 3a. chat_sessions → chats（兼容重命名）
RENAME TABLE chat_sessions TO chats;

-- 3b. 新建 messages 表（含 LONGTEXT 支持大对话）
CREATE TABLE IF NOT EXISTS messages (
    id          INT             AUTO_INCREMENT PRIMARY KEY,
    content     LONGTEXT        NOT NULL COMMENT 'LONGTEXT 支持长 AI 回复',
    role        VARCHAR(50)     NOT NULL COMMENT 'user / assistant',
    chat_id     INT             NOT NULL,
    created_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_msg_chat (chat_id),
    CONSTRAINT fk_msg_chat FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3c. 从旧 chat_messages 复制数据到 messages
INSERT INTO messages (id, content, role, chat_id, created_at, updated_at)
SELECT cm.id, cm.content, cm.role, cm.session_id, cm.created_at, NOW()
FROM chat_messages cm;

-- 3d. 删除旧表
DROP TABLE IF EXISTS chat_messages;

-- ====================
-- 4. 新建多对多中间表
-- ====================

CREATE TABLE IF NOT EXISTS chat_knowledge_bases (
    chat_id             INT     NOT NULL,
    knowledge_base_id   INT     NOT NULL,
    PRIMARY KEY (chat_id, knowledge_base_id),
    CONSTRAINT fk_ckb_chat FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    CONSTRAINT fk_ckb_kb   FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 完成
-- ============================================================
SELECT 'Migration completed successfully' AS status;
