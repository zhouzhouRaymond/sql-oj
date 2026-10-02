import request from './request'

interface LoginData {
  username: string
  password: string
}

interface RegisterData {
  username: string
  display_name?: string  // 自定义用户名（展示名），可留空
  email?: string         // 邮箱选填
  password: string
  user_type: 'student' | 'teacher'
}

export const login = (data: LoginData) => {
  return request.post('/auth/login/', data)
}

export const register = (data: RegisterData) => {
  return request.post('/auth/register/', data)
}

export const getCurrentUser = () => {
  return request.get('/users/me/')
}

// 登出：通知后端结束当前会话（使已签发的 token 立即失效）。
// 显式传入 token，因为本地登录态会在此之前被清空。
export const logout = (accessToken?: string) => {
  return request.post('/auth/logout/', null, {
    headers: accessToken
      ? { Authorization: `Bearer ${accessToken}` }
      : undefined,
  })
}