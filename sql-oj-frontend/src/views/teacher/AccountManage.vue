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

      <el-table :data="users" v-loading="loading" stripe :row-class-name="rowClassName">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="登录名" min-width="130" />
        <el-table-column label="用户名" min-width="130">
          <template #default="{ row }">
            {{ row.name || row.display_name || row.username }}
          </template>
        </el-table-column>
        <el-table-column label="邮箱" min-width="180">
          <template #default="{ row }">{{ row.email || '-' }}</template>
        </el-table-column>
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

      <!-- 底部加载状态：与题目列表一致，滚动到这里自动加载下一页 -->
      <div v-if="users.length > 0 || loading" class="load-more">
        <template v-if="loadingMore">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在加载更多账号…</span>
        </template>
        <template v-else-if="loadError">
          <span>加载失败，</span>
          <el-button type="primary" link size="small" @click="retryLoad">点击重试</el-button>
        </template>
        <template v-else-if="finished">
          <span>🎉 已加载全部 {{ total }} 个账号</span>
        </template>
        <template v-else>
          <span>下滑加载更多…</span>
        </template>
      </div>
      <div v-else class="empty-hint">暂无账号</div>
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
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="选填，可不填" clearable />
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
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { createUser, getUsers, updateUserById } from '../../api/users'
import { formatDateTime } from '../../utils/time'

const users = ref<any[]>([])
const loading = ref(false)      // 首屏 / 重置加载
const loadingMore = ref(false)  // 触底加载下一页
const finished = ref(false)     // 是否已加载完全部账号
const loadError = ref(false)    // 上一次加载是否失败
const saving = ref(false)
const keyword = ref('')
const roleFilter = ref('')
const currentPage = ref(1)
const total = ref(0)            // 账号总数（以后端 count 为准）

// 触底加载：滚动监听节流用
let scrollRafId = 0

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = ref({
  username: '',
  display_name: '',
  email: '',
  user_type: 'student' as 'student' | 'teacher',
  password: ''
})

/**
 * 加载账号列表：reset=true 时重新从第 1 页拉取，否则追加下一页。
 * 后端按 id 升序返回，每页 20 条（与题目列表一致）。
 */
const loadUsers = async (reset = false) => {
  if (reset) {
    users.value = []
    currentPage.value = 1
    finished.value = false
    loadError.value = false
  }
  if (loading.value || loadingMore.value || finished.value || loadError.value) return

  const isFirstPage = currentPage.value === 1
  if (isFirstPage) loading.value = true
  else loadingMore.value = true

  // 记录当前滚动位置：数据渲染完成后恢复，避免加载后页面跳到最底端
  const anchorScrollY = window.scrollY

  try {
    const res = await getUsers({
      page: currentPage.value,
      search: keyword.value.trim() || undefined,
      user_type: roleFilter.value || undefined
    })
    const data = res.data || {}
    // 兼容后端未开启分页（直接返回数组）的情况
    const list = Array.isArray(data) ? data : (data.results || [])
    if (isFirstPage) {
      users.value = list
    } else {
      // 追加时按 id 去重，避免重复请求导致同一账号出现两次
      const seen = new Set(users.value.map((item) => item.id))
      users.value = [...users.value, ...list.filter((item) => !seen.has(item.id))]
    }
    // 总数以后端返回的 count 为准（列表长度只代表“已加载”的数量）
    total.value = data.count ?? users.value.length

    // 没有下一页（或本页为空）→ 已加载全部
    if (Array.isArray(data) || !data.next || list.length === 0) {
      finished.value = true
    } else {
      currentPage.value += 1
    }
  } catch (error: any) {
    // 失败时不要标记为“已全部加载”，底部会给出「点击重试」
    loadError.value = true
    ElMessage.error(error.response?.data?.detail || '加载账号列表失败')
  } finally {
    loading.value = false
    loadingMore.value = false
  }

  // 等新数据渲染完成后再恢复滚动位置，保证「停在原来的位置」
  await nextTick()
  window.scrollTo(0, anchorScrollY)

  // 内容不足一屏（刚加载完底部仍在视口内）时，继续加载下一页
  if (!finished.value && !loadError.value && !loading.value && !loadingMore.value && nearBottom()) {
    loadMore()
  }
}

// 触底时加载下一页
const loadMore = () => loadUsers(false)

// 加载失败后手动重试当前页
const retryLoad = () => {
  loadError.value = false
  loadMore()
}

// 是否已滚动到接近页面底部
const nearBottom = (threshold = 200) => {
  const el = document.documentElement
  return window.scrollY + el.clientHeight >= el.scrollHeight - threshold
}

