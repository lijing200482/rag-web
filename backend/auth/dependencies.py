import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import Settings, get_settings
from ..db import get_db
from .security import decode_access_token
from .service import get_user_by_id

logger = logging.getLogger(__name__)
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """从 JWT 解析用户。无 token 时返回 None（允许匿名访问）。"""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials, settings)
        user = await get_user_by_id(payload["user_id"], db)
        # is_active=False 的用户视为未登录，防止禁用后旧 token 仍可用
        if user is None or not user.is_active:
            return None
        return user
    except ExpiredSignatureError:
        logger.info("Token expired, user needs to re-login")
        return None
    except InvalidTokenError:
        logger.warning("Invalid or tampered token")
        return None
    except Exception as e:
        logger.error(f"Auth dependency error: {e}", exc_info=True)
        return None


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
