/**
 * 时间显示工具：把后端返回的 ISO 时间格式化成更易读的形式。
 */

const pad2 = (value: number): string => String(value).padStart(2, '0')

/** 解析时间；无法解析（或空值）时返回 null */
const toDate = (value?: string | number | Date | null): Date | null => {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 绝对时间：2026-10-02 09:26:31 */
export const formatDateTime = (value?: string | number | Date | null): string => {
  const date = toDate(value)
  if (!date) return value ? String(value) : '-'
  return (
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ` +
    `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
  )
}

/**
 * 相对时间：刚刚 / 5 分钟前 / 3 小时前 / 2 天前。
 * 超过一周回退为绝对时间。
 *
 * `now` 默认为当前时间；页面可传入自己的「当前时间戳」并配合定时器刷新，
 * 这样相对时间会随时间自动更新。
 */
export const formatRelativeTime = (
  value?: string | number | Date | null,
  now: number = Date.now(),
): string => {
  const date = toDate(value)
  if (!date) return value ? String(value) : '-'

  const diff = now - date.getTime()
  if (diff < 0) return formatDateTime(date)
  if (diff < 60 * 1000) return '刚刚'
  if (diff < 60 * 60 * 1000) return `${Math.floor(diff / (60 * 1000))} 分钟前`
  if (diff < 24 * 60 * 60 * 1000) return `${Math.floor(diff / (60 * 60 * 1000))} 小时前`
  if (diff < 7 * 24 * 60 * 60 * 1000) return `${Math.floor(diff / (24 * 60 * 60 * 1000))} 天前`
  return formatDateTime(date)
}
