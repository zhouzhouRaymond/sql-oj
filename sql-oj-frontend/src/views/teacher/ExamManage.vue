<template>
  <div class="exam-manage">
    <div class="header">
      <h1>📋 考试管理</h1>
      <el-button type="primary" @click="dialogVisible = true">+ 创建考试</el-button>
    </div>

    <el-table :data="exams" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="title" label="考试名称" min-width="160">
        <template #default="{ row }">
          <span :class="{ 'title-hidden': row.is_visible === false }">{{ row.title }}</span>
        </template>
      </el-table-column>
      <!-- 创建人：考试由全体教师共享，这里标注是谁创建的（任何教师都能查看 / 编辑） -->
      <el-table-column label="创建人" width="120">
        <template #default="{ row }">
          <span :title="row.teacher_username ? `登录名：${row.teacher_username}` : ''">
            {{ row.teacher_name || row.teacher_username || '-' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="examStatus(row).type" size="small">{{ examStatus(row).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="考试时间" width="200">
        <template #default="{ row }">
          <div class="exam-time">
            <span>{{ formatDateTime(row.start_time) }}</span>
            <span class="time-to">至 {{ formatDateTime(row.end_time) }}</span>
            <span class="time-duration">
              时长 {{ row.duration_minutes ? `${row.duration_minutes} 分钟` : '不限时' }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="total_score" label="总分" width="80" />
      <!-- 教师可控制该考试是否对学生公开：关闭后学生「我的考试」里看不到、也进不去 -->
      <el-table-column label="学生可见" width="130">
        <template #default="{ row }">
          <el-switch
            v-model="row.is_visible"
            :loading="savingVisible.includes(row.id)"
            :disabled="savingVisible.includes(row.id)"
            :width="56"
            inline-prompt
            active-text="公开"
            inactive-text="隐藏"
            @change="toggleVisible(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link @click="openEditDialog(row)">编辑</el-button>
          <!-- 考试情况：成绩排名 + 参加考试学生的提交明细（含重置考试次数），一个入口看全 -->
          <el-button type="primary" link @click="viewSubmissions(row)">考试情况</el-button>
          <!-- 导出成绩单：考试结束后才可用 -->
          <el-tooltip
            :disabled="isExamEnded(row)"
            content="考试结束后才能导出成绩"
            placement="top"
          >
            <span>
              <el-button
                type="success"
                link
                :disabled="!isExamEnded(row)"
                :loading="exportingId === row.id"
                @click="handleExport(row)"
              >导出</el-button>
            </span>
          </el-tooltip>
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

        <el-form-item label="考试时长">
          <el-input-number v-model="examForm.duration_minutes" :min="0" :step="10" />
          <span class="unit-hint">分钟（0 = 不限时，仅受考试起止时间约束）</span>
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
        <!-- 考试由全体教师共享：展示创建人，任何教师都可以编辑 -->
        <el-form-item v-if="editingExamCreator" label="创建人">
          <span class="creator-text">{{ editingExamCreator }}</span>
        </el-form-item>
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

        <el-form-item label="考试时长">
          <el-input-number v-model="examForm.duration_minutes" :min="0" :step="10" />
          <span class="unit-hint">分钟（0 = 不限时，仅受考试起止时间约束）</span>
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

    <!-- 考试情况弹窗：成绩排名 + 参加考试学生的提交明细（含重置考试次数），展开行看每道题 -->
    <el-dialog
      v-model="submissionVisible"
      :title="`考试情况 - ${currentExamTitle}`"
      width="1040px"
      top="6vh"
      @closed="submissionRows = []"
    >
      <div class="sub-overview">
        <el-tag type="info" effect="plain">参加考试 {{ submissionRows.length }} 人</el-tag>
        <el-tag type="success" effect="plain">已提交 {{ submittedRows.length }} 人</el-tag>
        <el-tag type="warning" effect="plain">未提交 {{ unsubmittedRows.length }} 人</el-tag>
        <el-tag effect="plain">提交记录 {{ submissionTotal }} 条</el-tag>
        <el-tag type="danger" effect="plain">已提交者平均分 {{ avgScore }}</el-tag>
      </div>

      <el-table
        v-loading="submissionLoading"
        :data="submissionRows"
        :row-key="(row: any) => row.student_id"
        empty-text="本场考试暂无学生参加"
        :default-sort="{ prop: 'score', order: 'descending' }"
        stripe
        size="small"
        max-height="460"
      >
        <!-- 展开行：该生在本场考试每道题的提交（得分 / 判题状态 / 时间 / 详情） -->
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="stu-subs">
              <div v-if="row.submissions.length === 0" class="empty-hint">
                该学生已进入考试，但未提交任何题目
              </div>
              <el-table v-else :data="row.submissions" border size="small">
                <el-table-column label="题目" min-width="160" show-overflow-tooltip>
                  <template #default="{ row: sub }">
                    {{ sub.question_title || sub.question_desc || `题目 ${sub.question}` }}
                  </template>
                </el-table-column>
                <el-table-column label="得分" width="80" align="center">
                  <template #default="{ row: sub }">{{ sub.score ?? 0 }}</template>
                </el-table-column>
                <el-table-column label="判题状态" width="130" align="center">
                  <template #default="{ row: sub }">
                    <el-tag :type="statusTagType(sub.execution_status)" size="small">
                      {{ sub.execution_status || 'PENDING' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="提交时间" width="160" align="center">
                  <template #default="{ row: sub }">
                    {{ formatDateTime(sub.submission_time) }}
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="100" align="center">
                  <template #default="{ row: sub }">
                    <el-button type="primary" link @click="viewSubmissionDetail(sub.id)">
                      查看详情
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="rank" label="排名" width="70" align="center" />
        <el-table-column label="用户名" min-width="120">
          <template #default="{ row }">{{ row.student_name || row.username || '-' }}</template>
        </el-table-column>
        <el-table-column label="登录名" min-width="120">
          <template #default="{ row }">{{ row.username || '-' }}</template>
        </el-table-column>
        <!-- 只显示得分：默认按得分降序排列，点击表头可切换排序 -->
        <el-table-column prop="score" label="得分" width="100" align="center" sortable>
          <template #default="{ row }">
            <span v-if="row.submissions.length" class="score-strong">{{ row.score }}</span>
            <span v-else class="score-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="studentStatus(row).type" size="small">
              {{ studentStatus(row).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已答题目" width="100" align="center">
          <template #default="{ row }">{{ row.doneQuestions }} / {{ examQuestionCount }}</template>
        </el-table-column>
        <el-table-column label="最近提交" width="160" align="center">
          <template #default="{ row }">
            {{ row.lastSubmit ? formatDateTime(row.lastSubmit) : '-' }}
          </template>
        </el-table-column>
        <!-- 重置考试次数（按个人）：清除该生本场考试的作答记录，使其可重新参加 -->
        <el-table-column label="操作" width="130" align="center" fixed="right">
          <template #default="{ row }">
            <el-tooltip content="清除该生本场考试的作答记录，可重新参加" placement="top">
              <span>
                <el-button
                  type="warning"
                  link
                  :disabled="!row.student_id"
                  :loading="resettingId === row.student_id"
                  @click="handleResetAttempt(row)"
                >重置考试次数</el-button>
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <span class="sub-tip">
          展开左侧箭头可查看该生每道题的提交明细；「查看详情」可看提交的 SQL 与判题用例
        </span>
      </template>
    </el-dialog>

    <!-- 提交详情弹窗：SQL + 判题明细（与「我的提交记录」共用同一组件） -->
    <el-dialog v-model="subDetailVisible" title="提交详情" width="760px" append-to-body>
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
        <pre class="sql-detail">{{ subDetailLoading ? '加载中…' : (currentDetail.submitted_sql || '（空）') }}</pre>
      </div>
      <div v-if="!subDetailLoading" class="detail-item">
        <SubmissionCaseDetail :detail="currentDetail" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getAllExams, createExam as createExamApi, deleteExam, getExamResult, updateExam as updateExamApi, patchExam, exportExamScores, resetExamAttempt } from '../../api/exams'
import { getAllQuestions } from '../../api/questions'
import { getExamSubmissions, getSubmission } from '../../api/submissions'
import { formatDateTime } from '../../utils/time'
import SubmissionCaseDetail from '../../components/SubmissionCaseDetail.vue'

// ===== 防死循环锁 =====
let isLoadingExams = false

const loading = ref(false)
const creating = ref(false)
const loadingStudents = ref(false)
const dialogVisible = ref(false)
const editDialogVisible = ref(false)
const editingExamId = ref<number | null>(null)
const editingExamCreator = ref('')   // 编辑弹窗展示的创建人
const exams = ref<any[]>([])
const allQuestions = ref<any[]>([])
const currentExamTitle = ref('')
const currentExamId = ref<number | null>(null)
const currentExam = ref<any>(null)   // 当前查看「考试情况」的考试（重置后刷新用）
const resettingId = ref<number | null>(null)  // 正在重置考试次数的学生 id

// 正在切换「学生可见」的考试 id（同一行保存期间禁用开关，避免重复提交）
const savingVisible = ref<number[]>([])

const examForm = ref({
  title: '',
  start_time: '',
  end_time: '',
  total_score: 100,
  duration_minutes: 0
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
    total_score: 100,
    duration_minutes: 0
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
      duration_minutes: examForm.value.duration_minutes,
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
  editingExamCreator.value = exam.teacher_name || exam.teacher_username || ''

  examForm.value = {
    title: exam.title || '',
    start_time: exam.start_time || '',
    end_time: exam.end_time || '',
    total_score: exam.total_score || 100,
    duration_minutes: exam.duration_minutes || 0
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
      duration_minutes: examForm.value.duration_minutes,
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

// ===== 重置某位学生的考试次数（按个人）=====
const handleResetAttempt = (row: any) => {
  if (!currentExamId.value || !row.student_id) return
  const examId = currentExamId.value
  ElMessageBox.confirm(
    `确定重置「${row.student_name}」在本场考试的考试次数？重置后其作答记录将被清除，可重新参加考试`,
    '重置考试次数',
    { confirmButtonText: '确定重置', cancelButtonText: '取消', type: 'warning' },
  ).then(async () => {
    resettingId.value = row.student_id
    try {
      await resetExamAttempt(examId, row.student_id)
      ElMessage.success('已重置，该学生可重新参加考试 ✅')
      if (currentExam.value) await loadSubmissions(currentExam.value)  // 静默刷新
    } catch (error: any) {
      ElMessage.error(error.response?.data?.error || '重置失败，请重试')
    } finally {
      resettingId.value = null
    }
  }).catch(() => {})
}

// ===== 本场考试所有学生的提交情况 =====
const submissionVisible = ref(false)
const submissionLoading = ref(false)
const submissionRows = ref<any[]>([])
const examQuestionCount = ref(0)

// 提交详情弹窗（SQL + 判题明细，与「我的提交」共用同一组件）
const subDetailVisible = ref(false)
const subDetailLoading = ref(false)
const currentDetail = ref<any>({})

// 判题状态 → 标签颜色（与「我的提交记录」保持一致）
const statusTagType = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'error'
    case 'ERROR': return 'error'
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
}

// 学生在本场考试的状态：已提交 / 未提交（已进入考试但没交）
const studentStatus = (row: any) => {
  if (row.submissions.length > 0) return { text: '已提交', type: 'success' as const }
  return { text: '未提交', type: 'warning' as const }
}

// 汇总：参加考试人数 / 已提交 / 未提交 / 提交记录数 / 平均分
const submittedRows = computed(
  () => submissionRows.value.filter((r) => r.submissions.length > 0),
)
const unsubmittedRows = computed(
  () => submissionRows.value.filter((r) => r.submissions.length === 0),
)
const submissionTotal = computed(
  () => submissionRows.value.reduce((n, r) => n + r.submissions.length, 0),
)
const avgScore = computed(() => {
  if (submittedRows.value.length === 0) return '-'
  const sum = submittedRows.value.reduce((n, r) => n + (Number(r.score) || 0), 0)
  return (sum / submittedRows.value.length).toFixed(1)
})

// 整理数据：只列「参加本场考试」的学生——排名接口给出已提交者与「已进入但未提交」者
// （两者都来自该场考试的作答记录 / 进入记录），未参加考试的学生不会出现在列表里。
const loadSubmissions = async (exam: any) => {
  submissionLoading.value = true
  currentExam.value = exam
  try {
    const [rankRes, submissions] = await Promise.all([
      getExamResult(exam.id),
      getExamSubmissions(exam.id),
    ])

    examQuestionCount.value = (exam.exam_questions || []).length

    // 学生 id → 该生在本场考试的提交
    const subsByStudent = new Map<number, any[]>()
    submissions.forEach((sub: any) => {
      const sid = Number(sub.student)
      if (!Number.isFinite(sid)) return
      if (!subsByStudent.has(sid)) subsByStudent.set(sid, [])
      subsByStudent.get(sid)!.push(sub)
    })

    const rows = new Map<number, any>()

    // 排名里的参考学生（含已进入但未提交者）：用户名 / 得分 / 是否已提交
    const ranking = rankRes.data?.ranking || rankRes.data?.details || []
    ranking.forEach((item: any, index: number) => {
      const sid = Number(item.student__id ?? item.student_id ?? item.student?.id)
      if (!Number.isFinite(sid)) return
      rows.set(sid, {
        rank: index + 1,          // 名次与教师端排名一致（同分按学号先后）
        student_id: sid,
        student_name: item.student__display_name || item.student__username || `学生 ${sid}`,
        username: item.student__username || '',
        score: item.score ?? item.total ?? 0,
        entered: true,
        submitted: item.submitted !== false,
      })
    })

    submissionRows.value = [...rows.values()]
      .map((row) => {
        const mine = (subsByStudent.get(row.student_id) || [])
          .slice()
          .sort(
            (a, b) =>
              new Date(a.submission_time).getTime() - new Date(b.submission_time).getTime(),
          )
        const lastSubmit = mine.reduce(
          (acc: string, s: any) => (s.submission_time > acc ? s.submission_time : acc),
          '',
        )
        return {
          ...row,
          submissions: mine,
          score: row.score ?? 0,
          doneQuestions: new Set(mine.map((s: any) => Number(s.question))).size,
          lastSubmit,
        }
      })
      .sort((a, b) => (a.rank || 0) - (b.rank || 0))   // 按官方名次排列（未提交者名次在后）
  } catch (error) {
    ElMessage.error('加载提交情况失败')
  } finally {
    submissionLoading.value = false
  }
}

const viewSubmissions = async (exam: any) => {
  currentExamId.value = exam.id
  currentExamTitle.value = exam.title || '未命名考试'
  submissionRows.value = []
  submissionVisible.value = true
  await loadSubmissions(exam)
}

// 查看某条提交的详情（SQL + 判题明细）
const viewSubmissionDetail = async (submissionId: number) => {
  if (!submissionId) return
  subDetailVisible.value = true
  subDetailLoading.value = true
  currentDetail.value = { id: submissionId }
  try {
    const res = await getSubmission(submissionId)
    currentDetail.value = res.data || {}
  } catch (error) {
    ElMessage.error('获取提交详情失败')
  } finally {
    subDetailLoading.value = false
  }
}

// 切换「学生可见」：v-model 已先更新开关状态，这里落库；失败则回滚开关
const toggleVisible = async (row: any) => {
  const next = Boolean(row.is_visible)
  savingVisible.value = [...savingVisible.value, row.id]
  try {
    await patchExam(row.id, { is_visible: next })
    ElMessage.success(next ? '已公开给学生 ✅' : '已对学生隐藏 🙈')
  } catch (error) {
    row.is_visible = !next
    ElMessage.error('操作失败，请重试')
  } finally {
    savingVisible.value = savingVisible.value.filter((id) => id !== row.id)
  }
}

// ===== 导出成绩单（考试结束后可用） =====
const exportingId = ref<number | null>(null)

// 考试是否已结束（结束后才允许导出成绩单）
const isExamEnded = (exam: any) => {
  const end = new Date(exam?.end_time).getTime()
  return Number.isFinite(end) && Date.now() > end
}

// 列表状态：未开始 / 进行中 / 已结束
const examStatus = (exam: any) => {
  const now = Date.now()
  const start = new Date(exam?.start_time).getTime()
  const end = new Date(exam?.end_time).getTime()
  if (Number.isFinite(end) && now > end) return { text: '已结束', type: 'info' as const }
  if (Number.isFinite(start) && now < start) return { text: '未开始', type: 'warning' as const }
  return { text: '进行中', type: 'success' as const }
}

// 导出接口失败时响应体是 blob，这里读出后端的中文提示
const readBlobError = async (error: any): Promise<string> => {
  const data = error?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      return parsed.error || parsed.detail || '请稍后重试'
    } catch {
      return '请稍后重试'
    }
  }
  return error?.response?.data?.error || error?.response?.data?.detail || '请稍后重试'
}

const handleExport = async (row: any) => {
  if (!isExamEnded(row)) {
    ElMessage.warning('考试结束后才能导出成绩')
    return
  }
  exportingId.value = row.id
  try {
    const res = await exportExamScores(row.id)
    const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `${row.title || '考试'}-成绩单.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('成绩单已导出 ✅')
  } catch (error) {
    ElMessage.error(`导出失败：${await readBlobError(error)}`)
  } finally {
    exportingId.value = null
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
  font-size: 20px;
  color: #2d3748;
}

/* 已对学生隐藏的考试：标题弱化显示（与题目列表保持一致） */
.title-hidden {
  color: #a8abb2;
}

/* 考试时间：开始 / 结束两行显示，比原来的两个独立列更紧凑 */
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
  color: #909399;
}

/* 「考试时长」输入框后的单位说明 */
.unit-hint {
  margin-left: 8px;
  color: #909399;
  font-size: 13px;
}

/* 编辑弹窗里的「创建人」只读展示 */
.creator-text {
  color: #606266;
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

/* ===== 提交情况弹窗 ===== */
.sub-overview {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
/* 展开行内的「该生提交明细」 */
.stu-subs {
  padding: 8px 12px 12px;
  background: #fafbfc;
}
.stu-subs .empty-hint {
  padding: 8px 0;
}
.score-strong {
  font-weight: 700;
  color: #409eff;
}
.score-muted {
  color: #c0c4cc;
}
.sub-tip {
  font-size: 13px;
  color: #909399;
}

/* 提交详情弹窗内的 SQL 块 */
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