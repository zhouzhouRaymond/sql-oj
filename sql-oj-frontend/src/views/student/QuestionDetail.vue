<template>
  <div class="question-detail-container">
    <!-- 顶部导航 -->
    <div class="header">
      <el-button @click="goBack">← 返回题目列表</el-button>
      <h1>📝 题目详情</h1>
      <el-button
        class="my-submissions-btn"
        type="primary"
        plain
        size="small"
        @click="goToMySubmissions"
      >
        📝 我的提交
      </el-button>
    </div>

    <!-- 主要内容 -->
    <div v-loading="loading" class="content">
      <!-- 题目信息卡片 -->
      <el-card class="question-info">
        <template #header>
          <div class="card-header">
            <span class="question-title">{{ question.title || '未命名题目' }}</span>
            <el-tag :type="difficultyTagType(question.difficulty)">
              {{ difficultyText(question.difficulty) }}
            </el-tag>
          </div>
        </template>

        <!-- ✅ 题目描述：渲染 Markdown（右侧提供跳转到「我的提交」的入口） -->
        <div class="section">
          <div class="section-header">
            <h3>📖 题目描述</h3>
          </div>
          <div class="markdown-body" v-html="renderedDescription"></div>
        </div>

        <!-- ✅ 表结构预览：从建表语句中解析 -->
        <div v-if="tablePreview" class="section">
          <h3>📊 表结构预览</h3>
          <div class="table-preview">
            <el-table :data="tablePreview.rows" border stripe size="small">
              <el-table-column
                v-for="col in tablePreview.columns"
                :key="col"
                :prop="col"
                :label="col"
              />
            </el-table>
          </div>
        </div>

        <!-- ✅ 样例输入/输出：渲染 Markdown -->
        <div class="sample-row">
          <div class="sample-item">
            <h3>📥 样例输入</h3>
            <div class="markdown-body sample-content" v-html="renderedSampleInput"></div>
          </div>
          <div class="sample-item">
            <h3>📤 样例输出</h3>
            <div class="markdown-body sample-content" v-html="renderedSampleOutput"></div>
          </div>
        </div>

        <!-- ❌ 建表语句已隐藏，学生不需要看到 -->
      </el-card>

      <!-- SQL 编辑器 -->
      <el-card class="sql-editor">
        <template #header>
          <span>✏️ 编写你的 SQL</span>
        </template>
        <SqlEditor
          v-model="sqlCode"
          :min-height="240"
          placeholder="请输入你的 SQL 语句..."
        />
        <div class="actions">
          <el-button type="primary" @click="handleSubmit" :loading="submitting">
            🚀 提交判题
          </el-button>
          <el-button @click="resetCode">重置</el-button>
        </div>
      </el-card>

      <!-- 判题结果 -->
      <el-card v-if="result" class="result">
        <template #header>
          <span>📊 判题结果</span>
        </template>
        <div class="result-content">
          <div class="status">
            <span>状态：</span>
            <el-tag :type="statusTagType(result.execution_status)">
              {{ statusText(result.execution_status) }}
            </el-tag>
          </div>
          <div class="score">
            <span>得分：</span>
            <span class="score-value">{{ result.score ?? 0 }}</span>
          </div>
          <!-- 判题明细：判题错误时回显「未通过的测试用例」 -->
          <div v-if="result.judge_details" class="details">
            <h4>
              {{ result.execution_status === 'ACCEPTED' ? '✅ 用例通过情况' : '❌ 失败的测试用例' }}
            </h4>

            <!-- 整体执行失败（如建表语句报错、判题服务异常）时给出原因 -->
            <el-alert
              v-if="result.judge_details.error_message"
              class="detail-alert"
              type="warning"
              :closable="false"
              show-icon
              :title="result.judge_details.error_message"
            />

            <p class="detail-summary">
              共 {{ result.judge_details.total }} 个测试用例，通过
              {{ result.judge_details.passed_count }} 个。
            </p>

            <template v-if="failedCases.length > 0">
              <div
                v-for="caseItem in failedCases"
                :key="caseItem.index"
                class="failed-case"
              >
                <div class="failed-case-title">
                  <el-tag type="danger" size="small">用例 {{ caseItem.index }}</el-tag>
                  <span v-if="caseItem.error_message" class="case-error">
                    {{ caseItem.error_message }}
                  </span>
                  <span v-else class="case-hint">执行结果与预期不一致</span>
                </div>
                <div class="case-output">
                  <span class="label">你的输出：</span>
                  <pre>{{ caseItem.actual_output || '（空）' }}</pre>
                </div>
              </div>
              <p class="detail-note">
                为保护隐藏用例，此处不展示用例的输入与预期输出；可结合题目描述、样例与上表自行排查。
              </p>
            </template>
            <p v-else-if="!result.judge_details.total" class="detail-note">
              本次提交未记录用例明细（可能是较早的提交）。
            </p>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import { getQuestionDetail } from '../../api/questions'
