import request from './request'

// 获取题目列表
export const getQuestions = (params?: { page?: number; ordering?: string }) => {
  return request.get('/questions/', { params })
}

// 获取全部题目：后端分页（每页 20 条），这里自动翻页取完。
// 供「考试组卷」等需要完整题目列表的下拉选择使用（否则只能选到前 20 道）。
export const getAllQuestions = async (): Promise<any[]> => {
  const all: any[] = []
  const maxPages = 100 // 保险上限，避免分页异常时死循环
  for (let page = 1; page <= maxPages; page += 1) {
    const res = await request.get('/questions/', { params: { page, ordering: 'id' } })
    const data = res.data || {}
    // 兼容后端未开启分页（直接返回数组）的情况
    if (Array.isArray(data)) return [...all, ...data]
    const list = data.results || []
    all.push(...list)
    if (!data.next || list.length === 0) break
  }
  return all
}

// 获取题目详情
export const getQuestionDetail = (id: number) => {
  return request.get(`/questions/${id}/`)
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