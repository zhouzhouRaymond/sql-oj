// 用户相关类型
export interface User {
  id: number
  username: string       // 登录名（唯一，用于登录）
  display_name?: string  // 自定义用户名（展示名，可自行修改）
  name?: string          // 展示名：display_name 为空时后端回退为登录名
  email: string
  user_type: 'student' | 'teacher'
  avatar?: string         // 头像地址（Profile 页展示，未设置时用展示名首字母兜底）
}

// 题目相关类型
export interface Question {
  id: number
  description: string
  difficulty: 'easy' | 'medium' | 'hard'
  sample_input: string
  sample_output: string
  create_table_sql: string
}

// 提交相关类型
export interface Submission {
  id: number
  question: number
  submitted_sql: string
  execution_status: string
  score: number
  created_at: string
}

// API 响应格式（分页）
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}