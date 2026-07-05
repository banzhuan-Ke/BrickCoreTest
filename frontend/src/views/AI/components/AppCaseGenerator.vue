<template>
  <el-dialog
    v-model="visible"
    title="🤖 AI 生成 App 测试步骤"
    width="860px"
    destroy-on-close
    :close-on-click-modal="false"
    class="ai-generator-dialog"
  >
    <div v-if="!generatedSteps.length && !generating" class="generator-form">
      <el-form :model="form" label-width="100px">
        <el-form-item label="AI 配置">
          <el-select
            v-model="aiConfigId"
            placeholder="默认场景配置"
            clearable
            filterable
            :loading="loadingConfigs"
            style="width: 100%"
          >
            <el-option
              v-for="c in enabledConfigs"
              :key="c.id"
              :label="`${c.name} (${c.model})`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="驱动模式">
          <el-select v-model="form.driver_mode" style="width: 220px">
            <el-option
              v-for="opt in driverModeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="App ID">
          <el-input v-model="form.app_id" placeholder="可选，用于 launch_app 步骤" clearable />
        </el-form-item>
        <el-form-item required>
          <template #label>
            <span>测试描述</span>
            <el-tooltip placement="top" :show-after="200">
              <template #content>
                用自然语言描述操作流程与断言，例如：<br />
                启动应用 → 点击「我的」→ 登录 demo/demo123 → 预期：进入个人中心
              </template>
              <el-icon class="label-tip-icon"><QuestionFilled /></el-icon>
            </el-tooltip>
          </template>
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="6"
            placeholder="描述 App 上的操作步骤与预期结果"
          />
        </el-form-item>
        <el-form-item label="应用方式">
          <el-radio-group v-model="applyMode">
            <el-radio value="append">追加到现有步骤</el-radio>
            <el-radio value="replace">替换全部步骤</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
    </div>

    <div v-else-if="generating" class="generating-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      <span>AI 正在生成步骤，请稍候…</span>
    </div>

    <div v-else class="steps-preview">
      <el-alert
        v-if="errors.length"
        type="warning"
        :closable="false"
        show-icon
        :title="`有 ${errors.length} 条校验提示，应用前请核对`"
        style="margin-bottom: 12px"
      />
      <div v-for="(step, index) in generatedSteps" :key="index" class="step-card">
        <div class="step-head">
          <span class="step-index">#{{ index + 1 }}</span>
          <span class="step-keyword">{{ step.keyword }}.{{ step.method }}</span>
          <span v-if="step.desc" class="step-desc">{{ step.desc }}</span>
        </div>
        <code class="step-params">{{ JSON.stringify(step.params) }}</code>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <template v-if="!generatedSteps.length && !generating">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :loading="generating" icon="MagicStick" @click="handleGenerate">
            开始生成
          </el-button>
        </template>
        <template v-else-if="generatedSteps.length && !generating">
          <el-button @click="handleRegenerate">重新填写</el-button>
          <el-button @click="visible = false">关闭</el-button>
          <el-button type="primary" icon="Check" @click="handleApply">应用步骤</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, QuestionFilled } from '@element-plus/icons-vue'
import { aiGenerateApi } from '@/api/modules/ai'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import { APP_DRIVER_MODE_OPTIONS } from '@/datas/AppActionGroup.js'
import { validateAppStepParams, isAppMethod } from '@/utils/appStepMeta.js'

const props = defineProps({
  modelValue: Boolean,
  initialDescription: { type: String, default: '' },
  driverMode: { type: String, default: 'hybrid' },
  appId: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'apply'])

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect({ scene: 'app_case_generate' })
const driverModeOptions = APP_DRIVER_MODE_OPTIONS

const visible = ref(false)
const generating = ref(false)
const generatedSteps = ref([])
const errors = ref([])
const applyMode = ref('append')

const form = reactive({
  description: '',
  app_id: '',
  driver_mode: 'hybrid',
})

watch(
  () => props.modelValue,
  (val) => {
    visible.value = val
    if (val) {
      loadConfigs()
      form.description = props.initialDescription || ''
      form.driver_mode = props.driverMode || 'hybrid'
      form.app_id = props.appId || ''
      generatedSteps.value = []
      errors.value = []
      applyMode.value = 'append'
    }
  },
  { immediate: true }
)

watch(visible, (val) => emit('update:modelValue', val))

const handleGenerate = async () => {
  if (!form.description.trim()) {
    ElMessage.warning('请输入测试描述')
    return
  }
  generating.value = true
  generatedSteps.value = []
  errors.value = []
  try {
    const res = await aiGenerateApi.generateAppCase({
      description: form.description.trim(),
      app_id: form.app_id?.trim() || undefined,
      driver_mode: form.driver_mode,
      ai_config_id: aiConfigId.value || undefined,
    })
    if (res.status === 200 && res.data?.data?.steps?.length) {
      generatedSteps.value = res.data.data.steps
      errors.value = res.data.data.errors || []
      ElMessage.success(`成功生成 ${generatedSteps.value.length} 个步骤`)
    } else if (res.status === 200 && res.data?.data?.steps) {
      ElMessage.warning('AI 未返回有效步骤')
    } else {
      ElMessage.error(res.data?.message || res.data?.detail || '生成失败')
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message || '生成失败')
  } finally {
    generating.value = false
  }
}

const handleRegenerate = () => {
  generatedSteps.value = []
  errors.value = []
}

const handleApply = () => {
  if (!generatedSteps.value.length) {
    ElMessage.warning('没有可应用的步骤')
    return
  }
  for (let i = 0; i < generatedSteps.value.length; i += 1) {
    const step = generatedSteps.value[i]
    if (!isAppMethod(step.method)) continue
    const err = validateAppStepParams(step.method, step.params || {})
    if (err) {
      ElMessage.error(`第 ${i + 1} 步：${err}，请重新生成或手动补全后再应用`)
      return
    }
  }
  emit('apply', {
    steps: JSON.parse(JSON.stringify(generatedSteps.value)),
    mode: applyMode.value,
  })
  visible.value = false
}
</script>

<style scoped lang="scss">
.ai-generator-dialog {
  :deep(.el-dialog__body) {
    max-height: 70vh;
    overflow-y: auto;
  }
}

.label-tip-icon {
  margin-left: 4px;
  font-size: 14px;
  color: var(--el-color-info);
  vertical-align: middle;
}

.generating-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 0;
  color: var(--el-text-color-secondary);
}

.step-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 10px;

  .step-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .step-index {
    font-weight: 600;
    color: var(--el-color-primary);
  }

  .step-keyword {
    font-family: monospace;
    font-size: 13px;
  }

  .step-desc {
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }

  .step-params {
    display: block;
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-all;
    background: var(--el-fill-color-light);
    padding: 8px;
    border-radius: 4px;
  }
}
</style>
