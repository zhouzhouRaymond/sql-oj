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

export const getSubmissions = (params?: { question_id?: number; page?: number }) => {
  return request.get('/submissions/', { params })
}