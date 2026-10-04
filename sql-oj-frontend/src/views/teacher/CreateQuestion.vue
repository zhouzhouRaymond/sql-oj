<template>
  <div class="create-container">
    <div class="header">
      <el-button @click="goBack">← 返回</el-button>
      <h1>{{ isEdit ? '编辑题目' : '创建题目' }}</h1>
    </div>

    <el-form :model="form" label-width="120px" v-loading="loading">
      <!-- 题目名称 -->
      <el-form-item label="题目名称" required>
        <el-input
          v-model="form.title"
          placeholder="请输入简短题目名称，如：查询员工信息"
          maxlength="50"
          show-word-limit
        />
        <div class="input-hint">用于列表展示，建议不超过 20 个字</div>
      </el-form-item>

      <!-- 题目描述 -->
      <el-form-item label="题目描述" required>
        <el-input v-model="form.description" type="textarea" :rows="4" placeholder="请输入完整题目描述（支持 Markdown 格式）" />
      </el-form-item>

      <!-- 难度 -->
      <el-form-item label="难度" required>
        <el-radio-group v-model="form.difficulty">
          <el-radio value="easy">简单</el-radio>
          <el-radio value="medium">中等</el-radio>
          <el-radio value="hard">困难</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 判题模式：query=查询结果，schema=DDL 结构判题 -->
      <el-form-item label="判题模式" required>
        <el-radio-group v-model="form.judge_mode">
          <el-radio value="query">查询结果</el-radio>
          <el-radio value="schema">表结构（DDL）</el-radio>
        </el-radio-group>
        <div class="input-hint">
          表结构模式用于 CREATE TABLE / 约束 / 索引 / ALTER 类题目：执行学生 DDL 后比对结构并跑行为探针
        </div>
      </el-form-item>

      <!-- 答题失败时是否展示用例明细（默认关闭） -->
      <el-form-item label="失败详情">
        <el-switch v-model="form.show_case_details" />
        <span class="input-hint" style="display: inline-block; margin-left: 10px;">
          开启后学生答错时可查看该用例的「测试输入」与「预期输出」（便于教学排查，但会降低判题防作弊强度，建议仅在演示题开启）
        </span>
      </el-form-item>

      <!-- 表结构模式：出题模板 + 前置语句 + 自动期望/探针 -->
      <template v-if="form.judge_mode === 'schema'">
        <el-form-item label="出题模板">
          <el-select
            v-model="templateId"
            placeholder="选择一个模板快速填充"
            style="width: 280px"
            @change="applyTemplate"
          >
            <el-option
              v-for="tpl in DDL_TEMPLATES"
              :key="tpl.id"
              :label="tpl.label"
              :value="tpl.id"
            />
          </el-select>
          <span class="input-hint" style="display: inline-block; margin-left: 10px;">
            模板会填充题目描述与参考 DDL，可再修改
          </span>
        </el-form-item>

        <el-form-item label="前置语句">
          <SqlEditor
            v-model="form.schema_setup_sql"
            :min-height="110"
            placeholder="选填：ALTER 类题目的初始表结构（学生只写 ALTER 语句）"
          />
        </el-form-item>

        <el-form-item label="结构严格度">
          <el-select v-model="form.judge_strictness" style="width: 260px">
            <el-option label="宽松：多出的列/约束/索引不判错" value="subset" />
            <el-option label="严格：对象集合必须与期望一致" value="exact" />
          </el-select>
          <el-switch
            v-model="form.judge_compare_names"
            style="margin-left: 16px"
            active-text="比对约束/索引名称"
          />
        </el-form-item>

        <el-form-item label="期望结构">
          <el-button type="primary" :loading="generating" @click="generateSchema">
            由参考 DDL 生成期望结构与探针
          </el-button>
          <div class="input-hint">
            生成后下方会写入期望结构（只读）与自动验证过的行为探针（可编辑 JSON）
          </div>
        </el-form-item>

        <el-form-item label="期望结构 JSON">
          <el-input
            :model-value="form.schema_expected_schema
              ? JSON.stringify(form.schema_expected_schema, null, 2) : ''"
            type="textarea"
            :rows="6"
            readonly
            placeholder="点击上方按钮生成"
          />
        </el-form-item>

        <el-form-item label="行为探针 JSON">
          <el-input
            v-model="form.schema_probes_text"
            type="textarea"
            :rows="6"
            placeholder='[{"sql": "...", "expect": "error", "error_code": "23505", "description": "..."}]'
          />
          <div class="input-hint">
            探针用于验证约束真的生效；自动生成的探针已在参考结构上验证过，可继续增删
          </div>
        </el-form-item>
      </template>

      <!-- 建表语句（查询模式） -->
      <el-form-item v-if="form.judge_mode === 'query'" label="建表语句">
        <SqlEditor v-model="form.create_table_sql" :min-height="150" placeholder="CREATE TABLE ..." />
        <div class="input-hint">建表语句中可以包含 INSERT 数据，用于初始化测试环境</div>
      </el-form-item>

      <!-- 样例输入（展示给学生看） -->
      <el-form-item label="输入样例">
        <el-input v-model="form.sample_input" type="textarea" :rows="2" placeholder="样例输入（展示给学生看）" />
        <div class="input-hint">仅用于展示，学生看到的是此内容，支持 Markdown</div>
      </el-form-item>

      <!-- 样例输出（展示给学生看） -->
      <el-form-item label="输出样例">
        <el-input v-model="form.sample_output" type="textarea" :rows="2" placeholder="样例输出（展示给学生看）" />
        <div class="input-hint">仅用于展示，学生看到的是此内容，支持 Markdown</div>
      </el-form-item>

      <!-- ✅ 新增：测试用例管理（用于判题） -->
      <el-form-item v-if="form.judge_mode === 'query'" label="测试用例">
        <div class="test-cases-area">
          <div
            v-for="(testCase, index) in form.test_cases"
            :key="index"
            class="test-case-item"
          >
            <div class="test-case-header">
              <span class="test-case-label">用例 {{ index + 1 }}</span>
              <el-button
                type="danger"
                size="small"
                text
                @click="removeTestCase(index)"
              >
                删除
              </el-button>
            </div>
            <div class="test-case-row">
              <SqlEditor
                v-model="testCase.test_input"
                :min-height="90"
                placeholder="测试输入（如 INSERT 语句或空）"
                style="flex: 1"
              />
              <el-input
                v-model="testCase.expected_output"
                type="textarea"
                :rows="2"
                placeholder="预期输出（执行 SQL 后的预期结果）"
                style="flex: 1"
              />
            </div>
          </div>
          <el-button type="primary" text @click="addTestCase">
            + 添加测试用例
          </el-button>
          <div class="input-hint">测试用例用于判题时比对实际输出与预期输出</div>
        </div>
      </el-form-item>

      <!-- 正确答案 SQL -->
      <el-form-item :label="form.judge_mode === 'schema' ? '参考 DDL（标准答案）' : '正确答案 SQL'">
        <SqlEditor v-model="form.correct_sql" :min-height="110" placeholder="SELECT ..." />
        <div class="input-hint">学生的 SQL 会与正确答案的结果进行比对</div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">提交</el-button>
        <el-button @click="goBack">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createQuestion,
  updateQuestion,
  getQuestionDetail,
  introspectReference,
} from '../../api/questions'
import { DDL_TEMPLATES } from '../../constants/ddlTemplates'
import SqlEditor from '../../components/SqlEditor.vue'

