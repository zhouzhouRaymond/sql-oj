<template>
  <div class="login-page">
    <div class="login-box">
      <!-- 左侧装饰区 -->
      <div class="login-banner">
        <div class="banner-content">
          <h1>📘 SQL OJ</h1>
          <p>在线 SQL 判题系统</p>
          <div class="banner-features">
            <span>✅ 练习 SQL</span>
            <span>✅ 在线考试</span>
            <span>✅ 实时判题</span>
          </div>
        </div>
      </div>

      <!-- 右侧表单区 -->
      <div class="login-form">
        <div class="form-header">
          <h2>{{ isLogin ? '欢迎回来' : '创建账号' }}</h2>
          <p>{{ isLogin ? '登录以继续你的学习' : '注册开始你的 SQL 之旅' }}</p>
        </div>

        <el-form :model="form" label-position="top" @submit.prevent="handleSubmit">
          <el-form-item label="登录名" required>
            <el-input
              v-model="form.username"
              placeholder="请输入登录名（至少 3 位）"
              prefix-icon="User"
              clearable
            />
            <div class="input-hint">登录名用于登录，至少 3 个字符，仅限字母、数字</div>
          </el-form-item>

          <!-- ✅ 注册时可自定义用户名（展示名），留空则与登录名相同 -->
          <el-form-item v-if="!isLogin" label="用户名">
            <el-input
              v-model="form.display_name"
              placeholder="请输入用户名（可留空，默认与登录名相同）"
              prefix-icon="Avatar"
              clearable
              maxlength="50"
            />
            <div class="input-hint">展示用用户名，注册后也可在个人中心修改</div>
          </el-form-item>

          <!-- ✅ 新增邮箱输入框 -->
          <el-form-item v-if="!isLogin" label="邮箱" required>
            <el-input
              v-model="form.email"
              placeholder="请输入邮箱地址"
              prefix-icon="Message"
              clearable
            />
            <div class="input-hint">用于接收通知和找回密码</div>
          </el-form-item>

          <el-form-item label="密码" required>
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码（至少 6 位）"
              prefix-icon="Lock"
              show-password
            />
            <div class="input-hint">密码至少 6 个字符</div>
          </el-form-item>

          <el-form-item label="身份" required>
            <el-radio-group v-model="form.user_type">
              <el-radio value="student">👨‍🎓 学生</el-radio>
              <el-radio value="teacher">👩‍🏫 教师</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item>
            <el-button
              type="primary"
              size="large"
              style="width: 100%"
              :loading="loading"
              @click="handleSubmit"
            >
              {{ isLogin ? '登 录' : '注 册' }}
            </el-button>
          </el-form-item>

          <div class="form-footer">
            <span>{{ isLogin ? '还没有账号？' : '已有账号？' }}</span>
            <el-button type="primary" link @click="toggleMode">
              {{ isLogin ? '立即注册' : '去登录' }}
            </el-button>
          </div>
        </el-form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import { register } from '../api/auth'

const router = useRouter()
const userStore = useUserStore()

const isLogin = ref(true)
const loading = ref(false)

const form = reactive({
  username: '',      // 登录名（唯一，用于登录）
  display_name: '',  // 自定义用户名（展示名，注册时可留空）
  email: '',
  password: '',
  user_type: 'student' as 'student' | 'teacher'
})

// 表单校验（前端基础校验）
const validateForm = (): boolean => {
  if (!form.username || form.username.length < 3) {
    ElMessage.warning('登录名至少需要 3 个字符')
    return false
  }
  
  // ✅ 注册时校验邮箱格式
  if (!isLogin.value) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!form.email || !emailRegex.test(form.email)) {
      ElMessage.warning('请输入正确的邮箱格式')
      return false
    }
  }
  
  if (!form.password || form.password.length < 6) {
    ElMessage.warning('密码至少需要 6 个字符')
    return false
  }
  return true
}

// 统一提交处理：登录或注册
const handleSubmit = async () => {
  if (!validateForm()) return

  loading.value = true
  try {
    if (isLogin.value) {
      await handleLogin()
    } else {
      await handleRegister()
    }
  } catch (error) {
    // 错误已在具体方法中处理
  } finally {
    loading.value = false
  }
}

// 登录逻辑
const handleLogin = async () => {
  try {
    await userStore.login(form.username, form.password)
    ElMessage.success('登录成功 🎉')

    if (userStore.user?.user_type === 'teacher') {
      router.push('/teacher')
    } else {
      router.push('/questions')
    }
  } catch (error: any) {
    const msg = error.response?.data?.error || '登录失败，请检查登录名和密码'
    ElMessage.error(msg)
  }
}

