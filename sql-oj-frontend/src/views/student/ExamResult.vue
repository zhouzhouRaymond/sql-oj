<template>
  <div class="exam-result-container">
    <div class="header">
      <div class="header-title">
        <h1>📊 考试结果</h1>
        <!-- 交卷结束进入：唯一出口是退出登录；从「考试记录」进入：可返回考试记录 -->
        <p class="subtitle">{{ headerHint }}</p>
      </div>
      <el-button v-if="enteredFromRecords" type="primary" plain @click="goBackToRecords">
        ← 返回考试记录
      </el-button>
      <el-button v-else type="danger" @click="handleLogout">退出登录</el-button>
    </div>

    <div v-loading="loading" class="content">
      <!-- 总分 -->
      <el-card class="score-card">
        <div class="total-score">
          <span class="label">总分</span>
          <span class="value">{{ result.total_score || 0 }}</span>
          <span class="unit">分</span>
        </div>
        <div class="score-detail">
          <span>题目数：{{ result.question_count || 0 }}</span>
          <span>正确数：{{ result.correct_count || 0 }}</span>
        </div>
      </el-card>

      <!-- 每题详情 -->
      <el-card class="detail-card" v-if="result.details && result.details.length">
        <template #header>
          <span>📝 答题详情</span>
        </template>
        <el-table :data="result.details" stripe>
          <el-table-column prop="question_title" label="题目" min-width="150" />
          <el-table-column prop="score" label="得分" width="80" align="center">
            <template #default="{ row }">
              <span :class="{ 'correct': row.score > 0, 'wrong': row.score === 0 }">
                {{ row.score || 0 }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.score > 0 ? 'success' : 'danger'" size="small">
                {{ row.score > 0 ? '正确' : '错误' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center">
            <template #default="{ row }">
              <el-button type="primary" link @click="viewSubmission(row.submission_id)">查看详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
      <div v-else class="no-detail">
        暂无详细答题记录
      </div>
    </div>

    <!-- 查看提交详情：SQL + 判题明细（失败用例 / 运行结果表格化） -->
    <el-dialog v-model="detailVisible" title="提交详情" width="760px">
      <div class="detail-item">
        <strong>提交 ID：</strong>{{ currentDetail.id }}
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
      <div class="detail-item">
        <strong>提交的 SQL：</strong>
        <pre class="sql-detail">{{ detailLoading ? '加载中…' : (currentDetail.submitted_sql || '（空）') }}</pre>
      </div>
      <!-- 判题明细：与「我的提交」「题目详情」共用同一组件 -->
      <div v-if="!detailLoading" class="detail-item">
        <SubmissionCaseDetail :detail="currentDetail" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getExamResult } from '../../api/exams'
import request from '../../api/request'
import SubmissionCaseDetail from '../../components/SubmissionCaseDetail.vue'
import { useUserStore } from '../../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const examId = computed(() => Number(route.params.id))

const loading = ref(false)
const result = ref<any>({
  total_score: 0,
  question_count: 0,
  correct_count: 0,
  details: []
})

// 提交详情弹窗：SQL + 判题明细（失败用例 / 运行结果表格化展示）
const detailVisible = ref(false)
const detailLoading = ref(false)
const currentDetail = ref<any>({})

const statusTagType = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'danger'
    case 'ERROR': return 'danger'
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
}


const getCurrentUser = () => {
  const userStr = localStorage.getItem('user')
  if (userStr) {
    try {
      return JSON.parse(userStr)
    } catch (e) {
      return null
    }
  }
  return null
}

const loadResult = async () => {
  loading.value = true
  try {
    const currentUser = getCurrentUser()
    if (!currentUser) {
      ElMessage.error('无法获取用户信息')
      router.push('/login')
      return
    }

    // 1. 获取排名信息（得到总分）
    const rankRes = await getExamResult(examId.value)
    const rankData = rankRes.data || {}
    const ranking: any[] = rankData.ranking || rankData.details || rankData.results || []
    const myRecord = ranking.find((item: any) => {
      const itemUserId = item.student__id || item.student_id || item.user_id
      return itemUserId && Number(itemUserId) === Number(currentUser.id)
    })
    const totalScore = myRecord ? (myRecord.total || myRecord.score || 0) : 0

    // 2. 获取提交记录 —— 只获取本次考试的提交
    // 兼容后端是否支持 exam 参数过滤
    const subRes = await request.get('/submissions/', {
      params: { exam: examId.value }
    })
    let submissions = subRes.data?.results || subRes.data || []

    // 手动过滤：确保每条记录的考试ID等于当前考试ID
    submissions = submissions.filter((sub: any) => {
      // 考试ID可能在 exam 字段（数字或对象）或 exam_id 字段
      let subExamId: number | null = null
      if (sub.exam !== undefined && sub.exam !== null) {
        if (typeof sub.exam === 'object' && sub.exam.id) {
          subExamId = sub.exam.id
        } else if (typeof sub.exam === 'number') {
          subExamId = sub.exam
        }
      } else if (sub.exam_id !== undefined && sub.exam_id !== null) {
        subExamId = Number(sub.exam_id)
      }
      return subExamId === examId.value
    })

    // 再过滤当前用户（如果后端返回了所有学生的提交）
    if (submissions.length > 0 && submissions[0].student !== undefined) {
      submissions = submissions.filter((sub: any) => {
        const studentId = sub.student?.id || sub.student
        return Number(studentId) === Number(currentUser.id)
      })
    }

    // 统计
    const questionIds = new Set<number>()
    let correctCount = 0
    const details: any[] = []

    submissions.forEach((sub: any) => {
      const qid = sub.question || sub.question_id
      if (qid) {
        questionIds.add(qid)
        const score = sub.score || 0
        if (score > 0) correctCount++
        details.push({
          question_title: sub.question_title || sub.question_desc || `题目 ${qid}`,
          score: score,
          submission_id: sub.id,
          status: score > 0 ? '正确' : '错误'
        })
      }
    })

    result.value = {
      total_score: totalScore,
      question_count: questionIds.size,
      correct_count: correctCount,
      details: details
    }
  } catch (error) {
    ElMessage.error('加载考试结果失败')
  } finally {
    loading.value = false
  }
}

// ===== 跳转策略：按「进入本页的入口」决定出口 =====
// - 交卷 / 倒计时自动交卷进入（?from=exam，缺省同样是该模式）：本场考试已结束，
//   本页不提供任何其它页面入口，唯一出口是「退出登录」；
//   任何离开本页的导航（含浏览器「后退」回到考试页）都会被拦截为退出登录。
// - 从「考试记录」点击「查看结果」进入（?from=records）：只是回顾历史成绩，
//   属于正常浏览，允许返回考试记录，不登出。
const enteredFromRecords = computed(() => route.query.from === 'records')

const headerHint = computed(() =>
  enteredFromRecords.value
    ? '从「考试记录」查看历史成绩，可返回考试记录'
    : '离开本页会退出登录，返回登录界面',
)

// 考试结束模式：退出登录 → 登录界面
const handleLogout = () => {
  ElMessageBox.confirm('退出登录后将返回登录界面，确定继续吗？', '退出登录', {
    confirmButtonText: '确定退出',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logout()
    router.push('/login')
    ElMessage.success('已退出登录')
  }).catch(() => {})
}

// 考试记录模式：返回「考试记录」标签页（不登出）
const goBackToRecords = () => {
  router.push({ path: '/exams', query: { tab: 'history' } })
}

// 兜底拦截：考试结束模式下，任何离开本页的导航都改为退出登录并跳转登录界面；
// 「考试记录」入口与教师不受此限制（教师访问本页不应被误踢会话）。
onBeforeRouteLeave((to) => {
  if (to.path === '/login' || userStore.isTeacher || enteredFromRecords.value) return true
  userStore.logout()
  ElMessage.warning('本场考试已结束，已退出登录')
  return { path: '/login' }
})

// 点击「查看详情」：先展示基础信息，再按 id 拉取 SQL 与判题明细
const viewSubmission = async (submissionId: number) => {
  if (!submissionId) return
  detailVisible.value = true
  detailLoading.value = true
  currentDetail.value = { id: submissionId }
  try {
    const res = await request.get(`/submissions/${submissionId}/`)
    currentDetail.value = res.data || {}
  } catch (error) {
    ElMessage.error('获取提交详情失败')
  } finally {
    detailLoading.value = false
  }
}

onMounted(() => {
  loadResult()
})
</script>

<style scoped>
.exam-result-container {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
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
/* 页面副标题：说明本页只提供「退出登录」一个出口 */
.header-title .subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  color: #909399;
}
.content {
  max-width: 800px;
  margin: 0 auto;
}
.score-card {
  margin-bottom: 20px;
  text-align: center;
}
.total-score .label {
  font-size: 16px;
  color: #909399;
}
.total-score .value {
  font-size: 48px;
  font-weight: 700;
  color: #409eff;
  margin: 0 8px;
}
.total-score .unit {
  font-size: 18px;
  color: #909399;
}
.score-detail {
  margin-top: 12px;
  display: flex;
  justify-content: center;
  gap: 30px;
  color: #606266;
}
.correct { color: #67c23a; font-weight: 600; }
.wrong { color: #f56c6c; font-weight: 600; }
.no-detail {
  text-align: center;
  color: #909399;
  padding: 20px;
}

/* 提交详情弹窗 */
.detail-item {
  margin-bottom: 12px;
}
.sql-detail {
  background-color: #f5f7fa;
  padding: 12px 16px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  margin: 4px 0 0;
  font-family: 'Courier New', monospace;
  font-size: 14px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

/* ===== 窄窗口自适应 ===== */

@media (max-width: 768px) {
  .exam-result-container {
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
  .total-score .value {
    font-size: 34px;
  }
  .score-detail {
    gap: 16px;
    flex-wrap: wrap;
  }
}
</style>
