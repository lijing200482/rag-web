from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class DocumentInfo(BaseModel):
    source: str
    document_type: str
    chunk_count: int
    uploaded_at: Optional[datetime] = None


class DeleteRequest(BaseModel):
    ids: list[str]
