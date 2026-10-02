/**
 * 本地作答草稿：把未提交的编辑内容暂存到浏览器，
 * 刷新 / 误关页面后重新进入即可恢复。
 *
 * - 按「用途 + 登录名 + 对象 id」隔离，换账号 / 换题目 / 换考试都不会串味；
 * - localStorage 不可用（隐私模式 / 配额已满）时静默降级，不影响正常作答。
 */

export type DraftKind = 'exam' | 'question'

/** 草稿 key：exam_draft_<登录名>_<id> / question_draft_<登录名>_<id> */
export const buildDraftKey = (
  kind: DraftKind,
  username: string | undefined,
  id: number | string,
) => `${kind}_draft_${username || 'anon'}_${id}`

/**
 * 保存草稿。支持两种取值：
 * - 字符串（如单题 SQL 代码）
 * - 键值对象（如考试中「题目 id → SQL」的作答表）
 * 内容全为空时删除记录，避免留下空草稿。
 */
export const saveDraft = (key: string, value: unknown) => {
  try {
    const items =
      typeof value === 'string'
        ? [value]
        : Object.values((value ?? {}) as Record<string, unknown>)
    const hasContent = items.some((item) => String(item ?? '').trim() !== '')
    if (!hasContent) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 写入失败（隐私模式 / 配额已满）时忽略
  }
}

/** 读取草稿；无内容或解析失败时返回 null */
export const loadDraft = <T = unknown>(key: string): T | null => {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed === null || parsed === undefined ? null : (parsed as T)
  } catch {
    return null
  }
}

/** 删除单个草稿 */
export const clearDraft = (key: string) => {
  try {
    localStorage.removeItem(key)
  } catch {
    // 忽略
  }
}

/** 清理某个用户在本机的全部作答草稿（登出时调用，避免换账号后残留） */
export const clearUserDrafts = (username: string | undefined) => {
  if (!username) return
  try {
    const prefixes = [`exam_draft_${username}_`, `question_draft_${username}_`]
    Object.keys(localStorage)
      .filter((key) => prefixes.some((prefix) => key.startsWith(prefix)))
      .forEach((key) => localStorage.removeItem(key))
  } catch {
    // 忽略
  }
}
