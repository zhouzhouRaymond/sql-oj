<template>
  <div class="exam-manage">
    <div class="header">
      <h1>📋 考试管理</h1>
      <el-button type="primary" @click="dialogVisible = true">+ 创建考试</el-button>
    </div>

    <el-table :data="exams" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="考试名称" />
      <el-table-column prop="start_time" label="开始时间" width="180" />
      <el-table-column prop="end_time" label="结束时间" width="180" />
      <el-table-column prop="total_score" label="总分" width="80" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
          <el-button type="primary" link @click="viewRanking(row.id)">排名</el-button>
          <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建考试弹窗 -->
    <el-dialog v-model="dialogVisible" title="创建考试" width="700px" @close="resetForm">
      <el-form :model="examForm" label-width="100px">
        <el-form-item label="考试名称" required>
          <el-input v-model="examForm.title" placeholder="请输入考试名称" />
        </el-form-item>

        <el-form-item label="开始时间" required>
          <el-date-picker
            v-model="examForm.start_time"
            type="datetime"
            placeholder="选择日期时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="结束时间" required>
          <el-date-picker
            v-model="examForm.end_time"
            type="datetime"
            placeholder="选择日期时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="总分" required>
          <el-input-number v-model="examForm.total_score" :min="0" :step="10" />
        </el-form-item>

        <!-- 选择题目区域 -->
        <el-form-item label="选择题目">
          <div class="question-select-area">
            <div v-if="selectedQuestions.length === 0" class="empty-hint">
              暂无已选题目，请从下方添加
            </div>
            <div v-for="q in selectedQuestions" :key="q.id" class="question-item">
              <span class="question-title">{{ getDisplayTitle(q) }}</span>
              <div class="question-score-wrapper">
                <el-input-number
                  v-model="q.score"
                  :min="0"
                  :max="100"
                  size="small"
                  controls-position="right"
                  style="width: 100px"
                />
                <span class="score-unit">分</span>
              </div>
              <el-button type="danger" size="small" @click="removeQuestion(q.id)">移除</el-button>
            </div>
            <div class="add-question-row">
              <el-select
                v-model="selectedQuestionId"
                placeholder="选择要添加的题目"
                @change="addQuestion"
                style="flex: 1"
                clearable
              >
                <el-option
                  v-for="q in availableQuestions"
                  :key="q.id"
                  :label="getDisplayTitle(q)"
                  :value="q.id"
                />
              </el-select>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="createExam" :loading="creating">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑考试弹窗 -->
    <el-dialog v-model="editDialogVisible" title="编辑考试" width="700px" @close="resetForm">
      <el-form :model="examForm" label-width="100px">
        <el-form-item label="考试名称" required>
          <el-input v-model="examForm.title" placeholder="请输入考试名称" />
        </el-form-item>

        <el-form-item label="开始时间" required>
          <el-date-picker
            v-model="examForm.start_time"
            type="datetime"
            placeholder="选择日期时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="结束时间" required>
          <el-date-picker
            v-model="examForm.end_time"
            type="datetime"
            placeholder="选择日期时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="总分" required>
          <el-input-number v-model="examForm.total_score" :min="0" :step="10" />
        </el-form-item>

        <!-- 选择题目区域 -->
        <el-form-item label="选择题目">
          <div class="question-select-area">
            <div v-if="selectedQuestions.length === 0" class="empty-hint">
              暂无已选题目，请从下方添加
            </div>
            <div v-for="q in selectedQuestions" :key="q.id" class="question-item">
              <span class="question-title">{{ getDisplayTitle(q) }}</span>
              <div class="question-score-wrapper">
                <el-input-number
                  v-model="q.score"
                  :min="0"
                  :max="100"
                  size="small"
                  controls-position="right"
                  style="width: 100px"
                />
                <span class="score-unit">分</span>
              </div>
              <el-button type="danger" size="small" @click="removeQuestion(q.id)">移除</el-button>
            </div>
            <div class="add-question-row">
              <el-select
                v-model="selectedQuestionId"
                placeholder="选择要添加的题目"
                @change="addQuestion"
                style="flex: 1"
                clearable
              >
                <el-option
                  v-for="q in availableQuestions"
                  :key="q.id"
                  :label="getDisplayTitle(q)"
                  :value="q.id"
                />
              </el-select>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="updateExam" :loading="creating">保存修改</el-button>
      </template>
    </el-dialog>

    <!-- 排名弹窗 -->
    <el-dialog v-model="rankVisible" :title="`考试成绩排名 - ${currentExamTitle}`" width="600px">
      <el-table :data="rankings" stripe>
        <el-table-column prop="rank" label="排名" width="70" />
        <el-table-column prop="student_name" label="学生" />
        <el-table-column prop="score" label="得分" />
      </el-table>
      <template #footer v-if="rankings.length === 0">
        <span style="color: #909399; font-size: 14px;">暂无学生参加此考试</span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getAllExams, createExam as createExamApi, deleteExam, getExamResult, updateExam as updateExamApi } from '../../api/exams'
