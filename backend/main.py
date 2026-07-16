import logging
import threading
from contextlib import asynccontextmanager

# Patch for PyCharm debugger compatibility with Python 3.13+
if not hasattr(threading.Thread, 'isAlive'):
    threading.Thread.isAlive = threading.Thread.is_alive

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router as api_router
from .api.chat_routes import router as chat_router
from .api.stream_routes import router as stream_router
from .api.knowledge_routes import router as knowledge_router
from .api.document_routes import router as document_router
from .api.api_key_routes import router as api_key_router
from .auth.routes import router as auth_router
from .core.config import get_settings
from .db import init_db
from .cache.redis_client import close_redis
from .api.dependencies import get_vector_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)


def _validate_security() -> None:
    """启动时校验关键安全配置。"""
    s = get_settings()
    if s.jwt_secret_key == "change-me-in-production":
        logger.warning(
            "JWT_SECRET_KEY 仍为默认值！请修改 .env 中的 JWT_SECRET_KEY 为随机长字符串，"
            "否则任何人都可以伪造 JWT 令牌。"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    _validate_security()
    await init_db()
    logger.info("RAG Service started")
    yield
    # 关闭：释放向量存储、缓存等资源
    try:
        store = get_vector_store()
        store.close()
        logger.info("Milvus connection closed")
    except Exception as e:
        logger.warning(f"Failed to close Milvus connection: {e}")
    await close_redis()
    logger.info("RAG Service shutting down")


settings = get_settings()

app = FastAPI(title="RAG Service", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(stream_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(document_router, prefix="/api/v1")
app.include_router(api_key_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "RAG Service running"}