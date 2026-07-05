<template>
  <el-dialog
    v-model="visible"
    title="🤖 功能用例 → App 自动化"
    width="920px"
    destroy-on-close
    :close-on-click-modal="false"
    @closed="handleClosed"
  >
    <el-alert type="info" :closable="false" show-icon style="margin-bottom: 12px;">
      <template #title>
        已选择 {{ caseIds.length }} 条功能用例，将<strong>逐条串行</strong>调用 AI 生成 App 步骤（单次最多 {{ maxBatch }} 条）
      </template>
    </el-alert>

    <el-form v-if="phase === 'config'" label-width="110px" class="to-app-form">
      <FunctionalCaseAppContext v-model="appContext" :project-id="projectId" />
      <el-form-item label="AI 模型" required>
        <el-select
          v-model="aiConfigId"
          placeholder="请选择已启用的模型"
          style="width: 100%;"
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
      <el-form-item label="已选用例">
        <ul class="case-title-list">
          <li v-for="c in selectedCases" :key="c.id">{{ c.title }}</li>
        </ul>
      </el-form-item>
    </el-form>

    <div v-else-if="phase === 'generating'" class="generating-box">
      <el-icon class="is-loading" :size="36"><Loading /></el-icon>
      <p>AI 正在生成 App 步骤，请稍候…</p>
      <p class="hint">批量按条串行执行，条数较多时可能需数分钟</p>
    </div>

    <div v-else-if="phase === 'preview'" class="preview-box">
      <div class="preview-summary">
        成功 {{ previewResult.success_count }} 条，失败 {{ previewResult.failed_count }} 条
        <span v-if="previewResult.total_tokens"> · Token {{ previewResult.total_tokens }}</span>
      </div>
      <el-table
        ref="previewTableRef"
        :data="previewItems"
        border
        stripe
        max-height="420"
        @selection-change="onPreviewSelect"
      >
        <el-table-column type="selection" width="45" :selectable="row => row.status === 'success'" />
        <el-table-column prop="title" label="功能用例" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="88" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="步骤数" width="80" align="center">
          <template #default="{ row }">{{ row.steps?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="160">
          <template #default="{ row }">
            <span v-if="row.error" class="err-text">{{ row.error }}</span>
            <span v-else-if="row.login_prefix_count">含登录前置 {{ row.login_prefix_count }} 步</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button v-if="phase === 'config'" type="primary" :loading="generating" @click="handlePreview">
        开始生成预览
      </el-button>
      <el-button
        v-else-if="phase === 'preview'"
        type="success"
        :loading="importing"
        @click="handleImport"
      >
        导入选中到 App 用例库
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { aiFunctionalCaseApi } from '@/api/modules/ai.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import FunctionalCaseAppContext from '@/views/AI/components/FunctionalCaseAppContext.vue'

const defaultAppContext = () => ({
  app_id: '',
  driver_mode: 'hybrid',
  test_username: '',
  test_password: '',
  login_app_case_id: null,
  login_strategy: 'none',
  extra_context: '',
})

const props = defineProps({
  modelValue: Boolean,
  caseIds: { type: Array, default: () => [] },
  cases: { type: Array, default: () => [] },
  projectId: { type: [Number, String], required: true },
})

const emit = defineEmits(['update:modelValue', 'done'])

const maxBatch = 10
const visible = ref(false)
const phase = ref('config')
const generating = ref(false)
const importing = ref(false)
const previewTableRef = ref(null)
const previewResult = reactive({ success_count: 0, failed_count: 0, total_tokens: 0 })
const importSelected = ref([])
const appContext = reactive(defaultAppContext())
const previewItems = ref([])

const { aiConfigId, enabledConfigs, loadingConfigs, loadConfigs } = useAiConfigSelect()

const selectedCases = computed(() =>
  props.cases.filter(c => props.caseIds.includes(c.id))
)

