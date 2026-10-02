<template>
  <div class="statistics">
    <h1>📊 统计分析</h1>

    <el-row :gutter="20">
      <!-- ✅ 左侧：题目通过率（表格形式） -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>📈 题目通过率</span>
          </template>
          <el-table :data="questionStats" stripe v-loading="loading" max-height="350">
            <el-table-column prop="question_title" label="题目名称" min-width="150" />
            <el-table-column prop="pass_rate" label="通过率" width="120">
              <template #default="{ row }">
                <el-progress :percentage="row.pass_rate" :stroke-width="8" :show-text="true" />
              </template>
            </el-table-column>
            <el-table-column prop="passed_count" label="通过数" width="80" align="center" />
            <el-table-column prop="attempted_count" label="提交人数" width="80" align="center" />
            <el-table-column prop="total_submissions" label="提交次数" width="80" align="center" />
          </el-table>
          <div v-if="questionStats.length === 0 && !loading" class="empty-hint">
            暂无题目数据
          </div>
        </el-card>
      </el-col>

      <!-- ✅ 右侧：学生通过率排名 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>🏆 学生通过率排名</span>
          </template>
          <el-table :data="studentRanking" stripe v-loading="rankingLoading" max-height="350">
            <el-table-column label="排名" width="70" align="center">
              <template #default="{ $index }">
                <span :class="{ 'top-rank': $index < 3 }">{{ $index + 1 }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="username" label="学生" min-width="100" />
            <el-table-column prop="pass_rate" label="通过率" width="120">
              <template #default="{ row }">
                <el-progress :percentage="row.pass_rate" :stroke-width="8" />
              </template>
            </el-table-column>
            <el-table-column prop="passed" label="通过数" width="80" align="center" />
            <el-table-column prop="total_submissions" label="提交次数" width="80" align="center" />
          </el-table>
          <div v-if="studentRanking.length === 0 && !rankingLoading" class="empty-hint">
            暂无学生数据
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ✅ 整体数据概览 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card>
          <template #header>
            <span>📋 整体数据概览</span>
          </template>
          <div class="overview-stats">
            <div class="stat-card">
              <div class="stat-value">{{ overview.total_questions || 0 }}</div>
              <div class="stat-label">题目总数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ overview.total_submissions || 0 }}</div>
              <div class="stat-label">总提交次数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ overview.total_users || 0 }}</div>
              <div class="stat-label">注册用户</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">{{ overview.average_pass_rate != null ? overview.average_pass_rate : 0 }}%</div>
              <div class="stat-label">平均通过率</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getQuestionStats, getStudentStats, getOverview } from '../../api/stats'

const loading = ref(false)
const rankingLoading = ref(false)
const questionStats = ref<any[]>([])
const studentRanking = ref<any[]>([])
const overview = ref({
  total_questions: 0,
  total_submissions: 0,
  total_users: 0,
  average_pass_rate: 0
})

// 安全解析数值（处理 null/undefined）
const safeNumber = (val: any, defaultVal = 0): number => {
  const num = Number(val)
  return isNaN(num) ? defaultVal : num
}

// 将 rate 转换为百分比整数（0～100）
const toPercent = (rate: any): number => {
  const raw = safeNumber(rate)
  // 如果 rate 明显大于 1，视为已百分比数值（如 75），否则视为小数（如 0.75）
  if (raw > 1.01) return Math.round(raw)
  return Math.round(raw * 100)
}

// ===== 加载题目通过率 =====
const loadQuestionStats = async () => {
  loading.value = true
  try {
    const res = await getQuestionStats()
    const rawData = res.data || []
    const data = Array.isArray(rawData) ? rawData : (rawData.results || [])

    questionStats.value = data.map((item: any) => ({
      question_id: item.question_id || item.id,
      question_title: item.title || item.question_title || `题目 ${item.question_id || item.id}`,
      pass_rate: toPercent(item.rate ?? item.pass_rate),          // 主要使用 rate 字段
      passed_count: safeNumber(item.passed_count ?? item.passed_students ?? item.passed),
      attempted_count: safeNumber(item.attempted_students ?? item.attempted_count),  // 提交人数
      total_submissions: safeNumber(item.total_submissions)
    }))
  } catch (error) {
    console.error('加载题目统计失败', error)
  } finally {
    loading.value = false
  }
}

// ===== 加载学生排名 =====
const loadStudentStats = async () => {
  rankingLoading.value = true
  try {
    const res = await getStudentStats()
    const rawData = res.data || []
    const data = Array.isArray(rawData) ? rawData : (rawData.results || [])

    studentRanking.value = data.map((item: any, index: number) => ({
      rank: index + 1,
      username: item.name || item.username || item.student_name || `用户 ${item.user_id || item.id}`,
      pass_rate: toPercent(item.pass_rate ?? item.rate ?? 0),
      passed: safeNumber(item.passed ?? item.passed_count),
      total_submissions: safeNumber(item.total_submissions ?? item.submissions)
    }))
  } catch (error) {
    console.error('加载学生排名失败', error)
  } finally {
    rankingLoading.value = false
  }
}

// ===== 加载概览数据 =====
const loadOverview = async () => {
  try {
    const res = await getOverview()
    const data = res.data || {}
    const avgRate = data.average_pass_rate ?? data.avg_pass_rate ?? data.avgRate ?? 0
    overview.value = {
      total_questions: safeNumber(data.total_questions ?? data.question_count),
      total_submissions: safeNumber(data.total_submissions ?? data.submission_count),
      total_users: safeNumber(data.total_users ?? data.user_count),
      average_pass_rate: toPercent(avgRate)
    }
  } catch (error) {
    console.error('加载概览数据失败', error)
  }
}

const refreshAll = () => {
  loadQuestionStats()
  loadStudentStats()
  loadOverview()
}

onMounted(() => {
  refreshAll()
})
</script>

<style scoped>
.statistics {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
}
.statistics > h1 {
  margin: 0 0 20px 0;
  font-size: 22px;
  color: #2d3748;
}

.overview-stats {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}
.stat-card {
  flex: 1;
  min-width: 150px;
  padding: 20px;
  text-align: center;
  background-color: #f5f7fa;
  border-radius: 8px;
}
.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
}
.stat-label {
  margin-top: 8px;
  color: #909399;
  font-size: 14px;
}

.top-rank {
  font-weight: 700;
  color: #e6a23c;
}

.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 30px 0;
  font-size: 14px;
}

:deep(.el-table .cell) {
  font-size: 13px;
}
</style>