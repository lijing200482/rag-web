"""用户服务层 —— 基于 ORM 模型的 CRUD。"""
import logging
from sqlalchemy import select, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..model.user import User

logger = logging.getLogger(__name__)


async def create_user(
    email: str, username: str, hashed_pwd: str, db: AsyncSession
) -> User:
    """创建用户并返回 ORM 对象。"""
    user = User(email=email, username=username, hashed_pwd=hashed_pwd)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"User created: id={user.id}, username={username}")
    return user


async def get_user_by_id(user_id: int, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_credential(credential: str, db: AsyncSession) -> User | None:
    """按邮箱或用户名查找用户。"""
    result = await db.execute(
        select(User).where(or_(User.email == credential, User.username == credential))
    )
    return result.scalar_one_or_none()


async def user_exists(email: str, username: str, db: AsyncSession) -> tuple[bool, str]:
    """检查邮箱/用户名是否已存在。返回 (exists, field_name)。"""
    result = await db.execute(
        select(User.id).where(or_(User.email == email, User.username == username))
    )
    row = result.first()
    if not row:
        return False, ""
    # 区分是 email 还是 username 冲突
    existing = await db.execute(
        select(User.id).where(User.email == email)
    )
    if existing.first():
        return True, "email"
    return True, "username"


async def list_users(db: AsyncSession) -> list[User]:
    """获取所有用户列表（管理员用）。"""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def update_user_status(user_id: int, is_active: bool, db: AsyncSession) -> User | None:
    """启用/禁用用户。返回更新后的用户，不存在则返回 None。"""
    await db.execute(
        update(User).where(User.id == user_id).values(is_active=is_active)
    )
    await db.commit()
    logger.info(f"User id={user_id} is_active set to {is_active}")
    return await get_user_by_id(user_id, db)
