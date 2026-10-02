import request from './request'

/**
 * 分页接口「自动翻页取全量」。
 *
 * 后端列表接口每页 20 条，考试 / 题目 / 提交列表都可能超过一页，漏页会丢数据；
 * 这里统一处理两个细节，避免各 api 文件重复实现：
 *
 * - 兼容后端未开启分页（直接返回数组）的情况；
 * - 设保险上限，避免分页字段异常时死循环。
 */
export const MAX_PAGES = 100

export const fetchAllPages = async <T = any>(
  url: string,
  params: Record<string, any> = {},
): Promise<T[]> => {
  const all: T[] = []
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const res = await request.get(url, { params: { ...params, page } })
    const data = res.data || {}
    if (Array.isArray(data)) return [...all, ...data]
    const list: T[] = data.results || []
    all.push(...list)
    if (!data.next || list.length === 0) break
  }
  return all
}
