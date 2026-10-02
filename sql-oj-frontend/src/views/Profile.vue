<template>
  <div class="profile-container">
    <div class="header">
      <h1>👤 个人中心</h1>
      <el-button @click="goBack">← 返回</el-button>
    </div>

    <div class="profile-content">
      <!-- 左侧：用户信息卡片 -->
      <el-card class="info-card">
        <template #header>
          <span>📋 个人信息</span>
        </template>
        <div class="avatar-section">
          <el-avatar :size="80" :src="userAvatar">
            {{ userStore.displayName?.charAt(0)?.toUpperCase() }}
          </el-avatar>
          <div class="user-badge">
            <el-tag :type="userStore.user?.user_type === 'teacher' ? 'warning' : 'success'">
              {{ userStore.user?.user_type === 'teacher' ? '教师' : '学生' }}
            </el-tag>
          </div>
        </div>

        <el-form :model="profileForm" label-width="80px" class="profile-form">
          <el-form-item label="登录名">
            <el-input v-model="profileForm.username" disabled />
            <div style="margin-top: 4px; color: #909399; font-size: 12px;">登录名用于登录，不可修改</div>
          </el-form-item>
          <el-form-item label="用户名">
            <el-input
              v-model="profileForm.display_name"
              placeholder="请输入用户名（留空则与登录名相同）"
              maxlength="50"
              clearable
            />
            <div style="margin-top: 4px; color: #909399; font-size: 12px;">展示用用户名，可自定义</div>
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="profileForm.email" placeholder="选填，可不填" clearable />
            <div style="margin-top: 4px; color: #909399; font-size: 12px;">选填，用于接收通知</div>
          </el-form-item>
          <el-form-item label="身份">
            <el-input :value="userStore.user?.user_type === 'teacher' ? '教师' : '学生'" disabled />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="updateProfile" :loading="updating">
              保存修改
            </el-button>
            <el-button @click="openPasswordDialog">🔒 修改密码</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 右侧：统计数据 -->
      <el-card class="stats-card">
        <template #header>
          <span>📊 个人数据</span>
        </template>

        <div class="stats-grid">
          <!-- 学生统计 -->
          <template v-if="!isTeacher">
            <div class="stat-item">
              <div class="stat-value">{{ stats.total_submissions || 0 }}</div>
              <div class="stat-label">总提交次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ stats.pass_rate != null ? (stats.pass_rate * 100).toFixed(0) : 0 }}%</div>
              <div class="stat-label">通过率</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ stats.passed_questions || 0 }}</div>
              <div class="stat-label">通过题目数</div>
            </div>
          </template>

          <!-- 教师统计 -->
          <template v-if="isTeacher">
            <div class="stat-item">
              <div class="stat-value">{{ stats.questions_created || 0 }}</div>
              <div class="stat-label">创建题目数</div>
            </div>
            <div class="stat-item">
              <div class="stat-value">{{ stats.exams_created || 0 }}</div>
              <div class="stat-label">创建考试数</div>
            </div>
          </template>
        </div>

        <!-- 提交记录（仅学生可见）：显示全部记录，按时间由近到远，每页 20 条 -->
        <div v-if="!isTeacher" class="recent-submissions">
          <h4>📝 提交记录</h4>
          <el-table :data="recentSubmissions" v-loading="submissionsLoading" size="small">
            <!-- 使用 min-width 让列随容器浮动，表格始终撑满所在卡片 -->
            <el-table-column prop="question" label="题目ID" min-width="90" />
            <el-table-column prop="execution_status" label="状态" min-width="120">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.execution_status)" size="small">
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
            <el-table-column label="操作" min-width="130" align="center">
              <template #default="{ row }">
                <el-button type="primary" link size="small" @click="viewCode(row)">
                  查看提交代码
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!submissionsLoading && recentSubmissions.length === 0" class="empty-hint">
            暂无提交记录
          </div>
          <div v-if="total > 0" class="pagination">
            <el-pagination
              v-model:current-page="currentPage"
              :page-size="pageSize"
              :total="total"
              layout="prev, pager, next, total"
              small
              @current-change="loadSubmissions"
            />
          </div>
        </div>
      </el-card>
    </div>

    <!-- 🔒 修改密码浮窗 -->
    <el-dialog v-model="passwordDialogVisible" title="修改密码" width="420px">
      <el-form :model="passwordForm" label-width="90px">
        <el-form-item label="登录名">
          <el-input :value="userStore.user?.username" disabled />
        </el-form-item>
        <el-form-item label="原密码" required>
          <el-input
            v-model="passwordForm.old_password"
            type="password"
            show-password
            placeholder="请输入原密码"
          />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input
            v-model="passwordForm.new_password"
            type="password"
            show-password
            placeholder="请输入新密码（至少 6 位）"
          />
        </el-form-item>
        <el-form-item label="确认新密码" required>
          <el-input
            v-model="passwordForm.confirm_password"
            type="password"
            show-password
            placeholder="请再次输入新密码"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="passwordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="passwordSaving" @click="submitPassword">
          确定修改
        </el-button>
      </template>
    </el-dialog>

    <!-- 提交代码浮窗 -->
    <el-dialog v-model="codeDialogVisible" title="提交代码" width="640px">
      <div class="code-meta">
        <span>题目 ID：{{ currentSubmission.question ?? '-' }}</span>
        <span>状态：{{ currentSubmission.execution_status || 'PENDING' }}</span>
        <span>得分：{{ currentSubmission.score ?? 0 }}</span>
        <span>提交时间：{{ formatDateTime(currentSubmission.submission_time || currentSubmission.created_at) }}</span>
      </div>
      <!-- 打开浮窗时才请求详情接口获取 SQL（列表接口不返回该字段） -->
      <pre class="code-block">{{ codeLoading ? '加载中…' : (currentSubmission.submitted_sql || '（无提交代码）') }}</pre>
      <template #footer>
        <el-button @click="codeDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import { updateUser, getUserStats, getMySubmissions, changePassword } from '../api/users'
