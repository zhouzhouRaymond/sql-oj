<template>
  <div class="submissions-container">
    <div class="header">
      <el-button @click="goBack">← 返回</el-button>
      <div class="header-title">
        <!-- 教师进入本页看到的是全班提交，标题随之区分 -->
        <h1>{{ userStore.isTeacher ? '📝 学生提交记录' : '📝 我的提交记录' }}</h1>
        <p class="subtitle">
          共 {{ total }} 条，按提交时间由近到远排列；点「查看详情」可看提交的 SQL 与判题用例
        </p>
      </div>
    </div>

    <el-card class="table-card" shadow="never">
      <el-table
        :data="submissions"
        v-loading="loading"
        :row-key="(row: any) => row.id"
        class="sub-table"
        empty-text="暂无提交记录"
        stripe
      >
        <!-- 全部列使用 min-width：表格自动撑满父容器，多余宽度按比例分配到各列 -->
        <el-table-column label="ID" width="72" align="center">
          <template #default="{ row }"><span class="muted">#{{ row.id }}</span></template>
        </el-table-column>
        <!-- 题目：显示题目标题（比题目ID 直观），悬停可看完整内容 -->
        <el-table-column label="题目" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="q-title">{{ questionTitle(row) }}</div>
            <div class="q-sub">
              题目 #{{ row.question }}<span v-if="row.exam"> · 考试 #{{ row.exam }}</span>
            </div>
          </template>
        </el-table-column>
        <!-- 教师查看全部提交时显示提交人（学生只能看到自己的提交） -->
        <el-table-column v-if="userStore.isTeacher" label="学生" min-width="140">
          <template #default="{ row }">
            <div>{{ row.student_name || `学生 #${row.student}` }}</div>
            <div class="q-sub">#{{ row.student }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="120" align="center">
          <template #default="{ row }">
            <!-- 中文标签更易读，悬停可看后端原始状态码 -->
            <el-tooltip :content="row.execution_status || 'PENDING'" placement="top">
              <el-tag :type="statusTagType(row.execution_status)" size="small">
                {{ statusText(row.execution_status) }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="得分" min-width="90" align="center">
          <template #default="{ row }">
            <span class="score" :class="{ 'score-zero': !row.score }">{{ row.score ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" min-width="110" align="center">
          <template #default="{ row }">
            <span class="origin">{{ row.exam ? `考试 #${row.exam}` : '练习' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" min-width="150" align="center">
          <template #default="{ row }">
            <!-- 人类友好的相对时间，悬停显示完整时间 -->
            <span :title="formatDateTime(row.submission_time || row.created_at)">
              {{ formatRelativeTime(row.submission_time || row.created_at, nowTick) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="110" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="viewDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="pagination">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadSubmissions"
      />
    </div>

    <!-- ✅ 详情弹窗：先给一致的元信息表格，再放 SQL 与判题明细 -->
    <el-dialog v-model="detailVisible" title="提交详情" width="760px" top="8vh">
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="题目">
          {{ currentDetail.question_title || `题目 #${currentDetail.question}` }}
        </el-descriptions-item>
        <el-descriptions-item label="来源">
          {{ currentDetail.exam ? `考试 #${currentDetail.exam}` : '练习' }}
        </el-descriptions-item>
        <el-descriptions-item label="判题状态">
          <el-tag :type="statusTagType(currentDetail.execution_status)" size="small">
            {{ statusText(currentDetail.execution_status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="得分">{{ currentDetail.score ?? 0 }}</el-descriptions-item>
        <el-descriptions-item label="提交 ID">#{{ currentDetail.id }}</el-descriptions-item>
        <el-descriptions-item label="提交时间">{{ timeText(currentDetail) }}</el-descriptions-item>
      </el-descriptions>

      <div class="detail-block">
        <div class="detail-label">提交的 SQL</div>
        <!-- 打开弹窗时才请求详情接口获取 SQL（列表接口不返回该字段） -->
        <pre class="sql-detail">{{ detailLoading ? '加载中…' : (currentDetail.submitted_sql || '（空）') }}</pre>
      </div>

      <!-- 判题明细（失败用例 / 运行结果）：与教师端提交记录共用同一组件 -->
      <div class="detail-block">
        <div class="detail-label">判题明细</div>
        <SubmissionCaseDetail :detail="currentDetail" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../../stores/user'
import { getSubmission, getSubmissions } from '../../api/submissions'
import { formatDateTime, formatRelativeTime } from '../../utils/time'
import SubmissionCaseDetail from '../../components/SubmissionCaseDetail.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const submissions = ref<any[]>([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// ✅ 详情弹窗相关
const detailVisible = ref(false)
const detailLoading = ref(false)
const currentDetail = ref<any>({})

// 用于让「相对时间」随时间自动刷新
const nowTick = ref(Date.now())
let clockTimer: number | undefined

const statusTagType = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'danger'
    case 'ERROR': return 'danger'
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
}

// 判题状态码 → 人类可读的中文（悬停可看原始状态码）
const statusText = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return '通过'
    case 'WRONG_ANSWER': return '答案错误'
    case 'ERROR': return '运行错误'
    case 'TIMEOUT': return '超时'
    case 'PENDING':
    case '':
    case undefined:
    case null:
      return '判题中'
    default: return status
  }
}

// 题目展示：优先标题，其次描述前 40 字，最后回退「题目 #id」
const questionTitle = (row: any) => {
  if (row?.question_title) return row.question_title
  const desc = String(row?.question_desc || '').replace(/\s+/g, ' ').trim()
  if (desc) return desc.length > 40 ? `${desc.slice(0, 40)}…` : desc
  return `题目 #${row?.question ?? ''}`
}

// 提交时间：完整时间；缺失时用 - 占位，避免出现空单元格
const timeText = (row: any) => {
  const raw = row?.submission_time || row?.created_at
  return raw ? formatDateTime(raw) : '-'
}

const loadSubmissions = async () => {
  loading.value = true
  try {
    const res = await getSubmissions({ page: currentPage.value })
    submissions.value = res.data.results || []
    total.value = res.data.count || 0
  } catch (error) {
    ElMessage.error('加载提交记录失败')
  } finally {
    loading.value = false
  }
}

// 返回上一级：优先回到来源页面（入口通过 ?from= 传入），否则按身份回到各自首页
const goBack = () => {
  const from = route.query.from
  if (typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')) {
    router.push(from)
    return
  }
  router.push(userStore.user?.user_type === 'teacher' ? '/teacher' : '/questions')
}

// ✅ 查看详情：先展示列表中的基础信息，再按 id 懒加载完整详情（含 submitted_sql）
const viewDetail = async (row: any) => {
  if (!row?.id) return
  detailVisible.value = true
  detailLoading.value = true
  currentDetail.value = row
  try {
    const res = await getSubmission(row.id)
    currentDetail.value = { ...row, ...(res.data || {}) }
  } catch (error) {
    ElMessage.error('加载提交详情失败')
  } finally {
    detailLoading.value = false
  }
}

onMounted(() => {
  loadSubmissions()
  // 每分钟刷新一次相对时间显示
  clockTimer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 60 * 1000)
})

onUnmounted(() => {
  if (clockTimer !== undefined) {
    window.clearInterval(clockTimer)
    clockTimer = undefined
  }
})
</script>

<style scoped>
.submissions-container {
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
.header-title .subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: #909399;
}

/* 表格卡片：与考试列表保持一致的观感 */
.table-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.table-card :deep(.el-card__body) {
  padding: 0;
}
/* 浅色表头 + 更宽松的行高，长列表更易读 */
.sub-table :deep(th.el-table__cell) {
  background: #fafbfc;
  color: #606266;
  font-weight: 600;
}
.sub-table :deep(.el-table__row) {
  height: 56px;
}
.sub-table :deep(td.el-table__cell) {
  padding: 8px 0;
}

/* 单元格内容：题目标题 / 次要信息 / 弱化的ID */
.q-title {
  font-weight: 600;
  color: #303133;
}
.q-sub {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
}
.muted {
  color: #a8abb2;
}
.score {
  font-size: 16px;
  font-weight: 700;
  color: #409eff;
}
.score-zero {
  color: #f56c6c;
}
.origin {
  font-size: 13px;
  color: #606266;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* ✅ 详情弹窗样式 */
.detail-block {
  margin-top: 16px;
}
.detail-label {
  margin-bottom: 6px;
  font-weight: 600;
  color: #303133;
}
.detail-block :deep(.el-descriptions) {
  margin-bottom: 4px;
}
.sql-detail {
  background-color: #f5f7fa;
  padding: 12px 16px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-all;
  border: 1px solid #e4e7ed;
  margin: 4px 0 0 0;
  max-height: 200px;
  overflow-y: auto;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .submissions-container {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px 16px;
  }
  .header h1 {
    font-size: 18px;
  }
}
</style>