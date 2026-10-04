import request from './request'
import { fetchAllPages } from './paging'

// 获取题目列表
// 支持服务端筛选：search（题号/题目名称/描述）、difficulty、is_visible（仅教师）
export const getQuestions = (params?: {
  page?: number
  ordering?: string
  search?: string
  difficulty?: string
  is_visible?: string
}) => {
  return request.get('/questions/', { params })
}

// 获取全部题目：后端分页（每页 20 条），这里自动翻页取完。
// 供「考试组卷」等需要完整题目列表的下拉选择使用（否则只能选到前 20 道）。
export const getAllQuestions = (): Promise<any[]> =>
  fetchAllPages('/questions/', { ordering: 'id' })

// 获取题目详情
export const getQuestionDetail = (id: number) => {
  return request.get(`/questions/${id}/`)
}

// 老师端出题辅助：参考 DDL → 期望结构（并可自动生成、验证行为探针）
export const introspectReference = (data: {
  reference_sql: string
  setup_sql?: string
  suggest_probes?: boolean
}) => {
  return request.post('/questions/introspect/', data)
}

// 创建题目
export const createQuestion = (data: any) => {
  return request.post('/questions/', data)
}

// 更新题目
export const updateQuestion = (id: number, data: any) => {
  return request.put(`/questions/${id}/`, data)
}

// 局部更新题目（例如切换「学生可见」开关，只提交变化的字段）
export const patchQuestion = (id: number, data: any) => {
  return request.patch(`/questions/${id}/`, data)
}

// 删除题目
export const deleteQuestion = (id: number) => {
  return request.delete(`/questions/${id}/`)
}
