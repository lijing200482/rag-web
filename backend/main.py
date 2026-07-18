import logging
import os
import threading
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Patch for PyCharm debugger compatibility with Python 3.13+
if not hasattr(threading.Thread, 'isAlive'):
    threading.Thread.isAlive = threading.Thread.is_alive

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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


def _setup_logging() -> None:
    """配置全局日志：控制台 + 文件（轮转）。

    通过 .env 的 LOG_LEVEL 控制级别：
        - INFO: 默认，打印关键链路节点（切分数量/检索结果/父块回查/生成耗时）
        - DEBUG: 打印切分内容、检索 distance、prompt 全文等详细信息
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # 统一格式：时间 - 模块 - 级别 - 消息
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt)

    # 根 logger 清空默认 handler，避免重复输出
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # 控制台 handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # 文件 handler（轮转，避免日志文件无限增长）
    if settings.log_file:
        log_path = Path(settings.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=settings.log_file_max_mb * 1024 * 1024,
            backupCount=settings.log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # 降低第三方库的日志噪音
    for noisy in ("uvicorn.access", "httpx", "httpcore", "pymilvus"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.info(
        f"Logging initialized: level={settings.log_level}, "
        f"file={settings.log_file or 'disabled'}"
    )


_setup_logging()

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
    # --reload 模式下，子进程需要重新配置日志（主进程的 handler 不会继承）
    _setup_logging()
    _validate_security()
    await init_db()
    logger.info("RAG Service started")

    # 预加载 Reranker 模型（如果启用），避免第一次请求的用户卡几秒
    # 在后台线程加载，不阻塞服务启动
    settings = get_settings()
    if settings.rerank_enabled:
        def _preload_reranker():
            try:
                from .retrieval.reranker import Reranker
                r = Reranker(
                    model_name=settings.rerank_model,
                    max_length=settings.rerank_max_length,
                )
                # _ensure_model 是同步阻塞调用，放后台线程不阻塞事件循环
                ok = r._ensure_model()
                if ok:
                    logger.info("[Lifespan] Reranker model preloaded")
                else:
                    logger.warning("[Lifespan] Reranker model preload failed, will retry on first request")
            except Exception as e:
                logger.warning(f"[Lifespan] Reranker preload error: {e}")

        import threading
        threading.Thread(target=_preload_reranker, daemon=True).start()

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
    # 如果存在前端构建产物，返回 index.html；否则返回健康检查 JSON
    static_dir = Path(__file__).parent.parent / "static"
    index_html = static_dir / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return {"message": "RAG Service running"}


# 静态文件 serve（前端构建产物）
# Docker 部署时前端 build 输出到项目根目录 static/，FastAPI 直接 serve
_static_dir = Path(__file__).parent.parent / "static"
if _static_dir.exists():
    # 挂载 /assets 静态资源
    assets_dir = _static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA 路由兜底：所有非 /api、非 /assets、非已注册路径的 GET 请求返回 index.html
    # 让 vue-router 的 history 模式可以正常工作
    @app.get("/{path:path}")
    async def spa_fallback(path: str, request: Request):
        # 排除 API 路径（已注册的 router 会优先匹配，不会进这里）
        # 排除静态资源文件（如 favicon.ico, logo.png 等放在 static 根目录的）
        candidate = _static_dir / path
        if candidate.is_file():
            return FileResponse(candidate)
        # 其他所有路径返回 index.html，交给前端路由
        index_html = _static_dir / "index.html"
        if index_html.exists():
            return FileResponse(index_html)
        return JSONResponse({"detail": "Not found"}, status_code=404)