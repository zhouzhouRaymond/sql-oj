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

// 题目历史表现（仅教师端返回）：通过率与基于通过率推断的难度建议
export interface QuestionHistory {
  total_submissions: number
  accepted_submissions: number
  attempted_students: number
  passed_students: number
  // 提交通过率（ACCEPTED 提交 / 总提交），0~1
  pass_rate: number
  // 学生通过率（至少通过一次的学生 / 尝试过的学生），0~1，难度建议以此为准
  student_pass_rate: number
  recommended_difficulty: 'easy' | 'medium' | 'hard' | null
  confidence: 'none' | 'low' | 'medium' | 'high'
  reason: string
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
