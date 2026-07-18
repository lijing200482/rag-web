import request from './request'

// ==================== 认证 ====================
export const register = (email, username, password) =>
  request.post('/auth/register', { email, username, password })

export const login = (credential, password) =>
  request.post('/auth/login', { credential, password })

// ==================== 健康检查 ====================
export const healthCheck = () => request.get('/health')

// ==================== 用户管理（管理员） ====================
export const getUsers = () => request.get('/auth/users')

export const toggleUserStatus = (userId, isActive) =>
  request.patch(`/auth/users/${userId}/status?is_active=${isActive}`)

// ==================== SSE 流式问答 ====================

/**
 * SSE 流式问答：逐 token 推送，实时显示 LLM 回答。
 */
export const askQuestionStream = (question, topK = null, sessionId = null, callbacks = {}) => {
  const { onToken, onSources, onDone, onError } = callbacks
  const token = localStorage.getItem('token')
  const headers = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`

  // AbortController：允许调用方在组件卸载或用户取消时中断 fetch + reader
  const controller = new AbortController()

  fetch('/api/v1/query/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      question,
      top_k: topK || undefined,
      include_sources: true,
      session_id: sessionId || undefined,
    }),
    signal: controller.signal,
  }).then(async response => {
    if (!response.ok) {
      let detail = '请求失败'
      try { const err = await response.json(); detail = err.detail || detail } catch (_) {}
      if (response.status === 401) {
        localStorage.removeItem('token'); localStorage.removeItem('user')
        window.location.href = '/login'; return
      }
      if (onError) onError(new Error(detail))
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        let eventType = ''
        let data = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) eventType = line.slice(7).trim()
          else if (line.startsWith('data: ')) data = line.slice(6)
          else if (line === '') {
            if (eventType && data) {
              try {
                const parsed = JSON.parse(data)
                switch (eventType) {
                  case 'token':  if (onToken) onToken(parsed); break
                  case 'sources': if (onSources) onSources(parsed); break
                  case 'done':   if (onDone) onDone(parsed); break
                  case 'error':  if (onError) onError(new Error(parsed.detail)); break
                }
              } catch (_) {}
            }
            eventType = ''
            data = ''
          }
        }
      }
    } catch (err) {
      // 用户主动取消（组件卸载/切换会话）：AbortError 静默退出，不触发 onError
      if (err.name === 'AbortError') return
      if (onError) onError(err)
    }
  }).catch(err => {
    // 用户主动取消：AbortError 静默退出
    if (err.name === 'AbortError') return
    if (onError) onError(err)
  })

  return {
    cancel: () => controller.abort()
  }
}

// ==================== 聊天会话 ====================
export const createSession = (title = '') =>
  request.post('/chat/sessions', { title })

export const listSessions = () =>
  request.get('/chat/sessions')

export const renameSession = (sessionId, title) =>
  request.patch(`/chat/sessions/${sessionId}`, { title })

export const deleteSession = (sessionId) =>
  request.delete(`/chat/sessions/${sessionId}`)

export const getSessionMessages = (sessionId, cursor = null, limit = 20) => {
  const params = { limit }
  if (cursor !== null) params.cursor = cursor
  return request.get(`/chat/sessions/${sessionId}/messages`, { params })
}

// 对话 ↔ 知识库关联
export const getChatKnowledgeBases = (sessionId) =>
  request.get(`/chat/sessions/${sessionId}/knowledge`)

export const setChatKnowledgeBases = (sessionId, kbIds) =>
  request.put(`/chat/sessions/${sessionId}/knowledge`, { kb_ids: kbIds })

export const addChatKnowledgeBase = (sessionId, kbId) =>
  request.post(`/chat/sessions/${sessionId}/knowledge/${kbId}`)

export const removeChatKnowledgeBase = (sessionId, kbId) =>
  request.delete(`/chat/sessions/${sessionId}/knowledge/${kbId}`)

// ==================== 知识库 ====================
export const getKnowledgeBases = () =>
  request.get('/knowledge')

export const createKnowledgeBase = (name, description = null) =>
  request.post('/knowledge', { name, description })

export const getKnowledgeBase = (kbId) =>
  request.get(`/knowledge/${kbId}`)

export const updateKnowledgeBase = (kbId, data) =>
  request.patch(`/knowledge/${kbId}`, data)

export const deleteKnowledgeBase = (kbId) =>
  request.delete(`/knowledge/${kbId}`)

// ==================== 文档 ====================
export const getDocumentsByKb = (kbId, params = {}) =>
  request.get(`/knowledge/${kbId}/documents`, { params })

export const uploadDocumentToKb = (kbId, file) => {
  const fd = new FormData()
  fd.append('file', file)
  return request.post(`/knowledge/${kbId}/documents`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const deleteDocument = (docId) =>
  request.delete(`/documents/${docId}`)

// ==================== 文档块 ====================
export const getChunksByKb = (kbId, params = {}) =>
  request.get(`/knowledge/${kbId}/chunks`, { params })

// ==================== 上传记录 ====================
export const getUploadsByKb = (kbId, params = {}) =>
  request.get(`/knowledge/${kbId}/uploads`, { params })

// ==================== 处理任务 ====================
export const getTasksByKb = (kbId, params = {}) =>
  request.get(`/knowledge/${kbId}/tasks`, { params })

export const getTask = (taskId) =>
  request.get(`/knowledge/tasks/${taskId}`)

export const retryTask = (taskId) =>
  request.post(`/knowledge/tasks/${taskId}/retry`)
