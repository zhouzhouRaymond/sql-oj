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