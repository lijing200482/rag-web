from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from ..config import Settings


def get_llm(settings: Settings | None = None) -> BaseChatModel:
    """Factory function to create an LLM instance based on configuration."""
    settings = settings or Settings()
    provider = settings.llm_provider.lower().strip()

    if provider == "openai-compatible" or (provider == "openai" and settings.openai_base_url):
        from langchain_openai import ChatOpenAI

        kwargs: dict = {
            "model": settings.llm_model,
            "temperature": 0,
            "api_key": settings.openai_api_key,
        }
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)

    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.llm_model, temperature=0, api_key=settings.openai_api_key)

    elif provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.llm_model,
            base_url=settings.ollama_base_url,
            temperature=0,
        )

    else:
        # Default fallback to OpenAI
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=settings.llm_model, temperature=0)
