"""文档分块器 —— V4 Small-to-Big 父子索引。

V4-B+ 改造（Token 切分 + Markdown 分隔符）：
    - 切分单位从"字符"改为"token"（用 tiktoken cl100k_base 编码）
    - 与 LLM 计费单位一致，避免中文 800字≈1300token 超出预期
    - 分隔符优先 Markdown 结构边界（标题/代码块/列表/表格），减少语义断裂

V4 改造（Small-to-Big）：
    - 两级切分：先切父块（大，用于生成）→ 再对每个父块切子块（小，用于检索）
    - 父块和子块都返回，pipeline 会统一写入向量库（同一个 collection）
    - 子块 metadata 带 parent_id 指向父块 chunk_id
    - 检索时只命中子块（filter is_parent==false），再按 parent_id 回查父块全文

V2 历史保留：
    - chunk_id 仍基于 (kb_id, file_name, content) 的 SHA-256 → 相同内容自动去重
    - 父块和子块的 content 不同 → 各自生成独立的 chunk_id，互不冲突
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


# ── 文档预处理正则 ─────────────────────────────────────────────────────
# Markdown 图片标记：![alt text](url "title") —— 对 RAG 检索无价值，纯占 token
# URL 内可能含 ( )，故用非贪婪 + 允许括号嵌套的简化模式
_MD_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]*(?:\([^)]*\)[^)]*)*\)')
# 独占一行的图片标记（含前后所有换行）：整段移除，避免过滤后留下多余空行
# 解决"图片过滤后每句话都被空行隔开"的问题：
#   "文字\n\n![img]\n\n文字" → 旧逻辑变成 "文字\n\n文字"（仍被空行隔开）
#   本正则匹配 "\n+![img]\n+" 替换为 "\n"，让前后文字紧邻
# 用 \n+ 而非 \n：吃掉图片前后所有连续空行，否则替换后会残留 \n\n\n 被合并为空行
_MD_IMAGE_LINE_RE = re.compile(
    r'(?:^|\n+)[ \t]*!\[[^\]]*\]\([^)]*(?:\([^)]*\)[^)]*)*\)[ \t]*(?:\n+|$)'
)
# HTML 图片标签：<img src="..." />
_HTML_IMG_RE = re.compile(r'<img\s+[^>]*/?>', re.IGNORECASE)
# 连续 3+ 空行合并为 2 行（保留段落分隔，去除冗余空白）
_EXCESS_BLANK_RE = re.compile(r'\n{3,}')
# 行尾多余空格（影响 token 计数，且无语义价值）
_TRAILING_SPACES_RE = re.compile(r'[ \t]+\n')
# 以中文/英文冒号结尾的小标题行后的空行压缩为换行
# 让小标题和后续内容紧邻，避免"每句话都被空行隔开"的散碎感
# 例如 "SLOW模式规则：\n\n* 执行..." → "SLOW模式规则：\n* 执行..."
_AFTER_COLON_BLANK_RE = re.compile(r'([：:])\n\n+')


def _preprocess_content(text: str) -> str:
    """切分前的文档预处理：清理对 RAG 无价值的内容，减少 token 浪费和向量噪声。

    处理内容：
        1. 移除独占一行的 Markdown 图片标记 `![alt](url)`（连同前后换行），
           避免图片过滤后留下多余空行导致"每句话都被空行隔开"
        2. 移除残留的行内图片标记和 HTML `<img>` 标签（兜底）
        3. 清除行尾空格
        4. 压缩小标题（以冒号结尾的行）后的空行为换行，让小标题和内容紧邻
        5. 合并连续 3+ 空行为 2 行（保留段落边界，去冗余）

    注意：保留代码块、表格、列表等有语义价值的 Markdown 结构。
    """
    if not text:
        return text
    # 1. 移除独占一行的图片标记（连同前后换行，替换为单个换行）
    #    让前后文字紧邻，避免图片过滤后留下空行把句子拆散
    text = _MD_IMAGE_LINE_RE.sub('\n', text)
    # 2. 移除残留的行内图片标记和 HTML <img>（兜底，理论上少见）
    text = _MD_IMAGE_RE.sub('', text)
    text = _HTML_IMG_RE.sub('', text)
    # 3. 清除行尾空格
    text = _TRAILING_SPACES_RE.sub('\n', text)
    # 4. 压缩小标题（以冒号结尾的行）后的空行为换行，让小标题和内容紧邻
    text = _AFTER_COLON_BLANK_RE.sub(r'\1\n', text)
    # 5. 合并多余空行
    text = _EXCESS_BLANK_RE.sub('\n\n', text)
    return text.strip()


# Markdown 优先的分隔符（按优先级从高到低）
# 设计原则：优先在 Markdown 结构边界切分，避免切断标题/代码块/表格等语义单元
_DEFAULT_SEPARATORS = [
    # ── Markdown 结构边界（最高优先级，保护语义完整性）──
    "\n## ",      # 二级标题（章节边界）
    "\n### ",     # 三级标题（小节边界）
    "\n#### ",    # 四级标题
    "\n##### ",   # 五级标题
    "\n```",      # 代码块边界（```python / ```yaml 等）
    "\n---\n",    # 水平分割线（Markdown 分隔符）
    # ── 段落级 ──
    "\n\n",       # 空行（段落分隔）
    # ── 行级 Markdown 元素 ──
    "\n- ",       # 无序列表项
    "\n* ",       # 无序列表项（另一种语法）
    "\n| ",       # 表格行
    "\n",         # 普通换行
    # ── 句末标点（中英文）──
    "。",
    ". ",
    "!", "?",
    "！", "？",
    # ── 子句级 ──
    "，", ",",
    "；", ";",
    # ── 兜底 ──
    " ",          # 空格
    "",           # 逐字符（最后手段）
]


def _make_splitter(
    chunk_size: int,
    chunk_overlap: int,
    encoding_name: str = "cl100k_base",
) -> RecursiveCharacterTextSplitter:
    """创建基于 token 计数的递归切分器。

    使用 RecursiveCharacterTextSplitter.from_tiktoken_encoder：
        - 按 token 计数（与 LLM 计费单位一致）
        - 保留递归分隔符能力（在语义边界切分）
        - cl100k_base 编码对中文近似合理（1 token ≈ 0.5-1 中文字符）

    Args:
        chunk_size: 块的 token 上限
        chunk_overlap: 块之间的 token 重叠
        encoding_name: tiktoken 编码名称
    """
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=encoding_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_DEFAULT_SEPARATORS,
    )


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    kb_id: int | None = None,
    file_name: str | None = None,
    parent_chunk_size: int | None = None,
    child_chunk_size: int | None = None,
    child_chunk_overlap: int | None = None,
    encoding_name: str = "cl100k_base",
) -> list[Document]:
    """Small-to-Big 两级切分（token 计数）。

    Args:
        chunk_size / chunk_overlap: 旧参数（向后兼容）。若 parent_chunk_size
            未提供，则回退到旧的单一硬切分模式。
        kb_id: 知识库 ID（写入 metadata，检索时按知识库过滤）
        file_name: 文件名（与 kb_id 一起用于生成稳定 chunk_id）
        parent_chunk_size: 父块 token 上限（默认 500）
        child_chunk_size: 子块 token 上限（默认 128）
        child_chunk_overlap: 子块 token 重叠（默认 10）
        encoding_name: tiktoken 编码名称（默认 cl100k_base）

    返回的列表同时包含父块和子块：
        - 父块 metadata: is_parent=True, chunk_id, hash, kb_id, source, ...
        - 子块 metadata: is_parent=False, parent_id, chunk_id, hash, kb_id, source, chunk_index, ...

    V4: 若提供 parent_chunk_size，走两级切分；否则回退到 V2 单一切分（向后兼容）。
    """
    # V2 兼容路径：未指定 parent_chunk_size 时走旧的单一硬切分
    if parent_chunk_size is None:
        return _chunk_documents_v2(
            documents, chunk_size, chunk_overlap, kb_id, file_name, encoding_name
        )

    # V4: Small-to-Big 两级切分
    # 处理可选参数默认值
    if child_chunk_size is None:
        child_chunk_size = 256
    if child_chunk_overlap is None:
        child_chunk_overlap = 30

    # ── 预处理：清理图片标记/冗余空行，减少 token 浪费 ──
    # 对每个文档的 page_content 做清理（不修改原始 Document，用副本）
    cleaned_documents: list[Document] = []
    total_removed = 0
    for doc in documents:
        original_len = len(doc.page_content)
        cleaned = _preprocess_content(doc.page_content)
        total_removed += original_len - len(cleaned)
        # 保留原始 metadata，只替换 content
        cleaned_documents.append(Document(page_content=cleaned, metadata=dict(doc.metadata or {})))
    if total_removed > 0 and logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            f"[Splitter] Preprocessing removed {total_removed} chars "
            f"(images/html/redundant blanks) from {len(documents)} docs"
        )

    # 第 1 级：父块切分（大块，按 token 计数）
    parent_splitter = _make_splitter(
        chunk_size=parent_chunk_size,
        chunk_overlap=child_chunk_overlap,  # 父块之间留少量重叠避免边界丢语义
        encoding_name=encoding_name,
    )
    parent_docs = parent_splitter.split_documents(cleaned_documents)

    # 第 2 级：子块切分（小块，从每个父块再切）
    child_splitter = _make_splitter(
        chunk_size=child_chunk_size,
        chunk_overlap=child_chunk_overlap,
        encoding_name=encoding_name,
    )

    result: list[Document] = []

    for parent_idx, parent_doc in enumerate(parent_docs):
        parent_content = parent_doc.page_content

        # 生成父块 chunk_id（基于 kb_id+file_name+content 的 SHA-256）
        if kb_id is not None and file_name is not None:
            parent_chunk_id = _compute_chunk_id(kb_id, file_name, parent_content)
        else:
            parent_chunk_id = str(uuid.uuid4())

        # 父块 metadata：is_parent=True，无 parent_id
        parent_metadata = dict(parent_doc.metadata or {})  # 保留 loader 注入的 page 等字段
        parent_metadata.update({
            "chunk_id": parent_chunk_id,
            "hash": hashlib.sha256(parent_content.encode("utf-8")).hexdigest(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "is_parent": True,
            "parent_id": None,
            "parent_index": parent_idx,
        })
        if kb_id is not None:
            parent_metadata["kb_id"] = kb_id

        result.append(Document(page_content=parent_content, metadata=parent_metadata))

        # 切子块
        child_docs = child_splitter.split_documents([parent_doc])
        for child_idx, child_doc in enumerate(child_docs):
            child_content = child_doc.page_content

            # 子块 chunk_id（与父块内容不同，故 ID 不同）
            if kb_id is not None and file_name is not None:
                child_chunk_id = _compute_chunk_id(
                    kb_id, file_name, f"child:{parent_chunk_id}:{child_content}"
                )
            else:
                child_chunk_id = str(uuid.uuid4())

            child_metadata = dict(child_doc.metadata or {})
            child_metadata.update({
                "chunk_id": child_chunk_id,
                "hash": hashlib.sha256(child_content.encode("utf-8")).hexdigest(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "is_parent": False,
                "parent_id": parent_chunk_id,
                "parent_index": parent_idx,
                "chunk_index": child_idx,
            })
            if kb_id is not None:
                child_metadata["kb_id"] = kb_id

            result.append(Document(page_content=child_content, metadata=child_metadata))

    return result


def _chunk_documents_v2(
    documents: list[Document],
    chunk_size: int,
    chunk_overlap: int,
    kb_id: int | None,
    file_name: str | None,
    encoding_name: str = "cl100k_base",
) -> list[Document]:
    """V2 单一硬切分（向后兼容路径）。

    保留原行为：所有 chunk 都不带 is_parent/parent_id，pipeline 不做父子回查。
    旧数据迁移或未启用 Small-to-Big 时使用。
    """
    splitter = _make_splitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        encoding_name=encoding_name,
    )
    chunks = splitter.split_documents(documents)

    for chunk in chunks:
        content = chunk.page_content
        if kb_id is not None and file_name is not None:
            chunk_id = _compute_chunk_id(kb_id, file_name, content)
        else:
            chunk_id = str(uuid.uuid4())

        chunk.metadata["chunk_id"] = chunk_id
        chunk.metadata["hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk.metadata["timestamp"] = datetime.now(timezone.utc).isoformat()
        if kb_id is not None:
            chunk.metadata["kb_id"] = kb_id

    return chunks


def _compute_chunk_id(kb_id: int, file_name: str, content: str) -> str:
    """计算 chunk 的稳定 ID：基于 (kb_id, file_name, content) 的 SHA-256。

    相同内容 → 相同 ID，与 DocumentChunk 表的主键设计一致 → 自动去重。
    """
    raw = f"{kb_id}:{file_name}:{content}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
