<template>
  <div class="api-test-file-picker">
    <el-select
      v-model="selectedId"
      filterable
      clearable
      placeholder="选择已上传的测试文件"
      style="width: 100%"
      :loading="loading"
      @change="onSelectChange"
    >
      <el-option
        v-for="item in fileList"
        :key="item.id"
        :label="`${item.file_name} (${formatSize(item.size)})`"
        :value="item.id"
      />
    </el-select>
    <div class="picker-actions">
      <el-upload
        :show-file-list="false"
        :auto-upload="false"
        :on-change="onUpload"
        accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,.zip,.json,.pem,.p12,.pfx,.cer,.crt,.key"
      >
        <el-button type="primary" link :loading="uploading">上传新文件</el-button>
      </el-upload>
      <el-button type="info" link @click="loadFiles">刷新列表</el-button>
    </div>
    <p v-if="modelValue?.file_name && !selectedId" class="legacy-hint">
      已绑定文件：{{ modelValue.file_name }}（历史直传，可重新选择以纳入项目文件库）
    </p>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { apiTestFileApi } from '@/api/modules/apiTestFile'
import { ProjectStore } from '@/stores/module/ProjectStore'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const loading = ref(false)
const uploading = ref(false)
const fileList = ref([])
const selectedId = ref(null)

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function emitField(patch) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function syncFromModel() {
  const f = props.modelValue || {}
  if (f.file_key) {
    const match = fileList.value.find((item) => item.file_key === f.file_key)
    selectedId.value = match?.id ?? null
  } else {
    selectedId.value = null
  }
}

async function loadFiles() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await apiTestFileApi.getList({ project_id: projectId, page: 1, size: 200 })
    fileList.value = res.data?.data?.items || []
    syncFromModel()
  } finally {
    loading.value = false
  }
}

function onSelectChange(id) {
  if (!id) {
    emitField({ file_key: '', file_bucket: '', file_name: '', mime_type: 'application/octet-stream' })
    return
  }
  const row = fileList.value.find((item) => item.id === id)
  if (!row) return
  emitField({
    file_key: row.file_key,
    file_bucket: row.file_bucket,
    file_name: row.file_name,
    mime_type: row.mime_type || 'application/octet-stream',
    value: '',
  })
}

async function onUpload(uploadFile) {
  const projectId = proStore.projectInfo?.id
  const raw = uploadFile?.raw
  if (!projectId || !raw) return
  uploading.value = true
  try {
    const res = await apiTestFileApi.upload(projectId, raw)
    const data = res.data?.data
    if (res.data?.code !== 200 || !data) {
      ElMessage.error(res.data?.message || '上传失败')
      return
    }
    ElMessage.success('上传成功')
    await loadFiles()
    selectedId.value = data.id
    emitField({
      file_key: data.file_key,
      file_bucket: data.file_bucket,
      file_name: data.file_name,
      mime_type: data.mime_type || 'application/octet-stream',
      value: '',
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

watch(() => props.modelValue, syncFromModel, { deep: true })
onMounted(loadFiles)
</script>

<style scoped lang="scss">
.api-test-file-picker {
  width: 100%;
}
.picker-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.legacy-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
