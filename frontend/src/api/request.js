import axios from 'axios'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截器
request.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    const detail = error.response?.data?.detail || error.message || 'Unknown error'
    console.error('API Error:', detail)
    const enriched = new Error(detail)
    enriched.status = error.response?.status
    return Promise.reject(enriched)
  }
)

export default request
