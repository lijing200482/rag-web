"""Schema 包 —— API 请求/响应数据格式 (Pydantic)。

与 model 包 (ORM 表结构) 分离：
    model  = 数据库表结构 (SQLAlchemy)
    schema = API 数据格式  (Pydantic)
"""
from .auth import UserRegister, UserLogin, UserResponse, TokenResponse
from .document import DocumentInfo, DeleteRequest
from .query import QueryRequest, QueryResponse

__all__ = [
    "UserRegister", "UserLogin", "UserResponse", "TokenResponse",
    "DocumentInfo", "DeleteRequest",
    "QueryRequest", "QueryResponse",
]
