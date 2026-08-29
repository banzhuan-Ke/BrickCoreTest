<template>
  <el-form-item :label="label" :required="required">
    <template v-if="showOptimize || labelTooltip" #label>
      <div class="label-row">
        <span>{{ label }}</span>
        <el-tooltip
          v-if="labelTooltip"
          :content="labelTooltip"
          placement="top"
          raw-content
          :show-after="200"
        >
          <el-icon class="label-tip-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
        <el-button
          v-if="showOptimize"
          link
          type="primary"
          :disabled="!canOptimize"
          :loading="optimizing"
          @click="runOptimize"
        >
          AI 优化
        </el-button>
      </div>
    </template>
    <el-input
      :model-value="modelValue"
      type="textarea"
      :rows="rows"
      :placeholder="placeholder"
      @update:model-value="$emit('update:modelValue', $event)"
    />
    <div class="task-text-tools">
      <VarInsertButton :env-id="numericEnvId" label="插入变量" />
    </div>
    <div v-if="defaultHint" class="field-hint">{{ defaultHint }}</div>

    <el-dialog
      v-model="dialog.visible"
      :title="optimizeDialogTitle"
      width="640px"
      destroy-on-close
      append-to-body
    >
      <div v-if="dialog.changesSummary" class="changes-box">
        <div class="changes-title">优化说明</div>
        <div class="changes-text">{{ dialog.changesSummary }}</div>
        <div v-if="dialog.tokensUsed" class="changes-meta">Token：{{ dialog.tokensUsed }}</div>
      </div>
      <el-form label-width="72px">
        <el-form-item label="原文">
          <el-input :model-value="dialog.original" type="textarea" :rows="4" readonly />
        </el-form-item>
        <el-form-item label="优化后">
          <el-input v-model="dialog.optimized" type="textarea" :rows="6" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :disabled="!dialog.optimized?.trim()" @click="applyOptimized">采用优化结果</el-button>
      </template>
    </el-dialog>
  </el-form-item>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { browserLabApi, aiGenerateApi } from '@/api/modules/ai.js'
import VarInsertButton from '@/components/VarInsertButton.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '任务描述' },
  required: { type: Boolean, default: false },
  rows: { type: Number, default: 4 },
  placeholder: { type: String, default: '自然语言描述要完成的浏览器操作' },
  hint: { type: String, default: '' },
  startUrl: { type: String, default: '' },
  caseName: { type: String, default: '' },
  aiConfigId: { type: [Number, String], default: null },
  projectId: { type: [Number, String], default: null },
  envId: { type: [Number, String], default: null },
  showOptimize: { type: Boolean, default: true },
  /** browser_lab | ui_case | ui_agent_solidify */
  optimizeScene: { type: String, default: 'browser_lab' },
  generationMode: { type: String, default: '' },
  labelTooltip: { type: String, default: '' },
})

const defaultHint = computed(() => {
  if (props.hint) return props.hint
  if (props.optimizeScene === 'ui_agent_solidify') {
    return '可点击「AI 优化」改写为 Agent 逐步固化更易执行的目标（填表/搜索/菜单导航，不含成功结论报告）'
  }
  if (props.optimizeScene === 'ui_case') {
    return '可点击「AI 优化」改写为更适合 AI 生成 Playwright 步骤的描述（含登录、导航、预期结果）'
  }
  return '可点击「AI 优化」改写为更适合 browser-use 自动执行的中文步骤说明'
})

const optimizeDialogTitle = computed(() => {
  if (props.optimizeScene === 'ui_agent_solidify') return 'AI 优化 Agent 固化目标'
  if (props.optimizeScene === 'ui_case') return 'AI 优化测试描述'
  return 'AI 优化任务描述'
})

const emit = defineEmits(['update:modelValue'])

const optimizing = ref(false)
const dialog = ref({
  visible: false,
  original: '',
  optimized: '',
  changesSummary: '',
  tokensUsed: 0
})

const canOptimize = computed(() => Boolean((props.modelValue || '').trim().length >= 2 && props.projectId))
const numericEnvId = computed(() => {
  const n = Number(props.envId)
  return Number.isFinite(n) && n > 0 ? n : null
})

async function runOptimize() {
  if (!props.projectId) return ElMessage.warning('请先选择项目')
  if (!(props.modelValue || '').trim()) {
    const msg = {
      ui_case: '请先填写测试描述',
      ui_agent_solidify: '请先填写 Agent 固化目标',
    }[props.optimizeScene] || '请先填写任务描述'
    return ElMessage.warning(msg)
  }
  optimizing.value = true
  try {
    const payload = {
      task_text: props.modelValue,
      start_url: props.startUrl || undefined,
      case_name: props.caseName || undefined,
      ai_config_id: props.aiConfigId || undefined,
    }
    let res
    if (props.optimizeScene === 'ui_case') {
      res = await aiGenerateApi.optimizeDescription({
        ...payload,
        generation_mode: props.generationMode || undefined,
      }, props.projectId)
    } else if (props.optimizeScene === 'ui_agent_solidify') {
      res = await browserLabApi.optimizeTaskText({
        ...payload,
        optimize_mode: 'solidify',
      }, props.projectId)
    } else {
      res = await browserLabApi.optimizeTaskText(payload, props.projectId)
    }
    if (res.data?.code !== 200) throw new Error(res.data?.message || '优化失败')
    const d = res.data.data || {}
    dialog.value = {
      visible: true,
      original: d.original_task_text || props.modelValue,
      optimized: d.task_text || '',
      changesSummary: d.changes_summary || '',
      tokensUsed: d.tokens_used || 0
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || 'AI 优化失败')
  } finally {
    optimizing.value = false
  }
}

function applyOptimized() {
  const text = (dialog.value.optimized || '').trim()
  if (!text) return
  emit('update:modelValue', text)
  dialog.value.visible = false
  ElMessage.success(
    {
      ui_case: '已采用优化后的测试描述',
      ui_agent_solidify: '已采用优化后的 Agent 固化目标',
    }[props.optimizeScene] || '已采用优化后的任务描述'
  )
}
</script>

<style scoped>
.label-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.label-tip-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  vertical-align: middle;
  cursor: help;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.task-text-tools {
  margin-top: 6px;
}
.changes-box {
  margin-bottom: 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.changes-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 4px;
}
.changes-text {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.changes-meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
