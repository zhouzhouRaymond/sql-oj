<template>
  <div class="exam-panel" v-loading="loading">
    <div class="exam-header">
      <h1>{{ examInfo.title }}</h1>
      <div class="timer" :class="{ warning: remainingSeconds < 300 }">
        ⏰ 剩余时间：{{ formatTime(remainingSeconds) }}
      </div>
    </div>

    <div class="exam-content">
      <div class="questions-nav">
        <h3>题目列表</h3>
        <div class="question-buttons">
          <el-button
            v-for="(q, idx) in questions"
            :key="q.id"
            :type="getButtonType(idx)"
            size="small"
            @click="currentIndex = idx"
          >
            {{ idx + 1 }}
          </el-button>
        </div>
      </div>

      <div class="question-area">
        <div class="question-header">
          <h3>题目 {{ currentIndex + 1 }}</h3>
          <span class="score">分值：{{ currentQuestion?.score || 0 }} 分</span>
        </div>
        <div class="description markdown-body" v-html="renderMarkdown(currentQuestion?.description)"></div>

        <div class="editor-hint">
          💾 作答会自动暂存（本机 + 服务端），刷新或换设备都能恢复；到点未交卷会按最后暂存的作答自动交卷
        </div>

        <SqlEditor
          v-if="currentQuestion"
          v-model="answers[currentQuestion.id]"
          :min-height="220"
          placeholder="请输入 SQL 语句..."
        />

        <div class="actions">
          <el-button @click="prevQuestion" :disabled="currentIndex === 0">上一题</el-button>
          <el-button type="primary" @click="nextQuestion" :disabled="currentIndex === questions.length - 1">下一题</el-button>
          <el-button type="success" @click="submitAll">提交试卷</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { startExam, saveExamDraft } from '../../api/exams'
import { marked } from 'marked'
import request from '../../api/request'          // 直接导入 axios 实例，确保请求体格式正确
import SqlEditor from '../../components/SqlEditor.vue'
import { useUserStore } from '../../stores/user'
import { buildDraftKey, clearDraft, loadDraft, saveDraft } from '../../utils/draft'

// 配置 marked
marked.setOptions({
  breaks: true,
  gfm: true,
  tables: true
})

// 渲染 Markdown
const renderMarkdown = (text: string) => {
  if (!text) return ''
  return marked.parse(text)
}

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const examId = computed(() => Number(route.params.id))

const loading = ref(false)
const examInfo = ref<any>({})
const questions = ref<any[]>([])
const answers = ref<Record<number, string>>({})
const currentIndex = ref(0)
const remainingSeconds = ref(0)
let timer: any = null

// ===== 作答草稿：本机（localStorage）+ 服务端双重暂存 =====
// - 本机草稿：刷新 / 误关页面后仍保留已编辑的内容（按「登录名 + 考试 id」隔离）；
// - 服务端草稿：定时同步，换设备 / 换浏览器也能接着答；到点未交卷时由服务端兜底交卷。
const draftKey = computed(
  () => buildDraftKey('exam', userStore.user?.username, examId.value),
)
let draftTimer: any = null
let finished = false  // 已交卷后不再回写草稿
let localDraftRestored = false  // 本机是否已恢复过草稿（决定是否用服务端草稿兜底）

const hasAnswer = () =>
  Object.values(answers.value).some((sql) => String(sql ?? '').trim() !== '')

const persistDraft = () => saveDraft(draftKey.value, answers.value)

// 用 {题目 id: SQL} 填充编辑器（忽略空白作答）
const applyDraft = (draft: Record<string, string>) => {
  Object.entries(draft || {}).forEach(([id, sql]) => {
    if (String(sql ?? '').trim() === '') return
    answers.value[Number(id)] = String(sql ?? '')
  })
}

const restoreDraft = (): boolean => {
  const parsed = loadDraft<Record<string, string>>(draftKey.value)
  if (!parsed || typeof parsed !== 'object') return false
  applyDraft(parsed)
  return hasAnswer()
}

// 编辑内容变化后防抖落盘，避免每次按键都写 localStorage
watch(answers, () => {
  if (draftTimer) clearTimeout(draftTimer)
  draftTimer = setTimeout(persistDraft, 300)
}, { deep: true })

// ===== 服务端草稿同步（作答自动暂存 + 服务端兜底交卷的前提）=====
const DRAFT_SYNC_INTERVAL = 20000  // 20 秒检查一次，内容有变化才发请求
let syncTimer: any = null
let lastSyncedDraft = ''

const syncDraft = async (force = false) => {
  if (finished || !hasAnswer()) return
  const payload = JSON.stringify(answers.value)
  if (!force && payload === lastSyncedDraft) return
  try {
    const res = await saveExamDraft(examId.value, answers.value)
    lastSyncedDraft = payload
    // 以服务端为准校正倒计时，避免本地计时漂移
    if (typeof res.data?.remaining_seconds === 'number') {
      remainingSeconds.value = res.data.remaining_seconds
    }
  } catch (error) {
    // 网络异常 / 已交卷等：静默失败，本机草稿仍在，下次同步会重试
  }
}

// 页面被隐藏（切标签 / 关闭页面）时尽快同步一次
const handleVisibilityChange = () => {
  if (document.visibilityState === 'hidden') syncDraft(true)
}

// 离开页面前提醒：作答已暂存，但仍需回来点「提交试卷」才会判分
const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (finished || !hasAnswer()) return
  event.preventDefault()
  event.returnValue = ''
}

const currentQuestion = computed(() => questions.value[currentIndex.value])

const getButtonType = (idx: number) => {
  const q = questions.value[idx]
  if (answers.value[q?.id]) return 'success'
  if (idx === currentIndex.value) return 'primary'
  return 'default'
}

