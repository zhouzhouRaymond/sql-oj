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

      <!-- 建表语句 -->
      <el-form-item label="建表语句">
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
      <el-form-item label="测试用例">
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
      <el-form-item label="正确答案 SQL">
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
import { createQuestion, updateQuestion, getQuestionDetail } from '../../api/questions'
import SqlEditor from '../../components/SqlEditor.vue'

const route = useRoute()
const router = useRouter()

const isEdit = ref(false)
const loading = ref(false)
const submitting = ref(false)

// ✅ 表单包含 test_cases
const form = ref({
  title: '',
  description: '',
  difficulty: 'easy',
  create_table_sql: '',
  sample_input: '',
  sample_output: '',
  correct_sql: '',
  test_cases: [] as { test_input: string; expected_output: string }[]
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
      create_table_sql: data.create_table_sql || '',
      sample_input: data.sample_input || '',
      sample_output: data.sample_output || '',
      correct_sql: data.answers?.[0]?.correct_sql || '',
      test_cases: data.test_cases || []
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

  submitting.value = true
  try {
    const submitData = {
      title: form.value.title,
      description: form.value.description,
      difficulty: form.value.difficulty,
      create_table_sql: form.value.create_table_sql,
      sample_input: form.value.sample_input,
      sample_output: form.value.sample_output,
      answers: form.value.correct_sql ? [{ correct_sql: form.value.correct_sql }] : [],
      test_cases: form.value.test_cases
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
  font-size: 22px;
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