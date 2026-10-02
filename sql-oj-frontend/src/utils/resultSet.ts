/**
 * 解析判题服务返回的结果集文本，供前端渲染成表格。
 *
 * 判题服务输出的格式为：`列1|列2\n值1|值2\n值3|值4`
 * （第一行列名，之后每行一条记录，列之间用 `|` 分隔）。
 * 列名可能重复，因此行数据用「列下标」作为键，避免 prop 冲突。
 */
export interface ResultSetColumn {
  prop: string
  label: string
}

export interface ResultSetTable {
  columns: ResultSetColumn[]
  rows: Record<string, string>[]
}

export const parseResultSet = (text: string): ResultSetTable => {
  const empty: ResultSetTable = { columns: [], rows: [] }
  if (!text) return empty

  const lines = text.replace(/\r\n/g, '\n').split('\n')
  // 结果集通常以换行结尾：去掉末尾空行；中间的空行保留（可能是空字符串数据）
  while (lines.length > 0 && lines[lines.length - 1] === '') lines.pop()
  if (lines.length === 0) return empty

  const headers = lines[0].split('|')
  const columns: ResultSetColumn[] = headers.map((header, index) => ({
    prop: `col_${index}`,
    label: header || `列 ${index + 1}`
  }))

  const rows = lines.slice(1).map((line) => {
    const values = line.split('|')
    const row: Record<string, string> = {}
    headers.forEach((_, index) => {
      row[`col_${index}`] = values[index] ?? ''
    })
    return row
  })

  return { columns, rows }
}
