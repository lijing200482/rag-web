from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    Docx2txtLoader,
)
from langchain_core.documents import Document
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".docx"}

_LOADER_MAP = {
    ".pdf": PyPDFLoader,
    ".md": TextLoader,
    ".markdown": TextLoader,
    ".txt": TextLoader,
    ".docx": Docx2txtLoader,
}

_TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}


def load_document(file_path: Path) -> list[Document]:
    """Load a document from disk using the appropriate LangChain loader."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    ext = file_path.suffix.lower()
    if ext not in _LOADER_MAP:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    
    loader_cls = _LOADER_MAP[ext]
    logger.info(f"Loading document: {file_path} (type: {ext})")
    
    try:
        if ext in _TEXT_EXTENSIONS:
            docs = loader_cls(file_path=str(file_path), encoding="utf-8").load()
        else:
            docs = loader_cls(file_path=str(file_path)).load()
        logger.info(f"Loaded {len(docs)} document pages from {file_path}")
        return docs
    except Exception as e:
        logger.error(f"Failed to load document {file_path}: {str(e)}", exc_info=True)
        raise RuntimeError(f"Failed to load document: {str(e)}") from e
