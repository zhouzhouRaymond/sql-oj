import request from './request'

// 获取所有学生用户（教师专用）
export const getStudents = () => {
  return request.get('/users/', {
    params: { user_type: 'student' }
  })
}

// 获取当前用户信息
export const getCurrentUser = () => {
  return request.get('/users/me/')
}

// ✅ 修改个人信息（自定义用户名 / 邮箱）
export const updateUser = (data: { email?: string; username?: string; display_name?: string }) => {
  return request.put('/users/me/', data)
}

// ✅ 修改密码
export const changePassword = (data: { old_password: string; new_password: string }) => {
  return request.post('/users/change-password/', data)
}

// ✅ 获取个人统计数据（通过率、提交次数等）
export const getUserStats = () => {
  return request.get('/users/me/stats/')
}

// ✅ 获取个人提交记录（后端按提交时间倒序，每页 20 条）
export const getMySubmissions = (params?: { page?: number }) => {
  return request.get('/submissions/', { params })
}

// ===== 账号管理（教师专用）=====
// 账号列表：支持分页 / 关键词搜索（登录名、用户名、邮箱）/ 角色过滤
export const getUsers = (params?: {
  page?: number
  search?: string
  user_type?: string
}) => {
  return request.get('/users/', { params })
}

// 新建账号（学生 / 教师均可）
export const createUser = (data: {
  username: string
  display_name?: string
  email?: string
  password: string
  user_type: 'student' | 'teacher'
  is_active?: boolean
}) => {
  return request.post('/users/', data)
}

// 修改账号：用户名/邮箱/角色/启用状态，传 password 即为重置密码
export const updateUserById = (id: number, data: any) => {
  return request.patch(`/users/${id}/`, data)
}