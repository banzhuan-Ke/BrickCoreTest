<template>
  <el-form-item :label="label" :required="required">
    <template v-if="showOptimize" #label>
      <div class="label-row">
        <span>{{ label }}</span>
        <el-button
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
    <div v-if="hint" class="field-hint">{{ hint }}</div>

    <el-dialog v-model="dialog.visible" title="AI 优化任务描述" width="640px" destroy-on-close append-to-body>
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
import { browserLabApi } from '@/api/modules/ai.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: '任务描述' },
  required: { type: Boolean, default: false },
  rows: { type: Number, default: 4 },
  placeholder: { type: String, default: '自然语言描述要完成的浏览器操作' },
  hint: { type: String, default: '可点击「AI 优化」改写为更适合 browser-use 自动执行的中文步骤说明' },
  startUrl: { type: String, default: '' },
  caseName: { type: String, default: '' },
  aiConfigId: { type: [Number, String], default: null },
  projectId: { type: [Number, String], default: null },
  showOptimize: { type: Boolean, default: true }
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

async function runOptimize() {
  if (!props.projectId) return ElMessage.warning('请先选择项目')
  if (!(props.modelValue || '').trim()) return ElMessage.warning('请先填写任务描述')
  optimizing.value = true
  try {
    const res = await browserLabApi.optimizeTaskText({
      task_text: props.modelValue,
      start_url: props.startUrl || undefined,
      case_name: props.caseName || undefined,
      ai_config_id: props.aiConfigId || undefined
    }, props.projectId)
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
  ElMessage.success('已采用优化后的任务描述')
}
</script>

<style scoped>
.label-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
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
