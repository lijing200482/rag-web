import axios from 'axios'
import { useAuthStore } from '../stores/auth.js'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

request.interceptors.request.use(
  config => {
    const auth = useAuthStore()
    if (auth.token) {
      config.headers.Authorization = `Bearer ${auth.token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

request.interceptors.response.use(
  response => {
    return response.data
  },
  error => {
    const detail = error.response?.data?.detail || error.message || 'Unknown error'
    if (error.response?.status === 401) {
      const auth = useAuthStore()
      auth.clearAuth()
      window.location.href = '/login'
    }
    console.error('API Error:', detail)
    const enriched = new Error(detail)
    enriched.status = error.response?.status
    return Promise.reject(enriched)
  }
)

export default request
