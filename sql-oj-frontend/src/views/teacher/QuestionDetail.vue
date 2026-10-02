<template>
  <div class="teacher-question-detail">
    <div class="header">
      <el-button @click="goBack">← 返回题目管理</el-button>
      <h1>📝 题目详情（教师视图）</h1>
    </div>

    <div v-loading="loading" class="content">
      <el-card class="question-info">
        <template #header>
          <div class="card-header">
            <span class="question-title">{{ question.title || '未命名题目' }}</span>
            <el-tag :type="difficultyTagType(question.difficulty)">
              {{ difficultyText(question.difficulty) }}
            </el-tag>
          </div>
        </template>

        <!-- ✅ 教师视图：渲染 Markdown -->
        <div class="section">
          <h3>📖 题目描述</h3>
          <div class="markdown-body" v-html="renderedDescription"></div>
        </div>

        <!-- 建表语句（教师可见） 
        <div v-if="question.create_table_sql" class="section">
          <h3>📊 建表语句</h3>
          <pre class="sql-block">{{ question.create_table_sql }}</pre>
        </div>

        <!-- 样例输入/输出 -->
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

        <!-- 教师可见：参考答案 -->
        <div class="section answer-section">
          <el-collapse v-model="activePanels" class="detail-collapse">
            <el-collapse-item name="answers">
              <template #title>
                <span class="collapse-title">
                  🔑 参考答案
                  <span v-if="question.answers && question.answers.length > 0" class="collapse-count">
                    共 {{ question.answers.length }} 条
                  </span>
                </span>
              </template>
              <div v-if="question.answers && question.answers.length > 0">
                <div v-for="(ans, idx) in question.answers" :key="idx" class="answer-item">
                  <span class="answer-label">答案 {{ idx + 1 }}：</span>
                  <pre class="answer-sql">{{ ans.correct_sql }}</pre>
                </div>
              </div>
              <div v-else class="no-answer">
                <span style="color: #909399;">暂未设置参考答案</span>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- 教师可见：测试用例（默认折叠，点击标题展开） -->
        <div class="section test-cases-section">
          <el-collapse v-model="testCasePanels" class="detail-collapse">
            <el-collapse-item name="test-cases">
              <template #title>
                <span class="collapse-title">
                  🧪 测试用例
                  <span v-if="question.test_cases && question.test_cases.length > 0" class="collapse-count">
                    共 {{ question.test_cases.length }} 个
                  </span>
                </span>
              </template>
              <div v-if="question.test_cases && question.test_cases.length > 0">
                <div v-for="(tc, idx) in testCaseViews" :key="idx" class="test-case-item">
                  <span class="test-case-label">用例 {{ idx + 1 }}</span>
                  <div class="test-case-row">
                    <div>
                      <span class="label">测试输入：</span>
                      <pre>{{ tc.test_input || '（空）' }}</pre>
                    </div>
                    <div>
                      <span class="label">预期输出：</span>
                      <div
                        v-if="tc.expectedTable.columns.length > 0"
                        class="result-table-wrap"
                      >
                        <el-table
                          :data="tc.expectedTable.rows"
                          border
                          size="small"
                          :style="{ minWidth: tableMinWidth(tc.expectedTable) }"
                        >
                          <el-table-column
                            v-for="col in tc.expectedTable.columns"
                            :key="col.prop"
                            :prop="col.prop"
                            :label="col.label"
                            min-width="120"
                          />
                        </el-table>
                      </div>
                      <pre v-else>{{ tc.expected_output || '（空）' }}</pre>
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="no-answer">
                <span style="color: #909399;">暂未设置测试用例</span>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- 教师可见：本题数据统计（可选时间段，动态获取） -->
        <div class="section stats-section">
          <h3>📊 数据统计</h3>
          <div class="stats-toolbar">
            <el-date-picker
              v-model="dateRange"
              type="datetimerange"
              value-format="YYYY-MM-DD HH:mm"
              format="YYYY-MM-DD HH:mm"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              :default-time="defaultTime"
              :shortcuts="dateShortcuts"
              :clearable="true"
              @change="scheduleStatsLoad"
            />
            <!-- 手动查询：force=true 强制重新拉取，不受节流/去重限制 -->
            <el-button type="primary" :loading="statsLoading" @click="loadStats(true)">查询</el-button>
            <el-button v-if="dateRange" text @click="clearDateRange">全部时间</el-button>
          </div>

          <div v-loading="statsLoading" class="overview-stats">
            <div class="stat-card">
              <div class="stat-value">{{ stats.total_submissions }}</div>
              <div class="stat-label">提交次数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ stats.distinct_submissions }}</div>
              <div class="stat-label">提交人数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ passRatePercent }}%</div>
              <div class="stat-label">通过率</div>
            </div>
          </div>

          <!-- 刷新反馈：显示本次统计实际生效的时间段与刷新时刻，便于确认是否已更新 -->
          <div class="stats-meta">
            <span>实际统计：{{ appliedRangeText }}</span>
            <span v-if="lastUpdated">· 最近更新 {{ lastUpdated }}</span>
            <span v-if="statsLoaded && stats.total_submissions === 0" class="stats-empty">
              · 该时间段内暂无提交
            </span>
          </div>

          <!-- 🏆 该时间段内本题的学生通过率排名 -->
          <div v-loading="statsLoading" class="ranking-block">
            <h4 class="ranking-title">
              🏆 学生通过率排名（本题 · 当前时间段）
              <span class="ranking-tip">点击学生姓名可查看其提交记录</span>
            </h4>
            <el-table v-if="ranking.length > 0" :data="ranking" stripe size="small" max-height="320">
              <el-table-column label="排名" width="70" align="center">
                <template #default="{ $index }">
                  <span :class="{ 'top-rank': $index < 3 }">{{ $index + 1 }}</span>
                </template>
              </el-table-column>
              <el-table-column label="学生" min-width="120">
                <template #default="{ row }">
                  <!-- 点击学生姓名 → 查看该学生本时间段内本题的提交记录 -->
                  <el-button type="primary" link @click="openStudentSubmissions(row)">
                    {{ row.student_name }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column label="通过率" width="160">
                <template #default="{ row }">
                  <el-progress :percentage="row.passRatePercent" :stroke-width="8" />
                </template>
              </el-table-column>
              <el-table-column prop="accepted" label="通过提交数" width="100" align="center" />
              <el-table-column prop="total" label="提交次数" width="90" align="center" />
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.passed ? 'success' : 'info'" size="small">
                    {{ row.passed ? '已通过' : '未通过' }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
            <div v-else class="ranking-empty">该时间段内暂无学生提交，暂无排名数据</div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 👤 学生提交记录下钻：点排名表中的学生姓名打开（时间段与上方统计口径一致） -->
    <el-dialog
      v-model="studentDialogVisible"
      :title="studentDialogTitle"
      width="880px"
      top="8vh"
      @closed="resetStudentDialog"
    >
      <div class="student-sub-summary">
        <span>该时间段内提交次数：<b>{{ currentStudent.total }}</b></span>
        <span>通过提交数：<b>{{ currentStudent.accepted }}</b></span>
        <span>通过率：<b>{{ currentStudent.passRatePercent }}%</b></span>
        <span>时间段：{{ appliedRangeText }}</span>
      </div>

      <el-table
        v-loading="studentSubLoading"
        :data="studentSubmissions"
        :row-key="(row: any) => row.id"
        stripe
        size="small"
        max-height="440"
        @expand-change="onRowExpand"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-detail">
              <div class="expand-item">
                <strong>提交的 SQL：</strong>
                <pre class="sql-block">{{ row.__loading ? '加载中…' : (row.submitted_sql || '（空）') }}</pre>
              </div>
              <!-- 与「我的提交记录」共用同一判题明细组件（表格化展示） -->
              <SubmissionCaseDetail v-if="!row.__loading" :detail="row" />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="提交ID" width="90" />
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.execution_status)">
              {{ row.execution_status || 'PENDING' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="得分" width="80" />
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <span>{{ row.exam ? `考试 #${row.exam}` : '练习' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" min-width="160">
          <template #default="{ row }">
            <span :title="formatDateTime(row.submission_time)">
              {{ formatDateTime(row.submission_time) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!studentSubLoading && studentSubmissions.length === 0" class="ranking-empty">
        该时间段内该学生没有本题的提交记录
      </div>

      <div class="pagination">
        <el-pagination
          v-model:current-page="studentSubPage"
          :page-size="studentSubPageSize"
          :total="studentSubTotal"
          layout="prev, pager, next"
          @current-change="loadStudentSubmissions"
        />
      </div>
      <div class="ranking-tip">提示：展开某一行可查看该次提交的 SQL 与判题明细</div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import { getQuestionDetail } from '../../api/questions'
import { getQuestionSubmissionStats } from '../../api/stats'
import { getSubmission, getSubmissions } from '../../api/submissions'
import { formatDateTime } from '../../utils/time'
import { parseResultSet } from '../../utils/resultSet'
import SubmissionCaseDetail from '../../components/SubmissionCaseDetail.vue'

const route = useRoute()
const router = useRouter()
const questionId = computed(() => Number(route.params.id))

const loading = ref(false)
const question = ref<any>({})

// 测试用例的展示数据：把「预期输出」解析成表格（可能很宽，由外层容器横向滚动）
const testCaseViews = computed(() =>
  (question.value?.test_cases || []).map((tc: any) => ({
    ...tc,
    expectedTable: parseResultSet(tc.expected_output || '')
  }))
)

// 表格最小宽度：列多时保持宽度，由外层容器横向滚动
const tableMinWidth = (table: { columns: unknown[] }) =>
  `${Math.max((table?.columns?.length || 0) * 140, 320)}px`

// 🔑 参考答案 / 📥📤 样例 / 🧪 测试用例 默认折叠（空数组=收起），点击标题后才展开显示
const activePanels = ref<string[]>([])
const sampleInputPanels = ref<string[]>([])
const sampleOutputPanels = ref<string[]>([])
const testCasePanels = ref<string[]>([])

// 📊 本题数据统计：时间段筛选 + 动态获取（null = 全部时间）
const dateRange = ref<[string, string] | null>(null)
const statsLoading = ref(false)
const stats = ref({
  total_submissions: 0,
  distinct_submissions: 0,
  accepted_submissions: 0,
  passed_students: 0,
  pass_rate: 0,
  student_pass_rate: 0
})

// 时间段偏移工具（精确到分钟）
const minutesBefore = (minutes: number) => new Date(Date.now() - minutes * 60 * 1000)
const minutesAfter = (minutes: number) => new Date(Date.now() + minutes * 60 * 1000)

// 只选日期没选时间时：开始时间用 00:00，结束时间用 23:59
const defaultTime: [Date, Date] = [
  new Date(2000, 0, 1, 0, 0, 0),
  new Date(2000, 0, 1, 23, 59, 0)
]

// 常用时间段快捷选项（滚动窗口，精确到分钟）
const dateShortcuts = [
  { text: '最近 1 小时', value: () => [minutesBefore(60), new Date()] },
  { text: '最近 24 小时', value: () => [minutesBefore(24 * 60), new Date()] },
  { text: '最近 7 天', value: () => [minutesBefore(7 * 24 * 60), new Date()] },
  { text: '最近 30 天', value: () => [minutesBefore(30 * 24 * 60), new Date()] },
  { text: '最近 90 天', value: () => [minutesBefore(90 * 24 * 60), new Date()] },
  // 未来 1 小时：从现在到一小时后（用于观察即将开始的考试/活动时间窗）
  { text: '未来 1 小时', value: () => [new Date(), minutesAfter(60)] }
]

// 本次统计实际生效的时间段 / 刷新时刻 / 是否已加载过
const appliedRange = ref<{ start: string; end: string } | null>(null)
// 本次统计实际生效的时间段原始值：下钻「学生提交记录」时按同一时间窗过滤
const appliedRangeRaw = ref<{ start: string; end: string } | null>(null)
const lastUpdated = ref('')
const statsLoaded = ref(false)

const appliedRangeText = computed(() => {
  if (!appliedRange.value) return '全部时间'
  return `${appliedRange.value.start} ~ ${appliedRange.value.end}`
})

// el-date-picker 在面板操作过程中会连续触发 change，这里做防抖，避免一次选择发出几十个请求
let statsTimer: ReturnType<typeof setTimeout> | null = null
let statsSeq = 0           // 请求序号：只采用最后一次发出的请求结果
let statsInFlightKey = ''  // 正在请求中的查询条件
let statsAppliedKey = ''   // 结果已生效的查询条件

const buildStatsKey = (start: string, end: string) => `${questionId.value}|${start}|${end}`
const formatServerTime = (value: any) => (value ? String(value).slice(0, 16).replace('T', ' ') : '')

// 选择时间段后延迟 600ms 再请求（面板滚动/中间态都会触发 change）
const scheduleStatsLoad = () => {
  if (statsTimer) clearTimeout(statsTimer)
  statsTimer = setTimeout(() => {
    statsTimer = null
    loadStats()
  }, 600)
}

// 清空时间段 → 统计全部时间
const clearDateRange = () => {
  dateRange.value = null
  loadStats(true)
}

// 后端返回 0~1 的小数，统一转成百分比整数
const toPercent = (rate: any): number => {
  const raw = Number(rate) || 0
  if (raw > 1.01) return Math.round(raw)
  return Math.round(raw * 100)
}

const passRatePercent = computed(() => toPercent(stats.value.pass_rate))
const studentPassRatePercent = computed(() => toPercent(stats.value.student_pass_rate))

// 🏆 当前时间段内本题的学生通过率排名（与汇总数据同一次请求返回，口径一致）
const ranking = ref<any[]>([])

const normalizeRanking = (list: any): any[] =>
  (Array.isArray(list) ? list : []).map((item: any) => ({
    student_id: item.student_id,
    // 展示用用户名（自定义用户名，为空时后端回退为登录名）
    student_name: item.name || item.username || `用户 ${item.student_id}`,
    total: Number(item.total_submissions) || 0,
    accepted: Number(item.accepted_submissions) || 0,
    passRatePercent: toPercent(item.pass_rate),
    passed: Boolean(item.passed ?? Number(item.accepted_submissions) > 0)
  }))

/**
 * 拉取本题统计。
 * force=false：条件未变化（已在请求中 / 结果已生效）时跳过，避免重复请求；
 * force=true：点击「查询」按钮时强制刷新。
 */
const loadStats = async (force = false) => {
  if (!questionId.value) return
  const [start, end] = dateRange.value || []
  const key = buildStatsKey(start || '', end || '')
  if (statsInFlightKey === key) return
  if (!force && statsAppliedKey === key) return

  const seq = ++statsSeq
  statsInFlightKey = key
  statsLoading.value = true
  try {
    const res = await getQuestionSubmissionStats({
      question_id: questionId.value,
      start: start || undefined,
      end: end || undefined
    })
    // 已有更新的请求发出时，丢弃这次的结果，避免旧数据覆盖新数据
    if (seq !== statsSeq) return
    const data = res.data || {}
    stats.value = {
      total_submissions: Number(data.total_submissions) || 0,
      distinct_submissions: Number(data.distinct_submissions) || 0,
      accepted_submissions: Number(data.accepted_submissions) || 0,
      passed_students: Number(data.passed_students) || 0,
      pass_rate: Number(data.pass_rate) || 0,
      student_pass_rate: Number(data.student_pass_rate) || 0
    }
    appliedRange.value = data.start
      ? { start: formatServerTime(data.start), end: formatServerTime(data.end) }
      : null
    appliedRangeRaw.value = data.start
      ? { start: String(data.start), end: String(data.end || '') }
      : null
    ranking.value = normalizeRanking(data.student_ranking)
    statsAppliedKey = key
    statsLoaded.value = true
    lastUpdated.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } catch (error) {
    if (seq === statsSeq) ElMessage.error('加载统计数据失败')
  } finally {
    if (seq === statsSeq) {
      statsLoading.value = false
      statsInFlightKey = ''
    }
  }
}

// 👤 学生提交记录下钻：点排名表中的学生姓名，查看该学生本时间段内本题的提交
const studentDialogVisible = ref(false)
const studentSubLoading = ref(false)
const studentSubPage = ref(1)
const studentSubPageSize = 20
const studentSubTotal = ref(0)
const studentSubmissions = ref<any[]>([])
const currentStudent = ref<any>({
  student_id: 0,
  student_name: '',
  total: 0,
  accepted: 0,
  passRatePercent: 0
})

const studentDialogTitle = computed(
  () => `${currentStudent.value.student_name || '学生'} · 本题提交记录（${appliedRangeText.value}）`
)

const statusTagType = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'danger'
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
}

const openStudentSubmissions = (row: any) => {
  if (!row?.student_id) return
  currentStudent.value = row
  studentSubPage.value = 1
  studentDialogVisible.value = true
  loadStudentSubmissions()
}

// 拉取该学生在「本次统计生效时间段」内本题的提交列表
const loadStudentSubmissions = async () => {
  studentSubLoading.value = true
  try {
    const res = await getSubmissions({
      question_id: questionId.value,
      student_id: currentStudent.value.student_id,
      start: appliedRangeRaw.value?.start || undefined,
      end: appliedRangeRaw.value?.end || undefined,
      page: studentSubPage.value
    })
    studentSubmissions.value = (res.data.results || []).map((row: any) => ({
      ...row,
      __loading: false,
      __loaded: false
    }))
    studentSubTotal.value = res.data.count || 0
  } catch (error) {
    ElMessage.error('加载该学生的提交记录失败')
  } finally {
    studentSubLoading.value = false
  }
}

// 展开某一行时才按 id 懒加载完整详情（列表接口不返回 submitted_sql 与判题明细）
const onRowExpand = async (row: any, expandedRows?: any) => {
  const expanded: any[] = Array.isArray(expandedRows) ? expandedRows : []
  if (!expanded.some((item: any) => item?.id === row?.id)) return
  if (row.__loaded || row.__loading) return
  row.__loading = true
  try {
    const res = await getSubmission(row.id)
    const detail = res.data || {}
    row.submitted_sql = detail.submitted_sql || ''
    row.judge_details = detail.judge_details || null
    row.execution_status = detail.execution_status || row.execution_status
    row.score = detail.score ?? row.score
    row.__loaded = true
  } catch (error) {
    ElMessage.error('加载提交详情失败')
  } finally {
    row.__loading = false
  }
}

// 关闭弹窗时清空，避免下次打开先看到上一个学生的数据
const resetStudentDialog = () => {
  studentSubmissions.value = []
  studentSubTotal.value = 0
  studentSubPage.value = 1
}

// ✅ 配置 marked 渲染选项
marked.setOptions({
  breaks: true,
  gfm: true,
  tables: true
})

const renderMarkdown = (text: string) => {
  if (!text) return ''
  return marked.parse(text)
}

const renderedDescription = computed(() => {
  return renderMarkdown(question.value.description || '暂无描述')
})

const renderedSampleInput = computed(() => {
  return renderMarkdown(question.value.sample_input || '无')
})

const renderedSampleOutput = computed(() => {
  return renderMarkdown(question.value.sample_output || '无')
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

const goBack = () => {
  router.push('/teacher/questions')
}

const difficultyTagType = (diff: string) => {
  switch (diff) {
    case 'easy': return 'success'
    case 'medium': return 'warning'
    case 'hard': return 'danger'
    default: return 'info'
  }
}

const difficultyText = (diff: string) => {
  switch (diff) {
    case 'easy': return '简单'
    case 'medium': return '中等'
    case 'hard': return '困难'
    default: return diff || '未知'
  }
}

onMounted(() => {
  // 默认统计「全部时间」的历史提交（不传时间段），可在工具栏切换时间窗
  loadQuestion()
  loadStats(true)
})

onUnmounted(() => {
  // 离开页面时清掉待执行的防抖任务
  if (statsTimer) clearTimeout(statsTimer)
  statsTimer = null
})
</script>

<style scoped>
.teacher-question-detail {
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

/* ✅ Markdown 样式 */
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
  font-size: 14px;
}
.markdown-body :deep(pre) {
  background-color: #1e293b;
  color: #e2e8f0;
  padding: 12px 16px;
  border-radius: 8px;
  overflow-x: auto;
  font-family: 'Courier New', monospace;
  font-size: 14px;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
}

.sample-content {
  background-color: #f7fafc;
  border-left-color: #e6a23c;
}

.sample-row {
  /* 样例输入 / 样例输出 上下排列（与学生题目详情页保持一致） */
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}
.sample-item {
  /* 单列布局下占满整栏，宽样例表格不再被挤成半栏 */
  width: 100%;
}

.sql-block,
.answer-sql {
  background-color: #1e293b;
  color: #e2e8f0;
  padding: 12px 16px;
  border-radius: 8px;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  border: none;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}

.answer-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}
.answer-item {
  margin-bottom: 8px;
}
.answer-label {
  font-weight: 500;
  color: #2d3748;
  display: block;
  margin-bottom: 4px;
}

/* 🔑 参考答案 / 📥📤 样例：折叠面板去掉默认边框，标题样式与其它小节标题保持一致 */
.detail-collapse {
  border-top: none;
}
.detail-collapse :deep(.el-collapse-item__header) {
  height: 40px;
  line-height: 40px;
  font-size: 15px;
  font-weight: 600;
  color: #2d3748;
  background-color: transparent;
  border-bottom: none;
}
.detail-collapse :deep(.el-collapse-item__wrap) {
  background-color: transparent;
  border-bottom: none;
}
.detail-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}

/* 样例面板：标题沿用原来的 14px 小标题尺寸，内容与标题间留一点间距 */
.sample-collapse :deep(.el-collapse-item__header) {
  height: 34px;
  line-height: 34px;
  font-size: 14px;
}
.sample-collapse :deep(.el-collapse-item__content) {
  padding-top: 4px;
}
.collapse-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
/* 折叠面板标题右侧的数量提示（参考答案 / 测试用例共用） */
.collapse-count {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}

.test-cases-section {
  margin-top: 16px;
}
.test-case-item {
  background-color: #f7fafc;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 8px;
  border: 1px solid #e2e8f0;
}
.test-case-label {
  font-weight: 600;
  color: #2d3748;
  display: block;
  margin-bottom: 6px;
}
.test-case-row {
  /* 测试输入 / 预期输出 上下排列（预期输出多为表格，占满整栏更易读） */
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.test-case-row > div {
  width: 100%;
}
.test-case-row .label {
  font-size: 13px;
  color: #606266;
}
.test-case-row pre {
  background-color: white;
  padding: 8px 12px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  margin: 4px 0 0;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-all;
}
/* 预期输出用表格展示：宽表格交给外层容器横向滚动 */
.result-table-wrap {
  margin-top: 4px;
  overflow-x: auto;
  border-radius: 6px;
}
.result-table-wrap .el-table {
  border-radius: 6px;
}
.no-answer {
  padding: 12px;
  background-color: #f7fafc;
  border-radius: 8px;
}

/* 📊 数据统计 */
.stats-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}
.stats-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.stats-meta {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}
.stats-empty {
  color: #e6a23c;
}
.overview-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.stat-card {
  flex: 1;
  min-width: 140px;
  padding: 16px;
  text-align: center;
  background-color: #f7fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: #409eff;
}
.stat-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}
.stats-extra {
  margin-top: 10px;
  color: #909399;
  font-size: 13px;
}

/* 🏆 学生通过率排名 */
.ranking-block {
  margin-top: 16px;
}
.ranking-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
}
.ranking-block :deep(.el-table .cell) {
  font-size: 14px;
}
.ranking-empty {
  padding: 12px;
  background-color: #f7fafc;
  border-radius: 8px;
  color: #909399;
  font-size: 13px;
  text-align: center;
}
.top-rank {
  font-weight: 700;
  color: #e6a23c;
}

/* 👤 学生提交记录下钻弹窗 */
.student-sub-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
  color: #606266;
  font-size: 13px;
}
.student-sub-summary b {
  color: #409eff;
}
.expand-detail {
  padding: 8px 12px;
  background-color: #f7fafc;
  border-radius: 6px;
}
.expand-item {
  margin-bottom: 8px;
}
.expand-detail .sql-block {
  max-height: 220px;
  overflow-y: auto;
}
.pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.ranking-tip {
  margin-left: 8px;
  font-weight: 400;
  font-size: 12px;
  color: #909399;
}
/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .teacher-question-detail {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
  }
  .card-header {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>