from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # ChromaDB
    chroma_persist_dir: str = "chroma_db"
    chroma_collection: str = "rag_collection"

    # Embedding 提供者: "local", "openai", 或 "ollama"
    embedding_provider: Literal["local", "openai", "ollama"] = "ollama"
    embedding_model: str = "nomic-embed-text"
    openai_embedding_model: str = "text-embedding-ada-002"
    ollama_base_url: str = "http://localhost:11434"

    # LLM 提供者: "openai", "openai-compatible", "anthropic", "ollama"
    llm_provider: str = "openai-compatible"
    llm_model: str = "step-3.7-flash"
    openai_api_key: str = ""
    openai_base_url: str = ""

    # 分块参数
    chunk_size: int = 500
    chunk_overlap: int = 50

    # 检索参数
    top_k: int = 4
    # 相似度分数阈值（cosine distance，越小越相似）
    # 超过此阈值的文档视为不相关并过滤掉。0=完全相同，2=完全相反。
    # 设为 None 则禁用过滤（返回 top_k 结果不论相关度）
    similarity_threshold: float | None = 0.5

    # 对话记忆窗口：注入 prompt 的最近消息条数
    memory_window: int = 10

    # 文档上传目录
    documents_dir: str = "documents"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # 数据库 (MySQL, 库名 rag)
    database_url: str = "mysql+aiomysql://root:root@localhost:3306/rag"

    # CORS 白名单（逗号分隔，例如 "http://localhost:5173,http://localhost:3000"）
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"

    # ===== Redis 对话缓存 =====
    # Redis 连接地址，格式: redis://[:password@]host:port/db
    # 强制使用 RESP2 协议（?protocol=2），避免 redis-py 6.x 默认发送 HELLO 3 命令
    # 兼容 Redis < 6.0 的老版本服务器
    redis_url: str = "redis://localhost:6379/0?protocol=2"
    # 对话缓存过期时间（秒），默认 30 分钟，过期后从 MySQL 回源
    redis_conversation_ttl: int = 1800
    # Redis 中每个会话最多保留的消息条数
    redis_conversation_max_messages: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def cors_origins_list(self) -> list[str]:
        """解析 CORS 白名单为列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """全局缓存 Settings 实例，避免每个请求都重新解析 .env。"""
    return Settings()
