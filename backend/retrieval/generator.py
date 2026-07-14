from __future__ import annotations

"""生成器：将检索上下文与用户问题组装成 Prompt，调用 LLM 生成回答。

支持两种模式：
  - generate(): 一次性返回完整回答（现有 /query 端点）
  - generate_stream(): 异步流式逐 token 输出（SSE /query/stream 端点）
"""

import re
from collections.abc import AsyncIterator, Iterator

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel


# 安全切分点：句末标点。绝不在 markdown 标记（**、*、`、[]()）中间切。
# 这样大 chunk 被切成多段时，每段都是完整的 markdown 单元。
_SENT_END_RE = re.compile(r'(?<=[。！？!?\n])|(?<=;)|(?<=; )')
_COMMA_RE = re.compile(r'(?<=[，,；;])')


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

    async def generate(
        self,
        question: str,
        context: str,
        conversation_history: str = "",
    ) -> str:
        """生成回答。

        :param question: 用户问题
        :param context: 检索拼装得到的上下文
        :param conversation_history: 之前的对话历史文本，留空表示无上下文（无状态模式）
        """
        result = await self._chain.ainvoke(
            {
                "question": question,
                "context": context,
                "conversation_history": conversation_history,
            }
        )
        return result

    async def generate_stream(
        self,
        question: str,
        context: str,
        conversation_history: str = "",
    ) -> AsyncIterator[str]:
        """流式生成回答，逐 token 输出。

        检测 LLM 返回的 chunk 大小：如果服务端将大量 token 打包成
        一个 chunk（如 StepFun 的行为），则自动拆成 3–10 字的片段，
        确保前端获得流畅的逐字打字效果。
        """
        accumulated = ""
        async for chunk in self._chain.astream(
            {
                "question": question,
                "context": context,
                "conversation_history": conversation_history,
            }
        ):
            delta = chunk[len(accumulated):]
            accumulated = chunk
            if delta:
                for piece in _split_delta(delta):
                    yield piece


def format_history(messages) -> str:
    """将 ORM ChatMessage 列表格式化为历史对话字符串。

    格式：user: xxx\nassistant: yyy\n...
    """
    if not messages:
        return ""
    lines = []
    for m in messages:
        lines.append(f"{m.role}: {m.content}")
    return "\n".join(lines)


def _split_delta(delta: str) -> Iterator[str]:
    """安全切分：在句末标点处分块，绝不截断 markdown 标记。

    之前的固定 8 字切分会把 `**没有提供的**` 切成两段不完整 markdown，
    导致前端显示原始 `**` 字符。现在改用标点边界。
    """
    if not delta:
        return
    if len(delta) <= 4:
        yield delta
        return

    # 优先在句末标点切
    pieces = _SENT_END_RE.split(delta)
    pieces = [p for p in pieces if p]

    # 残留的过长段（>16 字且无标点）再按逗号切
    final: list[str] = []
    for piece in pieces:
        if len(piece) > 16:
            sub = _COMMA_RE.split(piece)
            final.extend(p for p in sub if p)
        else:
            final.append(piece)

    for piece in final:
        yield piece
