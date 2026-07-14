import logging
import threading

# Patch for PyCharm debugger compatibility with Python 3.13+
if not hasattr(threading.Thread, 'isAlive'):
    threading.Thread.isAlive = threading.Thread.is_alive

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(title="RAG Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "RAG Service running"}


@app.on_event("startup")
async def startup():
    logger.info("RAG Service starting up...")


@app.on_event("shutdown")
async def shutdown():
    logger.info("RAG Service shutting down...")
