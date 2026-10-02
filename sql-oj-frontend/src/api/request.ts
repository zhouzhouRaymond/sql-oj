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

// ===== 访问令牌自动续期（免登录窗口内）=====
// access token 只有 2 小时：过期后用 HttpOnly 登录 Cookie 换新的并重试原请求，用户无感；
// 免登录窗口（默认 7 天）过后刷新会失败，此时才提示重新登录。
let refreshing: Promise<string | null> | null = null

const refreshAccessToken = (): Promise<string | null> => {
  if (!refreshing) {
    // 直接用 axios 发起，避免再次进入本拦截器造成递归
    refreshing = axios
      .post('/api/auth/refresh/', {}, { timeout: 10000 })
      .then((res) => {
        const access: string | undefined = res.data?.access
        if (!access) return null
        localStorage.setItem('access_token', access)
        const days = Number(res.data?.remember_days)
        if (Number.isFinite(days) && days > 0) {
          // 窗口顺延：与服务端登录 Cookie 的滑动有效期保持一致
          localStorage.setItem('remember_until', String(Date.now() + days * 86400000))
        }
        return access
      })
      .catch(() => null)
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

// 响应拦截器：统一处理错误
request.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status
    const url: string = error.config?.url || ''
    const isAuthEndpoint = url.includes('/auth/login/') || url.includes('/auth/refresh/')

    // 1) access token 过期：先尝试用登录 Cookie 静默续期，成功则重试原请求
    if (status === 401 && !isAuthEndpoint && !error.config?.__retried) {
      const access = await refreshAccessToken()
      if (access) {
        error.config.__retried = true
        error.config.headers = {
          ...(error.config.headers || {}),
          Authorization: `Bearer ${access}`,
        }
        return request(error.config)
      }
    }

    if (status === 401) {
      // 2) 续期失败（免登录窗口已过期 / 账号已在其它设备登录）：清理登录态并要求重新登录
      // 优先展示后端返回的原因（如“账号已在其它设备登录，请重新登录”）
      const detail = error.response?.data?.detail
      ElMessage.error(typeof detail === 'string' && detail ? detail : '登录已过期，请重新登录')
      localStorage.removeItem('access_token')
      localStorage.removeItem('remember_until')
      localStorage.removeItem('user')
      window.location.href = '/login'
    } else {
      ElMessage.error(error.response?.data?.error || '请求失败')
    }
    return Promise.reject(error)
  }
)

export default request