<template>
  <!-- 学生端统一的页面头部：标题（+ 副标题）在左，操作按钮固定在右 -->
  <div class="page-header">
    <!-- 左侧前置区（如学生从题目详情进来时的「← 返回」）：没有内容时不占位、不留空隙 -->
    <slot name="leading" />
    <div class="page-header-title">
      <h1>{{ title }}</h1>
      <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
    </div>
    <div class="page-header-actions">
      <span v-if="welcome" class="welcome">欢迎，{{ welcome }}</span>
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 页面头部：把「标题 / 副标题 / 欢迎语 / 右侧操作区」的样式与位置收敛到一处。
 *
 * 用法：
 *   <PageHeader title="📚 SQL 题库" subtitle="选一道题开始作答" :welcome="userStore.displayName">
 *     <template #actions>
 *       <StudentNav />                      <!-- 四个功能入口 + 退出，全站同一组 -->
 *     </template>
 *   </PageHeader>
 *
 * 插槽：
 * - `#actions`（右侧）：统一放 `<StudentNav />`；
 * - `#leading`（最左侧）：按需放页面级按钮（如「← 返回」），没有内容时不占位。
 *
 * 按钮约定（保证各页面一致）：
 * - 学生端头部按钮一律用 `<StudentNav />`（四个入口 + 退出的样式与顺序由它唯一负责）；
 * - 页面特有按钮放进 StudentNav 的默认插槽，它渲染在统一按钮之后，
 *   因此四个入口与「退出」在各页面的位置完全一致；
 * - 跳转用 `type="primary" link`，退出固定 `type="danger" size="small"`；
 * - 头部高度固定（见下方 min-height），有/无副标题都等高，按钮不会上下浮动。
 */
defineProps<{
  title: string
  subtitle?: string
  /** 右侧的「欢迎，xxx」：传展示名即可；教师端嵌在布局里（侧边栏已有）时可不传 */
  welcome?: string
}>()
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  background: #fff;
  padding: 16px 24px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  /* 固定高度：有 / 无副标题都一样高，按钮在各页面之间不会上下浮动
     （26 + 6 + 18 + 上下 padding 32 = 82） */
  min-height: 82px;
  box-sizing: border-box;
}
.page-header h1 {
  margin: 0;
  font-size: 20px;
  line-height: 26px;
  color: #2d3748;
}
/* 标题区占满剩余宽度：左侧前置按钮贴左、右侧操作区始终贴右 */
.page-header-title {
  flex: 1;
  min-width: 0;
}
.subtitle {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 18px;
  color: #909399;
}
/* 右侧操作区：欢迎语 + 跳转链接 + 退出，统一间距与垂直居中 */
.page-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
/* 右侧的「欢迎，xxx」：字号与颜色统一 */
.welcome {
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .page-header {
    flex-wrap: wrap;
    padding: 12px 16px;
    /* 换行后高度不再固定，避免内容被裁切 */
    min-height: auto;
  }
  .page-header-actions {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
