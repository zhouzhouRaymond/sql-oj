<template>
  <!-- 学生端统一的头部按钮：四个功能入口 + 退出登录 +（页面特有按钮）。
       把页面特有按钮统一放在最后，四个入口与「退出」在所有页面里的位置就完全一致了。 -->
  <el-button type="primary" link :disabled="isHere('/questions')" @click="go('/questions')">
    📚 题库
  </el-button>
  <el-button type="primary" link :disabled="isHere('/exams')" @click="go('/exams')">
    📋 考试
  </el-button>
  <el-button type="primary" link :disabled="isHere('/submissions')" @click="goToSubmissions">
    📝 我的提交
  </el-button>
  <el-button type="primary" link :disabled="isHere('/profile')" @click="go('/profile')">
    👤 个人中心
  </el-button>
  <el-button type="danger" size="small" @click="handleLogout">退出</el-button>
  <!-- 页面特有按钮（如「← 返回」「← 返回考试记录」）插在这里 -->
  <slot />
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { confirmLogout } from '../utils/session'

const router = useRouter()
const route = useRoute()

const go = (path: string) => {
  router.push(path)
}

// 当前所在页面（精确匹配）→ 对应按钮置灰，表示「你在这里」；
// 题目详情等子页面不做匹配，仍可点击回到所属列表。
const isHere = (path: string) => route.path === path

// 「我的提交」带上来源路径：该页的「← 返回」可原路回到来源页面（如某道题的详情）
const goToSubmissions = () => {
  router.push({ path: '/submissions', query: { from: route.fullPath } })
}

// 退出登录：确认弹窗 + 清会话 + 回登录页，统一实现见 utils/session
const handleLogout = () => confirmLogout()
</script>
