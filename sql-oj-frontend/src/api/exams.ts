import request from './request'

// 获取考试列表
export const getExams = () => {
  return request.get('/exams/')
}

// 获取全部考试：后端分页（每页 20 条），这里自动翻页取完。
// 学生「我的考试」/ 教师考试列表都可能超过一页，否则会漏考试。
export const getAllExams = async (): Promise<any[]> => {
  const all: any[] = []
  const maxPages = 100 // 保险上限，避免分页异常时死循环
  for (let page = 1; page <= maxPages; page += 1) {
    const res = await request.get('/exams/', { params: { page } })
    const data = res.data || {}
    // 兼容后端未开启分页（直接返回数组）的情况
    if (Array.isArray(data)) return [...all, ...data]
    const list = data.results || []
    all.push(...list)
    if (!data.next || list.length === 0) break
  }
  return all
}

// 创建考试
export const createExam = (data: {
  title: string
  start_time: string
  end_time: string
  total_score: number
  exam_questions: { question: number; score: number }[]
}) => {
  return request.post('/exams/', data)
}

// 删除考试
export const deleteExam = (id: number) => {
  return request.delete(`/exams/${id}/`)
}

// 获取考试排名
export const getExamResult = (id: number) => {
  return request.get(`/exams/${id}/result/`)
}

// 开始考试
export const startExam = (id: number) => {
  return request.post(`/exams/${id}/start/`)
}

// 同步作答草稿到服务端：换设备 / 换浏览器可恢复作答；
// 到点未交卷时服务端会按这份草稿兜底交卷（避免成绩漏掉）
export const saveExamDraft = (examId: number, answers: Record<number, string>) => {
  return request.post(`/exams/${examId}/draft/`, { answers })
}

// 提交考试答案（学生端用）
export const submitExam = (examId: number, answers: { question_id: number; submitted_sql: string }[]) => {
  return request.post(`/exams/${examId}/submit/`, { answers })
}

// 更新考试
export const updateExam = (id: number, data: any) => {
  return request.put(`/exams/${id}/`, data)
}

// 局部更新考试（例如切换「学生可见」开关，只提交变化的字段）
export const patchExam = (id: number, data: any) => {
  return request.patch(`/exams/${id}/`, data)
}

// 导出考试成绩单（CSV）：仅考试结束后可用，返回文件流
export const exportExamScores = (id: number) => {
  return request.get(`/exams/${id}/export/`, { responseType: 'blob' })
}

// 重置某位学生在本场考试的作答记录（教师端「重置考试次数」）
export const resetExamAttempt = (examId: number, studentId: number) => {
  return request.post(`/exams/${examId}/reset-attempt/`, { student_id: studentId })
}

// 当前学生每场考试的得分（同一题多次提交只取最高分后求和），键为考试 id。
// 学生端「我的考试」用它展示「得分」列，并据此判断该生是否已参加过某场考试。
export const getMyExamScores = async (): Promise<Record<number, number>> => {
  const res = await request.get('/exams/my-scores/')
  const raw = res.data?.scores || {}
  const scores: Record<number, number> = {}
  Object.entries(raw).forEach(([examId, score]) => {
    scores[Number(examId)] = Number(score) || 0
  })
  return scores
}