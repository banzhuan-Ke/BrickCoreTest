<template>
  <div class="header-editor-panel">
    <div class="section-head">
      <span class="section-title">{{ localTitle }}</span>
      <div class="section-actions">
        <el-select
          v-model="selectedTemplateId"
          placeholder="选择 Header 模板"
          size="small"
          clearable
          filterable
          class="template-select"
          :loading="templatesLoading"
          @visible-change="onTemplateDropdown"
        >
          <el-option
            v-for="item in templateOptions"
            :key="item.id"
            :label="item.is_default ? `${item.name}（默认）` : item.name"
            :value="item.id"
          />
        </el-select>
        <el-button
          type="info"
          link
          size="small"
          icon="Download"
          :disabled="!selectedTemplateId"
          :loading="importLoading"
          @click="importFromTemplate"
        >
          从模板导入
        </el-button>
        <el-button type="primary" link size="small" icon="Plus" @click="addLocalHeader">添加</el-button>
        <el-button type="primary" link size="small" @click="goManageTemplates">管理模板</el-button>
        <slot name="toolbar-extra" />
      </div>
    </div>

    <el-table :data="localHeaders" size="small" border class="header-table">
      <el-table-column label="Header 名" width="200">
        <template #default="{ $index }">
          <el-input v-model="localHeaders[$index].key" size="small" placeholder="Content-Type" @blur="emitLocalHeaders" />
        </template>
      </el-table-column>
      <el-table-column label="Header 值">
        <template #default="{ $index }">
          <el-input
            v-model="localHeaders[$index].value"
            size="small"
            placeholder="application/json 或 ${{token}}"
            @blur="emitLocalHeaders"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="showDescription" label="描述" width="150">
        <template #default="{ $index }">
          <el-input v-model="localHeaders[$index].description" size="small" placeholder="描述" @blur="emitLocalHeaders" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" icon="Delete" @click="removeLocalHeader($index)" />
        </template>
      </el-table-column>
    </el-table>

    <p class="panel-hint">
      执行/调试时仅使用上方本地 Header；值中的 <code v-pre>${{变量名}}</code> 会按所选环境替换。
      「从模板导入」只追加本地不存在的 key，不会覆盖已有项。
    </p>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpHeaderTemplatesApi } from '@/api/modules/httpHeaderTemplates.js'
import { importTemplateHeadersToLocal, normalizeTemplateHeaderList } from '@/utils/headerTemplates.js'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [],
  },
  localTitle: {
    type: String,
    default: '本接口 Header',
  },
  showDescription: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['update:modelValue'])

const router = useRouter()
const proStore = ProjectStore()
const localHeaders = ref([])
const syncingLocal = ref(false)
const templateOptions = ref([])
const selectedTemplateId = ref(null)
const templatesLoading = ref(false)
const importLoading = ref(false)
const templatesLoaded = ref(false)

function syncLocalFromProps(val) {
  syncingLocal.value = true
  localHeaders.value = normalizeTemplateHeaderList(val, { keepEmpty: true })
  syncingLocal.value = false
}

watch(
  () => props.modelValue,
  (val) => syncLocalFromProps(val),
  { immediate: true, deep: true }
)

function emitLocalHeaders() {
  if (syncingLocal.value) return
  emit('update:modelValue', localHeaders.value.map((h) => ({ ...h })))
}

const addLocalHeader = () => {
  localHeaders.value.push({ key: '', value: '', description: '' })
}

const removeLocalHeader = (index) => {
  localHeaders.value.splice(index, 1)
  emitLocalHeaders()
}

const loadTemplateOptions = async () => {
  const projectId = proStore.projectInfo?.id
  if (!projectId || templatesLoaded.value) return
  templatesLoading.value = true
  try {
    const res = await httpHeaderTemplatesApi.getOptions(projectId)
    if (res.data?.code === 200) {
      templateOptions.value = res.data.data?.list || []
      templatesLoaded.value = true
      const defaultItem = templateOptions.value.find((item) => item.is_default)
      if (defaultItem && !selectedTemplateId.value) {
        selectedTemplateId.value = defaultItem.id
      }
    }
  } catch {
    ElMessage.error('加载 Header 模板失败')
  } finally {
    templatesLoading.value = false
  }
}

const onTemplateDropdown = (visible) => {
  if (visible) loadTemplateOptions()
}

const importFromTemplate = async () => {
  const projectId = proStore.projectInfo?.id
  if (!projectId || !selectedTemplateId.value) return
  importLoading.value = true
  try {
    const res = await httpHeaderTemplatesApi.getDetail(selectedTemplateId.value, projectId)
    const headers = res.data?.data?.headers || []
    const { headers: merged, imported, skipped } = importTemplateHeadersToLocal(localHeaders.value, headers)
    localHeaders.value = merged
    emitLocalHeaders()
    if (imported.length) {
      ElMessage.success(`已导入 ${imported.length} 个 Header${skipped.length ? `，跳过 ${skipped.length} 个已存在项` : ''}`)
    } else {
      ElMessage.info('没有可导入的新 Header（本地已存在同名 key）')
    }
  } catch {
    ElMessage.error('从模板导入失败')
  } finally {
    importLoading.value = false
  }
}

const goManageTemplates = () => {
  router.push('/api-header-templates')
}

watch(
  () => proStore.projectInfo?.id,
  () => {
    templatesLoaded.value = false
    templateOptions.value = []
    selectedTemplateId.value = null
  }
)
</script>

<style scoped lang="scss">
.header-editor-panel {
  width: 100%;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 10px;
}

.section-title {
  font-weight: 600;
  font-size: 13px;
  flex-shrink: 0;
  line-height: 1.4;
}

.section-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.template-select {
  width: 180px;
}

.panel-hint {
  margin: 10px 0 0;
  padding: 0 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.header-table {
  width: 100%;

  :deep(.el-table__cell) {
    padding: 8px 10px;
  }

  :deep(.el-table .cell) {
    padding: 0 4px;
    line-height: 1.4;
  }
}
</style>