import { getAllQuestions } from '../../api/questions'

// ===== 防死循环锁 =====
let isLoadingExams = false

const loading = ref(false)
const creating = ref(false)
const loadingStudents = ref(false)
const dialogVisible = ref(false)
const editDialogVisible = ref(false)
const rankVisible = ref(false)
const editingExamId = ref<number | null>(null)
const exams = ref<any[]>([])
const allQuestions = ref<any[]>([])
const rankings = ref<any[]>([])
const currentExamTitle = ref('')

const examForm = ref({
  title: '',
  start_time: '',
  end_time: '',
  total_score: 100
})

const selectedQuestions = ref<{ id: number; title: string; description: string; score: number }[]>([])
const selectedQuestionId = ref<number | null>(null)

const getDisplayTitle = (q: any) => {
  if (q.title) return q.title
  if (q.description) {
    return q.description.length > 30 ? q.description.substring(0, 30) + '...' : q.description
  }
  return `题目 ${q.id}`
}

const availableQuestions = computed(() => {
  return allQuestions.value.filter(q => !selectedQuestions.value.some(sq => sq.id === q.id))
})

// ===== loadExams 加锁 =====
const loadExams = async () => {
  if (isLoadingExams) {
    console.warn('⏳ 考试列表正在加载中，跳过重复请求')
    return
  }

  isLoadingExams = true
  loading.value = true

  try {
    // 考试列表可能超过一页（后端每页 20 条），这里自动翻页取全量
    exams.value = await getAllExams()
  } catch (error) {
    if (exams.value.length === 0) {
      ElMessage.error('加载考试列表失败')
    }
  } finally {
    loading.value = false
    isLoadingExams = false
  }
}

const loadQuestions = async () => {
  try {
    // 组卷需要完整题目列表（后端每页 20 条），这里自动翻页取全量
    allQuestions.value = await getAllQuestions()
  } catch (error) {
    ElMessage.error('加载题目列表失败')
  }
}

const addQuestion = () => {
  if (!selectedQuestionId.value) return
  const question = allQuestions.value.find(q => q.id === selectedQuestionId.value)
  if (question) {
    selectedQuestions.value.push({
      id: question.id,
      title: question.title || '',
      description: question.description || '',
      score: 10
    })
  }
  selectedQuestionId.value = null
}

const removeQuestion = (id: number) => {
  selectedQuestions.value = selectedQuestions.value.filter(q => q.id !== id)
}

const resetForm = () => {
  examForm.value = {
    title: '',
    start_time: '',
    end_time: '',
    total_score: 100
  }
  selectedQuestions.value = []
}

// ===== 创建考试 =====
const createExam = async () => {
  if (!examForm.value.title) {
    ElMessage.warning('请填写考试名称')
    return
  }
  if (!examForm.value.start_time || !examForm.value.end_time) {
    ElMessage.warning('请选择考试时间')
    return
  }
  if (selectedQuestions.value.length === 0) {
    ElMessage.warning('请至少选择一道题目')
    return
  }

  creating.value = true
  try {
    await createExamApi({
      title: examForm.value.title,
      start_time: examForm.value.start_time,
      end_time: examForm.value.end_time,
      total_score: examForm.value.total_score,
      exam_questions: selectedQuestions.value.map(q => ({
        question: q.id,
        score: q.score
      }))
    })
    ElMessage.success('创建成功 ✅')
    dialogVisible.value = false
    resetForm()
    await nextTick()
    await loadExams()
  } catch (error: any) {
    const msg = error.response?.data?.error || '创建失败，请重试'
    ElMessage.error(msg)
  } finally {
    creating.value = false
  }
}

