<template>
  <el-dialog
    v-model="visible"
    title="🤖 批量 AI 生成用例"
    width="960px"
    destroy-on-close
    :close-on-click-modal="false"
    class="batch-ai-dialog"
  >
    <div v-if="!running && !finished" class="batch-form">
      <el-alert type="info" :closable="false" show-icon class="batch-hint">
        已选择 {{ apis.length }} 个接口，将依次为每个接口生成用例。已有用例会作为参考，避免重复场景。
      </el-alert>

      <el-form :model="form" label-width="100px">
        <el-form-item label="每接口数量">
          <el-slider v-model="form.count" :min="1" :max="5" show-stops style="width: 280px;" />
          <span class="count-label">{{ form.count }} 条</span>
        </el-form-item>
        <el-form-item label="补充要求">
          <el-input
            v-model="form.prompt_override"
            type="textarea"
            :rows="3"
            placeholder="对所有接口生效的补充说明，例如：补充边界值与异常场景"
          />
        </el-form-item>
        <el-form-item label="所属目录">
          <el-tree-select
            v-model="form.catalog_id"
            :data="catalogTree"
            :props="{ label: 'name', value: 'id', children: 'children' }"
            placeholder="选择目录（可选）"
            clearable
            style="width: 280px;"
          />
        </el-form-item>
        <el-form-item label="AI 模型">
          <el-select
            v-model="aiConfigId"
            placeholder="默认模型"
            clearable
            style="width: 100%; max-width: 400px;"
            :loading="loadingConfigs"
          >
            <el-option
              v-for="c in enabledConfigs"
              :key="c.id"
              :label="`${c.name} (${c.model})`"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="apis" size="small" border max-height="280">
        <el-table-column type="index" width="50" />
        <el-table-column label="方法" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="getMethodType(row.method)">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="接口名称" prop="name" min-width="160" show-overflow-tooltip />
        <el-table-column label="路径" prop="path" min-width="180" show-overflow-tooltip />
        <el-table-column label="已有用例" width="90" align="center">
          <template #default="{ row }">{{ row.case_count ?? 0 }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="running || finished" class="batch-progress">
      <div class="progress-header">
        <span>进度：{{ completedCount }} / {{ apis.length }}</span>
        <el-progress
          :percentage="progressPercent"
          :status="running ? undefined : (failedCount ? 'warning' : 'success')"
          style="flex: 1; margin-left: 16px;"
        />
      </div>

      <el-table :data="taskRows" size="small" border max-height="420">
        <el-table-column label="接口" min-width="200">
          <template #default="{ row }">
            <div class="api-cell">
              <el-tag size="small" :type="getMethodType(row.api.method)">{{ row.api.method }}</el-tag>
              <span>{{ row.api.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'pending'" type="info" size="small">等待</el-tag>
            <el-tag v-else-if="row.status === 'running'" type="primary" size="small">
              <el-icon class="is-loading"><Loading /></el-icon> 生成中
            </el-tag>
            <el-tag v-else-if="row.status === 'success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.status === 'imported'" type="success" size="small">已导入</el-tag>
            <el-tag v-else type="danger" size="small">失败</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="120" align="center">
          <template #default="{ row }">
            <span v-if="row.generatedCount">{{ row.generatedCount }} 条</span>
            <span v-else-if="row.error" class="error-text">{{ row.error }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'success' && row.cases?.length"
              type="primary"
              link
              size="small"
              :loading="row.importing"
              @click="importOne(row)"
            >
              导入
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <template v-if="!running && !finished">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="startBatch" icon="MagicStick">开始批量生成</el-button>
      </template>
      <template v-else-if="running">
        <el-button disabled>生成中…</el-button>
      </template>
      <template v-else>
        <el-button @click="visible = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="successCount === 0"
          :loading="importingAll"
          @click="importAll"
          icon="Download"
        >
          全部导入 ({{ successCount }})
        </el-button>
      </template>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { aiGenerateApi } from '@/api/modules/ai'
import { catalogApi, buildCatalogTree } from '@/api/modules/catalog'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const props = defineProps({
  modelValue: Boolean,
  apis: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'success'])

const proStore = ProjectStore()
const visible = ref(false)
const running = ref(false)
const finished = ref(false)
const importingAll = ref(false)
const catalogTree = ref([])
const taskRows = ref([])

const form = reactive({
  count: 2,
  prompt_override: '',
  catalog_id: null,
})

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val) {
    resetState()
    loadCatalogTree()
    await loadConfigs()
  }
})

watch(visible, (val) => emit('update:modelValue', val))