import { getSubmission } from '../api/submissions'
import { formatDateTime, formatRelativeTime } from '../utils/time'

const router = useRouter()
const userStore = useUserStore()

const isTeacher = computed(() => userStore.user?.user_type === 'teacher')

const profileForm = ref({
  username: userStore.user?.username || '',          // 登录名（只读展示）
  display_name: userStore.user?.display_name || '',  // 自定义用户名（可修改）
  email: userStore.user?.email || ''
})

// ✅ 使用后端实际返回的字段名
const stats = ref({
  total_submissions: 0,
  pass_rate: 0,
  passed_questions: 0,
  questions_created: 0,
  exams_created: 0
})

const recentSubmissions = ref<any[]>([])
const updating = ref(false)
const submissionsLoading = ref(false)

// 🔒 修改密码
const passwordDialogVisible = ref(false)
const passwordSaving = ref(false)
const passwordForm = ref({
  old_password: '',
  new_password: '',
  confirm_password: ''
})
// 提交记录分页：每页 20 条
const currentPage = ref(1)
const pageSize = 20
const total = ref(0)

// 提交代码浮窗
const codeDialogVisible = ref(false)
const codeLoading = ref(false)
const currentSubmission = ref<any>({})

// 用于让「相对时间」随时间自动刷新
const nowTick = ref(Date.now())
let clockTimer: number | undefined

// 查看某次提交的 SQL 代码：列表接口不返回 submitted_sql，点开时按 id 懒加载
const viewCode = async (row: any) => {
  if (!row?.id) return
  codeDialogVisible.value = true
  codeLoading.value = true
  currentSubmission.value = row || {}
  try {
    const res = await getSubmission(row.id)
    currentSubmission.value = { ...row, ...(res.data || {}) }
  } catch (error) {
    ElMessage.error('加载提交代码失败')
  } finally {
    codeLoading.value = false
  }
}

const userAvatar = computed(() => {
  return userStore.user?.avatar || ''
})

// ✅ 加载统计数据，直接映射后端字段
const loadStats = async () => {
  try {
    const res = await getUserStats()
    const data = res.data || {}
    stats.value = {
      total_submissions: data.total_submissions || 0,
      pass_rate: data.pass_rate || 0,
      passed_questions: data.passed_questions || 0,
      questions_created: data.questions_created || 0,
      exams_created: data.exams_created || 0
    }
  } catch (error) {
    console.log('📊 统计数据接口暂不可用（后端未实现）')
  }
}

