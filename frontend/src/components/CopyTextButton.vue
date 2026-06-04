<template>
  <el-button
    link
    type="primary"
    size="small"
    :icon="CopyDocument"
    :loading="loading"
    @click.stop="handleCopy"
  >
    {{ label }}
  </el-button>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument } from '@element-plus/icons-vue'
import { copyToClipboard } from '@/utils/clipboard.js'

const props = defineProps({
  text: { type: [String, Number, Object, Array], default: '' },
  label: { type: String, default: '复制' },
  successMessage: { type: String, default: '已复制到剪贴板' },
})

const loading = ref(false)

function normalizeText(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

async function handleCopy() {
  const content = normalizeText(props.text)
  if (!content) {
    ElMessage.warning('暂无内容可复制')
    return
  }
  loading.value = true
  try {
    const ok = await copyToClipboard(content)
    if (ok) ElMessage.success(props.successMessage)
    else ElMessage.error('复制失败，请手动选择复制')
  } finally {
    loading.value = false
  }
}

defineExpose({ copy: handleCopy })
</script>
