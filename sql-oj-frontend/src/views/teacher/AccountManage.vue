<template>
  <div class="account-manage">
    <div class="header">
      <h1>👥 账号管理</h1>
      <el-button type="primary" @click="openCreate">+ 新建账号</el-button>
    </div>

    <el-card>
      <!-- 筛选：关键词 + 角色 -->
      <div class="filters">
        <el-input
          v-model="keyword"
          placeholder="搜索登录名 / 用户名 / 邮箱"
          clearable
          style="width: 280px"
          @keyup.enter="loadUsers(true)"
          @clear="loadUsers(true)"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select
          v-model="roleFilter"
          placeholder="全部角色"
          clearable
          style="width: 140px"
          @change="loadUsers(true)"
        >
          <el-option label="学生" value="student" />
          <el-option label="教师" value="teacher" />
        </el-select>
        <el-button type="primary" @click="loadUsers(true)">查询</el-button>
        <span class="total-hint">共 {{ total }} 个账号</span>
      </div>

      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="登录名" min-width="130" />
        <el-table-column label="用户名" min-width="130">
          <template #default="{ row }">
            {{ row.name || row.display_name || row.username }}
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="180" />
        <el-table-column label="角色" width="90">
          <template #default="{ row }">
            <el-tag :type="row.user_type === 'teacher' ? 'warning' : 'success'" size="small">
              {{ row.user_type === 'teacher' ? '教师' : '学生' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '正常' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.date_joined) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button
              :type="row.is_active ? 'warning' : 'success'"
              link
              @click="toggleActive(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, total"
          small
          @current-change="loadUsers()"
        />
      </div>
    </el-card>

    <!-- 新建 / 编辑账号 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑账号' : '新建账号'"
      width="480px"
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="登录名" required>
          <el-input
            v-model="form.username"
            :disabled="!!editingId"
            placeholder="用于登录，全站唯一"
          />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input
            v-model="form.display_name"
            maxlength="50"
            placeholder="展示名，留空则与登录名相同"
          />
        </el-form-item>
        <el-form-item label="邮箱" required>
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-radio-group v-model="form.user_type">
            <el-radio value="student">👨‍🎓 学生</el-radio>
            <el-radio value="teacher">👩‍🏫 教师</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="editingId ? '重置密码' : '初始密码'" :required="!editingId">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="editingId ? '留空则不修改密码' : '至少 6 位'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { createUser, getUsers, updateUserById } from '../../api/users'
import { formatDateTime } from '../../utils/time'

const users = ref<any[]>([])
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const roleFilter = ref('')
const currentPage = ref(1)
const pageSize = 20
const total = ref(0)

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = ref({
  username: '',
  display_name: '',
  email: '',
  user_type: 'student' as 'student' | 'teacher',
  password: ''
})

// 加载账号列表（reset=true 时回到第 1 页）
const loadUsers = async (reset = false) => {
  if (reset) currentPage.value = 1
  loading.value = true
  try {
    const res = await getUsers({
      page: currentPage.value,
      search: keyword.value.trim() || undefined,
      user_type: roleFilter.value || undefined
    })
    const data = res.data || {}
    if (Array.isArray(data)) {
      users.value = data
      total.value = data.length
    } else {
      users.value = data.results || []
      total.value = data.count || 0
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载账号列表失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editingId.value = null
  form.value = {
    username: '',
    display_name: '',
    email: '',
    user_type: 'student',
    password: ''
  }
  dialogVisible.value = true
}

const openEdit = (row: any) => {
  editingId.value = row.id
  form.value = {
    username: row.username || '',
    display_name: row.display_name || '',
    email: row.email || '',
    user_type: row.user_type || 'student',
    password: ''
  }
  dialogVisible.value = true
}

// 提取后端返回的第一条错误信息（DRF 字段错误）
const firstErrorMessage = (data: any, fallback: string) => {
  if (data && typeof data === 'object') {
    const first = Object.values(data)[0]
    return Array.isArray(first) ? String(first[0]) : String(first)
  }
  return fallback
}

const submitForm = async () => {
  const { username, display_name, email, user_type, password } = form.value
  if (!editingId.value && (!username || username.length < 3)) {
    ElMessage.warning('登录名至少 3 个字符')
    return
  }
  if (!email) {
    ElMessage.warning('请输入邮箱')
    return
  }
  if (!editingId.value && (!password || password.length < 6)) {
    ElMessage.warning('初始密码至少 6 位')
    return
  }
  if (editingId.value && password && password.length < 6) {
    ElMessage.warning('重置的密码至少 6 位')
    return
  }

  saving.value = true
  try {
    if (editingId.value) {
      const payload: any = { display_name, email, user_type }
      if (password) payload.password = password
      await updateUserById(editingId.value, payload)
      ElMessage.success('账号已更新 ✅')
    } else {
      await createUser({ username, display_name, email, user_type, password })
      ElMessage.success('账号创建成功 ✅')
    }
    dialogVisible.value = false
    await loadUsers(true)
  } catch (error: any) {
    ElMessage.error(firstErrorMessage(error.response?.data, '保存失败，请重试'))
  } finally {
    saving.value = false
  }
}

// 停用 / 启用账号：停用后该账号无法登录，已签发的 token 也会立即失效
const toggleActive = (row: any) => {
  const action = row.is_active ? '停用' : '启用'
  ElMessageBox.confirm(
    `确定要${action}账号「${row.name || row.username}」吗？` +
      (row.is_active ? ' 停用后该账号将无法登录。' : ''),
    '提示',
    { confirmButtonText: `确定${action}`, cancelButtonText: '取消', type: 'warning' }
  ).then(async () => {
    try {
      await updateUserById(row.id, { is_active: !row.is_active })
      ElMessage.success(`已${action} ✅`)
      await loadUsers()
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || `${action}失败，请重试`)
    }
  }).catch(() => {})
}

onMounted(() => {
  loadUsers()
})
</script>

<style scoped>
.account-manage {
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
.filters {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.total-hint {
  color: #909399;
  font-size: 13px;
}
.account-manage :deep(.el-table .cell) {
  font-size: 13px;
}
.pagination {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .account-manage {
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
}
</style>
