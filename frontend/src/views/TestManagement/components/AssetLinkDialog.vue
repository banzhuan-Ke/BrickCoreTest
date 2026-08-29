<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="720px"
    destroy-on-close
    @close="emit('update:modelValue', false)"
  >
    <div class="toolbar" v-if="canEdit">
      <template v-if="functionalCaseId">
        <el-select v-model="form.asset_type" style="width: 130px" @change="onAssetTypeChange">
          <el-option label="UI 用例" value="ui_case" />
          <el-option label="App 用例" value="app_case" />
          <el-option label="接口用例" value="api_case" />
          <el-option label="压测场景" value="perf_scene" />
        </el-select>
        <el-select
          v-model="form.asset_id"
          filterable
          remote
          clearable
          reserve-keyword
          :remote-method="searchAssets"
          :loading="assetSearching"
          placeholder="输入名称搜索用例 / 场景"
          style="width: 320px"
          @visible-change="(v) => v && searchAssets('')"
        >
          <el-option
            v-for="opt in assetOptions"
            :key="`${opt.id}`"
            :label="opt.label"
            :value="opt.id"
          />
        </el-select>
      </template>
      <template v-else>
        <span class="hint">功能用例 ID</span>
        <el-input-number v-model="form.functional_case_id" :min="1" controls-position="right" />
      </template>
      <el-select v-model="form.link_type" style="width: 120px">
        <el-option label="主覆盖" value="primary" />
        <el-option label="部分" value="partial" />
        <el-option label="回归" value="regression" />
      </el-select>
      <el-button type="primary" :loading="saving" @click="addLink">添加</el-button>
    </div>
    <el-table v-loading="loading" :data="links" border stripe>
      <el-table-column prop="asset_type" label="类型" width="110">
        <template #default="{ row }">{{ typeLabel(row.asset_type) }}</template>
      </el-table-column>
      <el-table-column prop="asset_id" label="资产ID" width="90" />
      <el-table-column prop="asset_name" label="名称" min-width="160" show-overflow-tooltip />
      <el-table-column prop="link_type" label="用途" width="90">
        <template #default="{ row }">{{ linkLabel(row.link_type) }}</template>
      </el-table-column>
      <el-table-column label="跳转" width="80">
        <template #default="{ row }">
          <el-button link type="primary" @click="goAsset(row)">打开</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" v-if="canEdit">
        <template #default="{ row }">
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { testAssetLinkApi } from '@/api/testManagement'
import { uiCaseApi } from '@/api/modules/ui'
import { appCaseApi } from '@/api/modules/app'
import { httpCaseApi } from '@/api/modules/http'
import { perfSceneApi } from '@/api/modules/perf'
import { UserStore } from '@/stores/module/UserStore'

const props = defineProps({
  modelValue: Boolean,
  projectId: { type: Number, required: true },
  functionalCaseId: { type: Number, default: null },
  caseTitle: { type: String, default: '' },
  /** 从自动化侧反查时使用 */
  assetType: { type: String, default: '' },
  assetId: { type: Number, default: null }
})
const emit = defineEmits(['update:modelValue', 'changed'])

const router = useRouter()
const uStore = UserStore()
const canEdit = computed(() => uStore.hasPermission('test_release:edit'))

const loading = ref(false)
const saving = ref(false)
const assetSearching = ref(false)
const links = ref([])
const assetOptions = ref([])
const form = reactive({
  asset_type: 'ui_case',
  asset_id: null,
  link_type: 'primary',
  functional_case_id: null
})

const dialogTitle = computed(() => {
  if (props.functionalCaseId) {
    return `关联自动化 — ${props.caseTitle || '#' + props.functionalCaseId}`
  }
  return `关联功能用例 — ${typeLabel(props.assetType)} #${props.assetId}`
})

const typeLabel = (t) =>
  ({ ui_case: 'UI', app_case: 'App', api_case: '接口', perf_scene: '压测' }[t] || t)
const linkLabel = (t) => ({ primary: '主覆盖', partial: '部分', regression: '回归' }[t] || t)

