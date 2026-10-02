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

// 提交列表：可按题目 / 学生 / 考试 / 时间段过滤（教师端「学生提交记录」「考试提交情况」下钻用）。
// student_id 仅教师有效（学生只能看到自己的提交）。
export const getSubmissions = (params?: {
  question_id?: number
  student_id?: number
  exam?: number
  start?: string
  end?: string
  page?: number
}) => {
  return request.get('/submissions/', { params })
}

// 某场考试的全部提交（学生端自动限定为本人；教师端为所有学生）。
// 后端分页每页 20 条，这里自动翻页取全量，供教师端「提交情况」展示。
export const getExamSubmissions = async (examId: number): Promise<any[]> => {
  const all: any[] = []
  const maxPages = 100 // 保险上限，避免分页异常时死循环
  for (let page = 1; page <= maxPages; page += 1) {
    const res = await request.get('/submissions/', { params: { exam: examId, page } })
    const data = res.data || {}
    // 兼容后端未开启分页（直接返回数组）的情况
    if (Array.isArray(data)) return [...all, ...data]
    const list = data.results || []
    all.push(...list)
    if (!data.next || list.length === 0) break
  }
  return all
}