<template>
  <div class="sql-editor" :class="{ 'sql-editor--disabled': disabled }">
    <div class="sql-editor__toolbar">
      <span class="sql-editor__label">
        <span class="sql-editor__dot" />
        SQL 编辑器 · 语法高亮
      </span>
      <div class="sql-editor__actions">
        <el-button size="small" text type="primary" :disabled="disabled" @click="handleFormat">
          🪄 格式化
        </el-button>
      </div>
    </div>

    <!-- 高亮层（pre）与输入层（文字透明的 textarea）完全重叠，实现输入框内的实时语法高亮 -->
    <div class="sql-editor__viewport">
      <pre ref="preRef" class="sql-editor__highlight" aria-hidden="true"><code v-html="highlighted"></code></pre>
      <textarea
        ref="textareaRef"
        class="sql-editor__input"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :style="{ minHeight: `${minHeight}px` }"
        spellcheck="false"
        autocomplete="off"
        autocapitalize="off"
        @input="onInput"
        @scroll="syncScroll"
        @keydown="onKeydown"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus'

/**
 * SQL 代码编辑器（零依赖实现）
 * - 实时语法高亮：关键字 / 函数 / 字符串 / 数字 / 注释 / 运算符
 * - 一键格式化：统一关键字大小写与子句换行缩进（格式化前先屏蔽字符串与注释）
 * - v-model 双向绑定，支持禁用态与外部赋值（切换题目 / 重置）
 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    disabled?: boolean
    minHeight?: number
  }>(),
  {
    modelValue: '',
    placeholder: '请输入 SQL 语句...',
    disabled: false,
    minHeight: 220,
  },
)

const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

const preRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

/* ------------------------------ 词法定义 ------------------------------ */

const SQL_KEYWORDS = new Set(
  (
    'SELECT FROM WHERE GROUP BY ORDER HAVING LIMIT OFFSET UNION ALL INSERT INTO VALUES UPDATE SET ' +
    'DELETE CREATE TABLE VIEW INDEX DROP ALTER ADD COLUMN AS DISTINCT AND OR NOT NULL IS IN LIKE ' +
    'BETWEEN EXISTS CASE WHEN THEN ELSE END ASC DESC PRIMARY KEY FOREIGN REFERENCES DEFAULT ' +
    'CONSTRAINT UNIQUE CHECK ON JOIN INNER LEFT RIGHT FULL OUTER CROSS USING WITH RECURSIVE ROW ' +
    'OVER PARTITION ROWS RANGE IF TRUNCATE INTO INT INTEGER SMALLINT BIGINT DECIMAL NUMERIC FLOAT ' +
    'DOUBLE REAL CHAR VARCHAR TEXT DATE TIME DATETIME TIMESTAMP BOOLEAN'
  ).split(' '),
)

const SQL_FUNCTIONS = new Set(
  (
    'COUNT SUM AVG MIN MAX ROUND COALESCE IFNULL NULLIF ABS CEIL FLOOR MOD POWER SQRT CONCAT ' +
    'SUBSTRING SUBSTR LENGTH UPPER LOWER TRIM LTRIM RTRIM REPLACE INSTR LPAD RPAD NOW CURDATE ' +
    'CURTIME YEAR MONTH DAY HOUR MINUTE SECOND DATE_FORMAT DATEDIFF ROW_NUMBER RANK DENSE_RANK ' +
    'NTILE LAG LEAD FIRST_VALUE LAST_VALUE CAST CONVERT GROUP_CONCAT'
  ).split(' '),
)

/* 单次扫描分词：注释 / 字符串 / 数字 / 单词 / 运算符 / 空白 */
const TOKEN_RE =
  /(--[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)|('(?:''|\\[\s\S]|[^'\\])*'|"(?:[^"\\]|\\.)*"|`(?:[^`]|``)*`)|(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|([(),.;*+\-%/<=>!|&^~]+)|(\s+)/g

const escapeHtml = (value: string): string =>
  value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const highlight = (code: string): string => {
  if (!code) return ''
  let html = ''
  let last = 0
  let match: RegExpExecArray | null
  TOKEN_RE.lastIndex = 0

  while ((match = TOKEN_RE.exec(code)) !== null) {
    if (match.index > last) html += escapeHtml(code.slice(last, match.index))

    const [full, comment, str, num, word, operator] = match
    if (comment) {
      html += `<span class="tok-comment">${escapeHtml(full)}</span>`
    } else if (str) {
      html += `<span class="tok-string">${escapeHtml(full)}</span>`
    } else if (num) {
      html += `<span class="tok-number">${escapeHtml(full)}</span>`
    } else if (word) {
      const upper = word.toUpperCase()
      if (SQL_KEYWORDS.has(upper)) {
        html += `<span class="tok-keyword">${escapeHtml(full)}</span>`
      } else if (SQL_FUNCTIONS.has(upper)) {
        html += `<span class="tok-function">${escapeHtml(full)}</span>`
      } else {
        html += escapeHtml(full)
      }
    } else if (operator) {
      html += `<span class="tok-operator">${escapeHtml(full)}</span>`
    } else {
      html += escapeHtml(full)
    }

    last = match.index + full.length
  }

  if (last < code.length) html += escapeHtml(code.slice(last))
  // 末尾补一个换行，避免最后一行（空行）高度塌陷
  return `${html}\n`
}

const highlighted = computed(() => highlight(props.modelValue ?? ''))

/* ------------------------------ 格式化 ------------------------------ */

const MASK = '\u0000'

