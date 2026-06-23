<template>
  <div class="ui-test-multi-file-picker">
    <el-select
      v-model="selectedIds"
      multiple
      filterable
      collapse-tags
      collapse-tags-tooltip
      placeholder="选择多个测试文件（适用于 input[multiple]）"
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
      <el-button type="info" link @click="loadFiles">刷新列表</el-button>
    </div>

    <el-table v-if="fileItems.length" :data="fileItems" size="small" border class="items-table">
      <el-table-column prop="file_name" label="平台文件" min-width="160" show-overflow-tooltip />
      <el-table-column label="上传显示名（可选，支持变量）" min-width="240">
        <template #default="{ row, $index }">
          <div class="param-input-row">
            <el-input
              v-model="row.upload_as_name"
              placeholder="留空则用原文件名，如 ${{orderNo}}_报告.docx"
              @input="emitItems"
            />
            <VarInsertButton v-if="envId" :env-id="envId" label="变量" />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="70" align="center">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="removeItem(row.file_key)">移除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <p class="picker-hint">执行时 Runner 会按「上传显示名」重命名后再交给浏览器；留空则使用平台原文件名。</p>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, computed } from 'vue'
import { uiTestFileApi } from '@/api/modules/uiTestFile'
import { ProjectStore } from '@/stores/module/ProjectStore'
import VarInsertButton from '@/components/VarInsertButton.vue'

const props = defineProps({
  modelValue: { type: Object, default: () => ({}) },
  envId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:modelValue'])

const proStore = ProjectStore()
const loading = ref(false)
const fileList = ref([])
const selectedIds = ref([])

const fileItems = computed(() => props.modelValue?.file_items || [])

function formatSize(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function emitParams(patch) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function emitItems() {
  emitParams({ file_items: [...(props.modelValue?.file_items || [])] })
}

function syncFromModel() {
  const items = props.modelValue?.file_items || []
  if (items.length) {
    selectedIds.value = items
      .map((it) => fileList.value.find((f) => f.file_key === it.file_key)?.id)
      .filter(Boolean)
    return
  }
  selectedIds.value = []
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

function onSelectChange(ids) {
  const prev = props.modelValue?.file_items || []
  const nameMap = Object.fromEntries(prev.map((it) => [it.file_key, it.upload_as_name || '']))
  const items = (ids || [])
    .map((id) => fileList.value.find((f) => f.id === id))
    .filter(Boolean)
    .map((row) => ({
      file_key: row.file_key,
      file_bucket: row.file_bucket,
      file_name: row.file_name,
      upload_as_name: nameMap[row.file_key] || '',
    }))
  emitParams({
    upload_mode: 'multiple',
    file_items: items,
    file_key: '',
    file_bucket: '',
    file_name: '',
    file_path: '',
    folder_key: '',
    folder_bucket: '',
    folder_name: '',
  })
}

function removeItem(fileKey) {
  selectedIds.value = selectedIds.value.filter((id) => {
    const row = fileList.value.find((f) => f.id === id)
    return row?.file_key !== fileKey
  })
  onSelectChange(selectedIds.value)
}

watch(() => props.modelValue?.file_items, syncFromModel, { deep: true })
onMounted(loadFiles)
</script>

<style scoped lang="scss">
.ui-test-multi-file-picker {
  width: 100%;
}
.picker-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}
.items-table {
  margin-top: 12px;
}
.picker-hint {
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
