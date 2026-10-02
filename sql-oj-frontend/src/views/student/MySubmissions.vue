<template>
  <div class="submissions-container">
    <div class="header">
      <el-button @click="goBack">← 返回</el-button>
      <h1>📝 我的提交记录</h1>
    </div>

    <el-table :data="submissions" v-loading="loading" stripe>
      <!-- 全部列使用 min-width：表格自动撑满父容器，多余宽度按比例分配到各列 -->
      <el-table-column prop="id" label="提交ID" min-width="90" />
      <el-table-column prop="question" label="题目ID" min-width="90" />
      <el-table-column prop="execution_status" label="状态" min-width="110">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.execution_status)">
            {{ row.execution_status || 'PENDING' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="score" label="得分" min-width="90" />
      <el-table-column label="提交时间" min-width="150">
        <template #default="{ row }">
          <!-- 人类友好的相对时间，悬停显示完整时间 -->
          <span :title="formatDateTime(row.submission_time || row.created_at)">
            {{ formatRelativeTime(row.submission_time || row.created_at, nowTick) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="操作" min-width="110" align="center">
        <template #default="{ row }">
          <el-button type="primary" link @click="viewDetail(row)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        @current-change="loadSubmissions"
        layout="prev, pager, next"
      />
    </div>

    <!-- ✅ 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="提交详情" width="700px">
      <div class="detail-item">
        <strong>提交 ID：</strong>{{ currentDetail.id }}
      </div>
      <div class="detail-item">
        <strong>题目 ID：</strong>{{ currentDetail.question }}
      </div>
      <div class="detail-item">
        <strong>提交的 SQL：</strong>
        <!-- 打开弹窗时才请求详情接口获取 SQL（列表接口不返回该字段） -->
        <pre class="sql-detail">{{ detailLoading ? '加载中…' : (currentDetail.submitted_sql || '（空）') }}</pre>
      </div>
      <div class="detail-item">
        <strong>判题状态：</strong>
        <el-tag :type="statusTagType(currentDetail.execution_status)">
          {{ currentDetail.execution_status || 'PENDING' }}
        </el-tag>
      </div>
      <div class="detail-item">
        <strong>得分：</strong>{{ currentDetail.score ?? 0 }}
      </div>
      <!-- 判题明细：未通过的测试用例（后端仅返回序号 + 实际输出 + 错误信息） -->
      <div class="detail-item" v-if="currentDetail.judge_details">
        <strong>
          {{ currentDetail.execution_status === 'ACCEPTED' ? '✅ 用例通过情况：' : '❌ 失败的测试用例：' }}
        </strong>
        <div v-if="currentDetail.judge_details.error_message" class="detail-error">
          {{ currentDetail.judge_details.error_message }}
        </div>
        <div class="detail-summary">
          共 {{ currentDetail.judge_details.total }} 个测试用例，通过
          {{ currentDetail.judge_details.passed_count }} 个。
        </div>
        <div
          v-for="caseItem in (currentDetail.judge_details.failed_cases || [])"
          :key="caseItem.index"
          class="failed-case"
        >
          <div class="failed-case-title">
            <el-tag type="danger" size="small">用例 {{ caseItem.index }}</el-tag>
            <span class="case-hint">{{ caseItem.error_message || '执行结果与预期不一致' }}</span>
          </div>
          <span class="case-label">你的输出：</span>
          <pre class="sql-detail">{{ caseItem.actual_output || '（空）' }}</pre>
        </div>
      </div>
      <div class="detail-item" v-if="currentDetail.submission_time || currentDetail.created_at">
        <strong>提交时间：</strong>
        {{ formatDateTime(currentDetail.submission_time || currentDetail.created_at) }}
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
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
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
.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

/* ✅ 详情弹窗样式 */
.detail-item {
  margin-bottom: 12px;
}
.sql-detail {
  background-color: #f5f7fa;
  padding: 12px 16px;
  border-radius: 6px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  border: 1px solid #e4e7ed;
  margin: 4px 0 0 0;
  max-height: 200px;
  overflow-y: auto;
}

/* 判题明细：未通过的测试用例 */
.detail-summary {
  color: #606266;
  font-size: 13px;
  margin-bottom: 6px;
}
.detail-error {
  color: #e6a23c;
  font-size: 13px;
  margin-bottom: 6px;
}
.failed-case {
  background-color: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.failed-case-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.case-hint {
  color: #f56c6c;
  font-size: 13px;
}
.case-label {
  font-size: 13px;
  color: #606266;
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