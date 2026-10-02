import request from './request'

export const submitSQL = (data: {
  question_id: number
  submitted_sql: string
  exam_id?: number | null
}) => {
  return request.post('/submissions/submit/', data)
}

export const getSubmission = (id: number) => {
  return request.get(`/submissions/${id}/`)
}

// 提交列表：可按题目 / 学生 / 时间段过滤（教师端「学生提交记录」下钻用）。
// student_id 仅教师有效（学生只能看到自己的提交）。
export const getSubmissions = (params?: {
  question_id?: number
  student_id?: number
  start?: string
  end?: string
  page?: number
}) => {
  return request.get('/submissions/', { params })
}