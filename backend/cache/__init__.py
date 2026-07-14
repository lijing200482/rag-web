"""Redis 缓存模块 — 对话记忆热缓存层。

包含:
  - redis_client: Redis 连接池管理 + 异步客户端
  - conversation_cache: 消息缓存的 Read-Through / Write-Through 实现
"""
