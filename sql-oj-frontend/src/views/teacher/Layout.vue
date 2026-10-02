<template>
  <div class="teacher-layout">
    <div class="sidebar" :class="{ collapsed: menuCollapsed }">
      <div class="logo">
        <div v-if="!menuCollapsed" class="logo-text">
          <h2>SQL OJ</h2>
          <p>教师端</p>
        </div>
        <!-- 折叠开关（窄屏已换成顶部横向菜单，无需折叠） -->
        <el-tooltip
          v-if="!isNarrow"
          :content="menuCollapsed ? '展开菜单' : '收起菜单'"
          placement="right"
        >
          <el-button class="collapse-btn" text @click="toggleCollapsed">
            <el-icon :size="18">
              <Expand v-if="menuCollapsed" />
              <Fold v-else />
            </el-icon>
          </el-button>
        </el-tooltip>
      </div>
      <el-menu :default-active="activeMenu" :collapse="menuCollapsed" router>
        <el-menu-item index="/teacher/questions">
          <el-icon><Document /></el-icon>
          <template #title>题目管理</template>
        </el-menu-item>
        <el-menu-item index="/teacher/exams">
          <el-icon><Notebook /></el-icon>
          <template #title>考试管理</template>
        </el-menu-item>
        <el-menu-item index="/teacher/stats">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>统计分析</template>
        </el-menu-item>
        <el-menu-item index="/teacher/submissions">
          <el-icon><Tickets /></el-icon>
          <template #title>提交记录</template>
        </el-menu-item>
        <el-menu-item index="/teacher/profile">
          <el-icon><User /></el-icon>
          <template #title>个人中心</template>
        </el-menu-item>
        <el-menu-item index="/teacher/accounts">
          <el-icon><UserFilled /></el-icon>
          <template #title>账号管理</template>
        </el-menu-item>
      </el-menu>
      <div class="user-info">
        <span v-if="!menuCollapsed" class="user-name" :title="userStore.displayName">
          {{ userStore.displayName }}
        </span>
        <!-- 折叠时只留图标，悬停显示「退出登录」 -->
        <el-tooltip content="退出登录" placement="right" :disabled="!menuCollapsed">
          <el-button type="danger" text @click="handleLogout">
            <el-icon v-if="menuCollapsed"><SwitchButton /></el-icon>
            <span v-else>退出</span>
          </el-button>
        </el-tooltip>
      </div>
    </div>
    <div class="main-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'  // ✅ 导入 ElMessageBox
import {
  Document, Notebook, DataAnalysis, Tickets, User, UserFilled,
  Fold, Expand, SwitchButton,
} from '@element-plus/icons-vue'
import { useUserStore } from '../../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)

// ===== 侧边栏折叠 =====
// 折叠偏好记在本机（刷新 / 换页面后保持）；窄屏时侧边栏已变成顶部横向菜单，
// 不参与折叠，避免出现“图标模式 + 横向排布”的叠加状态。
const COLLAPSE_KEY = 'teacher_sidebar_collapsed'
const NARROW_QUERY = '(max-width: 900px)'   // 与下方媒体查询断点保持一致

const isCollapsed = ref(false)
const isNarrow = ref(false)

try {
  isCollapsed.value = localStorage.getItem(COLLAPSE_KEY) === '1'
} catch {
  // localStorage 不可用（隐私模式）时按展开处理
}

const menuCollapsed = computed(() => isCollapsed.value && !isNarrow.value)

const toggleCollapsed = () => {
  isCollapsed.value = !isCollapsed.value
  try {
    localStorage.setItem(COLLAPSE_KEY, isCollapsed.value ? '1' : '0')
  } catch {
    // 写入失败仅影响下次进入时的默认状态
  }
}

// 跟随窗口宽度：窄屏自动展开（媒体查询把菜单改成横向）
let narrowMedia: MediaQueryList | undefined
const syncNarrow = (query: MediaQueryList | MediaQueryListEvent) => {
  isNarrow.value = query.matches
}

