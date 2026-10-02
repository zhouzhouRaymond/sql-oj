<template>
  <div class="submissions-container">
    <PageHeader
      :title="userStore.isTeacher ? '📝 学生提交记录' : '📝 我的提交记录'"
      :subtitle="`共 ${total} 条，按提交时间由近到远排列；点「查看详情」可看提交的 SQL 与判题用例`"
      :welcome="inTeacherLayout ? undefined : userStore.displayName"
    >
      <!-- 仅当学生从「题目详情」进来时，才在导航栏最左侧显示「← 返回」原路回到该题 -->
      <template #leading>
        <el-button
          v-if="!inTeacherLayout && backTarget"
          type="primary"
          link
          @click="goBack"
        >
          ← 返回
        </el-button>
      </template>
      <!-- 教师端嵌在布局里时，导航与退出由侧边栏负责，这里不再重复放按钮 -->
      <template #actions>
        <StudentNav v-if="!inTeacherLayout" />
      </template>
    </PageHeader>

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
            <div class="q-sub">题目 #{{ row.question }}</div>
          </template>
        </el-table-column>
        <!-- 教师查看全部提交时显示提交人（学生只能看到自己的提交） -->
        <el-table-column v-if="userStore.isTeacher" label="学生" min-width="160">
          <template #default="{ row }">
            <!-- 用户名（展示名）+ 登录名：同名用户可据此区分 -->
            <div>{{ row.student_name || row.student_username || `学生 #${row.student}` }}</div>
            <div class="q-sub">{{ row.student_username || `#${row.student}` }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" min-width="140" align="center">
          <template #default="{ row }">
            <!-- 中文标签 + 原始状态码（便于与接口 / 日志对账） -->
            <el-tag :type="statusTagType(row.execution_status)" size="small">
              {{ statusText(row.execution_status) }}
            </el-tag>
            <div class="status-code">{{ row.execution_status || 'PENDING' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="得分" min-width="90" align="center">
          <template #default="{ row }">
            <span class="score" :class="{ 'score-zero': !row.score }">{{ row.score ?? 0 }}</span>
          </template>
        </el-table-column>
        <!-- 来源：优先显示考试名称（人类可读），下方小字保留考试 id 便于对账 -->
        <el-table-column label="来源" min-width="180">
          <template #default="{ row }">
            <template v-if="row.exam">
              <div class="q-title">{{ row.exam_title || `考试 #${row.exam}` }}</div>
              <div class="q-sub">考试 #{{ row.exam }}</div>
            </template>
            <span v-else class="muted">练习</span>
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
          <template v-if="currentDetail.exam">
            {{ currentDetail.exam_title || `考试 #${currentDetail.exam}` }}
            <span class="q-sub">考试 #{{ currentDetail.exam }}</span>
          </template>
          <template v-else>练习</template>
        </el-descriptions-item>
        <el-descriptions-item v-if="userStore.isTeacher" label="提交人">
          {{ currentDetail.student_name || currentDetail.student_username || '-' }}
          <span class="q-sub">{{ currentDetail.student_username || '' }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="判题状态">
          <el-tag :type="statusTagType(currentDetail.execution_status)" size="small">
            {{ statusText(currentDetail.execution_status) }}
          </el-tag>
          <span class="status-code">{{ currentDetail.execution_status || 'PENDING' }}</span>
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import { getSubmission, getSubmissions } from '../api/submissions'
import { formatDateTime, formatRelativeTime } from '../utils/time'
import { statusTagType, statusText } from '../utils/status'
import PageHeader from '../components/PageHeader.vue'
import StudentNav from '../components/StudentNav.vue'
import SubmissionCaseDetail from '../components/SubmissionCaseDetail.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 教师端菜单通过 /teacher/submissions 把它嵌在布局里（侧边栏即导航），
// 此时不需要「返回」按钮；学生端是独立页面，仍显示「返回」。
const inTeacherLayout = computed(() => route.path.startsWith('/teacher'))

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

// 判题状态标签颜色与文案统一由 utils/status 提供（见文件顶部 import）

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

// 「← 返回」的目标：入口通过 ?from= 传来的来源路径。
// 只有「从题目详情页 /questions/<id> 进来」时才需要它 —— 从题库 / 考试 / 个人中心
// 等入口进来时，用顶部统一导航即可，多一个返回按钮反而多余，因此这些入口不显示。
const backTarget = computed(() => {
  const from = route.query.from
  if (typeof from !== 'string' || !from.startsWith('/')) return ''
  const [path] = from.split('?')
  return /^\/questions\/[^/]+$/.test(path) ? from : ''
})

const goBack = () => {
  if (backTarget.value) router.push(backTarget.value)
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
/* 原始状态码：等宽小字，与中文标签并列展示便于对账 */
.status-code {
  font-family: 'Courier New', monospace;
  font-size: 11px;
  color: #a8abb2;
  line-height: 1.4;
}
.score {
  font-size: 16px;
  font-weight: 700;
  color: #409eff;
}
.score-zero {
  color: #f56c6c;
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
}
</style>