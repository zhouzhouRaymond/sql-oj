<template>
  <div class="question-filter-bar">
    <el-input
      v-model="keyword"
      class="filter-item filter-search"
      placeholder="搜题号或题目名称"
      clearable
      :prefix-icon="Search"
      @input="onKeywordInput"
      @clear="emitChange"
      @keyup.enter="emitChange"
    />

    <el-select v-model="difficulty" class="filter-item filter-select" @change="emitChange">
      <el-option label="全部难度" value="" />
      <el-option label="简单" value="easy" />
      <el-option label="中等" value="medium" />
      <el-option label="困难" value="hard" />
    </el-select>

    <!-- 仅教师端显示：按「学生可见」状态筛选 -->
    <el-select
      v-if="showVisibility"
      v-model="visibility"
      class="filter-item filter-select"
      @change="emitChange"
    >
      <el-option label="全部状态" value="" />
      <el-option label="学生可见" value="true" />
      <el-option label="已隐藏" value="false" />
    </el-select>

    <div class="filter-tail">
      <span v-if="resultText" class="filter-result">{{ resultText }}</span>
      <el-button class="filter-reset" :disabled="!active" @click="reset">
        重置筛选
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 题目列表筛选栏（学生题库 / 教师题目管理共用，保证样式完全一致）。
 *
 * 筛选条件通过 `change` 事件抛出并交给父组件请求后端：
 *   { search, difficulty, is_visible }
 * 关键词输入做 300ms 防抖，下拉框与「重置筛选」立即触发。
 */
import { computed, onUnmounted, ref } from 'vue'
import { Search } from '@element-plus/icons-vue'

interface QuestionFilters {
  search: string
  difficulty: string
  is_visible: string
}

const props = withDefaults(
  defineProps<{
    /** 是否显示「学生可见」筛选（教师端为 true） */
    showVisibility?: boolean
    /** 右侧结果提示，如「共 12 道符合条件的题目」 */
    resultText?: string
  }>(),
  { showVisibility: false, resultText: '' },
)

const emit = defineEmits<{ (event: 'change', value: QuestionFilters): void }>()

const keyword = ref('')
const difficulty = ref('')
const visibility = ref('')
let debounceTimer: number | undefined

const active = computed(
  () => Boolean(keyword.value.trim() || difficulty.value || (props.showVisibility && visibility.value)),
)

const currentFilters = (): QuestionFilters => ({
  search: keyword.value.trim(),
  difficulty: difficulty.value,
  // 学生端不显示该筛选项，固定下发空值
  is_visible: props.showVisibility ? visibility.value : '',
})

const emitChange = () => {
  if (debounceTimer !== undefined) {
    window.clearTimeout(debounceTimer)
    debounceTimer = undefined
  }
  emit('change', currentFilters())
}

// 输入框防抖：避免每敲一个字都请求一次列表
const onKeywordInput = () => {
  if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
  debounceTimer = window.setTimeout(() => {
    debounceTimer = undefined
    emit('change', currentFilters())
  }, 300)
}

const reset = () => {
  keyword.value = ''
  difficulty.value = ''
  visibility.value = ''
  emitChange()
}

onUnmounted(() => {
  if (debounceTimer !== undefined) window.clearTimeout(debounceTimer)
})
</script>

<style scoped>
/* 与 PageHeader / 表格卡片保持一致的白底、圆角与阴影 */
.question-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px 24px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.filter-search {
  width: 260px;
}

.filter-select {
  width: 150px;
}

/* 右对齐的「结果提示 + 重置」区域 */
.filter-tail {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}

.filter-result {
  font-size: 13px;
  color: #909399;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .question-filter-bar {
    gap: 8px;
    padding: 12px 16px;
  }
  .filter-search,
  .filter-select {
    width: 100%;
  }
  .filter-tail {
    width: 100%;
    justify-content: space-between;
    margin-left: 0;
  }
}
</style>
