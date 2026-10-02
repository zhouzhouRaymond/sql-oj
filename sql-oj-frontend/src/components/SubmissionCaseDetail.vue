<template>
  <!-- 判题明细：失败用例（实际输出/预期输出表格化）+ 通过时的运行结果 -->
  <div class="case-detail">
    <template v-if="hasCases">
      <strong>{{ isAccepted ? '✅ 用例通过情况：' : '❌ 失败的测试用例：' }}</strong>
      <div v-if="errorMessage" class="detail-error">{{ errorMessage }}</div>
      <div class="detail-summary">
        共 {{ total }} 个测试用例，通过 {{ passedCount }} 个。
      </div>

      <!-- 未通过的用例：用例输入/预期输出仅在后端下发时展示（教师视角或题目开关开启） -->
      <div v-for="caseItem in failedCaseViews" :key="caseItem.index" class="failed-case">
        <div class="failed-case-title">
          <el-tag type="danger" size="small">用例 {{ caseItem.index }}</el-tag>
          <span class="case-hint">{{ caseItem.error_message || '执行结果与预期不一致' }}</span>
        </div>

        <template v-if="caseItem.test_input != null">
          <span class="case-label">测试输入（用例数据）：</span>
          <pre class="code-block">{{ caseItem.test_input || '（空）' }}</pre>
        </template>

        <span class="case-label">你的输出：</span>
        <div v-if="caseItem.actualTable.columns.length > 0" class="result-table-wrap">
          <el-table
            :data="caseItem.actualTable.rows"
            border
            size="small"
            :style="{ minWidth: tableMinWidth(caseItem.actualTable) }"
          >
            <el-table-column
              v-for="col in caseItem.actualTable.columns"
              :key="col.prop"
              :prop="col.prop"
              :label="col.label"
              min-width="120"
            />
          </el-table>
        </div>
        <pre v-else class="code-block">{{ caseItem.actual_output || '（空）' }}</pre>

        <template v-if="caseItem.expected_output != null">
          <span class="case-label">预期输出：</span>
          <div v-if="caseItem.expectedTable.columns.length > 0" class="result-table-wrap">
            <el-table
              :data="caseItem.expectedTable.rows"
              border
              size="small"
              :style="{ minWidth: tableMinWidth(caseItem.expectedTable) }"
            >
              <el-table-column
                v-for="col in caseItem.expectedTable.columns"
                :key="col.prop"
                :prop="col.prop"
                :label="col.label"
                min-width="120"
              />
            </el-table>
          </div>
          <pre v-else class="code-block">{{ caseItem.expected_output || '（空）' }}</pre>
        </template>
      </div>

      <div v-if="!caseDataShown" class="detail-summary">
        为保护隐藏用例，此处不展示用例的输入与预期输出。
      </div>
    </template>
    <div v-else class="detail-summary">暂无判题明细（判题中或未执行）。</div>

    <!-- ✅ 答对时直接展示运行结果（表格可能很宽，已支持横向滚动） -->
    <div v-if="isAccepted && caseOutputs.length > 0" class="accepted-block">
      <strong>📤 运行结果：</strong>
      <el-radio-group
        v-if="caseOutputs.length > 1"
        v-model="activeCaseIndex"
        size="small"
        class="case-output-tabs"
      >
        <el-radio-button
          v-for="item in caseOutputs"
          :key="item.index"
          :value="item.index"
        >
          用例 {{ item.index }}
        </el-radio-button>
      </el-radio-group>
      <div class="result-table-wrap">
        <el-table
          :data="resultTable.rows"
          border
          stripe
          size="small"
          :style="{ minWidth: tableMinWidth(resultTable) }"
        >
          <el-table-column
            v-for="col in resultTable.columns"
            :key="col.prop"
            :prop="col.prop"
            :label="col.label"
            min-width="120"
          />
        </el-table>
      </div>
      <div v-if="resultTable.rows.length === 0" class="detail-summary">
        查询结果为 0 行。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { parseResultSet } from '../utils/resultSet'

// 传入「提交详情」对象（含 judge_details）；只传列表行对象时渲染不出明细
// （列表接口不返回 judge_details，需先按 id 拉取详情）。
const props = defineProps<{ detail?: any }>()

const details = computed(() => props.detail?.judge_details || {})
const isAccepted = computed(() => props.detail?.execution_status === 'ACCEPTED')
const errorMessage = computed(() => details.value.error_message || '')
const total = computed(() => Number(details.value.total) || 0)
const passedCount = computed(() => Number(details.value.passed_count) || 0)
// 没有用例数据时不展示「共 0 个用例」这类空明细（判题中/未执行）
const hasCases = computed(() => total.value > 0)

// 答对时展示运行结果：把判题返回的结果集文本解析成表格
const caseOutputs = computed(() => {
  const list = details.value.case_outputs
  return Array.isArray(list) ? list : []
})

// 表格最小宽度：列多时保持宽度，由外层容器横向滚动
const tableMinWidth = (table: { columns: unknown[] }) =>
  `${Math.max((table?.columns?.length || 0) * 140, 320)}px`

// 失败用例：把「你的输出 / 预期输出」解析成表格（非结果集时回退为文本）
const failedCaseViews = computed(() => {
  const list = details.value.failed_cases
  return (Array.isArray(list) ? list : []).map((item: any) => ({
    ...item,
    actualTable: parseResultSet(item.actual_output || ''),
    expectedTable: parseResultSet(item.expected_output || '')
  }))
})

// 后端是否下发了用例输入/预期输出（题目开关开启，或当前视角是教师）
const caseDataShown = computed(() => {
  const list = details.value.failed_cases
  return (Array.isArray(list) ? list : []).some((item: any) => item.test_input != null)
})

// 结果集切换：默认选中第一个用例（切换提交详情时同步重置）
const activeCaseIndex = ref<number>(1)
const currentCaseOutput = computed(() => {
  const item = caseOutputs.value.find((c: any) => c.index === activeCaseIndex.value)
  return item?.actual_output || ''
})
const resultTable = computed(() => parseResultSet(currentCaseOutput.value))

watch(
  caseOutputs,
  (list) => {
    activeCaseIndex.value = list[0]?.index ?? 1
  },
  { immediate: true }
)
</script>

<style scoped>
.detail-summary {
  color: #606266;
  font-size: 13px;
  margin-bottom: 6px;
}
.detail-error {
  color: #e6a23c;
  font-size: 13px;
  margin-bottom: 6px;
}
.failed-case {
  background-color: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.failed-case-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.case-hint {
  color: #f56c6c;
  font-size: 13px;
}
.case-label {
  display: block;
  margin-top: 6px;
  font-size: 13px;
  color: #606266;
}
/* 非结果集时的原始文本回退展示 */
.code-block {
  background-color: #f5f7fa;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  margin: 4px 0 0;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow: auto;
}
/* 运行结果 / 预期输出用表格展示：宽表格交给外层容器横向滚动 */
.accepted-block {
  margin-top: 4px;
}
.case-output-tabs {
  margin: 6px 0;
}
.result-table-wrap {
  margin-top: 6px;
  border-radius: 6px;
  overflow-x: auto;
}
</style>
