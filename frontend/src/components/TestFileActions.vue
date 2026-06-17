<template>
  <div class="test-file-actions">
    <el-button link type="primary" size="small" :loading="loading" @click="handlePreview">预览</el-button>
    <el-button link type="success" size="small" :loading="loading" @click="handleDownload">下载</el-button>
    <el-dialog v-model="previewVisible" :title="fileName" width="80%" destroy-on-close append-to-body>
      <div v-if="previewUrl || previewHtml || previewText" class="preview-body">
        <img v-if="isImage" :src="previewUrl" alt="preview" class="preview-image" />
        <iframe v-else-if="isPdf" :src="previewUrl" class="preview-frame" />
        <iframe v-else-if="isText && previewUrl" :src="previewUrl" class="preview-frame preview-text" />
        <pre v-else-if="isText && previewText" class="preview-text-block">{{ previewText }}</pre>
        <div v-else-if="isDocHtml" class="preview-doc" v-html="previewHtml" />
        <el-alert v-else type="info" :closable="false" show-icon :title="unsupportedTip" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  fileId: { type: Number, required: true },
  projectId: { type: Number, required: true },
  fileName: { type: String, default: '' },
  mimeType: { type: String, default: '' },
  fetchUrl: { type: Function, required: true },
  fetchPreview: { type: Function, default: null },
})

const loading = ref(false)
const previewVisible = ref(false)
const previewUrl = ref('')
const previewHtml = ref('')
const previewText = ref('')

const lowerName = computed(() => (props.fileName || '').toLowerCase())

const isImage = computed(() => (props.mimeType || '').startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(lowerName.value))
const isPdf = computed(() => props.mimeType === 'application/pdf' || lowerName.value.endsWith('.pdf'))
const isText = computed(() => {
  const mt = props.mimeType || ''
  return mt.startsWith('text/') || ['.txt', '.md', '.csv', '.json'].some((ext) => lowerName.value.endsWith(ext))
})
const isDocHtml = computed(() => ['.docx', '.doc'].some((ext) => lowerName.value.endsWith(ext)))

const unsupportedTip = '该文件类型不支持在线预览（支持 PDF、图片、txt/md/csv/json、Word docx），请使用下载。'

function resetPreviewState() {
  previewUrl.value = ''
  previewHtml.value = ''
  previewText.value = ''
}

async function resolveUrl() {
  loading.value = true
  try {
    const res = await props.fetchUrl(props.fileId, props.projectId)
    const data = res.data?.data
    if (!data?.url) throw new Error('无下载地址')
    return data
  } finally {
    loading.value = false
  }
}

async function handleDownload() {
  try {
    const data = await resolveUrl()
    const a = document.createElement('a')
    a.href = data.url
    a.download = data.file_name || props.fileName || 'download'
    a.target = '_blank'
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } catch (e) {
    ElMessage.error(pickErrorMessage(e))
  }
}

async function handlePreview() {
  resetPreviewState()
  try {
    if (isDocHtml.value && props.fetchPreview) {
      loading.value = true
      try {
        const res = await props.fetchPreview(props.fileId, props.projectId)
        const data = res.data?.data
        if (data?.mode === 'html' && data.content) {
          previewHtml.value = data.content
          previewVisible.value = true
          return
        }
      } finally {
        loading.value = false
      }
    }
    if (isText.value && props.fetchPreview) {
      loading.value = true
      try {
        const res = await props.fetchPreview(props.fileId, props.projectId)
        const data = res.data?.data
        if (data?.mode === 'text' && data.content != null) {
          previewText.value = data.content
          previewVisible.value = true
          return
        }
      } finally {
        loading.value = false
      }
    }
    const data = await resolveUrl()
    previewUrl.value = data.url
    previewVisible.value = true
  } catch (e) {
    ElMessage.error(pickErrorMessage(e))
  }
}

function pickErrorMessage(e) {
  const data = e?.response?.data ?? e?.data
  if (typeof data?.detail === 'string' && data.detail) return data.detail
  if (data?.detail?.message) return data.detail.message
  if (data?.message) return data.message
  return e?.message || '操作失败'
}
</script>

<style scoped lang="scss">
.test-file-actions {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.preview-body {
  min-height: 200px;
}
.preview-image {
  max-width: 100%;
  max-height: 70vh;
  display: block;
  margin: 0 auto;
}
.preview-frame {
  width: 100%;
  height: 70vh;
  border: none;
}
.preview-text-block {
  max-height: 70vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.5;
}
.preview-doc {
  max-height: 70vh;
  overflow: auto;
  padding: 12px 16px;
  line-height: 1.6;
  :deep(p) {
    margin: 0 0 8px;
  }
  :deep(table) {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
  }
  :deep(td) {
    border: 1px solid var(--el-border-color);
    padding: 6px 8px;
    font-size: 13px;
  }
}
</style>
