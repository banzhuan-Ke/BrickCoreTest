<template>
  <div class="ui-test-file-picker">
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
        accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,.zip,.xmind,.json"
      >
        <el-button type="primary" link :loading="uploading">上传新文件</el-button>
      </el-upload>
      <el-button type="info" link @click="loadFiles">刷新列表</el-button>
    </div>
    <el-collapse v-if="showLegacy">
      <el-collapse-item title="高级：Runner 本地路径（兼容模式）" name="legacy">
        <div class="param-input-row">
          <el-input
            v-model="legacyPath"
            placeholder="如 ${{files_path}}/test.pdf"
            style="flex: 1"
            @input="emitLegacy"
          />
          <VarInsertButton v-if="envId" :env-id="envId" label="变量" />
        </div>
        <p class="legacy-hint">多 Runner 场景请优先使用上方平台文件；本地路径仅在单机 Runner 维护 files_path 目录时使用。</p>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { uiTestFileApi } from '@/api/modules/uiTestFile'
import { ProjectStore } from '@/stores/module/ProjectStore'
import VarInsertButton from '@/components/VarInsertButton.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  envId: { type: [Number, String], default: null },
  showLegacy: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const loading = ref(false)
const uploading = ref(false)
const fileList = ref([])
const selectedId = ref(null)
const legacyPath = ref('')

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function emitParams(patch) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function syncFromModel() {
  const p = props.modelValue || {}
  legacyPath.value = p.file_path || ''
  if (p.file_key) {
    const match = fileList.value.find((f) => f.file_key === p.file_key)
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
    const res = await uiTestFileApi.getList({ project_id: projectId, page: 1, size: 200 })
    fileList.value = res.data?.data?.items || []
    syncFromModel()
  } finally {
    loading.value = false
  }
}

function onSelectChange(id) {
  if (!id) {
    emitParams({ file_key: '', file_bucket: '', file_name: '' })
    return
  }
  const row = fileList.value.find((f) => f.id === id)
  if (!row) return
  emitParams({
    file_key: row.file_key,
    file_bucket: row.file_bucket,
    file_name: row.file_name,
    file_path: '',
  })
}

function emitLegacy() {
  emitParams({
    file_path: legacyPath.value,
    file_key: '',
    file_bucket: '',
    file_name: '',
  })
  selectedId.value = null
}

async function onUpload(uploadFile) {
  const projectId = proStore.projectInfo?.id
  const raw = uploadFile?.raw
  if (!projectId || !raw) return
  uploading.value = true
  try {
    const res = await uiTestFileApi.upload(projectId, raw)
    const data = res.data?.data
    if (res.data?.code !== 200 || !data) {
      ElMessage.error(res.data?.message || '上传失败')
      return
    }
    ElMessage.success('上传成功')
    await loadFiles()
    selectedId.value = data.id
    emitParams({
      file_key: data.file_key,
      file_bucket: data.file_bucket,
      file_name: data.file_name,
      file_path: '',
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
.ui-test-file-picker {
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
.param-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
</style>
