from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel


def assemble_context(documents: list[Document]) -> str:
    """Combine retrieved chunks into a single context string with source citations."""
    parts = []
    for doc in documents:
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page_number")
        page_ref = f", p.{page}" if page else ""
        parts.append(f"[{source}{page_ref}]:\n{doc.page_content}")
    return "\n\n---\n\n".join(parts)


class Generator:
    """LangChain chain that assembles context and generates an answer."""

    def __init__(self, llm: BaseChatModel, prompt_template: ChatPromptTemplate):
        self._llm = llm
        self._prompt = prompt_template
        self._chain = prompt_template | llm | StrOutputParser()

    async def generate(self, question: str, context: str) -> str:
        result = await self._chain.ainvoke({"question": question, "context": context})
        return result
