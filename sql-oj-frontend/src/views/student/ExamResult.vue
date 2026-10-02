<template>
  <div class="exam-result-container">
    <div class="header">
      <h1>📊 考试结果</h1>
      <el-button @click="goToSubmissions">查看提交记录 →</el-button>
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
              <el-button type="primary" link @click="viewSubmission(row.submission_id)">查看SQL</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
      <div v-else class="no-detail">
        暂无详细答题记录
      </div>
    </div>

    <!-- 查看SQL弹窗 -->
    <el-dialog v-model="sqlDialogVisible" title="提交的SQL" width="600px">
      <pre style="white-space: pre-wrap; word-break: break-all;">{{ currentSQL }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getExamResult } from '../../api/exams'
import request from '../../api/request'

const route = useRoute()
const router = useRouter()
const examId = computed(() => Number(route.params.id))

const loading = ref(false)
const result = ref<any>({
  total_score: 0,
  question_count: 0,
  correct_count: 0,
  details: []
})

const sqlDialogVisible = ref(false)
const currentSQL = ref('')

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

// 跳转「我的提交」，带上来源路径，便于在该页「返回」时回到本页
const goToSubmissions = () => {
  router.push({ path: '/submissions', query: { from: route.fullPath } })
}

const viewSubmission = async (submissionId: number) => {
  try {
    const res = await request.get(`/submissions/${submissionId}/`)
    currentSQL.value = res.data.submitted_sql || res.data.sql || '暂无SQL'
    sqlDialogVisible.value = true
  } catch (error) {
    ElMessage.error('获取SQL失败')
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
  font-size: 22px;
  color: #2d3748;
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