const route = useRoute()
const router = useRouter()

const isEdit = ref(false)
const loading = ref(false)
const submitting = ref(false)
const generating = ref(false)
const templateId = ref('')

// ✅ 表单包含 test_cases
const form = ref({
  title: '',
  description: '',
  difficulty: 'easy',
  judge_mode: 'query',
  judge_strictness: 'subset',
  judge_compare_names: false,
  create_table_sql: '',
  // schema 模式：前置语句 / 期望结构 / 探针 JSON 文本
  schema_setup_sql: '',
  schema_expected_schema: null as any,
  schema_probes_text: '[]',
  sample_input: '',
  sample_output: '',
  correct_sql: '',
  test_cases: [] as { test_input: string; expected_output: string }[],
  // 答题失败时是否向学生展示用例的「测试输入 / 预期输出」（默认关闭）
  show_case_details: false
})

// ✅ 添加测试用例
const addTestCase = () => {
  form.value.test_cases.push({
    test_input: '',
    expected_output: ''
  })
}

// ✅ 删除测试用例
const removeTestCase = (index: number) => {
  form.value.test_cases.splice(index, 1)
}

// ✅ 出题模板：一键填充题目描述与参考 DDL
const applyTemplate = (id: string) => {
  const template = DDL_TEMPLATES.find((item) => item.id === id)
  if (!template) return
  form.value.description = template.description
  form.value.correct_sql = template.reference_sql
  form.value.schema_setup_sql = template.setup_sql || ''
  form.value.schema_expected_schema = null
  form.value.schema_probes_text = '[]'
}

// ✅ 参考 DDL → 期望结构 + 自动生成并验证过的行为探针
const generateSchema = async () => {
  if (!form.value.correct_sql?.trim()) {
    ElMessage.warning('请先填写参考 DDL（标准答案）')
    return
  }
  generating.value = true
  try {
    const res = await introspectReference({
      reference_sql: form.value.correct_sql,
      setup_sql: form.value.schema_setup_sql,
      suggest_probes: true,
    })
    const data = res.data || {}
    if (data.error_message) {
      ElMessage.error(data.error_message)
      return
    }
    form.value.schema_expected_schema = data.expected_schema || null
    form.value.schema_probes_text = JSON.stringify(data.suggested_probes || [], null, 2)
    ElMessage.success('已生成期望结构与探针 ✅')
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '生成失败，请检查参考 DDL')
  } finally {
    generating.value = false
  }
}

