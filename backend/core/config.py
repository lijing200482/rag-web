from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # ===== 日志 =====
    # 日志级别: "DEBUG" / "INFO" / "WARNING" / "ERROR"
    # DEBUG 会打印切分结果、检索 distance、prompt 内容等详细链路信息
    log_level: str = "INFO"
    # 日志文件路径（相对项目根目录）；为空只输出到控制台
    log_file: str = "logs/rag.log"
    # 日志文件最大大小（MB），超过后轮转
    log_file_max_mb: int = 10
    # 保留的日志文件数量
    log_file_backup_count: int = 5

    # ===== Milvus =====
    # 部署模式: "lite"(本地文件，零外部依赖) 或 "standalone"(Docker)
    milvus_mode: Literal["lite", "standalone"] = "lite"
    # Milvus URI
    #   Lite 模式: "milvus.db"（本地文件路径，相对于项目根目录）
    #   Standalone 模式: "http://localhost:19530"
    milvus_uri: str = "milvus.db"
    # Collection 名称
    milvus_collection: str = "rag_collection"

    # Embedding 批量大小（V5 修复 12306 错误）
    # Ollama /api/embed 一次性接收大量文本时，内部 llama-server 子进程
    # tokenize 任务过重会无响应，主进程连接子进程端口失败返回 400。
    # 10MB PDF 可能切出几百到上千子块，必须分批 embed。
    # 默认 16：bge-m3 CPU 推理下单批 ~1-2 秒，平衡吞吐和子进程压力。
    embedding_batch_size: int = 16

    # Embedding 提供者: "local", "openai", 或 "ollama"
    # V5: 默认改为 bge-m3 (1024D, BAAI 中文 SOTA)，替代 nomic-embed-text (768D, 中文弱)
    embedding_provider: Literal["local", "openai", "ollama"] = "ollama"
    embedding_model: str = "bge-m3"
    openai_embedding_model: str = "text-embedding-ada-002"
    ollama_base_url: str = "http://localhost:11434"

    # LLM 提供者: "openai", "openai-compatible", "anthropic", "ollama"
    llm_provider: str = "openai-compatible"
    llm_model: str = "step-3.7-flash"
    openai_api_key: str = ""
    openai_base_url: str = ""

    # 分块参数
    # V4 起 Small-to-Big 父子索引：父块用于生成（喂 LLM），子块用于检索（embedding）。
    # 旧的单一 chunk_size/chunk_overlap 保留做向后兼容（旧数据迁移时使用），
    # 新数据走 parent/child 两级切分。
    #
    # V4-B+ 起：切分单位从"字符"改为"token"（用 tiktoken cl100k_base 编码），
    # 与 LLM 计费单位一致，避免中文 800字≈1300token 超出预期的问题。
    # 1 token ≈ 0.5-1 中文字符（cl100k_base 编码下）。
    chunk_size: int = 500
    chunk_overlap: int = 50
    # 父块 token 上限（喂 LLM 的完整语义单元，1024 token ≈ 700-1000 中文字符）
    # 业界典型值 1024（LlamaIndex 默认），够讲清一个完整主题
    parent_chunk_size: int = 1024
    # 子块 token 上限（embedding 检索用，256 token ≈ 150-200 中文字符）
    # 业界典型值 256，一个完整概念段落，向量表征聚焦且语义完整
    child_chunk_size: int = 256
    # 子块 token 重叠（避免父子边界切断语义，约为子块的 12%）
    child_chunk_overlap: int = 30
    # tiktoken 编码名称（cl100k_base = GPT-4/ChatGPT 编码，对中文近似合理）
    # step-3.7-flash 等国产模型无公开 tokenizer，用 cl100k_base 做近似计数。
    tiktoken_encoding: str = "cl100k_base"

    # 检索参数
    top_k: int = 4
    # 相似度分数阈值（Milvus COSINE distance = 1 - cosine_similarity，越小越相似）
    # V5: bge-m3 中文语义理解强，相关文档 distance 普遍在 0.1~0.4 之间，可设更严阈值。
    # 但 V5 暂保持 1.0（不限制），由 top_k 控制数量，方便对比验证；
    # 验证后可调到 0.6 过滤掉不相关结果降低 context 噪声。
    # 设为 None：完全禁用过滤。
    similarity_threshold: float | None = 1.0
    # V4-B: HNSW 检索 ef 参数（检查清单 P0-2）
    # ef 越大召回率越高但延迟上升；Milvus 默认 ef=top_k，对父子检索不够。
    # 建议值 128（M=16, efConstruction=200 的索引下，ef=128 召回率 >95%）。
    hnsw_ef: int = 128
    # V4-B: 父块字符上限（检查清单 P0-4，防止异常父块撑爆 LLM 上下文窗口）
    # 父块本身由 parent_chunk_size=800 切分控制，此为防御性截断。
    # 设为 None 完全禁用截断；默认 4000 字（约 2000 token，留 LLM 上下文余量）。
    max_parent_chars: int | None = 4000

    # ===== Hybrid 检索（V4-B+：向量 + BM25 关键词融合）=====
    # 是否启用 Hybrid 检索。关闭则纯向量检索（兼容旧行为）。
    # 启用后：向量召回子块 + BM25 召回父块，按 RRF 融合取 top_k。
    hybrid_search_enabled: bool = True
    # RRF (Reciprocal Rank Fusion) 参数 k
    # 融合公式：rrf_score = Σ 1/(k + rank_i)，rank 从 1 开始
    # k 越大，排名靠后的结果衰减越慢（更鼓励多样性）；k 越小，头部结果越占优
    # 业界默认 k=60（Elasticsearch / Lucene 默认值），经验值范围 10-100
    hybrid_rrf_k: int = 60
    # BM25 检索的候选数（在融合前召回的父块数，通常 > top_k 以提高召回率）
    hybrid_bm25_top_k: int = 20
    # 向量检索的候选数（在融合前召回的子块数，通常 > top_k 以提高召回率）
    hybrid_vector_top_k: int = 20

    # ===== 重排序（V5：cross-encoder 二阶段精排）=====
    # 是否启用 reranker。启用后：RRF 融合 + 父块回查后，对 top_k 候选做 cross-encoder 精排。
    # 关闭则保留 RRF 排序（兼容旧行为）。
    # 适用场景：召回结果排序不准（如"双写一致"排在"缓存穿透方案"前面），
    #          cross-encoder 用 (query, doc) 完整 attention 交互精排。
    rerank_enabled: bool = False
    # Reranker 模型名（HuggingFace Hub ID）
    # bge-reranker-v2-m3 与 bge-m3 同源（BAAI），XLMRoberta 架构，多语言 SOTA
    # 备选：BAAI/bge-reranker-large（560M, 纯英文更强）/ BAAI/bge-reranker-base（278M, 轻量）
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    # 精排后保留的文档数，None 表示保留全部（按原 top_k）
    # 通常与 top_k 一致，让 LLM 拿到精排后的最佳 top_k 个候选
    rerank_top_k: int | None = None
    # 输入 token 上限（cross-encoder 输入 (query, doc) 拼接长度）
    # 512 是 XLMRoberta 默认，覆盖 1024 token 父块截断后足够
    rerank_max_length: int = 512

    # 对话记忆窗口：注入 prompt 的最近消息条数
    memory_window: int = 10

    # ===== 对象存储 =====
    # 存储后端: "local"(本地文件系统) 或 "minio"(MinIO)
    storage_backend: Literal["local", "minio"] = "minio"

    # 本地存储根目录（storage_backend=local 时生效）
    documents_dir: str = "documents"

    # MinIO 配置（storage_backend=minio 时生效）
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "rag-documents"
    minio_secure: bool = False          # 本地开发用 HTTP
    minio_region: str = "us-east-1"     # MinIO 默认 region

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
