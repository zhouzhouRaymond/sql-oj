/**
 * 判题状态展示：各页面（我的提交 / 题目详情 / 考试情况）统一从这里取标签颜色与文案。
 *
 * 后端可能返回 ACCEPTED / WRONG_ANSWER / TIMEOUT / ERROR / PENDING；
 * 此前每个页面各写了一份 switch，容易改一处漏一处，这里收敛为唯一来源。
 */

/** el-tag 支持的状态色 */
export type StatusTagType = 'success' | 'danger' | 'warning' | 'info'

/** 状态码 → 标签颜色 */
export const statusTagType = (status?: string | null): StatusTagType => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'danger'
    case 'ERROR': return 'danger'
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
}

/** 状态码 → 中文文案（PENDING / 空值统一显示为「判题中」） */
export const statusText = (status?: string | null): string => {
  switch (status) {
    case 'ACCEPTED': return '通过'
    case 'WRONG_ANSWER': return '答案错误'
    case 'ERROR': return '运行错误'
    case 'TIMEOUT': return '超时'
    case 'PENDING': return '判题中'
    default: return status || '判题中'
  }
}
