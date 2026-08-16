<template>
  <div class="expected-after-fields">
    <el-form label-width="88px" size="default" @submit.prevent>
      <el-form-item label="后置类型">
        <el-select
          :model-value="local.type || ''"
          clearable
          placeholder="不校验（可选）"
          style="width: 100%"
          @update:model-value="onTypeChange"
        >
          <el-option
            v-for="opt in TYPE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item v-if="needsText" :label="textLabel">
        <el-input
          :model-value="local.text || ''"
          :placeholder="textPlaceholder"
          @update:model-value="patch({ text: $event })"
        />
      </el-form-item>

      <el-form-item v-if="needsLocator" label="定位器">
        <el-input
          :model-value="local.locator || ''"
          :placeholder="locatorPlaceholder"
          @update:model-value="patch({ locator: $event })"
        />
      </el-form-item>

      <el-form-item v-if="needsValue" label="期望值">
        <el-input
          :model-value="local.value ?? ''"
          placeholder="期望的输入框 value"
          @update:model-value="patch({ value: $event })"
        />
      </el-form-item>

      <el-form-item v-if="local.type" label="超时(ms)">
        <el-input-number
          :model-value="Number(local.timeout || 5000)"
          :min="500"
          :max="120000"
          :step="500"
          controls-position="right"
          style="width: 160px"
          @update:model-value="patch({ timeout: $event || 5000 })"
        />
      </el-form-item>
    </el-form>
    <p class="field-hint">
      危险动作（删除/提交等）必须配置；智能输入未配置时，执行侧默认校验输入值等于本次内容。
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const TYPE_OPTIONS = [
  { value: 'text_visible', label: '文本可见' },
  { value: 'locator_visible', label: '元素可见' },
  { value: 'locator_hidden', label: '元素消失/隐藏' },
  { value: 'url_contains', label: 'URL 包含' },
  { value: 'value_equals', label: '输入值等于' },
]

const props = defineProps({
  modelValue: { type: [Object, String, null], default: null },
})

const emit = defineEmits(['update:modelValue'])

const local = computed(() => {
  const raw = props.modelValue
  if (!raw) return {}
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch {
      return {}
    }
  }
  return typeof raw === 'object' ? raw : {}
})

const needsText = computed(() =>
  ['text_visible', 'url_contains'].includes(local.value.type),
)
const needsLocator = computed(() =>
  ['locator_visible', 'locator_hidden', 'value_equals', 'text_visible'].includes(
    local.value.type,
  ),
)
const needsValue = computed(() => local.value.type === 'value_equals')

const textLabel = computed(() =>
  local.value.type === 'url_contains' ? 'URL 片段' : '文本',
)
const textPlaceholder = computed(() =>
  local.value.type === 'url_contains' ? '如 /orders' : '页面上应出现的文案',
)
const locatorPlaceholder = computed(() => {
  if (local.value.type === 'text_visible') {
    return '可选；留空则按文本查找 get_by_text'
  }
  if (local.value.type === 'value_equals') {
    return '可选；留空则用本次选中的输入框'
  }
  return '后置校验定位表达式'
})

function emitValue(next) {
  if (!next || !next.type) {
    emit('update:modelValue', {})
    return
  }
  const cleaned = { type: next.type }
  if (next.text != null && String(next.text).trim() !== '') {
    cleaned.text = String(next.text)
  }
  if (next.locator != null && String(next.locator).trim() !== '') {
    cleaned.locator = String(next.locator)
  }
  if (next.value != null && String(next.value) !== '') {
    cleaned.value = next.value
  }
  if (next.timeout != null) {
    cleaned.timeout = Number(next.timeout) || 5000
  }
  emit('update:modelValue', cleaned)
}

function patch(partial) {
  emitValue({ ...local.value, ...partial })
}

function onTypeChange(type) {
  if (!type) {
    emit('update:modelValue', {})
    return
  }
  emitValue({
    type,
    text: local.value.text || '',
    locator: local.value.locator || '',
    value: local.value.value ?? '',
    timeout: local.value.timeout || 5000,
  })
}
</script>

<style scoped>
.expected-after-fields {
  width: 100%;
  padding: 10px 12px 8px;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.expected-after-fields :deep(.el-form-item) {
  margin-bottom: 12px;
}
.expected-after-fields :deep(.el-form-item:last-child) {
  margin-bottom: 4px;
}
.field-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
