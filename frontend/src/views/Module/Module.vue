<template>
  <PageCard>
    <template #title>
      <span class="page-title">测试目录</span>
    </template>
    <template #main>
      <div class="catalog-stats">
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.catalogCount }}</div>
          <div class="stat-label">目录数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.apiCount }}</div>
          <div class="stat-label">接口数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.caseCount }}</div>
          <div class="stat-label">接口用例</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.uiCaseCount }}</div>
          <div class="stat-label">UI 用例</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.suiteCount }}</div>
          <div class="stat-label">套件数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.uiTaskCount }}</div>
          <div class="stat-label">UI 计划</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.apiPlanCount }}</div>
          <div class="stat-label">接口计划</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ summaryStats.perfSceneCount }}</div>
          <div class="stat-label">性能场景</div>
        </div>
      </div>
      <div class="catalog-page">
        <div class="catalog-sidebar">
          <CatalogTree
            ref="catalogTreeRef"
            :project-id="proStore.projectInfo.id"
            v-model="selectedCatalogId"
            :show-manage="true"
            :include-all-node="true"
            all-node-label="全部目录"
            @change="handleCatalogChange"
          />
        </div>
        <div class="catalog-table">
          <el-table
            :data="filteredCatalogRows"
            :header-cell-style="{'text-align':'center'}"
            :cell-style="{'text-align':'center'}"
            stripe
            v-loading="tableLoading"
          >
            <template #empty>
              <div class="table-empty">
                <div class="empty-icon">
                  <el-icon :size="40" color="#909399"><Grid /></el-icon>
                </div>
                <div>暂无数据</div>
              </div>
            </template>
            <el-table-column label="序号" type="index" width="70"/>
            <el-table-column prop="name" label="目录名称" min-width="140"/>
            <el-table-column prop="parent_name" label="上级目录" min-width="120">
              <template #default="{ row }">{{ row.parent_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="接口数" width="80">
              <template #default="{ row }">{{ row.api_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="用例数" width="80">
              <template #default="{ row }">{{ row.case_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="套件数" width="80">
              <template #default="{ row }">{{ row.suite_count ?? row.suites ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="UI用例" width="80">
              <template #default="{ row }">{{ row.ui_case_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="UI计划" width="80">
              <template #default="{ row }">{{ row.ui_task_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="接口计划" width="90">
              <template #default="{ row }">{{ row.api_plan_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="性能场景" width="90">
              <template #default="{ row }">{{ row.perf_scene_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column prop="username" label="创建人" width="100">
              <template #default="{ row }">{{ row.username || row.create_by || '—' }}</template>
            </el-table-column>
            <el-table-column prop="create_time" label="创建时间" min-width="160">
              <template #default="scope">
                {{ dateTools.rTime(scope.row.create_time) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button @click="openAssets(row)" plain type="success" icon="View" size="small">资产</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </template>
  </PageCard>

  <el-drawer v-model="showAssets" :with-header="false" size="85%">
    <div class="drawer-header">
      <div class="title">{{ currentCatalog?.name }} — 关联资产</div>
    </div>
    <div class="filter-bar">
      <el-radio-group v-model="assetGroupFilter" size="small" @change="filterAssets">
        <el-radio-button label="all">全部 ({{ assetList.length }})</el-radio-button>
        <el-radio-button label="web">Web ({{ assetCountByGroup.web }})</el-radio-button>
        <el-radio-button label="api">接口 ({{ assetCountByGroup.api }})</el-radio-button>
        <el-radio-button label="perf">性能 ({{ assetCountByGroup.perf }})</el-radio-button>
      </el-radio-group>
    </div>
    <el-table
      :data="filteredAssetList"
      style="width: calc(100% - 40px)"
      :header-cell-style="{'text-align':'center'}"
      :cell-style="{'text-align':'center'}"
      stripe
      v-loading="assetsLoading"
    >
      <template #empty>
        <el-empty description="暂无资产" />
      </template>
      <el-table-column label="序号" type="index" width="70"/>
      <el-table-column prop="name" label="资产名称" min-width="180"/>
      <el-table-column label="资产类型" width="120">
        <template #default="{ row }">
          <el-tag :type="row.typeTag" size="small">{{ row.typeLabel }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="创建人" width="110"/>
      <el-table-column prop="create_time" label="创建时间" min-width="160">
        <template #default="scope">
          {{ dateTools.rTime(scope.row.create_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="scope">
          <el-button @click="handleEditAsset(scope.row)" size="small" icon="Edit" plain type="primary">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Grid } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import dateTools from '@/tools/dateTools'
import PageCard from '@/components/PageCard.vue'
import CatalogTree from '@/components/CatalogTree.vue'
import { collectCatalogSubtreeIds } from '@/api/modules/catalog'

const ASSET_TYPE_META = {
  ui_case: { label: 'UI 用例', tag: 'success', group: 'web' },
  ui_suite: { label: 'UI 套件', tag: 'success', group: 'web' },
  ui_task: { label: 'UI 计划', tag: 'success', group: 'web' },
  api_def: { label: '接口', tag: 'primary', group: 'api' },
  api_case: { label: '接口用例', tag: 'primary', group: 'api' },
  api_suite: { label: '接口套件', tag: 'primary', group: 'api' },
  api_plan: { label: '接口计划', tag: 'primary', group: 'api' },
  perf_scene: { label: '性能场景', tag: 'warning', group: 'perf' },
}

const router = useRouter()
const proStore = ProjectStore()
const catalogTreeRef = ref()
const selectedCatalogId = ref(null)
const catalogRows = ref([])
const tableLoading = ref(false)

const loadCatalogTable = async () => {
  if (!proStore.projectInfo?.id) return
  tableLoading.value = true
  try {
    const response = await http.catalogApi.getList({
      project_id: proStore.projectInfo.id,
      include_counts: true,
    })
    if (response.status === 200) {
      catalogRows.value = Array.isArray(response.data) ? response.data : []
      await proStore.getCatalogList()
    }
  } finally {
    tableLoading.value = false
  }
}

watch(
  () => proStore.projectInfo.id,
  () => loadCatalogTable(),
  { immediate: true }
)

const filteredCatalogRows = computed(() => {
  if (!selectedCatalogId.value) return catalogRows.value
  const ids = collectCatalogSubtreeIds(catalogRows.value, selectedCatalogId.value)
  return catalogRows.value.filter(row => ids.has(row.id))
})

const summaryStats = computed(() => {
  const rows = filteredCatalogRows.value
  return {
    catalogCount: rows.length,
    apiCount: rows.reduce((sum, row) => sum + (row.api_count ?? 0), 0),
    caseCount: rows.reduce((sum, row) => sum + (row.case_count ?? 0), 0),
    uiCaseCount: rows.reduce((sum, row) => sum + (row.ui_case_count ?? 0), 0),
    suiteCount: rows.reduce((sum, row) => sum + (row.suite_count ?? row.suites ?? 0), 0),
    uiTaskCount: rows.reduce((sum, row) => sum + (row.ui_task_count ?? 0), 0),
    apiPlanCount: rows.reduce((sum, row) => sum + (row.api_plan_count ?? 0), 0),
    perfSceneCount: rows.reduce((sum, row) => sum + (row.perf_scene_count ?? 0), 0),
  }
})

const handleCatalogChange = () => {
  // 筛选由 filteredCatalogRows 计算完成，无需重复拉取列表
}

const showAssets = ref(false)
const assetList = ref([])
const filteredAssetList = ref([])
const currentCatalog = ref(null)
const assetGroupFilter = ref('all')
const assetsLoading = ref(false)

const assetCountByGroup = computed(() => ({
  web: assetList.value.filter(a => a.group === 'web').length,
  api: assetList.value.filter(a => a.group === 'api').length,
  perf: assetList.value.filter(a => a.group === 'perf').length,
}))

const mapAsset = (item) => {
  const meta = ASSET_TYPE_META[item.asset_type] || { label: '未知', tag: 'info', group: 'web' }
  return {
    id: item.id,
    name: item.name,
    assetType: item.asset_type,
    typeLabel: meta.label,
    typeTag: meta.tag,
    group: meta.group,
    username: item.username || item.create_by || '—',
    create_time: item.create_time,
    api_id: item.api_id,
  }
}

const filterAssets = () => {
  if (assetGroupFilter.value === 'all') {
    filteredAssetList.value = assetList.value
  } else {
    filteredAssetList.value = assetList.value.filter(
      asset => asset.group === assetGroupFilter.value
    )
  }
}

const openAssets = async (catalog) => {
  currentCatalog.value = catalog
  showAssets.value = true
  assetsLoading.value = true
  assetGroupFilter.value = 'all'
  assetList.value = []

  try {
    const response = await http.catalogApi.getAssets(catalog.id, {
      project_id: proStore.projectInfo.id,
      include_children: false,
    })
    if (response.status === 200) {
      assetList.value = (response.data?.items || []).map(mapAsset)
    }
    filterAssets()
  } finally {
    assetsLoading.value = false
  }
}

const handleEditAsset = (asset) => {
  const id = String(asset.id)
  switch (asset.assetType) {
    case 'ui_case':
      router.push({ name: 'editCase', params: { id } })
      break
    case 'ui_suite':
      router.push({ name: 'editSuite', params: { id } })
      break
    case 'ui_task':
      router.push({ name: 'editTask', params: { id } })
      break
    case 'api_def':
      router.push({ name: 'apiModule', query: { api_id: id } })
      break
    case 'api_case':
      router.push({
        name: 'apiCase',
        query: { api_id: String(asset.api_id || ''), edit_case_id: id },
      })
      break
    case 'api_suite':
      router.push({ name: 'apiSuiteDetail', params: { suiteId: id } })
      break
    case 'api_plan':
      router.push({ name: 'apiPlanEdit', params: { planId: id } })
      break
    case 'perf_scene':
      router.push(`/perf-scene/edit/${id}`)
      break
  }
}
</script>

<style scoped lang="scss">
.page-title {
  font-size: 16px;
  font-weight: 600;
}

.catalog-stats {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.stat-card {
  flex: 1;
  min-width: 100px;
  padding: 12px 16px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
  text-align: center;

  .stat-value {
    font-size: 22px;
    font-weight: 600;
    color: var(--el-color-primary);
    line-height: 1.2;
  }

  .stat-label {
    margin-top: 4px;
    font-size: 13px;
    color: var(--el-text-color-secondary);
  }
}

.catalog-page {
  display: flex;
  gap: 20px;
  min-height: calc(100vh - 260px);
}

.catalog-sidebar {
  width: 280px;
  min-width: 280px;
}

.catalog-table {
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.drawer-header {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;

  .title {
    font-size: 18px;
    font-weight: bold;
  }
}

.filter-bar {
  display: flex;
  justify-content: center;
  margin-bottom: 15px;
}
</style>