// ✅ 注册逻辑：增加邮箱字段，完善错误翻译
const handleRegister = async () => {
  try {
    await register({
      username: form.username,
      display_name: form.display_name.trim(),   // ✅ 自定义用户名（可留空，后端回退为登录名）
      email: form.email,
      password: form.password,
      user_type: form.user_type
    })
    ElMessage.success('注册成功 🎉 请登录')
    isLogin.value = true
    form.password = ''
    form.email = ''
    form.display_name = ''
  } catch (error: any) {
    const data = error.response?.data
    let msg = '注册失败，请重试'

    // ✅ 优化错误翻译逻辑，区分不同字段
    if (data) {
      // 1. 检查用户名错误
      if (data.username) {
        const err = Array.isArray(data.username) ? data.username[0] : data.username
        if (err.includes('already exists') || err.includes('已存在')) {
          msg = '❌ 登录名已存在，请换一个'
        } else if (err.includes('required')) {
          msg = '❌ 登录名为必填项'
        } else if (err.includes('invalid') || err.includes('只允许')) {
          msg = '❌ 登录名格式不正确，仅限字母、数字'
        } else {
          msg = `❌ ${err}`
        }
      }
      // 2. 检查邮箱错误（单独处理）
      else if (data.email) {
        const err = Array.isArray(data.email) ? data.email[0] : data.email
        if (err.includes('invalid') || err.includes('格式')) {
          msg = '❌ 邮箱格式不正确，请检查后重试'
        } else if (err.includes('required')) {
          msg = '❌ 邮箱为必填项'
        } else if (err.includes('unique') || err.includes('已存在')) {
          msg = '❌ 该邮箱已被注册，请换一个'
        } else {
          msg = `❌ ${err}`
        }
      }
      // 3. 检查密码错误
      else if (data.password) {
        const err = Array.isArray(data.password) ? data.password[0] : data.password
        if (err.includes('too short')) {
          msg = '❌ 密码太短，至少 6 位'
        } else if (err.includes('required')) {
          msg = '❌ 密码为必填项'
        } else {
          msg = `❌ ${err}`
        }
      }
      // 4. 通用错误
      else if (data.error) {
        msg = `❌ ${data.error}`
      }
    }

    ElMessage.error(msg)
  }
}

// 切换登录/注册模式
const toggleMode = () => {
  isLogin.value = !isLogin.value
  form.password = ''
  form.email = ''   // ✅ 切换时清空邮箱
}
</script>

<style scoped>
/* ===== 页面整体布局 ===== */
.login-page {
  /* 用 min-height + padding：窗口过矮时页面可滚动，内容不会被裁掉 */
  min-height: 100vh;
  padding: 24px 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  font-family: 'Segoe UI', Roboto, sans-serif;
}

.login-box {
  display: flex;
  width: 900px;
  max-width: 95vw;
  min-height: 550px;
  background: #ffffff;
  border-radius: 24px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

/* ===== 左侧品牌区 ===== */
.login-banner {
  flex: 1;
  background: linear-gradient(135deg, #5b6abf 0%, #6c5b9e 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}

.banner-content {
  text-align: center;
}

.banner-content h1 {
  font-size: 42px;
  margin-bottom: 8px;
  font-weight: 700;
  letter-spacing: 1px;
}

.banner-content p {
  font-size: 18px;
  opacity: 0.85;
  margin-bottom: 30px;
}

.banner-features {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 16px;
}

.banner-features span {
  background: rgba(255, 255, 255, 0.15);
  padding: 8px 20px;
  border-radius: 30px;
  backdrop-filter: blur(4px);
}

/* ===== 右侧表单区 ===== */
.login-form {
  flex: 1;
  padding: 50px 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: #ffffff;
}

.form-header {
  margin-bottom: 30px;
}

.form-header h2 {
  font-size: 28px;
  color: #2d3748;
  margin: 0 0 4px 0;
}

.form-header p {
  color: #718096;
  margin: 0;
  font-size: 14px;
}

/* ===== 表单项样式 ===== */
.login-form :deep(.el-form-item) {
  margin-bottom: 16px;
}

.login-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #2d3748;
  padding-bottom: 4px;
}

.login-form :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 4px 16px;
  height: 44px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.login-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 1px 5px rgba(0, 0, 0, 0.12);
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.25);
}

.login-form :deep(.el-radio-group) {
  display: flex;
  gap: 24px;
}

.login-form :deep(.el-radio) {
  height: 40px;
  display: flex;
  align-items: center;
}

.login-form :deep(.el-button--primary) {
  border-radius: 10px;
  height: 48px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  transition: all 0.2s;
}

.login-form :deep(.el-button--primary:hover) {
  transform: translateY(-1px);
  box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
}

.input-hint {
  font-size: 12px;
  color: #a0aec0;
  margin-top: 4px;
  padding-left: 4px;
}

.form-footer {
  text-align: center;
  margin-top: 16px;
  color: #718096;
  font-size: 14px;
}

/* ✅ 修改这里：将“立即注册”链接颜色改为白色 */
.form-footer .el-button {
  font-weight: 600;
  font-size: 14px;
  color: #ffffff !important;
}

.form-footer .el-button:hover {
  color: #f0f0f0 !important;
}

/* ===== 响应式适配 ===== */
@media (max-width: 768px) {
  .login-box {
    flex-direction: column;
    width: 95vw;
    max-width: 95vw;
    min-height: auto;
  }
  .login-banner {
    padding: 30px 20px;
  }
  .login-banner h1 {
    font-size: 30px;
  }
  .login-form {
    padding: 30px 24px;
  }
}

/* 窗口过矮时顶部对齐，保证表单可完整滚动查看 */
@media (max-height: 680px) {
  .login-page {
    align-items: flex-start;
  }
}
</style>