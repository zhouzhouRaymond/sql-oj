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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { startExam } from '../../api/exams'      // 保留 startExam 导入
import { getQuestionDetail } from '../../api/questions'
import { marked } from 'marked'
import request from '../../api/request'          // 直接导入 axios 实例，确保请求体格式正确
import SqlEditor from '../../components/SqlEditor.vue'

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
const examId = computed(() => Number(route.params.id))

const loading = ref(false)
const examInfo = ref<any>({})
const questions = ref<any[]>([])
const answers = ref<Record<number, string>>({})
const currentIndex = ref(0)
const remainingSeconds = ref(0)
let timer: any = null

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
    startTimer()
  } catch (error) {
    ElMessage.error('加载考试失败')
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
      ElMessage.warning('考试时间已到，自动交卷')
      submitAll()
    }
  }, 1000)
}

const submitAll = async () => {
  ElMessageBox.confirm('确定要提交试卷吗？提交后无法修改', '提示', {
    confirmButtonText: '确定提交',
    cancelButtonText: '继续答题',
    type: 'warning'
  }).then(async () => {
    const answerList = Object.entries(answers.value).map(([questionId, sql]) => ({
      question_id: Number(questionId),
      submitted_sql: sql
    }))

    if (answerList.length === 0) {
      ElMessage.warning('请至少回答一道题')
      return
    }

    try {
      await request.post(`/exams/${examId.value}/submit/`, { answers: answerList })
      ElMessage.success('提交成功 ✅')
      router.push(`/exam/${examId.value}/result`)
    } catch (error: any) {
      const msg = error.response?.data?.error || '提交失败，请重试'
      ElMessage.error(msg)
    }
  })
}

onMounted(() => {
  loadExam()
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.exam-panel {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
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