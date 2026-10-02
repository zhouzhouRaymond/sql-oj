import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '../types/api'
import { login as loginApi, getCurrentUser } from '../api/auth'

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  // 本次应用生命周期内是否已尝试过恢复会话（避免守卫每次导航都重复请求）
  const sessionChecked = ref(false)
  // 会话恢复请求共享同一个 Promise，避免并发重复请求 /users/me/
  let restorePromise: Promise<boolean> | null = null

  // 真正的登录态：既要持有 token，也要有与之匹配的用户信息
  const isAuthenticated = computed(() => Boolean(token.value && user.value))

  // 展示用用户名：优先自定义用户名，其次登录名（username 仅用于登录）
  const displayName = computed(
    () => user.value?.name || user.value?.display_name || user.value?.username || ''
  )

  const setToken = (value: string | null) => {
    token.value = value
    if (value) {
      localStorage.setItem('access_token', value)
    } else {
      localStorage.removeItem('access_token')
    }
  }

  // 获取当前用户信息
  const fetchUser = async () => {
    const res = await getCurrentUser()
    user.value = res.data
    localStorage.setItem('user', JSON.stringify(res.data))
    return res
  }

  // 登录：先拿 token 再校验用户信息，任一环节失败都回滚，避免留下
  // “登录失败却仍有 token”的中间态（此前会表现为未登录却能访问题目页）。
  const login = async (username: string, password: string) => {
    const res = await loginApi({ username, password })
    const access = res.data?.access
    if (!access) {
      throw new Error('登录响应缺少 access token')
    }
    setToken(access)
    try {
      await fetchUser()
    } catch (error) {
      logout()
      throw error
    }
    sessionChecked.value = true
    return res
  }

  // 登出
  const logout = () => {
    user.value = null
    setToken(null)
    localStorage.removeItem('user')
    sessionChecked.value = true
  }

  // 从本地恢复用户信息（仅用于界面展示，不做校验）
  const restoreUser = () => {
    const storedUser = localStorage.getItem('user')
    if (storedUser) {
      user.value = JSON.parse(storedUser)
    }
  }

  // 应用启动 / 刷新时恢复并校验会话：
  // - 本地没有 token：视为未登录
  // - 本地有 token：调用 /users/me/ 校验，失败（token 失效或伪造）则清空登录态
  const restoreSession = (): Promise<boolean> => {
    if (sessionChecked.value) {
      return Promise.resolve(isAuthenticated.value)
    }
    if (!restorePromise) {
      restorePromise = (async () => {
        const storedToken = localStorage.getItem('access_token')
        if (!storedToken) {
          sessionChecked.value = true
          return false
        }
        token.value = storedToken
        try {
          await fetchUser()
        } catch (error) {
          // token 无效 / 已过期 / 用户不存在：彻底清除本地登录态
          logout()
        } finally {
          sessionChecked.value = true
        }
        return isAuthenticated.value
      })()
    }
    return restorePromise
  }

  // 在 return 里添加
  const isTeacher = computed(() => user.value?.user_type === 'teacher')
  const isStudent = computed(() => user.value?.user_type === 'student')

  return {
    user, token, isAuthenticated, sessionChecked,
    isTeacher, isStudent, displayName,
    login, fetchUser, logout, restoreUser, restoreSession,
  }

})
