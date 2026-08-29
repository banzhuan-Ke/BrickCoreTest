<template>
  <div class="tm-defect-attachments">
    <el-upload
      drag
      multiple
      :show-file-list="false"
      :http-request="doUpload"
      :disabled="!projectId || disabled"
      accept=".png,.jpg,.jpeg,.gif,.webp,.bmp,.svg,.pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.zip,.rar,.7z,.log,.json,.xml"
    >
      <div class="upload-inner">
        <el-icon class="upload-icon"><UploadFilled /></el-icon>
        <div class="upload-text">拖拽或点击上传图片 / 附件</div>
        <div class="upload-tip">支持粘贴截图；单文件 ≤ 20MB，最多 {{ maxCount }} 个</div>
      </div>
    </el-upload>

    <div v-if="images.length" class="image-grid">
      <div v-for="item in images" :key="item.uid" class="image-card">
        <el-image
          :src="previewMap[item.uid] || ''"
          fit="cover"
          :preview-src-list="imagePreviewList"
          :initial-index="imagePreviewIndex(item.uid)"
          preview-teleported
        >
          <template #error>
            <div class="image-fallback">{{ item.name }}</div>
          </template>
        </el-image>
        <div class="image-actions">
          <el-button link type="primary" size="small" @click="openUrl(item)">打开</el-button>
          <el-button link type="danger" size="small" :disabled="disabled" @click="remove(item.uid)">删除</el-button>
        </div>
        <div class="image-name" :title="item.name">{{ item.name }}</div>
      </div>
    </div>

    <el-table v-if="files.length" :data="files" size="small" border class="file-table">
      <el-table-column prop="name" label="附件" min-width="180" show-overflow-tooltip />
      <el-table-column label="大小" width="90">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openUrl(row)">下载</el-button>
          <el-button link type="danger" :disabled="disabled" @click="remove(row.uid)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { testDefectApi } from '@/api/testManagement'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  projectId: { type: [Number, String], default: null },
  disabled: { type: Boolean, default: false },
  maxCount: { type: Number, default: 20 },
  /** 可注入 { uploadAttachment, attachmentUrl }，默认走缺陷附件 API */
  api: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue'])

const fileApi = computed(() => props.api || testDefectApi)
const previewMap = ref({})
const items = computed(() => (Array.isArray(props.modelValue) ? props.modelValue : []))
const images = computed(() => items.value.filter((x) => x.kind === 'image'))
const files = computed(() => items.value.filter((x) => x.kind !== 'image'))
const imagePreviewList = computed(() =>
  images.value.map((x) => previewMap.value[x.uid]).filter(Boolean)
)

const imagePreviewIndex = (uid) => {
  const list = images.value
  const idx = list.findIndex((x) => x.uid === uid)
  return idx >= 0 ? idx : 0
}

const formatSize = (n) => {
  const size = Number(n) || 0
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

const setItems = (next) => emit('update:modelValue', next)

const remove = (uid) => {
  setItems(items.value.filter((x) => x.uid !== uid))
}

const refreshPreview = async (item) => {
  if (!props.projectId || !item?.key) return
  try {
    const res = await fileApi.value.attachmentUrl(props.projectId, item.key, item.bucket)
    const url = res.data?.data?.url
    if (url) {
      previewMap.value = { ...previewMap.value, [item.uid]: url }
    }
  } catch {
    /* 预览失败不阻断编辑 */
  }
}

const refreshAllPreviews = async () => {
  for (const item of images.value) {
    await refreshPreview(item)
  }
}

const doUpload = async ({ file }) => {
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (items.value.length >= props.maxCount) {
    ElMessage.warning(`最多上传 ${props.maxCount} 个附件`)
    return
  }
  try {
    const res = await fileApi.value.uploadAttachment(props.projectId, file)
    const meta = res.data?.data
    if (!meta?.uid) {
      ElMessage.error('上传失败：未返回附件信息')
      return
    }
    setItems([...items.value, meta])
    if (meta.kind === 'image') await refreshPreview(meta)
    ElMessage.success(`已上传 ${meta.name}`)
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  }
}

const openUrl = async (item) => {
  try {
    const res = await fileApi.value.attachmentUrl(props.projectId, item.key, item.bucket)
    const url = res.data?.data?.url
    if (url) window.open(url, '_blank', 'noopener,noreferrer')
    else ElMessage.error('无法获取下载链接')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '获取链接失败')
  }
}

const onPaste = async (e) => {
  if (props.disabled || !props.projectId) return
  const clipboard = e.clipboardData
  if (!clipboard?.items?.length) return
  const imageItems = [...clipboard.items].filter((it) => it.type?.startsWith('image/'))
  if (!imageItems.length) return
  e.preventDefault()
  for (const it of imageItems) {
    const file = it.getAsFile()
    if (file) await doUpload({ file })
  }
}

watch(
  () => [props.projectId, items.value.map((x) => x.uid).join(',')],
  () => refreshAllPreviews()
)

onMounted(() => {
  window.addEventListener('paste', onPaste)
  refreshAllPreviews()
})
onBeforeUnmount(() => {
  window.removeEventListener('paste', onPaste)
})
</script>

<style scoped>
.tm-defect-attachments {
  width: 100%;
}
.upload-inner {
  padding: 12px 8px;
}
.upload-icon {
  font-size: 36px;
  color: var(--el-color-primary);
}
.upload-text {
  margin-top: 6px;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.upload-tip {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.image-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background: var(--el-fill-color-blank);
}
.image-card :deep(.el-image) {
  width: 100%;
  height: 90px;
  display: block;
}
.image-fallback {
  height: 90px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  padding: 6px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}
.image-actions {
  display: flex;
  justify-content: space-between;
  padding: 0 6px;
}
.image-name {
  font-size: 12px;
  padding: 0 6px 6px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-table {
  margin-top: 12px;
}
</style>