// ===== 打开编辑弹窗 =====
const openEditDialog = (exam: any) => {
  editingExamId.value = exam.id

  examForm.value = {
    title: exam.title || '',
    start_time: exam.start_time || '',
    end_time: exam.end_time || '',
    total_score: exam.total_score || 100
  }

  selectedQuestions.value = (exam.exam_questions || []).map((q: any) => {
    const questionId = q.question || q.id
    const fullQuestion = allQuestions.value.find(aq => aq.id === questionId)
    return {
      id: questionId,
      title: fullQuestion?.title || q.title || '',
      description: fullQuestion?.description || q.description || '',
      score: q.score || 10
    }
  })

  editDialogVisible.value = true
}

// ===== 更新考试 =====
const updateExam = async () => {
  if (!examForm.value.title) {
    ElMessage.warning('请填写考试名称')
    return
  }
  if (!examForm.value.start_time || !examForm.value.end_time) {
    ElMessage.warning('请选择考试时间')
    return
  }
  if (selectedQuestions.value.length === 0) {
    ElMessage.warning('请至少选择一道题目')
    return
  }

  creating.value = true
  try {
    await updateExamApi(editingExamId.value!, {
      title: examForm.value.title,
      start_time: examForm.value.start_time,
      end_time: examForm.value.end_time,
      total_score: examForm.value.total_score,
      exam_questions: selectedQuestions.value.map(q => ({
        question: q.id,
        score: q.score
      }))
    })
    ElMessage.success('更新成功 ✅')
    editDialogVisible.value = false
    resetForm()
    await loadExams()
  } catch (error: any) {
    const msg = error.response?.data?.error || '更新失败，请重试'
    ElMessage.error(msg)
  } finally {
    creating.value = false
  }
}

// ===== 查看排名 =====
const viewRanking = async (examId: number) => {
  try {
    const res = await getExamResult(examId)
    const exam = exams.value.find(e => e.id === examId)
    currentExamTitle.value = exam?.title || ''
    const data = res.data || {}

    // ✅ 优先从 ranking 字段获取，兼容 details / results
    const rankingsList = data.ranking || data.details || data.results || []

    if (rankingsList.length === 0) {
      ElMessage.info('📭 暂无学生参加此考试')
      return
    }

    // ✅ 处理 ranking 列表中的字段：total → score，student__username → student_name
    rankings.value = rankingsList.map((item: any, index: number) => ({
      rank: index + 1,
      student_name: item.student_name || item.name || item.student__username || item.username || `学生 ${item.student_id || item.student__id || ''}`,
      score: item.score ?? item.total ?? 0,   // total 对应后端返回的得分
      submitted_at: item.submitted_at || '-'
    }))

    rankVisible.value = true
  } catch (error: any) {
    if (error.response?.status === 404) {
      ElMessage.info('📭 暂无排名数据')
    } else {
      ElMessage.error('加载排名失败')
    }
  }
}

// ===== 删除考试 =====
const handleDelete = (id: number) => {
  ElMessageBox.confirm('确定删除此考试？删除后不可恢复', '提示', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteExam(id)
      ElMessage.success('删除成功')
      await loadExams()
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

onMounted(() => {
  loadExams()
  loadQuestions()
})
</script>

<style scoped>
.exam-manage {
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

.exam-manage :deep(.el-dialog) {
  border-radius: 12px;
}
.exam-manage :deep(.el-dialog__header) {
  padding: 20px 24px 10px;
  border-bottom: 1px solid #f0f0f0;
}
.exam-manage :deep(.el-dialog__body) {
  padding: 20px 24px;
  max-height: 60vh;
  overflow-y: auto;
}
.exam-manage :deep(.el-dialog__footer) {
  padding: 12px 24px 20px;
  border-top: 1px solid #f0f0f0;
}

.question-select-area {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 12px;
  background-color: #fafafa;
  max-height: 220px;
  overflow-y: auto;
}

.empty-hint {
  color: #c0c4cc;
  font-size: 14px;
  text-align: center;
  padding: 16px 0;
}

.question-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  margin-bottom: 6px;
  background: white;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.question-item:last-child {
  margin-bottom: 0;
}

.question-title {
  flex: 1;
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.question-score-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.score-unit {
  font-size: 13px;
  color: #606266;
  margin-left: 2px;
}

.add-question-row {
  display: flex;
  gap: 12px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #dcdfe6;
}
.add-question-row .el-select {
  width: 100%;
}

.exam-manage :deep(.el-table) {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .exam-manage {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px 16px;
  }
  .question-item {
    flex-wrap: wrap;
  }
  .add-question-row {
    flex-wrap: wrap;
  }
}
</style>