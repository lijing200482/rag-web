from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
import uuid
from datetime import datetime, timezone


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Document]:
    """Split documents into chunks with semantic boundary awareness."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)

    # Enrich each chunk with traceability metadata
    for chunk in chunks:
        chunk.metadata["chunk_id"] = str(uuid.uuid4())
        chunk.metadata["timestamp"] = datetime.now(timezone.utc).isoformat()

    return chunks
