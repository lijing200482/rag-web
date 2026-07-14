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

    # 文档上传目录
    documents_dir: str = "documents"

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