const normalizeList = (res) => {
  const data = res?.data?.data
  if (Array.isArray(data)) return data
  if (Array.isArray(data?.items)) return data.items
  if (Array.isArray(data?.list)) return data.list
  if (Array.isArray(res?.data?.list)) return res.data.list
  return []
}

const searchAssets = async (keyword = '') => {
  if (!props.functionalCaseId || !props.projectId) return
  assetSearching.value = true
  try {
    const kw = String(keyword || '').trim()
    let rows = []
    if (form.asset_type === 'ui_case') {
      const res = await uiCaseApi.getList({
        project_id: props.projectId,
        page: 1,
        size: 30,
        name: kw || undefined
      })
      rows = normalizeList(res).map((r) => ({
        id: Number(r.id),
        label: `${r.name || '未命名'}（#${r.id}）`
      }))
    } else if (form.asset_type === 'app_case') {
      const res = await appCaseApi.list({
        project_id: props.projectId,
        page: 1,
        size: 30,
        name: kw || undefined
      })
      rows = normalizeList(res).map((r) => ({
        id: Number(r.id),
        label: `${r.name || '未命名'}（#${r.id}）`
      }))
    } else if (form.asset_type === 'api_case') {
      const res = await httpCaseApi.getList({
        project_id: props.projectId,
        page: 1,
        size: 30,
        keyword: kw || undefined
      })
      rows = normalizeList(res).map((r) => ({
        id: Number(r.id),
        label: `${r.name || '未命名'}（#${r.id}）`
      }))
    } else if (form.asset_type === 'perf_scene') {
      const res = await perfSceneApi.getList({
        project_id: props.projectId,
        page: 1,
        size: 30,
        keyword: kw || undefined
      })
      rows = normalizeList(res).map((r) => ({
        id: Number(r.id),
        label: `${r.name || '未命名'}（#${r.id}）`
      }))
    }
    assetOptions.value = rows.filter((r) => Number.isFinite(r.id) && r.id > 0)
  } catch {
    assetOptions.value = []
  } finally {
    assetSearching.value = false
  }
}

const onAssetTypeChange = () => {
  form.asset_id = null
  assetOptions.value = []
  searchAssets('')
}

const load = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    const params = { project_id: props.projectId }
    if (props.functionalCaseId) params.functional_case_id = props.functionalCaseId
    if (props.assetType && props.assetId) {
      params.asset_type = props.assetType
      params.asset_id = props.assetId
    }
    const res = await testAssetLinkApi.list(params)
    links.value = res.data?.data || []
  } finally {
    loading.value = false
  }
}

const addLink = async () => {
  const fcId = props.functionalCaseId || form.functional_case_id
  const aType = props.functionalCaseId ? form.asset_type : props.assetType
  const aId = props.functionalCaseId ? form.asset_id : props.assetId
  if (!fcId) {
    ElMessage.warning('请填写功能用例 ID')
    return
  }
  if (!aType || !aId) {
    ElMessage.warning('请选择要关联的自动化用例 / 场景')
    return
  }
  saving.value = true
  try {
    await testAssetLinkApi.create({
      project_id: props.projectId,
      functional_case_id: fcId,
      asset_type: aType,
      asset_id: aId,
      link_type: form.link_type
    })
    ElMessage.success('已添加')
    emit('changed')
    form.asset_id = null
    await load()
  } finally {
    saving.value = false
  }
}

const remove = async (row) => {
  await ElMessageBox.confirm('删除该映射？', '确认')
  await testAssetLinkApi.remove(row.id, props.projectId)
  ElMessage.success('已删除')
  emit('changed')
  await load()
}

const goAsset = (row) => {
  const map = {
    ui_case: `/case/edit/${row.asset_id}`,
    app_case: `/app-case/edit/${row.asset_id}`,
    api_case: `/api-case?edit_case_id=${row.asset_id}`,
    perf_scene: `/perf-scene/edit/${row.asset_id}`
  }
  const path = map[row.asset_type]
  if (path) router.push(path)
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      if (props.assetType) form.asset_type = props.assetType
      form.asset_id = null
      assetOptions.value = []
      load()
      if (props.functionalCaseId) searchAssets('')
    }
  }
)
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  align-items: center;
}
.hint {
  color: #909399;
  font-size: 13px;
}
</style>