/** 用占位符替换字符串与注释，避免格式化破坏其内容 */
const maskLiterals = (sql: string): { masked: string; literals: string[] } => {
  const literals: string[] = []
  const masked = sql.replace(
    /--[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|'(?:''|[^'])*'|"(?:[^"]|"")*"|`(?:[^`]|``)*`/g,
    (literal) => `${MASK}${literals.push(literal) - 1}${MASK}`,
  )
  return { masked, literals }
}

const restoreLiterals = (sql: string, literals: string[]): string =>
  sql.replace(new RegExp(`${MASK}(\\d+)${MASK}`, 'g'), (_match, index: string) => literals[Number(index)] ?? '')

/** 需要独占一行的主要子句 */
const CLAUSE_PATTERN = new RegExp(
  '\\b(' +
    [
      'SELECT', 'FROM', 'WHERE', 'GROUP\\s+BY', 'ORDER\\s+BY', 'HAVING', 'LIMIT', 'OFFSET',
      'UNION\\s+ALL', 'UNION', 'INSERT\\s+INTO', 'VALUES', 'UPDATE', 'DELETE\\s+FROM', 'RETURNING',
      'INNER\\s+JOIN', 'LEFT\\s+JOIN', 'RIGHT\\s+JOIN', 'FULL\\s+JOIN', 'CROSS\\s+JOIN', 'JOIN',
    ].join('|') +
    ')\\b',
  'g',
)

const CONTINUATION_RE = /^(AND|OR|ON|UNION)\b/

const formatSql = (raw: string): string => {
  const source = raw.trim()
  if (!source) return raw

  const { masked, literals } = maskLiterals(source)

  // 1) 压缩空白  2) 关键字大写  3) 主要子句换行  4) 连接条件缩进
  let text = masked.replace(/\s+/g, ' ')
  text = text.replace(/[A-Za-z_][A-Za-z0-9_]*/g, (word) =>
    SQL_KEYWORDS.has(word.toUpperCase()) ? word.toUpperCase() : word,
  )
  text = text.replace(CLAUSE_PATTERN, (clause) => `\n${clause.toUpperCase()}`)

  const lines = text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line, index) => (index > 0 && CONTINUATION_RE.test(line) ? `  ${line}` : line))

  return restoreLiterals(lines.join('\n'), literals)
}

/* ------------------------------ 交互 ------------------------------ */

const handleFormat = () => {
  if (props.disabled) return
  const source = props.modelValue ?? ''
  if (!source.trim()) {
    ElMessage.warning('请先输入 SQL 语句')
    return
  }
  const formatted = formatSql(source)
  if (formatted === source) {
    ElMessage.info('SQL 已经是格式化状态')
    return
  }
  emit('update:modelValue', formatted)
}

const onInput = (event: Event) => {
  emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
}

const syncScroll = () => {
  if (!preRef.value || !textareaRef.value) return
  preRef.value.scrollTop = textareaRef.value.scrollTop
  preRef.value.scrollLeft = textareaRef.value.scrollLeft
}

const onKeydown = (event: KeyboardEvent) => {
  // Tab 插入两个空格（而不是切换焦点）
  if (event.key === 'Tab' && !event.shiftKey) {
    event.preventDefault()
    const textarea = textareaRef.value
    if (!textarea || props.disabled) return
    const { selectionStart, selectionEnd, value } = textarea
    const next = `${value.slice(0, selectionStart)}  ${value.slice(selectionEnd)}`
    emit('update:modelValue', next)
    nextTick(() => {
      textarea.selectionStart = selectionStart + 2
      textarea.selectionEnd = selectionStart + 2
    })
    return
  }

  // Shift + Alt + F 格式化
  if (event.altKey && event.shiftKey && event.key.toLowerCase() === 'f') {
    event.preventDefault()
    handleFormat()
  }
}
</script>

<style scoped>
.sql-editor {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
  background: #fbfcfe;
}

.sql-editor--disabled {
  opacity: 0.7;
}

.sql-editor__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.sql-editor__label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #909399;
}

.sql-editor__dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #67c23a;
}

.sql-editor__viewport {
  position: relative;
}

/* 高亮层与输入层必须使用完全一致的排版参数，文字才能逐字对齐 */
.sql-editor__highlight,
.sql-editor__input {
  margin: 0;
  padding: 12px 14px;
  border: 0;
  box-sizing: border-box;
  font-family: 'JetBrains Mono', Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  letter-spacing: normal;
  tab-size: 2;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  word-break: break-word;
}

.sql-editor__highlight {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  color: #24292f;
}

.sql-editor__input {
  position: relative;
  display: block;
  width: 100%;
  background: transparent;
  color: transparent;
  caret-color: #1f2937;
  resize: vertical;
  outline: none;
}

.sql-editor__input::placeholder {
  color: #a8abb2;
}

.sql-editor__input:disabled {
  cursor: not-allowed;
}

/* 语法着色（v-html 内容需用 :deep 才能命中 scoped 样式） */
.sql-editor__highlight :deep(.tok-keyword) {
  color: #0550ae;
  font-weight: 600;
}

.sql-editor__highlight :deep(.tok-function) {
  color: #8250df;
}

.sql-editor__highlight :deep(.tok-string) {
  color: #0a7d33;
}

.sql-editor__highlight :deep(.tok-number) {
  color: #b45309;
}

.sql-editor__highlight :deep(.tok-comment) {
  color: #94a3b8;
  font-style: italic;
}

.sql-editor__highlight :deep(.tok-operator) {
  color: #57606a;
}
</style>