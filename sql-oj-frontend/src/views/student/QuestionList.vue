<template>
  <div class="question-list-container">
    <PageHeader title="📚 SQL 题库" :welcome="userStore.displayName">
      <template #actions>
        <!-- 学生端统一的四个功能入口 + 退出（见 StudentNav 组件） -->
        <StudentNav />
      </template>
    </PageHeader>

    <el-table :data="questions" v-loading="loading" stripe>
      <el-table-column prop="id" label="题号" width="80" />
      <el-table-column prop="title" label="题目名称" min-width="200">
        <template #default="{ row }">
          <span>{{ row.title || truncateDescription(row.description) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="difficulty" label="难度" width="100">
        <template #default="{ row }">
          <el-tag :type="difficultyTagType(row.difficulty)">
            {{ difficultyText(row.difficulty) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button type="primary" size="small" @click="goToDetail(row.id)">
            开始答题
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部加载状态：滚动到这里会自动加载下一页 -->
    <div v-if="questions.length > 0 || loading" class="load-more">
      <template v-if="loadingMore">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在加载更多题目…</span>
      </template>
      <template v-else-if="loadError">
        <span>加载失败，</span>
        <el-button type="primary" link size="small" @click="retryLoad">点击重试</el-button>
      </template>
      <template v-else-if="finished">
        <!-- 总数以后端返回的 count 为准 -->
        <span>🎉 已加载全部 {{ total }} 道题目</span>
      </template>
      <template v-else>
        <span>下滑加载更多…</span>
      </template>
    </div>
    <div v-else class="empty-hint">暂无题目</div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../../stores/user'
import { getQuestions } from '../../api/questions'
import PageHeader from '../../components/PageHeader.vue'
import StudentNav from '../../components/StudentNav.vue'

const router = useRouter()
const userStore = useUserStore()

const questions = ref<any[]>([])
const loading = ref(false)      // 首屏 / 重置加载
const loadingMore = ref(false)  // 触底加载下一页
const finished = ref(false)     // 是否已加载完全部题目
const loadError = ref(false)    // 上一次加载是否失败
const currentPage = ref(1)
const total = ref(0)            // 题目总数（以后端 count 为准）

// 触底加载：滚动监听节流用
let scrollRafId = 0

const truncateDescription = (desc: string) => {
  if (!desc) return '未命名题目'
  if (desc.length > 30) return desc.substring(0, 30) + '...'
  return desc
}

const difficultyTagType = (difficulty: string) => {
  switch (difficulty) {
    case 'easy': return 'success'
    case 'medium': return 'warning'
    case 'hard': return 'danger'
    default: return 'info'
  }
}

const difficultyText = (difficulty: string) => {
  switch (difficulty) {
    case 'easy': return '简单'
    case 'medium': return '中等'
    case 'hard': return '困难'
    default: return difficulty
  }
}

/**
 * 加载题目：reset=true 时重新从第 1 页拉取，否则追加下一页。
 * 后端按题号升序返回（ordering=id），每页 20 条。
 */
const loadQuestions = async (reset = false) => {
  if (reset) {
    questions.value = []
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
    const res = await getQuestions({ page: currentPage.value, ordering: 'id' })
    const data = res.data || {}
    // 兼容后端未开启分页（直接返回数组）的情况
    const list = Array.isArray(data) ? data : (data.results || [])
    if (isFirstPage) {
      questions.value = list
    } else {
      // 追加时按 id 去重，避免重复请求导致同一题出现两次
      const seen = new Set(questions.value.map((item) => item.id))
      questions.value = [...questions.value, ...list.filter((item: any) => !seen.has(item.id))]
    }
    // 总数以后端返回的 count 为准（列表长度只代表“已加载”的数量）
    total.value = data.count ?? questions.value.length

    // 没有下一页（或本页为空）→ 已加载全部
    if (Array.isArray(data) || !data.next || list.length === 0) {
      finished.value = true
    } else {
      currentPage.value += 1
    }
  } catch (error) {
    // 失败时不要标记为“已全部加载”，否则底部会显示错误的总数
    loadError.value = true
    ElMessage.error('加载题目列表失败')
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
const loadMore = () => loadQuestions(false)

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

const goToDetail = (id: number) => {
  router.push(`/questions/${id}`)
}

onMounted(() => {
  loadQuestions(true)
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  if (scrollRafId) window.cancelAnimationFrame(scrollRafId)
  scrollRafId = 0
})
</script>

<style scoped>
.question-list-container {
  padding: 20px;
  min-height: 100vh;
  background-color: #f5f7fa;
  /* 追加数据时禁用浏览器「滚动锚定」，避免视图被拉到最底端 */
  overflow-anchor: none;
}
/* 触底加载提示 */
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

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .question-list-container {
    padding: 12px;
  }
}
</style>