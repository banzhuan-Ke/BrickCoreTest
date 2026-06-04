<template>
  <div class="ui-context-block">
    <div class="block-title">执行上下文</div>
    <el-form label-width="110px" class="context-form">
      <el-form-item label="目标页面">
        <el-input
          v-model="modelValue.page_url"
          :placeholder="mode === 'record' ? '登录页或业务页 URL（录制起始地址）' : '登录页或业务页 URL（探索/录制必填）'"
          clearable
        />
        <div v-if="mode === 'record'" class="field-hint">
          录制时请在浏览器中手动完成登录与导航；业务背景可在录制结束后的「测试描述 / AI 优化」中补充。
        </div>
      </el-form-item>
      <template v-if="mode === 'generate'">
      <el-form-item label="登录策略">
        <el-radio-group v-model="modelValue.login_strategy">
          <el-radio value="none">仅功能用例描述</el-radio>
          <el-radio value="credentials">附加测试账号</el-radio>
          <el-radio value="prepend_login">引用登录 UI 用例</el-radio>
          <el-radio value="both">账号 + 引用登录</el-radio>
        </el-radio-group>
        <div class="field-hint login-strategy-hint">
          录制时 Runner 只打开页面，<strong>不会自动登录</strong>，仍需在浏览器中手动完成登录与导航。
          登录策略在「AI 生成」或「导入 UI 用例」时生效：写入 AI 描述、或前置引用登录用例步骤。
        </div>
      </el-form-item>
      <el-form-item
        v-if="needsCredentials"
        label="测试账号"
      >
        <div class="account-row">
          <el-input v-model="modelValue.test_username" placeholder="用户名" style="width: 160px;" />
          <el-input
            v-model="modelValue.test_password"
            placeholder="密码"
            type="password"
            show-password
            style="width: 160px;"
          />
        </div>
        <div class="field-hint">仅用于 AI 生成/录制，不会写入禅道功能用例</div>
      </el-form-item>
      <el-form-item
        v-if="needsLoginCase"
        label="登录 UI 用例"
      >
        <el-select
          v-model="modelValue.login_ui_case_id"
          clearable
          filterable
          placeholder="选择已维护的登录自动化用例"
          style="width: 100%;"
        >
          <el-option
            v-for="c in uiCaseOptions"
            :key="c.id"
            :label="`${c.name} (#${c.id})`"
            :value="c.id"
          />
        </el-select>
        <div class="field-hint">推荐：非登录类用例前置已有登录步骤，比纯 AI 猜登录更稳定</div>
      </el-form-item>
      <el-form-item label="细节补充">
        <el-input
          v-model="modelValue.extra_context"
          type="textarea"
          :rows="3"
          placeholder="例如：登录后点击左侧「知识库」→「文档抽取」进入目标模块；或补充业务背景、特殊校验点（功能用例正文未写明的部分）"
          maxlength="800"
          show-word-limit
        />
      </el-form-item>
      </template>
    </el-form>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import http from '@/api/index'

const props = defineProps({
  modelValue: {
    type: Object,
    required: true
  },
  projectId: {
    type: [Number, String],
    required: true
  },
  /** generate：AI 生成；record：录制（仅目标页面） */
  mode: {
    type: String,
    default: 'generate'
  }
})

const uiCaseOptions = ref([])

const needsCredentials = computed(() =>
  ['credentials', 'both'].includes(props.modelValue.login_strategy)
)
const needsLoginCase = computed(() =>
  ['prepend_login', 'both'].includes(props.modelValue.login_strategy)
)

const ensureDefaults = () => {
  const m = props.modelValue
  if (m.page_url === undefined) m.page_url = ''
  if (m.test_username === undefined) m.test_username = ''
  if (m.test_password === undefined) m.test_password = ''
  if (m.login_ui_case_id === undefined) m.login_ui_case_id = null
  if (m.login_strategy === undefined) m.login_strategy = 'none'
  if (m.extra_context === undefined) m.extra_context = ''
}

const loadUiCases = async () => {
  if (!props.projectId) return
  try {
    const res = await http.caseApi.getList({
      project_id: props.projectId,
      page: 1,
      size: 500
    })
    uiCaseOptions.value = res.data?.data || []
  } catch (e) {
    console.error(e)
  }
}

onMounted(() => {
  ensureDefaults()
  if (props.mode === 'generate') {
    loadUiCases()
  }
})
</script>

<style scoped lang="scss">
.ui-context-block {
  margin-bottom: 12px;
  padding: 12px 12px 4px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
}
.block-title {
  font-weight: 600;
  margin-bottom: 10px;
  font-size: 14px;
}
.account-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.field-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