import { getSubmission, submitSQL } from '../../api/submissions'
import SqlEditor from '../../components/SqlEditor.vue'

const route = useRoute()
const router = useRouter()
const questionId = computed(() => Number(route.params.id))

const loading = ref(false)
const submitting = ref(false)
const question = ref<any>({})
const sqlCode = ref('')
const result = ref<any>(null)

// ✅ 配置 marked 渲染选项
marked.setOptions({
  breaks: true,
  gfm: true,
  tables: true
})

// ✅ 渲染 Markdown 内容
const renderMarkdown = (text: string) => {
  if (!text) return ''
  return marked.parse(text)
}

// ✅ 渲染题目描述
const renderedDescription = computed(() => {
  return renderMarkdown(question.value.description || '暂无描述')
})

// ✅ 渲染样例输入
const renderedSampleInput = computed(() => {
  return renderMarkdown(question.value.sample_input || '无')
})

// ✅ 渲染样例输出
const renderedSampleOutput = computed(() => {
  return renderMarkdown(question.value.sample_output || '无')
})

// ✅ 从建表语句中解析表结构预览
const tablePreview = computed(() => {
  const sql = question.value.create_table_sql || ''
  // 简单解析：提取列名
  const match = sql.match(/CREATE\s+TABLE\s+\w+\s*\(([\s\S]*?)\)/i)
  if (!match) return null

  const columnsText = match[1]
  const columnLines = columnsText.split(',').map(s => s.trim())
  const columns: string[] = []
  const rows: Record<string, string>[] = [{}]

  columnLines.forEach(line => {
    const colMatch = line.match(/^\s*`?(\w+)`?\s+/)
    if (colMatch) {
      columns.push(colMatch[1])
      rows[0][colMatch[1]] = '—'
    }
  })

  if (columns.length === 0) return null

  return {
    columns,
    rows
  }
})

const loadQuestion = async () => {
  loading.value = true
  try {
    const res = await getQuestionDetail(questionId.value)
    question.value = res.data || {}
  } catch (error) {
    ElMessage.error('加载题目失败')
  } finally {
    loading.value = false
  }
}

const POLL_INTERVAL = 1500
const POLL_MAX_TRIES = 40 // 最长约 60s

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

// 判题已改为异步：提交后轮询该提交的状态，直到出结果（非 PENDING）
const pollResult = async (submissionId: number) => {
  for (let i = 0; i < POLL_MAX_TRIES; i++) {
    const res = await getSubmission(submissionId)
    result.value = res.data
    const status = res.data?.execution_status
    if (status && status !== 'PENDING') return
    await sleep(POLL_INTERVAL)
  }
  ElMessage.warning('判题耗时较长，请稍后在“我的提交”中查看结果')
}

const handleSubmit = async () => {
  if (!sqlCode.value.trim()) {
    ElMessage.warning('请输入 SQL 语句')
    return
  }

  submitting.value = true
  try {
    const res = await submitSQL({
      question_id: questionId.value,
      submitted_sql: sqlCode.value,
      exam_id: null
    })
    // 后端异步判题：先拿到 PENDING 的提交记录，再轮询最终结果
    result.value = res.data
    if (res.data?.id) {
      await pollResult(res.data.id)
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '提交失败')
  } finally {
    submitting.value = false
  }
}

const resetCode = () => {
  sqlCode.value = ''
  result.value = null
}

const goBack = () => {
  router.push('/questions')
}

// 跳转到「我的提交」页面（带上来源路径，便于在该页「返回」时回到本题详情）
const goToMySubmissions = () => {
  router.push({ path: '/submissions', query: { from: route.fullPath } })
}

const difficultyTagType = (difficulty: string) => {
  switch (difficulty) {
    case 'easy': return 'success'
    case 'medium': return 'warning'
    case 'hard': return 'danger'
    default: return 'info'
  }
}

