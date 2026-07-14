from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    top_k: Optional[int] = None
    include_sources: bool = True


class QueryResponse(BaseModel):
    answer: str
    sources: Optional[list[dict]] = None