const formatTime = (seconds: number) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

const prevQuestion = () => {
  if (currentIndex.value > 0) currentIndex.value--
}

const nextQuestion = () => {
  if (currentIndex.value < questions.value.length - 1) currentIndex.value++
}

const loadExam = async () => {
  loading.value = true
  try {
    const res = await startExam(examId.value)
    examInfo.value = res.data
    questions.value = res.data.questions || []
    remainingSeconds.value = res.data.remaining_seconds || 7200
    // 本机没有草稿时，用服务端同步过的草稿恢复（换设备 / 换浏览器也能接着答）
    const serverDraft = res.data.draft || {}
    if (!localDraftRestored && Object.keys(serverDraft).length > 0) {
      applyDraft(serverDraft)
      ElMessage.info('已从服务器恢复上次同步的作答内容')
    }
    startTimer()
    syncDraft(true)   // 进入考试先把当前作答同步一次
  } catch (error: any) {
    const data = error.response?.data || {}
    // 到点未交卷：服务端已按最后同步的作答自动交卷 → 直接看结果
    if (data.auto_submitted) {
      ElMessage.warning(data.error || '作答时间已到，系统已自动交卷')
      router.push({ path: `/exam/${examId.value}/result`, query: { from: 'exam' } })
      return
    }
    // 例如「你已参加过本次考试，不能重复参加」「考试已结束」等，直接展示后端提示
    ElMessage.error(data.error || '加载考试失败')
    router.push('/questions')
  } finally {
    loading.value = false
  }
}

const startTimer = () => {
  timer = setInterval(() => {
    if (remainingSeconds.value > 0) {
      remainingSeconds.value--
    } else {
      clearInterval(timer)
      autoSubmit()
    }
  }, 1000)
}

// 真正提交试卷（返回是否提交成功）
const doSubmit = async () => {
  const answerList = Object.entries(answers.value).map(([questionId, sql]) => ({
    question_id: Number(questionId),
    submitted_sql: sql
  }))

  if (answerList.length === 0) {
    ElMessage.warning('你还没有作答，无法提交')
    return false
  }

  try {
    await request.post(`/exams/${examId.value}/submit/`, { answers: answerList })
    finished = true
    clearDraft(draftKey.value)   // 交卷成功后清除本地草稿
    ElMessage.success('提交成功 ✅')
    // 带 from=exam：结果页据此判定为「考试结束」入口——离开即退出登录（详见 ExamResult.vue）
    router.push({ path: `/exam/${examId.value}/result`, query: { from: 'exam' } })
    return true
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '提交失败，请重试')
    return false
  }
}

// 手动交卷：先确认
const submitAll = () => {
  ElMessageBox.confirm('确定要提交试卷吗？提交后无法修改', '提示', {
    confirmButtonText: '确定提交',
    cancelButtonText: '继续答题',
    type: 'warning'
  }).then(doSubmit)
}

// 倒计时结束：自动交卷（无需确认）
const autoSubmit = async () => {
  ElMessage.warning('考试时间已到，正在自动交卷…')
  const ok = await doSubmit()
  if (!ok) router.push('/questions')  // 无作答 / 提交失败时离开考试页
}

onMounted(() => {
  // 先恢复上次未提交的作答，再加载考试（题目到达后即可直接编辑）
  localDraftRestored = restoreDraft()
  if (localDraftRestored) {
    ElMessage.info('已恢复上次未提交的作答内容')
  }
  loadExam()

  // 定时把作答同步到服务端：换设备可恢复；到点未交卷时服务端按它兜底交卷
  syncTimer = setInterval(() => syncDraft(), DRAFT_SYNC_INTERVAL)
  document.addEventListener('visibilitychange', handleVisibilityChange)
  window.addEventListener('beforeunload', handleBeforeUnload)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  if (draftTimer) clearTimeout(draftTimer)
  if (syncTimer) clearInterval(syncTimer)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (!finished) {
    persistDraft()    // 离开页面前落盘，避免防抖未触发导致丢失
    syncDraft(true)   // 并尽力同步到服务端（关闭页面时请求可能被中断，有定时同步兜底）
  }
})
</script>

<style scoped>
.exam-panel {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
}
.editor-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #909399;
}
.exam-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px 20px;
  background: white;
  border-radius: 8px;
  margin-bottom: 20px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.exam-header h1 {
  margin: 0;
  font-size: 20px;
}
.timer {
  font-size: 24px;
  font-weight: bold;
  color: #409eff;
  font-family: monospace;
}
.timer.warning {
  color: #f56c6c;
  animation: pulse 1s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
.exam-content {
  display: flex;
  gap: 20px;
}
.questions-nav {
  width: 200px;
  background: white;
  padding: 15px;
  border-radius: 8px;
  height: fit-content;
}
.question-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 15px;
}
.question-area {
  flex: 1;
  background: white;
  padding: 20px;
  border-radius: 8px;
}
.question-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}
.score {
  color: #e6a23c;
  font-weight: bold;
}
.description {
  padding: 15px;
  background-color: #f5f7fa;
  border-radius: 4px;
  margin: 15px 0;
  line-height: 1.6;
}
.actions {
  margin-top: 20px;
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 900px) {
  .exam-panel {
    padding: 12px;
  }
  .exam-header {
    flex-wrap: wrap;
    gap: 8px;
    padding: 12px 16px;
  }
  .timer {
    font-size: 18px;
  }
  .exam-content {
    flex-direction: column;
    gap: 12px;
  }
  .questions-nav {
    width: 100%;
  }
  .question-area {
    /* 允许收缩，避免长内容撑破页面 */
    min-width: 0;
    padding: 12px;
  }
}
</style>