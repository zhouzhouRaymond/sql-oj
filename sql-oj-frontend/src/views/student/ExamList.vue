<template>
  <div class="exam-list-container">
    <div class="header">
      <h1>📋 我的考试</h1>
      <div class="user-info">
        <span>欢迎，{{ userStore.displayName }}</span>
        <el-button type="primary" link @click="goToQuestions">← 返回题库</el-button>
        <el-button type="danger" size="small" @click="handleLogout">退出</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="exam-tabs">
      <el-tab-pane label="当前考试" name="current" />
      <el-tab-pane label="考试记录" name="history" />
    </el-tabs>

    <!-- 当前考试表格 -->
    <div v-if="activeTab === 'current'">
      <div v-if="!loading && currentExams.length === 0" class="empty-state">
        <el-empty description="暂无考试安排" />
      </div>
      <el-table v-else :data="currentExams" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="考试名称" min-width="150" />
        <el-table-column prop="start_time" label="开始时间" width="180" />
        <el-table-column prop="end_time" label="结束时间" width="180" />
        <el-table-column prop="total_score" label="总分" width="80" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getExamStatus(row).type">
              {{ getExamStatus(row).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="enterExam(row.id)"
              :disabled="getExamStatus(row).disabled"
            >
              {{ getExamStatus(row).buttonText }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 考试记录表格 -->
    <div v-if="activeTab === 'history'">
      <div v-if="!loading && historyExams.length === 0" class="empty-state">
        <el-empty description="暂无考试记录" />
      </div>
      <el-table v-else :data="historyExams" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="考试名称" min-width="150" />
        <el-table-column prop="start_time" label="开始时间" width="180" />
        <el-table-column prop="end_time" label="结束时间" width="180" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="goToResult(row.id || row.exam_id)"
            >
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '../../stores/user'
import { getAllExams } from '../../api/exams'
import { getSubmissions } from '../../api/submissions'

const router = useRouter()
const userStore = useUserStore()

const exams = ref<any[]>([])
const loading = ref(false)
const activeTab = ref('current')
const submittedExamIds = ref<Set<number>>(new Set())

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

const loadExams = async () => {
  loading.value = true
  try {
    const [rawExamList, subRes] = await Promise.all([
      getAllExams(),
      getSubmissions()
    ])

    // 考试可能超过一页（后端每页 20 条），getAllExams 已自动翻页取全量
    let rawExams = rawExamList
    // 确保每个考试对象都有数字 id，兼容 exam_id 字段
    exams.value = rawExams.map((exam: any) => ({
      ...exam,
      id: exam.id ?? exam.exam_id,   // 如果 id 缺失，尝试 exam_id
    }))

    const submissions = subRes.data?.results || subRes.data || []
    const ids = new Set<number>()
    submissions.forEach((sub: any) => {
      if (sub.exam) {
        ids.add(sub.exam)
      }
    })
    submittedExamIds.value = ids
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
    router.push(`/exam/${examId}/result`)
  } else {
    ElMessage.error('考试ID无效')
  }
}

const goToQuestions = () => {
  router.push('/questions')
}

const handleLogout = () => {
  ElMessageBox.confirm('确定退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logout()
    router.push('/login')
    ElMessage.success('已退出')
  })
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
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 0 20px;
}
.header h1 {
  margin: 0;
  font-size: 20px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 15px;
}
.empty-state {
  margin-top: 60px;
}
.exam-tabs {
  margin-bottom: 20px;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .exam-list-container {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 10px;
    padding: 0 4px;
  }
  .user-info {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>