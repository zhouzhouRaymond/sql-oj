<template>
  <div class="exam-list-container">
    <PageHeader
      title="📋 我的考试"
      subtitle="进入考试后按考试时长倒计时，倒计时结束会自动交卷；作答内容会自动暂存"
      :welcome="userStore.displayName"
    >
      <template #actions>
        <!-- 学生端统一的四个功能入口 + 退出（见 StudentNav 组件） -->
        <StudentNav />
      </template>
    </PageHeader>

    <el-tabs v-model="activeTab" class="exam-tabs">
      <el-tab-pane :label="currentTabLabel" name="current" />
      <el-tab-pane :label="historyTabLabel" name="history" />
    </el-tabs>

    <!-- 当前考试表格 -->
    <div v-if="activeTab === 'current'">
      <el-alert
        v-if="ongoingCount > 0"
        class="ongoing-hint"
        type="warning"
        show-icon
        :closable="false"
        :title="`你有 ${ongoingCount} 场考试正在进行中，请尽快完成（倒计时结束会自动交卷）`"
      />
      <div v-if="!loading && currentExams.length === 0" class="empty-card">
        <el-empty description="暂无考试安排" />
      </div>
      <el-card v-else class="table-card" shadow="never">
        <el-table :data="currentExams" v-loading="loading" stripe class="exam-table">
          <el-table-column label="考试名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="exam-name">{{ row.title || '未命名考试' }}</div>
              <div class="exam-name-sub">共 {{ questionCount(row) }} 题</div>
            </template>
          </el-table-column>
          <!-- 考试时间与时长合并为一格三行：比分列更紧凑，也更容易一行读完 -->
          <el-table-column label="考试时间" width="200">
            <template #default="{ row }">
              <div class="exam-time">
                <span>{{ formatDateTime(row.start_time) }}</span>
                <span class="time-to">至 {{ formatDateTime(row.end_time) }}</span>
                <span class="time-duration">时长 {{ durationText(row) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="总分" width="80" align="center">
            <template #default="{ row }">{{ row.total_score ?? 0 }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="getExamStatus(row).type" size="small">
                {{ getExamStatus(row).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                size="small"
                :disabled="getExamStatus(row).disabled"
                @click="enterExam(row.id)"
              >
                {{ getExamStatus(row).buttonText }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 考试记录表格 -->
    <div v-if="activeTab === 'history'">
      <div v-if="!loading && historyExams.length === 0" class="empty-card">
        <el-empty description="暂无考试记录" />
      </div>
      <el-card v-else class="table-card" shadow="never">
        <el-table :data="historyExams" v-loading="loading" stripe class="exam-table">
          <el-table-column label="考试名称" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="exam-name">{{ row.title || '未命名考试' }}</div>
              <div class="exam-name-sub">共 {{ questionCount(row) }} 题</div>
            </template>
          </el-table-column>
          <el-table-column label="考试时间" width="200">
            <template #default="{ row }">
              <div class="exam-time">
                <span>{{ formatDateTime(row.start_time) }}</span>
                <span class="time-to">至 {{ formatDateTime(row.end_time) }}</span>
                <span class="time-duration">时长 {{ durationText(row) }}</span>
              </div>
            </template>
          </el-table-column>
          <!-- 考试记录里的考试都已作答过，因此都带有得分（同一题只取最高分） -->
          <el-table-column label="得分 / 总分" width="180" align="center">
            <template #default="{ row }">
              <div class="score-main">
                <span class="score-value" :style="{ color: scoreColor(row) }">
                  {{ myScore(row) ?? '-' }}
                </span>
                <span class="score-total">/ {{ row.total_score ?? 0 }}</span>
              </div>
              <el-progress
                class="score-bar"
                :percentage="scorePercent(row)"
                :stroke-width="5"
                :show-text="false"
                :color="scoreColor(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="goToResult(row.id || row.exam_id)">
                查看结果
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../../stores/user'
import { getAllExams, getMyExamScores } from '../../api/exams'
import { formatDateTime } from '../../utils/time'
import PageHeader from '../../components/PageHeader.vue'
import StudentNav from '../../components/StudentNav.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const exams = ref<any[]>([])
const loading = ref(false)
// 从「考试结果」页点「返回考试记录」会带 ?tab=history，直接落在「考试记录」标签页
const activeTab = ref(route.query.tab === 'history' ? 'history' : 'current')
const submittedExamIds = ref<Set<number>>(new Set())
// 我的得分：{ 考试 id: 得分 }，来自后端 my-scores（同一题只取最高分后求和）
const myScores = ref<Record<number, number>>({})

const getExamStatus = (exam: any) => {
  const now = new Date()
  const start = new Date(exam.start_time)
  const end = new Date(exam.end_time)

  if (now < start) {
    return { text: '未开始', type: 'info', disabled: true, buttonText: '未开始' }
  } else if (now > end) {
    return { text: '已结束', type: 'danger', disabled: true, buttonText: '已结束' }
  } else {
    return { text: '进行中', type: 'success', disabled: false, buttonText: '进入考试' }
  }
}

const currentExams = computed(() => {
  return exams.value.filter(exam => !submittedExamIds.value.has(exam.id))
})

const historyExams = computed(() => {
  return exams.value.filter(exam => submittedExamIds.value.has(exam.id))
})

// 标签页上带数量，一眼看出有多少场考试
const currentTabLabel = computed(() => `当前考试（${currentExams.value.length}）`)
const historyTabLabel = computed(() => `考试记录（${historyExams.value.length}）`)

// 正在进行中的考试数量（顶部提醒用）
const ongoingCount = computed(
  () => currentExams.value.filter((exam) => !getExamStatus(exam).disabled).length
)

// 考试时长展示：0 = 不限时
const durationText = (exam: any) =>
  exam?.duration_minutes ? `${exam.duration_minutes} 分钟` : '不限时'

// 组卷题目数（列表接口已带 exam_questions）
const questionCount = (exam: any) => (exam?.exam_questions || []).length

// 我在某场考试的得分（未参加返回 null）
const myScore = (exam: any): number | null => {
  const id = Number(exam?.id)
  return Number.isFinite(id) && id in myScores.value ? myScores.value[id] : null
}

// 得分率（0~100）：用于进度条与配色
const scorePercent = (exam: any): number => {
  const total = Number(exam?.total_score) || 0
  const got = myScore(exam)
  if (!total || got === null) return 0
  return Math.max(0, Math.min(100, Math.round((got / total) * 100)))
}

// 得分配色：≥60% 绿、≥30% 橙、其余红，一眼看出得分高低
const scoreColor = (exam: any): string => {
  const percent = scorePercent(exam)
  if (percent >= 60) return '#67c23a'
  if (percent >= 30) return '#e6a23c'
  return '#f56c6c'
}

const loadExams = async () => {
  loading.value = true
  try {
    // 考试列表（自动翻页取全量）+ 我的得分（一次请求拿到所有已参加考试的得分）
    const [rawExamList, scoreMap] = await Promise.all([
      getAllExams(),
      getMyExamScores(),
    ])

    // 确保每个考试对象都有数字 id，兼容 exam_id 字段
    exams.value = rawExamList.map((exam: any) => ({
      ...exam,
      id: exam.id ?? exam.exam_id,   // 如果 id 缺失，尝试 exam_id
    }))

    // 有作答记录 = 已参加过该场考试：既用于「当前考试 / 考试记录」分栏，也用于展示得分
    myScores.value = scoreMap
    submittedExamIds.value = new Set(Object.keys(scoreMap).map(Number))
  } catch (error) {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

const enterExam = (examId: number) => {
  if (examId && !isNaN(examId)) {
    router.push(`/exam/${examId}`)
  }
}

const goToResult = (examId: number) => {
  if (examId && !isNaN(examId)) {
    // 带 from=records：结果页据此判定为「考试记录」入口——允许返回本页，不做登出
    router.push({ path: `/exam/${examId}/result`, query: { from: 'records' } })
  } else {
    ElMessage.error('考试ID无效')
  }
}

onMounted(() => {
  loadExams()
})
</script>

<style scoped>
.exam-list-container {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
}
.exam-tabs {
  margin-bottom: 8px;
}
.ongoing-hint {
  margin-bottom: 12px;
  border-radius: 10px;
}
.empty-card {
  margin-top: 20px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.table-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.table-card :deep(.el-card__body) {
  padding: 0;
}
/* 表格：浅色表头 + 更宽松的行高，长列表更易读 */
.exam-table :deep(th.el-table__cell) {
  background: #fafbfc;
  color: #606266;
  font-weight: 600;
}
.exam-table :deep(.el-table__row) {
  height: 60px;
}
.exam-table :deep(td.el-table__cell) {
  padding: 8px 0;
}

/* 考试名称：标题 + 题目数（次要信息弱化） */
.exam-name {
  font-weight: 600;
  color: #303133;
}
.exam-name-sub {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
}

/* 考试时间：开始 / 结束 / 时长三行显示，比拆成两列更易读 */
.exam-time {
  display: flex;
  flex-direction: column;
  line-height: 1.6;
  font-size: 13px;
  color: #303133;
}
.exam-time .time-to {
  color: #606266;
}
.exam-time .time-duration {
  font-size: 12px;
  color: #a8abb2;
}

/* 得分：大号彩色分数 + 得分占比进度条 */
.score-main {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 4px;
}
.score-value {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.2;
}
.score-total {
  font-size: 12px;
  color: #909399;
}
.score-bar {
  width: 96px;
  margin: 4px auto 0;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .exam-list-container {
    padding: 12px;
  }
}
</style>