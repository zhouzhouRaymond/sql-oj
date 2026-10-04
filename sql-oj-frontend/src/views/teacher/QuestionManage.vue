<template>
  <div class="manage-container">
    <div class="header">
      <h1>📝 题目管理</h1>
      <div class="actions">
        <el-button type="primary" @click="goToCreate">+ 创建题目</el-button>
      </div>
    </div>

    <QuestionFilterBar
      show-visibility
      :result-text="filterResultText"
      @change="onFilterChange"
    />

    <el-table :data="questions" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="60" />
      <!-- ✅ 显示题目名称，如果没有则截取描述（与学生端题库一致） -->
      <el-table-column prop="title" label="题目名称" min-width="200">
        <template #default="{ row }">
          <span :class="{ 'title-hidden': row.is_visible === false }">
            {{ row.title || truncateDescription(row.description) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="difficulty" label="难度" width="100">
        <template #default="{ row }">
          <el-tag :type="difficultyTagType(row.difficulty)">
            {{ difficultyText(row.difficulty) }}
          </el-tag>
        </template>
      </el-table-column>
      <!-- 历史通过率：来自真实学生提交，帮助教师判断题目实际难度 -->
      <el-table-column label="历史通过率" min-width="210">
        <template #default="{ row }">
          <div v-if="hasHistory(row)" class="pass-rate-cell">
            <el-tooltip placement="top" :content="passRateTooltip(row.history)">
              <el-progress
                :percentage="passRatePercent(row.history)"
                :stroke-width="7"
                :color="passRateColor(row.history.student_pass_rate)"
                :format="formatPercent"
              />
            </el-tooltip>
            <div class="pass-rate-meta">
              {{ row.history.passed_students }}/{{ row.history.attempted_students }} 人通过 ·
              {{ row.history.total_submissions }} 次提交
            </div>
          </div>
          <span v-else class="muted">暂无学生提交</span>
        </template>
      </el-table-column>
      <!-- 难度建议：样本足够且与当前难度不一致时可一键应用 -->
      <el-table-column label="建议难度" min-width="200">
        <template #default="{ row }">
          <div v-if="row.history?.recommended_difficulty" class="suggest-cell">
            <el-tooltip placement="top" :content="recommendTooltip(row.history)">
              <el-tag
                :type="difficultyTagType(row.history.recommended_difficulty)"
                effect="light"
                round
              >
                建议{{ difficultyText(row.history.recommended_difficulty) }}
              </el-tag>
            </el-tooltip>
            <el-button
              v-if="row.history.recommended_difficulty !== row.difficulty"
              type="primary"
              link
              size="small"
              :loading="savingDifficulty.includes(row.id)"
              @click="applyRecommendation(row)"
            >
              应用
            </el-button>
            <span v-else class="muted">与当前一致</span>
          </div>
          <el-tooltip
            v-else
            placement="top"
            :content="row.history?.reason || '暂无学生提交'"
          >
            <span class="muted">样本不足</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <!-- 教师可控制该题是否对学生公开：关闭后学生题库里看不到、也打不开 -->
      <el-table-column label="学生可见" width="130">
        <template #default="{ row }">
          <el-switch
            v-model="row.is_visible"
            :loading="savingVisible.includes(row.id)"
            :disabled="savingVisible.includes(row.id)"
            :width="56"
            inline-prompt
            active-text="公开"
            inactive-text="隐藏"
            @change="toggleVisible(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button type="info" link @click="viewDetail(row.id)">查看</el-button>
          <el-button type="primary" link @click="goToEdit(row.id)">编辑</el-button>
          <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部加载状态：与学生端题库一致，滚动到这里自动加载下一页 -->
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
    <div v-else class="empty-hint">
      {{ hasActiveFilter ? '没有符合条件的题目' : '暂无题目' }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getQuestions, deleteQuestion, patchQuestion } from '../../api/questions'
import QuestionFilterBar from '../../components/QuestionFilterBar.vue'

const router = useRouter()

const questions = ref<any[]>([])
const loading = ref(false)      // 首屏 / 重置加载
const loadingMore = ref(false)  // 触底加载下一页
const finished = ref(false)     // 是否已加载完全部题目
const loadError = ref(false)    // 上一次加载是否失败
const currentPage = ref(1)
const total = ref(0)            // 题目总数（以后端 count 为准）

// 筛选条件：由 QuestionFilterBar 触发，改动后重新从第 1 页加载
const filters = ref({ search: '', difficulty: '', is_visible: '' })
// 在途请求序号：筛选取代旧请求时用它丢弃过期响应
let requestSeq = 0

const hasActiveFilter = computed(
  () => Boolean(filters.value.search || filters.value.difficulty || filters.value.is_visible),
)

const filterResultText = computed(() => {
  if (!hasActiveFilter.value || loading.value) return ''
  return `共 ${total.value} 道符合条件的题目`
})

const onFilterChange = (next: { search: string; difficulty: string; is_visible: string }) => {
  filters.value = {
    search: next.search,
    difficulty: next.difficulty,
    is_visible: next.is_visible,
  }
  loadQuestions(true)
}

// 空筛选不下发，保持与后端默认行为一致
const buildQueryParams = () => {
  const params: {
    page: number
    ordering: string
    search?: string
    difficulty?: string
    is_visible?: string
  } = { page: currentPage.value, ordering: 'id' }
  if (filters.value.search) params.search = filters.value.search
  if (filters.value.difficulty) params.difficulty = filters.value.difficulty
  if (filters.value.is_visible) params.is_visible = filters.value.is_visible
  return params
}

// 正在切换「学生可见」的题目 id（同一行保存期间禁用开关，避免重复提交）
const savingVisible = ref<number[]>([])

// 触底加载：滚动监听节流用
let scrollRafId = 0

// ✅ 截取描述作为备选显示
const truncateDescription = (desc: string) => {
  if (!desc) return '未命名题目'
  if (desc.length > 30) return desc.substring(0, 30) + '...'
  return desc
}

// 难度标签颜色（与学生端题库一致，未知难度显示 info）
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

// 正在按建议修改难度的题目 id（保存期间禁用按钮，避免重复提交）
const savingDifficulty = ref<number[]>([])

// 是否已有学生提交：没有提交就只显示占位文案
const hasHistory = (row: any) =>
  Boolean(row.history && row.history.attempted_students > 0)

const formatPercent = (percentage: number) => `${percentage}%`

const passRatePercent = (history: any) =>
  Math.round((history?.student_pass_rate || 0) * 100)

// 通过率配色：>=80% 绿、>=40% 琥珀、其余红，与难度建议阈值保持一致
const passRateColor = (rate: number) => {
  if (rate >= 0.8) return '#10b981'
  if (rate >= 0.4) return '#f59e0b'
  return '#ef4444'
}

const passRateTooltip = (history: any) =>
  `学生通过率 ${passRatePercent(history)}%：${history.passed_students} 人通过 / ` +
  `${history.attempted_students} 人尝试；提交通过率 ` +
  `${Math.round((history.pass_rate || 0) * 100)}%（` +
  `${history.accepted_submissions}/${history.total_submissions}）`

const confidenceText = (confidence: string) => {
  switch (confidence) {
    case 'high': return '样本充分'
    case 'medium': return '样本一般'
    default: return '样本偏少'
  }
}

const recommendTooltip = (history: any) =>
  `${history.reason}（${confidenceText(history.confidence)}）`

// 一键采用建议难度
const applyRecommendation = async (row: any) => {
  const next = row.history?.recommended_difficulty
  if (!next || next === row.difficulty) return
  savingDifficulty.value = [...savingDifficulty.value, row.id]
  try {
    await patchQuestion(row.id, { difficulty: next })
    row.difficulty = next
    ElMessage.success(`已将难度更新为「${difficultyText(next)}」✅`)
  } catch (error) {
    ElMessage.error('应用建议失败，请重试')
  } finally {
    savingDifficulty.value = savingDifficulty.value.filter((id) => id !== row.id)
  }
}

// 切换「学生可见」：v-model 已先更新开关状态，这里落库；失败则回滚开关
const toggleVisible = async (row: any) => {
  const next = Boolean(row.is_visible)
  savingVisible.value = [...savingVisible.value, row.id]
  try {
    await patchQuestion(row.id, { is_visible: next })
    ElMessage.success(next ? '已公开给学生 ✅' : '已对学生隐藏 🙈')
  } catch (error) {
    row.is_visible = !next
    ElMessage.error('操作失败，请重试')
  } finally {
    savingVisible.value = savingVisible.value.filter((id) => id !== row.id)
  }
}

/**
 * 加载题目：reset=true 时重新从第 1 页拉取，否则追加下一页。
 * 后端按题号升序返回（ordering=id），每页 20 条。
 */
const loadQuestions = async (reset = false) => {
  if (reset) {
    // 筛选取代正在加载的这次请求：自增序号让旧响应作废
    requestSeq += 1
    questions.value = []
    currentPage.value = 1
    finished.value = false
    loadError.value = false
  } else if (loading.value || loadingMore.value || finished.value || loadError.value) {
    return
  }

  const seq = requestSeq
  const isFirstPage = currentPage.value === 1
  if (isFirstPage) loading.value = true
  else loadingMore.value = true

  // 记录当前滚动位置：数据渲染完成后恢复，避免加载后页面跳到最底端
  const anchorScrollY = window.scrollY

  try {
    const res = await getQuestions(buildQueryParams())
    // 期间筛选条件又变了：丢弃这次过期结果，交给最新请求渲染
    if (seq !== requestSeq) return

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
    if (seq !== requestSeq) return
    // 失败时不要标记为“已全部加载”，否则底部会显示错误的总数
    loadError.value = true
    ElMessage.error('加载题目列表失败')
  } finally {
    // 过期请求不要清掉最新请求的加载状态
    if (seq === requestSeq) {
      loading.value = false
      loadingMore.value = false
    }
  }

  // 等新数据渲染完成后再恢复滚动位置（重置筛选时回到顶部看结果）
  await nextTick()
  if (reset) window.scrollTo(0, 0)
  else window.scrollTo(0, anchorScrollY)

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

const goToCreate = () => {
  router.push('/teacher/questions/create')
}

const goToEdit = (id: number) => {
  router.push(`/teacher/questions/create?id=${id}`)
}

const viewDetail = (id: number) => {
  router.push(`/teacher/questions/${id}`)
}

const handleDelete = (id: number) => {
  ElMessageBox.confirm('确定要删除这道题吗？删除后不可恢复', '提示', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await deleteQuestion(id)
      ElMessage.success('删除成功 ✅')
      // 删除会改变总数与分页，重新从第 1 页加载
      await loadQuestions(true)
    } catch (error) {
      ElMessage.error('删除失败，请重试')
    }
  }).catch(() => {
    // 用户取消，不做任何事
  })
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
.manage-container {
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
  font-size: 20px;
  color: #2d3748;
}

.actions {
  display: flex;
  gap: 12px;
}

/* ✅ 表格样式优化 */
.manage-container :deep(.el-table) {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* 触底加载提示（与学生端题库一致） */
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

/* 已对学生隐藏的题目：标题弱化显示 */
.title-hidden {
  color: #a8abb2;
}

/* ===== 历史通过率 / 难度建议 ===== */
.pass-rate-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 170px;
}
.pass-rate-cell :deep(.el-progress__text) {
  font-size: 12px !important;
  min-width: 38px;
}
.pass-rate-meta {
  font-size: 12px;
  color: #909399;
  white-space: nowrap;
}
.suggest-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.muted {
  color: #a8abb2;
  font-size: 13px;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .manage-container {
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
  .actions {
    flex-wrap: wrap;
  }
}
</style>