onMounted(() => {
  narrowMedia = window.matchMedia(NARROW_QUERY)
  syncNarrow(narrowMedia)
  narrowMedia.addEventListener('change', syncNarrow)
})

onUnmounted(() => {
  narrowMedia?.removeEventListener('change', syncNarrow)
})

// ✅ 退出登录增加确认弹窗
const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    userStore.logout()
    router.push('/login')
    ElMessage.success('已退出登录')
  }).catch(() => {
    // 用户取消，不做任何事
  })
}
</script>

<style scoped>
.teacher-layout {
  display: flex;
  min-height: 100vh;
}
.sidebar {
  width: 260px;
  background-color: #304156;
  color: #fff;
  display: flex;
  flex-direction: column;
  /* 折叠 / 展开时宽度平滑过渡，避免侧边栏“跳一下” */
  transition: width 0.2s ease;
  /* 固定为视口高度并吸附在顶部：内容比一屏长时（如提交记录页），
     底部「用户名 + 退出」不会被页面撑到文档末尾而“消失”。
     用 sticky 而非 fixed，保持窗口仍是滚动容器（题目管理页依赖 window.scroll 触底加载）。 */
  height: 100vh;
  position: sticky;
  top: 0;
}
/* 折叠态：只留图标（64px 与 el-menu 默认的折叠宽度一致） */
.sidebar.collapsed {
  width: 64px;
}
.logo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 20px;
  border-bottom: 1px solid #4a5a6e;
}
.logo-text {
  flex: 1;
  min-width: 0;
  text-align: center;
}
/* 折叠后只剩开关按钮，居中显示 */
.sidebar.collapsed .logo {
  justify-content: center;
  padding: 20px 0;
}
/* 折叠开关：深色侧边栏里的浅色图标按钮 */
.logo .collapse-btn {
  color: #bfcbd9;
  padding: 6px;
}
.logo .collapse-btn:hover {
  color: #fff;
  background-color: #263445;
}
.logo h2 {
  margin: 0;
  font-size: 18px;
  color: #fff;
}
.logo p {
  margin: 5px 0 0;
  font-size: 12px;
  color: #a0b3c9;
}
.sidebar :deep(.el-menu) {
  flex: 1;
  border-right: none;
  background-color: #304156;
  /* 菜单过长时在侧边栏内部滚动，保证底部用户区始终可见 */
  overflow-y: auto;
}
.sidebar :deep(.el-menu-item) {
  color: #bfcbd9;
}
.sidebar :deep(.el-menu-item.is-active) {
  color: #409eff;
  background-color: #263445;
}
.sidebar :deep(.el-menu-item:hover) {
  background-color: #263445;
}
.user-info {
  padding: 20px;
  border-top: 1px solid #4a5a6e;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  color: #bfcbd9;
}
.user-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* 折叠态：隐藏用户名，退出按钮居中 */
.sidebar.collapsed .user-info {
  flex-direction: column;
  justify-content: center;
  padding: 16px 0;
}
.main-content {
  flex: 1;
  /* 关键：允许收缩，避免内部宽表格把整页撑出横向滚动条 */
  min-width: 0;
  background-color: #f0f2f5;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 900px) {
  .teacher-layout {
    flex-direction: column;
  }
  .sidebar {
    width: 100%;
    /* 窄屏是顶部横向菜单，恢复常规文档流（不吸附、不限制高度） */
    height: auto;
    position: static;
  }
  .sidebar :deep(.el-menu) {
    display: flex;
    flex-wrap: wrap;
    border-right: none;
    overflow-y: visible;
  }
  .sidebar :deep(.el-menu-item) {
    flex: 1 1 auto;
    height: 44px;
    line-height: 44px;
  }
  .user-info {
    padding: 10px 20px;
  }
}
</style>