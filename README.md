# RAG Service

基于 FastAPI + LangChain + ChromaDB 的文档问答系统。

## 快速开始

### 后端服务

```bash
# 激活虚拟环境
.venv\Scripts\activate

# 安装依赖
pip install -r backend/requirements.txt

# 首次运行会自动下载本地 embedding 模型（all-MiniLM-L6-v2）

# 启动服务（在项目根目录执行，确保相对导入正确）
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端界面

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动前端开发服务器
npm run dev
```

访问 `http://localhost:5173` 查看前端界面。

## API 端点

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/documents/upload` | POST | 上传文档（multipart/form-data） |
| `/api/v1/documents` | GET | 列出所有文档 |
| `/api/v1/documents/{source}` | DELETE | 删除指定文档 |
| `/api/v1/query` | POST | 提问并获取 RAG 回答 |

### 示例：上传文档

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@your_document.pdf"
```

### 示例：提问

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "你的问题", "top_k": 4}'
```

## 架构

```
上传 → loaders.py → splitter.py → embedder.py → chroma_store.py (upsert)
提问 → retriever.py → generator.py → LLM (answer + sources)
```

## 配置

编辑 `.env` 文件：
- `EMBEDDING_PROVIDER`: `local`（默认，免费）或 `openai`
- `LLM_PROVIDER` / `LLM_MODEL`: 后续接入具体大模型时修改
- `CHUNK_SIZE` / `CHUNK_OVERLAP`: 文本分块大小

## 扩展

- **混合检索**: 在 `retrieval/retriever.py` 中添加 BM25
- **重排序**: 在检索和生成之间插入 CrossEncoder reranker
- **流式响应**: 利用 LangChain chain 的异步流式能力
- **新数据源**: 在 `ingestion/loaders.py` 的 `_LOADER_MAP` 中添加