// ✅ 编辑时加载题目数据
const loadQuestion = async (id: number) => {
  loading.value = true
  try {
    const res = await getQuestionDetail(id)
    const data = res.data
    form.value = {
      title: data.title || '',
      description: data.description || '',
      difficulty: data.difficulty || 'easy',
      judge_mode: data.judge_mode || 'query',
      judge_strictness: data.judge_strictness || 'subset',
      judge_compare_names: !!data.judge_compare_names,
      create_table_sql: data.create_table_sql || '',
      schema_setup_sql: data.test_cases?.[0]?.test_input || '',
      schema_expected_schema: data.test_cases?.[0]?.expected_schema || null,
      schema_probes_text: JSON.stringify(data.test_cases?.[0]?.probes || [], null, 2),
      sample_input: data.sample_input || '',
      sample_output: data.sample_output || '',
      correct_sql: data.answers?.[0]?.correct_sql || '',
      test_cases: data.test_cases || [],
      show_case_details: !!data.show_case_details
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.error || '加载题目数据失败')
  } finally {
    loading.value = false
  }
}

// ✅ 提交处理
const handleSubmit = async () => {
  if (!form.value.title?.trim()) {
    ElMessage.warning('请填写题目名称')
    return
  }
  if (!form.value.description?.trim()) {
    ElMessage.warning('请填写题目描述')
    return
  }

  // schema 模式：整理成一个结构化测试用例（前置语句 + 期望结构 + 探针）
  let testCases = form.value.test_cases
  if (form.value.judge_mode === 'schema') {
    if (!form.value.schema_expected_schema) {
      ElMessage.warning('请先点击「生成期望结构」')
      return
    }
    let probes: any[] = []
    try {
      probes = JSON.parse(form.value.schema_probes_text || '[]')
    } catch (error) {
      ElMessage.error('行为探针 JSON 格式不正确')
      return
    }
    testCases = [{
      test_input: form.value.schema_setup_sql,
      expected_output: '',
      expected_schema: form.value.schema_expected_schema,
      probes,
    }] as any
  }

  submitting.value = true
  try {
    const submitData = {
      title: form.value.title,
      description: form.value.description,
      difficulty: form.value.difficulty,
      judge_mode: form.value.judge_mode,
      judge_strictness: form.value.judge_strictness,
      judge_compare_names: form.value.judge_compare_names,
      create_table_sql: form.value.judge_mode === 'schema' ? '' : form.value.create_table_sql,
      sample_input: form.value.sample_input,
      sample_output: form.value.sample_output,
      answers: form.value.correct_sql ? [{ correct_sql: form.value.correct_sql }] : [],
      test_cases: testCases,
      show_case_details: form.value.show_case_details
    }

    if (isEdit.value) {
      await updateQuestion(Number(route.query.id), submitData)
      ElMessage.success('编辑成功 ✅')
    } else {
      await createQuestion(submitData)
      ElMessage.success('创建成功 ✅')
    }
    router.push('/teacher/questions')
  } catch (error: any) {
    const msg = error.response?.data?.error || '操作失败，请重试'
    ElMessage.error(msg)
  } finally {
    submitting.value = false
  }
}

const goBack = () => {
  router.push('/teacher/questions')
}

onMounted(() => {
  const id = route.query.id
  if (id) {
    isEdit.value = true
    loadQuestion(Number(id))
  }
})
</script>

<style scoped>
.create-container {
  padding: 20px;
  max-width: 960px;
  margin: 0 auto;
  min-height: 100vh;
  background-color: #f5f7fa;
}

.header {
  display: flex;
  align-items: center;
  gap: 20px;
  margin-bottom: 30px;
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

.create-container :deep(.el-form) {
  background: white;
  padding: 30px 40px 20px;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.create-container :deep(.el-form-item) {
  margin-bottom: 22px;
}
.create-container :deep(.el-form-item__label) {
  font-weight: 500;
  color: #2d3748;
}

.input-hint {
  font-size: 12px;
  color: #a0aec0;
  margin-top: 4px;
  padding-left: 4px;
}

/* ✅ 测试用例样式 */
.test-cases-area {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 16px;
  background-color: #fafafa;
}

.test-case-item {
  background: white;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 12px;
}

.test-case-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.test-case-label {
  font-weight: 600;
  font-size: 14px;
  color: #2d3748;
}

.test-case-row {
  display: flex;
  gap: 16px;
}
.test-case-row .el-textarea {
  flex: 1;
}

/* ===== 窄窗口自适应 ===== */
@media (max-width: 768px) {
  .create-container {
    padding: 12px;
  }
  .create-container :deep(.el-form) {
    padding: 16px;
  }
  .header {
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px 16px;
  }
  .test-case-row {
    flex-direction: column;
  }
  /* 标签置顶：避免窄屏下输入框被 120px 宽的标签挤扁 */
  .create-container :deep(.el-form-item) {
    display: block;
  }
  .create-container :deep(.el-form-item__label) {
    width: auto !important;
    text-align: left;
    padding-right: 0;
  }
  .create-container :deep(.el-form-item__content) {
    margin-left: 0 !important;
  }
}
</style>