const difficultyText = (difficulty: string) => {
  switch (difficulty) {
    case 'easy': return '简单'
    case 'medium': return '中等'
    case 'hard': return '困难'
    default: return difficulty || '未知'
  }
}

const statusTagType = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'danger'
    case 'ERROR': return 'danger'
    case 'TIMEOUT': return 'warning'
    case 'PENDING': return 'info'
    default: return 'info'
  }
}

const statusText = (status: string) => {
  if (!status || status === 'PENDING') return '判题中…'
  return status
}

// 判题明细中「未通过」的用例（后端仅返回序号 + 实际输出 + 错误信息）
const failedCases = computed(() => {
  const details = result.value?.judge_details
  return Array.isArray(details?.failed_cases) ? details.failed_cases : []
})

onMounted(() => {
  loadQuestion()
})
</script>

<style scoped>
.question-detail-container {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
}

.header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 20px;
  background: white;
  padding: 16px 24px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.header h1 {
  margin: 0;
  font-size: 20px;
  color: #2d3748;
}
/* 顶栏右侧操作按钮 */
.my-submissions-btn {
  margin-left: auto;
}

.content {
  max-width: 1000px;
  margin: 0 auto;
}

.question-info {
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.question-title {
  font-size: 18px;
  font-weight: 600;
  color: #2d3748;
}

.section {
  margin-top: 16px;
}
.section h3 {
  font-size: 15px;
  font-weight: 600;
  color: #2d3748;
  margin-bottom: 8px;
}
/* 区块标题行：左侧标题 + 右侧操作按钮 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.section-header h3 {
  margin: 0;
}

/* ✅ Markdown 渲染样式（与 GitHub 风格一致） */
.markdown-body {
  background-color: #f7fafc;
  padding: 16px;
  border-radius: 8px;
  border-left: 4px solid #409eff;
  line-height: 1.8;
  font-size: 15px;
  color: #2d3748;
  overflow-x: auto;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-size: 16px;
  font-weight: 600;
  margin: 12px 0 8px;
}
.markdown-body :deep(p) {
  margin: 8px 0;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 14px;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #d1d5db;
  padding: 8px 12px;
  text-align: left;
}
.markdown-body :deep(th) {
  background-color: #e5e7eb;
  font-weight: 600;
}
.markdown-body :deep(code) {
  background-color: #e5e7eb;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}
.markdown-body :deep(pre) {
  background-color: #1e293b;
  color: #e2e8f0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
  font-size: 13px;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

/* ✅ 样例区块使用稍浅的背景 */
.sample-content {
  background-color: #f7fafc;
  border-left-color: #e6a23c;
}

.sample-row {
  display: flex;
  gap: 16px;
  margin-top: 16px;
}
.sample-item {
  flex: 1;
}
.sample-item h3 {
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
  margin-bottom: 6px;
}

/* ✅ 表格预览 */
.table-preview {
  background-color: #f7fafc;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.table-preview .el-table {
  border-radius: 6px;
}

/* SQL 编辑器 */
.sql-editor {
  margin-bottom: 20px;
}
.actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

/* 判题结果 */
.result {
  margin-top: 20px;
}
.result-content {
  padding: 4px 0;
}
.status {
  margin-bottom: 12px;
}
.score {
  margin-bottom: 12px;
}
.score-value {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
}
.details h4 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
}
.detail-alert {
  margin-bottom: 10px;
}
.detail-summary {
  margin: 0 0 10px;
  color: #606266;
  font-size: 13px;
}
/* 未通过的用例：标题 + 实际输出 */
.failed-case {
  background-color: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
}
.failed-case-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.case-error {
  color: #f56c6c;
  font-size: 13px;
}
.case-hint {
  color: #909399;
  font-size: 13px;
}
.case-output .label {
  font-size: 13px;
  color: #606266;
}
.case-output pre {
  background-color: white;
  padding: 8px 12px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  margin: 4px 0 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}
.detail-note {
  margin: 4px 0 0;
  color: #909399;
  font-size: 12px;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .question-detail-container {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
  }
  .sample-row {
    flex-direction: column;
    gap: 12px;
  }
  .card-header {
    flex-wrap: wrap;
    gap: 8px;
  }
  .section-header {
    flex-wrap: wrap;
  }
}
</style>