import request from './request'

// 认证
export const register = (email, username, password) => {
  return request.post('/auth/register', { email, username, password })
}

export const login = (credential, password) => {
  return request.post('/auth/login', { credential, password })
}

export const getMe = () => {
  return request.get('/auth/me')
}

// 用户管理（管理员）
export const getUsers = () => {
  return request.get('/auth/users')
}

export const toggleUserStatus = (userId, isActive) => {
  return request.patch(`/auth/users/${userId}/status?is_active=${isActive}`)
}

// 文档 & 问答
export const askQuestion = (question, top_k = null, session_id = null) => {
  return request.post('/query', { question, top_k, include_sources: true, session_id })
}

/**
 * SSE 流式问答：逐 token 推送，实时显示 LLM 回答。
 *
 * @param {string} question  用户问题
 * @param {number|null} topK  检索文档数
 * @param {number|null} sessionId  会话 ID
 * @param {object} callbacks  { onToken({content}), onSources(arr), onDone({session_id}), onError(err) }
 * @returns {Promise<void>}
 */
export const askQuestionStream = (question, topK = null, sessionId = null, callbacks = {}) => {
  const { onToken, onSources, onDone, onError } = callbacks
  const token = localStorage.getItem('token')
  const headers = {
    'Content-Type': 'application/json',
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  fetch('/api/v1/query/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      question,
      top_k: topK || undefined,
      include_sources: true,
      session_id: sessionId || undefined,
    }),
  }).then(async response => {
    if (!response.ok) {
      let detail = '请求失败'
      try {
        const err = await response.json()
        detail = err.detail || detail
      } catch (_) { /* ignore parse error */ }
      if (response.status === 401) {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
        window.location.href = '/login'
        return
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
        buffer = lines.pop() // 最后一行可能不完整，保留

        let eventType = ''
        let data = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            data = line.slice(6)
          } else if (line === '') {
            // 空行 = 事件结束
            if (eventType && data) {
              try {
                const parsed = JSON.parse(data)
                switch (eventType) {
                  case 'token':  if (onToken) onToken(parsed); break
                  case 'sources': if (onSources) onSources(parsed); break
                  case 'done':   if (onDone) onDone(parsed); break
                  case 'error':  if (onError) onError(new Error(parsed.detail)); break
                }
              } catch (_) { /* skip malformed JSON */ }
            }
            eventType = ''
            data = ''
          }
        }
      }
    } catch (err) {
      if (onError) onError(err)
    }
  }).catch(err => {
    if (onError) onError(err)
  })
}

// 聊天会话管理
export const createSession = (title = '') => {
  return request.post('/chat/sessions', { title })
}

export const listSessions = () => {
  return request.get('/chat/sessions')
}

export const getSession = (sessionId) => {
  return request.get(`/chat/sessions/${sessionId}`)
}

export const renameSession = (sessionId, title) => {
  return request.patch(`/chat/sessions/${sessionId}`, { title })
}

export const deleteSession = (sessionId) => {
  return request.delete(`/chat/sessions/${sessionId}`)
}

// 游标分页获取会话消息
export const getSessionMessages = (sessionId, cursor = null, limit = 20) => {
  const params = { limit }
  if (cursor !== null && cursor !== undefined) {
    params.cursor = cursor
  }
  return request.get(`/chat/sessions/${sessionId}/messages`, { params })
}

export const uploadDocument = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const getDocuments = () => {
  return request.get('/documents')
}

export const deleteDocument = (source) => {
  return request.delete(`/documents/${encodeURIComponent(source)}`)
}

export const healthCheck = () => {
  return request.get('/health')
}