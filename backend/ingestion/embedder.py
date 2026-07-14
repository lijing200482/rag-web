from abc import ABC, abstractmethod
from langchain_core.embeddings import Embeddings
from ..core.config import Settings


class EmbeddingProvider(ABC):
    def __init__(self, settings: Settings):
        self._settings = settings

    @abstractmethod
    def get_embedder(self) -> Embeddings: ...


class LocalEmbeddingProvider(EmbeddingProvider):
    def get_embedder(self) -> Embeddings:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=self._settings.embedding_model)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def get_embedder(self) -> Embeddings:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=self._settings.openai_embedding_model,
            api_key=self._settings.openai_api_key,
        )


class OllamaEmbeddingProvider(EmbeddingProvider):
    def get_embedder(self) -> Embeddings:
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=self._settings.embedding_model,
            base_url=self._settings.ollama_base_url,
        )


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Factory function to get the configured embedding provider."""
    settings = settings or Settings()
    providers = {
        "local": LocalEmbeddingProvider,
        "openai": OpenAIEmbeddingProvider,
        "ollama": OllamaEmbeddingProvider,
    }
    return providers[settings.embedding_provider](settings)
