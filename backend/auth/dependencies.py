import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import Settings, get_settings
from ..db import get_db
from .security import decode_access_token
from .service import get_user_by_id
from ..service.api_key import get_api_key_by_value

logger = logging.getLogger(__name__)
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """从 JWT 或 API Key 解析用户。无 token 时返回 None（允许匿名访问）。

    鉴权顺序：
    1. 先将 Bearer token 当作 JWT 解析。
    2. JWT 解析失败（过期 / 非法）时，退而将 token 作为 API Key 查库鉴权。
    仅捕获 JWT 专属异常（ExpiredSignatureError / InvalidTokenError），
    其他异常（如 DB 连接失败）向上抛出，由全局异常处理返回 500。
    """
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = decode_access_token(token, settings)
        user = await get_user_by_id(payload["user_id"], db)
        # is_active=False 的用户视为未登录，防止禁用后旧 token 仍可用
        if user is None or not user.is_active:
            return None
        return user
    except (ExpiredSignatureError, InvalidTokenError):
        # JWT 无效（过期/篡改）→ 退而将 token 作为 API Key 鉴权
        api_key = await get_api_key_by_value(token, db)
        if api_key is None or not api_key.is_active:
            return None
        user = await get_user_by_id(api_key.user_id, db)
        if user is None or not user.is_active:
            return None
        return user


async def require_user(current_user=Depends(get_current_user)):
    """要求已登录，否则 401。"""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return current_user


async def require_admin(current_user=Depends(require_user)):
    """要求管理员，否则 403。"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user
