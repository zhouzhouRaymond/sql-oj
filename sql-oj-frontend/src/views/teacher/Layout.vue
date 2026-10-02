<template>
  <div class="teacher-layout">
    <div class="sidebar">
      <div class="logo">
        <h2>SQL OJ</h2>
        <p>教师端</p>
      </div>
      <el-menu :default-active="activeMenu" router>
        <el-menu-item index="/teacher/questions">
          <el-icon><Document /></el-icon>
          <span>题目管理</span>
        </el-menu-item>
        <el-menu-item index="/teacher/exams">
          <el-icon><Notebook /></el-icon>
          <span>考试管理</span>
        </el-menu-item>
        <el-menu-item index="/teacher/stats">
          <el-icon><DataAnalysis /></el-icon>
          <span>统计分析</span>
        </el-menu-item>
        <el-menu-item index="/submissions">
          <el-icon><Tickets /></el-icon>
          <span>提交记录</span>
        </el-menu-item>
        <el-menu-item index="/profile">
          <el-icon><User /></el-icon>
          <span>个人中心</span>
        </el-menu-item>
        <el-menu-item index="/teacher/accounts">
          <el-icon><UserFilled /></el-icon>
          <span>账号管理</span>
        </el-menu-item>
      </el-menu>
      <div class="user-info">
        <span>{{ userStore.displayName }}</span>
        <el-button type="danger" text @click="handleLogout">退出</el-button>
      </div>
    </div>
    <div class="main-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'  // ✅ 导入 ElMessageBox
import { Document, Notebook, DataAnalysis, Tickets, User, UserFilled } from '@element-plus/icons-vue'
import { useUserStore } from '../../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)

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
}
.logo {
  padding: 20px;
  text-align: center;
  border-bottom: 1px solid #4a5a6e;
}
.logo h2 {
  margin: 0;
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
  color: #bfcbd9;
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
  }
  .sidebar :deep(.el-menu) {
    display: flex;
    flex-wrap: wrap;
    border-right: none;
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