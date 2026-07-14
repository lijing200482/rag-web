"""认证相关 API 数据格式。"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class UserRegister(BaseModel):
    """注册请求。"""
    email: EmailStr = Field(..., description="有效邮箱格式")
    username: str = Field(..., min_length=2, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    """登录请求。"""
    credential: str = Field(..., description="邮箱或用户名")
    password: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """用户信息响应。"""
    id: int
    email: str
    username: str
    is_active: bool
    is_superuser: bool
    created_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    """登录/注册成功响应。"""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
