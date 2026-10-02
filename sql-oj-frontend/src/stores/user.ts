import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '../types/api'
import { login as loginApi, getCurrentUser, logout as logoutApi } from '../api/auth'
import { clearUserDrafts } from '../utils/draft'

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  // 本次应用生命周期内是否已尝试过恢复会话（避免守卫每次导航都重复请求）
  const sessionChecked = ref(false)
  // 会话恢复请求共享同一个 Promise，避免并发重复请求 /users/me/
  let restorePromise: Promise<boolean> | null = null

  // 免登录窗口的到期时间（本机估算，与服务端登录 Cookie 的滑动有效期一致）
  const rememberUntilKey = 'remember_until'

  // 记录 / 顺延免登录窗口到期时间（days 为服务端返回的窗口天数）
  const saveRememberUntil = (days?: number | string | null) => {
    const value = Number(days)
    if (!Number.isFinite(value) || value <= 0) return
    localStorage.setItem(rememberUntilKey, String(Date.now() + value * 86400000))
  }

  // 本机记录的免登录窗口是否已过期（过期即应要求重新登录）
  const isRememberExpired = (): boolean => {
    const raw = localStorage.getItem(rememberUntilKey)
    if (!raw) return false  // 没有记录时交给服务端判断（刷新失败即要求登录）
    const until = Number(raw)
    return Number.isFinite(until) && Date.now() > until
  }

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
    // 记录免登录窗口的到期时间（登录响应里的 remember_days，默认 7 天）
    saveRememberUntil(res.data?.remember_days)
    try {
      await fetchUser()
    } catch (error) {
      logout()
      throw error
    }
    sessionChecked.value = true
    return res
  }

  // 登出：先清空本地登录态（同步，保证守卫立即生效），
  // 再尽力通知后端结束会话（失败忽略，不影响本地登出）。
  const logout = () => {
    const accessToken = token.value
    // 清理该用户在本机的作答草稿（考试 / 练习），避免换账号后残留
    clearUserDrafts(user.value?.username)
    user.value = null
    setToken(null)
    localStorage.removeItem('user')
    localStorage.removeItem(rememberUntilKey)
    sessionChecked.value = true
    if (accessToken) {
      logoutApi(accessToken).catch(() => {})
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
        // 免登录窗口已过期：直接要求重新登录（不必再打接口）
        if (isRememberExpired()) {
          logout()
          sessionChecked.value = true
          return false
        }
        const storedToken = localStorage.getItem('access_token')
        if (!storedToken) {
          sessionChecked.value = true
          return false
        }
        token.value = storedToken
        try {
          await fetchUser()
        } catch (error) {
          // 访问令牌过期已由请求拦截器用登录 Cookie 自动续期；
          // 仍失败说明免登录窗口过期或账号已在其它设备登录：彻底清除本地登录态
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
    login, fetchUser, logout, restoreSession,
  }

})
