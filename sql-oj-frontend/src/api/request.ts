import axios from 'axios'
import { ElMessage } from 'element-plus'

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：自动添加 Token
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：统一处理错误
request.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // 优先展示后端返回的原因（如“账号已在其它设备登录，请重新登录”）
      const detail = error.response?.data?.detail
      ElMessage.error(typeof detail === 'string' && detail ? detail : '登录已过期，请重新登录')
      localStorage.removeItem('access_token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    } else {
      ElMessage.error(error.response?.data?.error || '请求失败')
    }
    return Promise.reject(error)
  }
)

export default request