// 滚动监听（requestAnimationFrame 节流）：接近底部时加载下一页
const onScroll = () => {
  if (scrollRafId) return
  scrollRafId = window.requestAnimationFrame(() => {
    scrollRafId = 0
    if (finished.value || loadError.value || loading.value || loadingMore.value) return
    if (nearBottom()) loadMore()
  })
}

// 取全账号列表：新建的账号按 id 排在最后，要"定位到新账号"就必须把列表取全
const loadAllUsers = async () => {
  loading.value = true
  loadError.value = false
  currentPage.value = 1
  const all: any[] = []
  try {
    let page = 1
    while (page <= 100) {
      const res = await getUsers({
        page,
        search: keyword.value.trim() || undefined,
        user_type: roleFilter.value || undefined
      })
      const data = res.data || {}
      // 兼容后端未开启分页（直接返回数组）的情况
      if (Array.isArray(data)) {
        all.push(...data)
        total.value = all.length
        break
      }
      const list = data.results || []
      all.push(...list)
      total.value = data.count ?? all.length
      if (!data.next || list.length === 0) break
      page += 1
    }
    users.value = all
    finished.value = true
  } catch (error: any) {
    loadError.value = true
    ElMessage.error(error.response?.data?.detail || '加载账号列表失败')
  } finally {
    loading.value = false
  }
}

// 新建后需要高亮的账号 id
const highlightId = ref<number | null>(null)
let highlightTimer: ReturnType<typeof setTimeout> | null = null

const rowClassName = ({ row }: any) => (row.id === highlightId.value ? 'row-flash' : '')

// 滚动到指定账号并短暂高亮，便于「定位到新账号」
const locateAccount = async (id?: number) => {
  if (!id) return
  highlightId.value = id
  await nextTick()
  const row = document.querySelector<HTMLElement>('.account-manage .el-table__row.row-flash')
  if (row) {
    row.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
  if (highlightTimer) clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => {
    highlightId.value = null
    highlightTimer = null
  }, 2600)
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
  // 邮箱选填：填了才校验格式
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    ElMessage.warning('邮箱格式不正确（也可以留空不填）')
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
      const payload: any = { display_name, email: email.trim(), user_type }
      if (password) payload.password = password
      const res = await updateUserById(editingId.value, payload)
      const index = users.value.findIndex((item) => item.id === editingId.value)
      if (index >= 0) {
        // 就地更新，避免整表重载导致滚动位置跳动
        users.value[index] = { ...users.value[index], ...(res.data || {}) }
        // 改后不再符合当前角色筛选时，从列表移除并提示
        if (roleFilter.value && res.data?.user_type !== roleFilter.value) {
          users.value.splice(index, 1)
          total.value = Math.max(0, total.value - 1)
          ElMessage.info('该账号已不符合当前角色筛选，已从列表移除')
        }
      } else {
        await loadUsers(true)
      }
      ElMessage.success('账号已更新 ✅')
    } else {
      const created = await createUser({
        username,
        display_name,
        email: email.trim(),
        user_type,
        password
      })
      ElMessage.success('账号创建成功 ✅')
      dialogVisible.value = false
      // 新账号按 id 排在列表最末：清空筛选 → 取全列表 → 滚动定位并高亮
      keyword.value = ''
      roleFilter.value = ''
      await loadAllUsers()
      await locateAccount(created.data?.id)
      return
    }
    dialogVisible.value = false
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
      const res = await updateUserById(row.id, { is_active: !row.is_active })
      // 就地更新该行，避免整表重载导致滚动位置跳动
      const index = users.value.findIndex((item) => item.id === row.id)
      if (index >= 0) users.value[index] = { ...users.value[index], ...(res.data || {}) }
      ElMessage.success(`已${action} ✅`)
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || `${action}失败，请重试`)
    }
  }).catch(() => {})
}

onMounted(() => {
  loadUsers(true)
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  if (scrollRafId) window.cancelAnimationFrame(scrollRafId)
  scrollRafId = 0
  if (highlightTimer) clearTimeout(highlightTimer)
})
</script>

<style scoped>
.account-manage {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
  /* 追加数据时禁用浏览器「滚动锚定」，避免视图被拉到最底端 */
  overflow-anchor: none;
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
  font-size: 14px;
}
/* 触底加载提示（与题目列表一致） */
.load-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  /* 固定高度：提示文案切换时高度不变，避免布局抖动 */
  min-height: 46px;
  padding: 18px 0 8px;
  color: #909399;
  font-size: 13px;
}
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 40px 0;
  font-size: 14px;
}
/* 新建账号后短暂高亮该行，便于「定位到新账号」 */
.account-manage :deep(.el-table__row.row-flash td) {
  background-color: #fdf6ec !important;
  transition: background-color 0.3s;
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
