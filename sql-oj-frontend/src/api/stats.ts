import request from './request'

// 整体数据概览
export const getOverview = () => {
  return request.get('/stats/overview/')
}

// 题目通过率统计
export const getQuestionStats = () => {
  return request.get('/stats/questions/')
}

// 学生通过率排名
export const getStudentStats = () => {
  return request.get('/stats/students/')
}

// 单题提交统计（教师可见）：start/end 传 "YYYY-MM-DD HH:mm"（精确到分钟）
// 或 "YYYY-MM-DD"；不传则统计全部时间
export const getQuestionSubmissionStats = (params: {
  question_id: number
  start?: string
  end?: string
}) => {
  return request.get('/stats/question/', { params })
}