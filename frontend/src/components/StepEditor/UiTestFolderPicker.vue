<template>
  <div class="ui-test-folder-picker">
    <el-select
      v-model="selectedId"
      filterable
      clearable
      placeholder="选择已上传的测试文件夹"
      style="width: 100%"
      :loading="loading"
      @change="onSelectChange"
    >
      <el-option
        v-for="item in folderList"
        :key="item.id"
        :label="`${item.folder_name} (${item.file_count} 个文件, ${formatSize(item.total_size)})`"
        :value="item.id"
      />
    </el-select>
    <div class="picker-actions">
      <input
        ref="folderInputRef"
        type="file"
        webkitdirectory
        directory
        multiple
        class="hidden-folder-input"
        @change="onFolderInputChange"
      />
      <el-button type="primary" link :loading="uploading" @click="triggerFolderPick">上传新文件夹</el-button>
      <el-button type="info" link @click="loadFolders">刷新列表</el-button>
    </div>
    <p class="folder-hint">请选择浏览器「上传文件夹」；执行时 Runner 会按原目录结构下载到本地再交给 Playwright。</p>
    <el-collapse v-if="showLegacy">
      <el-collapse-item title="高级：Runner 本地文件夹路径（兼容模式）" name="legacy">
        <div class="param-input-row">
          <el-input
            v-model="legacyPath"
            placeholder="如 ${{files_path}}/import_data"
            style="flex: 1"
            @input="emitLegacy"
          />
          <VarInsertButton v-if="envId" :env-id="envId" label="变量" />
        </div>
        <p class="legacy-hint">本地路径须指向 Runner 本机上的文件夹目录；多 Runner 场景请优先使用上方平台文件夹。</p>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { uiTestFolderApi } from '@/api/modules/uiTestFolder'
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
const folderList = ref([])
const selectedId = ref(null)
const legacyPath = ref('')
const folderInputRef = ref(null)

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
  if (p.folder_key) {
    const match = folderList.value.find((f) => f.folder_key === p.folder_key)
    selectedId.value = match?.id ?? null
  } else {
    selectedId.value = null
  }
}

async function loadFolders() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await uiTestFolderApi.getList({ project_id: projectId, page: 1, size: 200 })
    folderList.value = res.data?.data?.items || []
    syncFromModel()
  } finally {
    loading.value = false
  }
}

function onSelectChange(id) {
  if (!id) {
    emitParams({
      folder_key: '',
      folder_bucket: '',
      folder_name: '',
      upload_mode: 'folder',
      file_key: '',
      file_bucket: '',
      file_name: '',
      file_path: '',
    })
    return
  }
  const row = folderList.value.find((f) => f.id === id)
  if (!row) return
  emitParams({
    upload_mode: 'folder',
    folder_key: row.folder_key,
    folder_bucket: row.file_bucket,
    folder_name: row.folder_name,
    file_key: '',
    file_bucket: '',
    file_name: '',
    file_path: '',
  })
}

function emitLegacy() {
  emitParams({
    upload_mode: 'folder',
    file_path: legacyPath.value,
    folder_key: '',
    folder_bucket: '',
    folder_name: '',
    file_key: '',
    file_bucket: '',
    file_name: '',
  })
  selectedId.value = null
}

function triggerFolderPick() {
  folderInputRef.value?.click()
}

async function onFolderInputChange(event) {
  const projectId = proStore.projectInfo?.id
  const fileList = Array.from(event.target.files || [])
  event.target.value = ''
  if (!projectId || !fileList.length) return

  const rootName = (fileList[0].webkitRelativePath || fileList[0].name || '').split('/')[0]
  uploading.value = true
  try {
    const res = await uiTestFolderApi.upload(projectId, fileList, rootName)
    const data = res.data?.data
    if (res.data?.code !== 200 || !data) {
      ElMessage.error(res.data?.message || '上传失败')
      return
    }
    ElMessage.success(`文件夹上传成功（${data.file_count} 个文件）`)
    await loadFolders()
    selectedId.value = data.id
    emitParams({
      upload_mode: 'folder',
      folder_key: data.folder_key,
      folder_bucket: data.file_bucket,
      folder_name: data.folder_name,
      file_key: '',
      file_bucket: '',
      file_name: '',
      file_path: '',
    })
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

watch(() => props.modelValue, syncFromModel, { deep: true })
onMounted(loadFolders)
</script>

<style scoped lang="scss">
.ui-test-folder-picker {
  width: 100%;
}
.picker-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.hidden-folder-input {
  display: none;
}
.folder-hint,
.legacy-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.param-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
</style>
