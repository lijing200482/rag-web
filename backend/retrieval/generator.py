from __future__ import annotations

"""生成器：将检索上下文与用户问题组装成 Prompt，调用 LLM 生成回答。

支持两种模式：
  - generate(): 一次性返回完整回答（现有 /query 端点）
  - generate_stream(): 异步流式逐 token 输出（SSE /query/stream 端点）
"""

import logging
import re
import time
from collections.abc import AsyncIterator, Iterator

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


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


# 匹配 LLM 答案中的引用标记：[filename.ext] 或 [filename.ext, p.X]
# 与前端 MarkdownText.vue 的 CITE_RE 正则保持一致
_CITE_MARK_RE = re.compile(
    r'\[([^\]\n]+?\.(?:md|pdf|docx|txt|markdown))(?:[，,]\s*p\.(\d+))?\]',
    re.IGNORECASE,
)


def extract_cited_sources(
    all_sources: list[dict],
    answer: str,
) -> list[dict]:
    """从候选 sources 中过滤出 LLM 实际引用的来源，按 (source, page) 去重。

    之前用 `s["source"] in answer` 做字符串包含判断有两个问题：
      1. 同一文件名的多个 chunk 会被全部保留（虚高卡片数）
      2. 文件名作为普通子串出现也会误判（非引用上下文）

    改为：正则匹配 [filename.ext] 引用标记，提取 (filename, page) 对，
    与 all_sources 按 (source, page) 精确匹配，去重后返回。

    fallback：LLM 未按格式引用（解析不到任何标记）→ 返回原始 all_sources，
    保证用户至少能看到检索候选来源。

    Args:
        all_sources: 检索返回的候选来源列表，每项含 source/page/content
        answer: LLM 完整回答文本

    Returns:
        过滤+去重后的 sources 列表
    """
    if not all_sources or not answer:
        return all_sources or []

    # 1. 从答案中解析所有引用标记 → {(filename, page_or_None)}
    cited_pairs: set[tuple[str, int | None]] = set()
    for m in _CITE_MARK_RE.finditer(answer):
        filename = m.group(1).strip()
        page = int(m.group(2)) if m.group(2) else None
        cited_pairs.add((filename, page))

    if not cited_pairs:
        # LLM 未按格式引用，fallback 返回原始候选
        return all_sources

    # 2. 按 (source, page) 精确匹配，去重
    # 匹配优先级：有页码的引用先匹配同页 chunk，无页码的引用只匹配第一个同文件 chunk
    seen_keys: set[tuple[str, int | None]] = set()
    cited: list[dict] = []

    # 先处理有页码的引用对（精确匹配）
    for (fname, fpage) in cited_pairs:
        if fpage is None:
            continue
        for s in all_sources:
            source = s.get("source")
            page = s.get("page")
            if source == fname and page == fpage:
                key = (source, page)
                if key not in seen_keys:
                    seen_keys.add(key)
                    cited.append(s)
                break

    # 再处理无页码的引用对（只取第一个同文件 chunk）
    for (fname, fpage) in cited_pairs:
        if fpage is not None:
            continue
        # 跳过已被有页码引用匹配过的文件
        if any((fname, p) in seen_keys for p in {s.get("page") for s in all_sources if s.get("source") == fname}):
            continue
        for s in all_sources:
            source = s.get("source")
            if source == fname:
                key = (source, s.get("page"))
                if key not in seen_keys:
                    seen_keys.add(key)
                    cited.append(s)
                break

    # 如果精确匹配失败（LLM 用了变体文件名等），fallback 返回原始候选
    return cited if cited else all_sources


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
        logger.info(
            f"[Generator] Generate start: question_len={len(question)}, "
            f"context_len={len(context)}, history_len={len(conversation_history)}"
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"[Generator] Question: {question!r}\n"
                f"[Generator] Context (first 500 chars): {context[:500]!r}...\n"
                f"[Generator] History: {conversation_history!r}"
            )

        t0 = time.perf_counter()
        result = await self._chain.ainvoke(
            {
                "question": question,
                "context": context,
                "conversation_history": conversation_history,
            }
        )
        t_elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            f"[Generator] Generate done in {t_elapsed:.1f}ms, "
            f"answer_len={len(result)}"
        )
        # INFO 级别直接记录 LLM 输出内容（生成回答通常几百字，日志量可控）
        # 超长回答截断到 1000 字符并标注
        if len(result) > 1000:
            logger.info(f"[Generator] Answer (truncated 1000/{len(result)}):\n{result[:1000]}...")
        else:
            logger.info(f"[Generator] Answer:\n{result}")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"[Generator] Answer full:\n{result}")
        return result

    async def generate_stream(
        self,
        question: str,
        context: str,
        conversation_history: str = "",
    ) -> AsyncIterator[str]:
        """流式生成回答，逐 token 输出。

        LangChain astream() + StrOutputParser 返回增量片段（每次只含新文本，
        非累积全文）。直接对每个 chunk 做安全切分即可。

        若服务端将多个 token 打包成一个大 chunk（如 StepFun 的行为），
        _split_delta 会按标点边界自动拆成小片段，确保前端逐字打字效果。
        """
        logger.info(
            f"[Generator] Stream start: question_len={len(question)}, "
            f"context_len={len(context)}, history_len={len(conversation_history)}"
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"[Generator] Stream Question: {question!r}\n"
                f"[Generator] Stream Context (first 500 chars): {context[:500]!r}..."
            )
        t0 = time.perf_counter()
        chunk_count = 0
        full_answer: list[str] = []

        async for chunk in self._chain.astream(
            {
                "question": question,
                "context": context,
                "conversation_history": conversation_history,
            }
        ):
            if chunk:
                chunk_count += 1
                full_answer.append(chunk)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"[Generator] Stream chunk[{chunk_count}]: {chunk!r}")
                for piece in _split_delta(chunk):
                    yield piece

        t_elapsed = (time.perf_counter() - t0) * 1000
        answer = "".join(full_answer)
        logger.info(
            f"[Generator] Stream done in {t_elapsed:.1f}ms, "
            f"chunks={chunk_count}, answer_len={len(answer)}"
        )
        # INFO 级别记录 LLM 完整输出（与 generate() 保持一致）
        if len(answer) > 1000:
            logger.info(f"[Generator] Stream answer (truncated 1000/{len(answer)}):\n{answer[:1000]}...")
        else:
            logger.info(f"[Generator] Stream answer:\n{answer}")


def format_history(messages) -> str:
    """将 ORM Message 列表格式化为历史对话字符串。

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
