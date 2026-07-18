"""知识库核心 ORM 模型 —— 5 个模型。

KnowledgeBase ──1:N──→ Document ──1:N──→ DocumentChunk
KnowledgeBase ──1:N──→ DocumentUpload
KnowledgeBase ──1:N──→ ProcessingTask
Document ──1:N──→ ProcessingTask
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from .base import Base, TimestampMixin


class KnowledgeBase(Base, TimestampMixin):
    """知识库表。"""

    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(LONGTEXT)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 关系
    documents = relationship(
        "Document",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    user = relationship("User", back_populates="knowledge_bases")
    processing_tasks = relationship(
        "ProcessingTask", back_populates="knowledge_base"
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    document_uploads = relationship(
        "DocumentUpload",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBase id={self.id} name={self.name!r}>"


class Document(Base, TimestampMixin):
    """文档表 —— 记录上传到知识库的文件元信息。

    表级约束：(knowledge_base_id, file_name) 唯一联合 → 同一知识库内文件名不重复。
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String(255), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    content_type = Column(String(100), nullable=False)
    file_hash = Column(String(64), index=True)
    knowledge_base_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=False
    )

    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    processing_tasks = relationship(
        "ProcessingTask", back_populates="document"
    )
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "knowledge_base_id", "file_name", name="uq_kb_file_name"
        ),
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} file_name={self.file_name!r}>"


class DocumentChunk(Base, TimestampMixin):
    """文档块表。

    关键设计：
        - id 使用 SHA-256 哈希作为主键 → 相同内容的块自动具有相同 ID
        - hash 用于增量更新时判断块是否变化
        - chunk_metadata 存储该块的 page_number、offset 等信息

    V4 Small-to-Big 父子索引新增字段：
        - is_parent: True=父块(用于生成), False=子块(用于检索)
        - parent_id: 子块指向父块的 chunk_id;父块本身为 NULL
        - page_content: 块全文。V4-B 起父块全文存这里(不再存 Milvus),
          检索时子块命中后从本字段回查父块全文。
          子块也存(便于排错/重建向量库),但检索时不读子块的 page_content。
    """

    __tablename__ = "document_chunks"

    id = Column(String(64), primary_key=True)
    kb_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=False
    )
    document_id = Column(
        Integer, ForeignKey("documents.id"), nullable=False
    )
    file_name = Column(String(255), nullable=False)
    chunk_metadata = Column(JSON, nullable=True)
    hash = Column(String(64), nullable=False, index=True)
    # V4: 父子索引字段
    is_parent = Column(Boolean, nullable=False, default=False, index=True)
    parent_id = Column(String(64), nullable=True, index=True)
    # V4-B: 块全文(父块回查数据源,子块也存便于排错)
    # MySQL 不允许 TEXT 有 DEFAULT,故 nullable;应用层保证非空
    page_content = Column(LONGTEXT, nullable=True)

    knowledge_base = relationship("KnowledgeBase", back_populates="chunks")
    document = relationship("Document", back_populates="chunks")

    def __repr__(self) -> str:
        role = "PARENT" if self.is_parent else "CHILD"
        return f"<DocumentChunk [{role}] id={self.id[:8]!r}... file_name={self.file_name!r}>"


class DocumentUpload(Base, TimestampMixin):
    """文档上传记录表 —— 追踪上传过程的状态。

    状态机：pending ──→ completed / failed
    """

    __tablename__ = "document_uploads"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=False
    )
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    content_type = Column(String(100), nullable=False)
    temp_path = Column(String(255))
    status = Column(String(50), nullable=False, default="pending")
    error_message = Column(Text)

    knowledge_base = relationship(
        "KnowledgeBase", back_populates="document_uploads"
    )

    def __repr__(self) -> str:
        return f"<DocumentUpload id={self.id} file_name={self.file_name!r} status={self.status!r}>"


class ProcessingTask(Base, TimestampMixin):
    """文档处理任务表 —— 追踪异步处理流水线。

    状态机：pending → processing → completed / failed
    """

    __tablename__ = "processing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    knowledge_base_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=False
    )
    document_id = Column(Integer, ForeignKey("documents.id"))
    document_upload_id = Column(
        Integer, ForeignKey("document_uploads.id")
    )
    status = Column(String(50), nullable=False, default="pending")
    error_message = Column(Text)

    knowledge_base = relationship(
        "KnowledgeBase", back_populates="processing_tasks"
    )
    document = relationship("Document", back_populates="processing_tasks")

    def __repr__(self) -> str:
        return f"<ProcessingTask id={self.id} status={self.status!r}>"