// 加载提交记录：显示全部记录，后端按提交时间倒序，每页 20 条
const loadSubmissions = async () => {
  submissionsLoading.value = true
  try {
    const res = await getMySubmissions({ page: currentPage.value })
    const data = res.data || {}
    if (Array.isArray(data)) {
      // 兜底：接口未开启分页时（直接返回数组）
      recentSubmissions.value = data
      total.value = data.length
    } else {
      recentSubmissions.value = data.results || []
      total.value = data.count || 0
    }
  } catch (error) {
    console.log('📝 提交记录接口暂不可用')
    recentSubmissions.value = []
    total.value = 0
  } finally {
    submissionsLoading.value = false
  }
}

const updateProfile = async () => {
  // 邮箱选填：填了才校验格式
  const email = profileForm.value.email.trim()
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    ElMessage.warning('邮箱格式不正确（也可以留空不填）')
    return
  }

  updating.value = true
  try {
    await updateUser({
      display_name: profileForm.value.display_name,  // 留空后端会回退为登录名
      email                                          // 邮箱选填，可为空串
    })
    await userStore.fetchUser()
    // 后端可能把空用户名回退为登录名，这里同步回表单
    profileForm.value.display_name = userStore.user?.display_name || ''
    ElMessage.success('个人信息已更新 ✅')
  } catch (error: any) {
    const msg = error.response?.data?.error || '更新失败，请重试'
    ElMessage.error(msg)
  } finally {
    updating.value = false
  }
}

// 🔒 打开修改密码浮窗（清空上次输入）
const openPasswordDialog = () => {
  passwordForm.value = { old_password: '', new_password: '', confirm_password: '' }
  passwordDialogVisible.value = true
}

// 🔒 提交修改密码：成功后退出登录，强制用新密码重新登录
const submitPassword = async () => {
  const { old_password, new_password, confirm_password } = passwordForm.value
  if (!old_password) {
    ElMessage.warning('请输入原密码')
    return
  }
  if (!new_password || new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (new_password !== confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  if (new_password === old_password) {
    ElMessage.warning('新密码不能与原密码相同')
    return
  }

  passwordSaving.value = true
  try {
    await changePassword({ old_password, new_password })
    ElMessage.success('密码修改成功，请用新密码重新登录')
    passwordDialogVisible.value = false
    userStore.logout()
    router.push('/login')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '修改密码失败，请重试')
  } finally {
    passwordSaving.value = false
  }
}

const goBack = () => {
  if (isTeacher.value) {
    router.push('/teacher')
  } else {
    router.push('/questions')
  }
}

const statusTagType = (status: string) => {
  switch (status) {
    case 'ACCEPTED': return 'success'
    case 'WRONG_ANSWER': return 'danger'
    case 'TIMEOUT': return 'warning'
    default: return 'info'
  }
}

onMounted(() => {
  loadStats()
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
.profile-container {
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

.profile-content {
  display: flex;
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  /* 卡片高度各自按内容自适应，不被右侧更高的卡片拉伸 */
  align-items: flex-start;
}
.info-card {
  flex: 1;
}
.stats-card {
  flex: 2;
}

.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-bottom: 20px;
}
.user-badge {
  margin-top: 10px;
}

.profile-form {
  margin-top: 10px;
}
.profile-form .el-form-item {
  margin-bottom: 16px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.stat-item {
  text-align: center;
  padding: 12px;
  background-color: #f7fafc;
  border-radius: 8px;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #409eff;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.recent-submissions {
  margin-top: 10px;
}
.recent-submissions h4 {
  margin: 0 0 12px 0;
  color: #2d3748;
}
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 20px 0;
}
.pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* ===== 提交代码浮窗 ===== */
.code-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}
.code-block {
  margin: 0;
  padding: 12px 14px;
  background-color: #1e293b;
  color: #e2e8f0;
  border-radius: 8px;
  font-family: 'JetBrains Mono', Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 50vh;
  overflow: auto;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 900px) {
  .profile-container {
    padding: 12px;
  }
  .header {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px 16px;
  }
  .profile-content {
    flex-direction: column;
    /* 纵向堆叠时恢复正常拉伸，卡片占满整行宽度 */
    align-items: stretch;
  }
  .info-card,
  .stats-card {
    /* 允许收缩，避免表格撑破页面 */
    min-width: 0;
  }
}
</style>