const completedCount = computed(() => taskRows.value.filter(r => r.status !== 'pending' && r.status !== 'running').length)
const progressPercent = computed(() => {
  if (!props.apis.length) return 0
  return Math.round((completedCount.value / props.apis.length) * 100)
})
const successCount = computed(() => taskRows.value.filter(r => r.status === 'success' && r.cases?.length).length)
const failedCount = computed(() => taskRows.value.filter(r => r.status === 'failed').length)

const resetState = () => {
  form.count = 2
  form.prompt_override = ''
  form.catalog_id = null
  running.value = false
  finished.value = false
  importingAll.value = false
  taskRows.value = (props.apis || []).map(api => ({
    api,
    status: 'pending',
    cases: [],
    generatedCount: 0,
    error: '',
    importing: false,
  }))
}

const loadCatalogTree = async () => {
  try {
    const res = await catalogApi.getList({ project_id: proStore.projectInfo.id, tree: true })
    if (res.status === 200) {
      const data = res.data
      catalogTree.value = Array.isArray(data) && data.some(item => item.children?.length)
        ? data
        : buildCatalogTree(data || [])
    }
  } catch {
    /* ignore */
  }
}

const getMethodType = (method) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info' }
  return map[method] || ''
}

const startBatch = async () => {
  if (!props.apis?.length) {
    ElMessage.warning('请先选择接口')
    return
  }
  running.value = true
  finished.value = false

  for (const row of taskRows.value) {
    row.status = 'running'
    row.error = ''
    try {
      const res = await aiGenerateApi.generateApiCase({
        api_definition_id: row.api.id,
        count: form.count,
        prompt_override: form.prompt_override || undefined,
        catalog_id: form.catalog_id || undefined,
        ai_config_id: aiConfigId.value || undefined,
      })
      if (res.status === 200 && res.data?.data?.cases?.length) {
        row.cases = res.data.data.cases
        row.generatedCount = row.cases.length
        row.status = 'success'
      } else {
        row.status = 'failed'
        row.error = res.data?.message || '无有效用例'
      }
    } catch (err) {
      row.status = 'failed'
      row.error = err.response?.data?.detail || '生成失败'
    }
  }

  running.value = false
  finished.value = true
  const ok = successCount.value
  if (ok > 0) {
    ElMessage.success(`批量生成完成：${ok} 个接口成功，${failedCount.value} 个失败`)
  } else {
    ElMessage.error('批量生成全部失败，请检查 AI 配置')
  }
}

const buildImportPayload = (cases) => cases.map(item => ({
  name: item.name,
  request_headers: item.request_headers || {},
  request_params: item.request_params || {},
  request_body: item.request_body_type === 'form-data' ? {} : (item.request_body || {}),
  request_body_type: item.request_body_type || 'json',
  request_body_fields: item.request_body_type === 'form-data'
    ? (item.request_body_fields || [])
    : [],
  assertions: item.assertions || [],
  extractors: item.extractors || [],
  priority: item.priority || 'P2',
  tags: item.tags || [],
}))

const importOne = async (row) => {
  if (!row.cases?.length) return
  row.importing = true
  try {
    const res = await aiGenerateApi.importApiCases({
      api_definition_id: row.api.id,
      cases: buildImportPayload(row.cases),
      catalog_id: form.catalog_id || undefined,
    })
    if (res.status === 200) {
      row.status = 'imported'
      ElMessage.success(`${row.api.name}：导入 ${res.data?.data?.imported_count || row.cases.length} 条`)
      emit('success')
    } else {
      ElMessage.error(res.data?.message || '导入失败')
    }
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '导入失败')
  } finally {
    row.importing = false
  }
}

const importAll = async () => {
  const rows = taskRows.value.filter(r => r.status === 'success' && r.cases?.length)
  if (!rows.length) return
  importingAll.value = true
  let total = 0
  try {
    for (const row of rows) {
      row.importing = true
      try {
        const res = await aiGenerateApi.importApiCases({
          api_definition_id: row.api.id,
          cases: buildImportPayload(row.cases),
          catalog_id: form.catalog_id || undefined,
        })
        if (res.status === 200) {
          row.status = 'imported'
          total += res.data?.data?.imported_count || row.cases.length
        }
      } catch {
        /* continue next */
      } finally {
        row.importing = false
      }
    }
    if (total > 0) {
      ElMessage.success(`共导入 ${total} 条用例`)
      emit('success')
    } else {
      ElMessage.error('导入失败')
    }
  } finally {
    importingAll.value = false
  }
}
</script>

<style scoped lang="scss">
.batch-ai-dialog {
  :deep(.el-dialog__body) {
    max-height: 72vh;
    overflow-y: auto;
  }
}
.batch-hint {
  margin-bottom: 16px;
}
.count-label {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
}
.progress-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
}
.api-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.error-text {
  color: var(--el-color-danger);
  font-size: 12px;
}
</style>
