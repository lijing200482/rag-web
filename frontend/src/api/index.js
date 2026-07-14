import request from './request'

// 发送问题
export const askQuestion = (question, top_k = null) => {
  return request.post('/query', {
    question,
    top_k,
    include_sources: true
  })
}

// 上传文档
export const uploadDocument = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
}

// 获取文档列表
export const getDocuments = () => {
  return request.get('/documents')
}

// 删除文档
export const deleteDocument = (source) => {
  return request.delete(`/documents/${encodeURIComponent(source)}`)
}

// 健康检查
export const healthCheck = () => {
  return request.get('/health')
}