const buildPreviewPayload = () => ({
  case_ids: props.caseIds,
  ai_config_id: aiConfigId.value || undefined,
  app_id: appContext.app_id?.trim() || undefined,
  driver_mode: appContext.driver_mode || 'hybrid',
  test_username: appContext.test_username?.trim() || undefined,
  test_password: appContext.test_password || undefined,
  login_app_case_id: appContext.login_app_case_id || undefined,
  login_strategy: appContext.login_strategy || 'none',
  extra_context: appContext.extra_context?.trim() || undefined,
})

const buildImportPayload = (rows) => ({
  ...buildPreviewPayload(),
  items: rows.map(row => ({
    functional_case_id: row.functional_case_id,
    steps: row.steps,
    case_name: row.suggested_case_name,
    level: row.suggested_level,
    driver_mode: row.suggested_driver_mode || appContext.driver_mode,
    login_prefix_count: row.login_prefix_count || 0,
  })),
})

watch(() => props.modelValue, async (val) => {
  visible.value = val
  if (val) {
    phase.value = 'config'
    previewItems.value = []
    importSelected.value = []
    Object.assign(appContext, defaultAppContext())
    await loadConfigs()
  }
})

watch(visible, (val) => emit('update:modelValue', val))

const handlePreview = async () => {
  if (!enabledConfigs.value.length) {
    ElMessage.warning('没有已启用的 AI 模型，请先在 AI 模型配置中创建并启用')
    return
  }
  if (!aiConfigId.value) {
    ElMessage.warning('请选择 AI 模型')
    return
  }
  if (['prepend_login', 'both'].includes(appContext.login_strategy) && !appContext.login_app_case_id) {
    ElMessage.warning('请选择登录 App 用例')
    return
  }
  if (['credentials', 'both'].includes(appContext.login_strategy) && !appContext.test_username?.trim()) {
    ElMessage.warning('请填写测试账号用户名')
    return
  }
  if (!props.caseIds.length) {
    ElMessage.warning('请先勾选功能用例')
    return
  }
  if (props.caseIds.length > maxBatch) {
    ElMessage.warning(`单次最多 ${maxBatch} 条，请减少勾选数量`)
    return
  }

  generating.value = true
  phase.value = 'generating'
  try {
    const res = await aiFunctionalCaseApi.previewToApp(buildPreviewPayload(), props.projectId)
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      previewItems.value = (d.items || []).map(it => ({ ...it }))
      previewResult.success_count = d.success_count || 0
      previewResult.failed_count = d.failed_count || 0
      previewResult.total_tokens = d.total_tokens || 0
      phase.value = 'preview'
      const successRows = previewItems.value.filter(i => i.status === 'success')
      importSelected.value = successRows
      await nextTick()
      successRows.forEach(row => previewTableRef.value?.toggleRowSelection(row, true))
      ElMessage.success(res.data.message || '预览完成')
    }
  } catch (e) {
    phase.value = 'config'
    ElMessage.error(e.response?.data?.detail || '生成预览失败')
  } finally {
    generating.value = false
  }
}

const onPreviewSelect = (rows) => {
  importSelected.value = rows
}

const handleImport = async () => {
  const rows = importSelected.value.length
    ? importSelected.value
    : previewItems.value.filter(i => i.status === 'success')
  if (!rows.length) {
    ElMessage.warning('请勾选要导入的用例')
    return
  }
  importing.value = true
  try {
    const res = await aiFunctionalCaseApi.importApp(buildImportPayload(rows), props.projectId)
    if (res.data?.code === 200) {
      const d = res.data.data || {}
      ElMessage.success(res.data.message || `已导入 ${d.imported_count} 条`)
      visible.value = false
      emit('done', d)
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '导入失败')
  } finally {
    importing.value = false
  }
}

const handleClosed = () => {
  phase.value = 'config'
  previewItems.value = []
  importSelected.value = []
}
</script>

<style scoped lang="scss">
.to-app-form { max-height: 55vh; overflow-y: auto; }
.case-title-list {
  margin: 0;
  padding-left: 18px;
  max-height: 120px;
  overflow-y: auto;
  font-size: 13px;
}
.generating-box {
  text-align: center;
  padding: 48px 0;
  .hint { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 8px; }
}
.preview-summary { margin-bottom: 10px; font-size: 14px; }
.err-text { color: var(--el-color-danger); font-size: 12px; }
</style>
