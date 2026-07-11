<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span class="page-title">测试目录</span>
        <el-tag v-if="selectedCatalogName" type="info" size="small" effect="plain" class="filter-tag">
          当前：{{ selectedCatalogName }}（含子目录）
        </el-tag>
      </div>
    </template>
    <template #main>
      <div class="catalog-stats">
        <div
          v-for="card in statCards"
          :key="card.key"
          class="summary-card"
          :class="[`summary-card--${card.key}`, { 'is-active': highlightGroup === card.key }]"
          @click="handleStatCardClick(card.key)"
        >
          <div class="summary-card-icon" :style="{ color: card.color }">
            <el-icon :size="22"><component :is="card.icon" /></el-icon>
          </div>
          <div class="summary-card-body">
            <div class="summary-card-value">{{ card.value }}</div>
            <div class="summary-card-label">{{ card.label }}</div>
            <div v-if="card.sub" class="summary-card-sub">{{ card.sub }}</div>
          </div>
        </div>
      </div>

      <div class="catalog-page">
        <div class="catalog-sidebar">
          <CatalogTree
            :project-id="proStore.projectInfo.id"
            v-model="selectedCatalogId"
            :show-manage="true"
            :include-all-node="true"
            all-node-label="全部目录"
            :count-map="catalogCountMap"
            :show-search="true"
            fill-height
            @change="handleCatalogChange"
            @changed="loadCatalogTable"
          />
        </div>

        <el-card shadow="never" class="catalog-table-card">
          <div class="table-toolbar">
            <div class="toolbar-left">
              <el-input
                v-model="searchKeyword"
                placeholder="搜索目录名称 / 创建人"
                clearable
                prefix-icon="Search"
                class="toolbar-search"
              />
              <span class="toolbar-count">共 {{ displayCatalogRows.length }} 个目录</span>
            </div>
            <div class="toolbar-right">
              <el-radio-group v-model="tableDensity" size="small">
                <el-radio-button label="default">默认</el-radio-button>
                <el-radio-button label="compact">紧凑</el-radio-button>
              </el-radio-group>
              <el-popover placement="bottom-end" :width="200" trigger="click">
                <template #reference>
                  <el-button size="small" icon="Setting">列设置</el-button>
                </template>
                <div class="column-settings">
                  <el-checkbox
                    v-for="col in columnOptions"
                    :key="col.key"
                    v-model="visibleColumns[col.key]"
                    :disabled="col.required"
                  >
                    {{ col.label }}
                  </el-checkbox>
                </div>
              </el-popover>
              <el-button size="small" icon="Refresh" :loading="tableLoading" @click="loadCatalogTable">
                刷新
              </el-button>
            </div>
          </div>

          <el-table
            :data="displayCatalogRows"
            :size="tableSize"
            stripe
            v-loading="tableLoading"
            class="catalog-data-table"
            :header-cell-style="headerCellStyle"
            :header-cell-class-name="headerCellClassName"
            :row-key="row => row.id"
          >
            <template #empty>
              <el-empty description="暂无目录数据" :image-size="72" />
            </template>

            <el-table-column v-if="visibleColumns.expand" type="expand" width="48">
              <template #default="{ row }">
                <div class="expand-detail">
                  <div
                    v-for="section in expandSections(row)"
                    :key="section.key"
                    class="expand-section"
                    :class="`expand-section--${section.key}`"
                  >
                    <div class="expand-section-title">{{ section.title }}</div>
                    <div class="expand-metrics">
                      <div
                        v-for="metric in section.metrics"
                        :key="metric.key"
                        class="expand-metric"
                        :class="{ 'is-zero': !metric.value }"
                        @click="metric.value && openAssetsByGroup(row, metric.group)"
                      >
                        <span class="expand-metric-label">{{ metric.label }}</span>
                        <span class="expand-metric-value">{{ metric.value }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>

            <el-table-column label="序号" type="index" width="60" align="center" />

            <el-table-column prop="name" label="目录名称" min-width="160" align="left">
              <template #default="{ row }">
                <span class="name-cell">
                  <el-icon class="name-icon"><Folder /></el-icon>
                  <span class="name-text">{{ row.name }}</span>
                </span>
              </template>
            </el-table-column>

            <el-table-column
              v-if="visibleColumns.parent"
              prop="parent_name"
              label="上级目录"
              min-width="120"
              align="left"
              show-overflow-tooltip
            >
              <template #default="{ row }">{{ row.parent_name || '—' }}</template>
            </el-table-column>

            <el-table-column
              v-if="visibleColumns.total"
              label="资产合计"
              width="90"
              align="right"
              column-key="total"
            >
              <template #default="{ row }">
                <CountNum :value="rowAssetTotal(row)" @click="openAssets(row)" />
              </template>
            </el-table-column>

            <el-table-column label="接口" align="center" column-key="api-group">
              <el-table-column label="接口" width="68" align="right" column-key="api-api">
                <template #default="{ row }">
                  <CountNum :value="row.api_count" @click="openAssetsByGroup(row, 'api')" />
                </template>
              </el-table-column>
              <el-table-column label="用例" width="68" align="right" column-key="api-case">
                <template #default="{ row }">
                  <CountNum :value="row.case_count" @click="openAssetsByGroup(row, 'api')" />
                </template>
              </el-table-column>
              <el-table-column label="计划" width="68" align="right" column-key="api-plan">
                <template #default="{ row }">
                  <CountNum :value="row.api_plan_count" @click="openAssetsByGroup(row, 'api')" />
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column label="Web" align="center" column-key="web-group">
              <el-table-column label="用例" width="68" align="right" column-key="web-case">
                <template #default="{ row }">
                  <CountNum :value="row.web_case_count ?? row.ui_case_count" @click="openAssetsByGroup(row, 'web')" />
                </template>
              </el-table-column>
              <el-table-column label="套件" width="68" align="right" column-key="web-suite">
                <template #default="{ row }">
                  <CountNum :value="row.web_suite_count ?? row.ui_suites" @click="openAssetsByGroup(row, 'web')" />
                </template>
              </el-table-column>
              <el-table-column label="计划" width="68" align="right" column-key="web-plan">
                <template #default="{ row }">
                  <CountNum :value="row.web_task_count ?? row.ui_task_count" @click="openAssetsByGroup(row, 'web')" />
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column label="App" align="center" column-key="app-group">
              <el-table-column label="用例" width="68" align="right" column-key="app-case">
                <template #default="{ row }">
                  <CountNum :value="row.app_case_count" @click="openAssetsByGroup(row, 'app')" />
                </template>
              </el-table-column>
              <el-table-column label="套件" width="68" align="right" column-key="app-suite">
                <template #default="{ row }">
                  <CountNum :value="row.app_suite_count" @click="openAssetsByGroup(row, 'app')" />
                </template>
              </el-table-column>
              <el-table-column label="计划" width="68" align="right" column-key="app-plan">
                <template #default="{ row }">
                  <CountNum :value="row.app_plan_count" @click="openAssetsByGroup(row, 'app')" />
                </template>
              </el-table-column>
            </el-table-column>

            <el-table-column
              v-if="visibleColumns.perf"
              label="性能"
              width="72"
              align="right"
              column-key="perf"
            >
              <template #default="{ row }">
                <CountNum :value="row.perf_scene_count" @click="openAssetsByGroup(row, 'perf')" />
              </template>
            </el-table-column>

            <el-table-column
              v-if="visibleColumns.creator"
              prop="username"
              label="创建人"
              width="100"
              align="left"
            >
              <template #default="{ row }">{{ row.username || row.create_by || '—' }}</template>
            </el-table-column>

            <el-table-column
              v-if="visibleColumns.createTime"
              prop="create_time"
              label="创建时间"
              min-width="160"
              align="left"
            >
              <template #default="{ row }">{{ dateTools.rTime(row.create_time) }}</template>
            </el-table-column>

            <el-table-column label="操作" width="100" fixed="right" align="center">
              <template #default="{ row }">
                <el-button plain type="success" icon="View" size="small" @click="openAssets(row)">
                  资产
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </div>
    </template>
  </PageCard>

  <el-drawer v-model="showAssets" :with-header="false" size="85%">
    <div class="drawer-header">
      <div class="title">{{ currentCatalog?.name }} — 关联资产</div>
      <el-button circle icon="Close" @click="showAssets = false" />
    </div>
    <div class="filter-bar">
      <el-radio-group v-model="assetGroupFilter" size="small" @change="filterAssets">
        <el-radio-button label="all">全部 ({{ assetList.length }})</el-radio-button>
        <el-radio-button label="web">Web ({{ assetCountByGroup.web }})</el-radio-button>
        <el-radio-button label="app">App ({{ assetCountByGroup.app }})</el-radio-button>
        <el-radio-button label="api">接口 ({{ assetCountByGroup.api }})</el-radio-button>
        <el-radio-button label="perf">性能 ({{ assetCountByGroup.perf }})</el-radio-button>
      </el-radio-group>
    </div>
    <el-table
      :data="filteredAssetList"
      :size="tableSize"
      style="width: calc(100% - 40px)"
      stripe
      v-loading="assetsLoading"
    >
      <template #empty>
        <el-empty description="暂无资产" />
      </template>
      <el-table-column label="序号" type="index" width="70" align="center" />
      <el-table-column prop="name" label="资产名称" min-width="180" align="left" />
      <el-table-column label="资产类型" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="row.typeTag" size="small">{{ row.typeLabel }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="创建人" width="110" align="left" />
      <el-table-column prop="create_time" label="创建时间" min-width="160" align="left">
        <template #default="{ row }">{{ dateTools.rTime(row.create_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button size="small" icon="Edit" plain type="primary" @click="handleEditAsset(row)">
            编辑
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch, defineComponent, h } from 'vue'
import { Folder, Files, Monitor, Iphone, Grid } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import dateTools from '@/tools/dateTools'
import PageCard from '@/components/PageCard.vue'
import CatalogTree from '@/components/CatalogTree.vue'
import { collectCatalogSubtreeIds } from '@/api/modules/catalog'

const STORAGE_KEY_COLUMNS = 'brickcore.catalog-module.columns'
const STORAGE_KEY_DENSITY = 'brickcore.catalog-module.density'

const GROUP_HEADER_BG = {
  api: '#ecf5ff',
  web: '#f0f9eb',
  app: '#f4ecff',
  perf: '#fdf6ec',
}

const ASSET_TYPE_META = {
  ui_case: { label: 'Web 用例', tag: 'success', group: 'web' },
  ui_suite: { label: 'Web 套件', tag: 'success', group: 'web' },
  ui_task: { label: 'Web 计划', tag: 'success', group: 'web' },
  app_case: { label: 'App 用例', tag: '', group: 'app' },
  app_suite: { label: 'App 套件', tag: '', group: 'app' },
  app_plan: { label: 'App 计划', tag: '', group: 'app' },
  api_def: { label: '接口', tag: 'primary', group: 'api' },
  api_case: { label: '接口用例', tag: 'primary', group: 'api' },
  api_suite: { label: '接口套件', tag: 'primary', group: 'api' },
  api_plan: { label: '接口计划', tag: 'primary', group: 'api' },
  perf_scene: { label: '性能场景', tag: 'warning', group: 'perf' },
}

const CountNum = defineComponent({
  name: 'CountNum',
  props: {
    value: { type: [Number, String, null], default: 0 },
  },
  emits: ['click'],
  setup(props, { emit }) {
    return () => {
      const n = Number(props.value ?? 0)
      return h(
        'span',
        {
          class: ['count-num', { 'is-zero': !n, 'is-clickable': n > 0 }],
          onClick: () => n > 0 && emit('click'),
        },
        String(n)
      )
    }
  },
})

const defaultVisibleColumns = () => ({
  expand: true,
  parent: true,
  total: true,
  perf: true,
  creator: false,
  createTime: false,
})

const loadVisibleColumns = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_COLUMNS)
    if (!raw) return defaultVisibleColumns()
    return { ...defaultVisibleColumns(), ...JSON.parse(raw) }
  } catch {
    return defaultVisibleColumns()
  }
}

const loadDensity = () => {
  try {
    return localStorage.getItem(STORAGE_KEY_DENSITY) === 'compact' ? 'compact' : 'default'
  } catch {
    return 'default'
  }
}

const router = useRouter()
const proStore = ProjectStore()
const selectedCatalogId = ref(null)
const catalogRows = ref([])
const projectTotals = ref(null)
const tableLoading = ref(false)
const searchKeyword = ref('')
const highlightGroup = ref(null)
const visibleColumns = ref(loadVisibleColumns())
const tableDensity = ref(loadDensity())

const columnOptions = [
  { key: 'expand', label: '展开详情', required: false },
  { key: 'parent', label: '上级目录', required: false },
  { key: 'total', label: '资产合计', required: false },
  { key: 'perf', label: '性能场景', required: false },
  { key: 'creator', label: '创建人', required: false },
  { key: 'createTime', label: '创建时间', required: false },
]

watch(visibleColumns, (val) => {
  try {
    localStorage.setItem(STORAGE_KEY_COLUMNS, JSON.stringify(val))
  } catch { /* ignore */ }
}, { deep: true })

watch(tableDensity, (val) => {
  try {
    localStorage.setItem(STORAGE_KEY_DENSITY, val)
  } catch { /* ignore */ }
})

const tableSize = computed(() => (tableDensity.value === 'compact' ? 'small' : 'default'))

const rowAssetTotal = (row) => {
  if (!row) return 0
  return (
    (row.api_count ?? 0) +
    (row.case_count ?? 0) +
    (row.suite_count ?? row.suites ?? 0) +
    (row.web_case_count ?? row.ui_case_count ?? 0) +
    (row.web_suite_count ?? row.ui_suites ?? 0) +
    (row.web_task_count ?? row.ui_task_count ?? 0) +
    (row.app_case_count ?? 0) +
    (row.app_suite_count ?? 0) +
    (row.app_plan_count ?? 0) +
    (row.api_plan_count ?? 0) +
    (row.perf_scene_count ?? 0)
  )
}

const catalogCountMap = computed(() => {
  const map = {}
  for (const row of catalogRows.value) {
    const total = rowAssetTotal(row)
    if (total > 0) map[row.id] = total
  }
  return map
})

const loadCatalogTable = async () => {
  if (!proStore.projectInfo?.id) return
  tableLoading.value = true
  try {
    const response = await http.catalogApi.getList({
      project_id: proStore.projectInfo.id,
      include_counts: true,
      include_project_totals: true,
    })
    if (response.status === 200) {
      const payload = response.data
      if (payload?.items) {
        catalogRows.value = payload.items
        projectTotals.value = payload.project_totals || null
      } else {
        catalogRows.value = Array.isArray(payload) ? payload : []
        projectTotals.value = null
      }
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

const displayCatalogRows = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return filteredCatalogRows.value
  return filteredCatalogRows.value.filter((row) => {
    const name = (row.name || '').toLowerCase()
    const creator = (row.username || row.create_by || '').toLowerCase()
    return name.includes(kw) || creator.includes(kw)
  })
})

const selectedCatalogName = computed(() => {
  if (!selectedCatalogId.value) return null
  const row = catalogRows.value.find(r => r.id === selectedCatalogId.value)
  return row?.name || null
})

const summaryStats = computed(() => {
  const rows = filteredCatalogRows.value
  const useProjectTotals = !selectedCatalogId.value && projectTotals.value
  const totals = useProjectTotals ? projectTotals.value : null
  const sum = (key, altKey) => {
    if (totals && totals[key] != null) return totals[key]
    if (altKey && totals && totals[altKey] != null) return totals[altKey]
    return rows.reduce((acc, row) => acc + (row[key] ?? (altKey ? row[altKey] : 0) ?? 0), 0)
  }
  return {
    catalogCount: totals?.catalog_count ?? rows.length,
    apiCount: sum('api_count'),
    caseCount: sum('case_count'),
    webCaseCount: sum('web_case_count', 'ui_case_count'),
    appCaseCount: sum('app_case_count'),
    webSuiteCount: sum('web_suite_count', 'ui_suites'),
    appSuiteCount: sum('app_suite_count'),
    suiteCount: sum('suite_count'),
    webTaskCount: sum('web_task_count', 'ui_task_count'),
    appPlanCount: sum('app_plan_count'),
    apiPlanCount: sum('api_plan_count'),
    perfSceneCount: sum('perf_scene_count'),
  }
})

const statCards = computed(() => {
  const s = summaryStats.value
  return [
    {
      key: 'catalog',
      icon: Files,
      color: '#606266',
      value: s.catalogCount,
      label: '目录数',
      sub: null,
    },
    {
      key: 'api',
      icon: Grid,
      color: '#409EFF',
      value: s.apiCount,
      label: '接口资产',
      sub: `用例 ${s.caseCount} · 计划 ${s.apiPlanCount} · 套件 ${s.suiteCount}`,
    },
    {
      key: 'web',
      icon: Monitor,
      color: '#67C23A',
      value: s.webCaseCount,
      label: 'Web 用例',
      sub: `套件 ${s.webSuiteCount} · 计划 ${s.webTaskCount}`,
    },
    {
      key: 'app',
      icon: Iphone,
      color: '#9B59B6',
      value: s.appCaseCount,
      label: 'App 用例',
      sub: `套件 ${s.appSuiteCount} · 计划 ${s.appPlanCount} · 性能 ${s.perfSceneCount}`,
    },
  ]
})

const handleStatCardClick = (key) => {
  if (key === 'catalog') {
    selectedCatalogId.value = null
    highlightGroup.value = null
    return
  }
  highlightGroup.value = highlightGroup.value === key ? null : key
}

const handleCatalogChange = () => {
  highlightGroup.value = null
}

const headerCellStyle = ({ column }) => {
  const key = column.columnKey || ''
  if (key.startsWith('api')) return { background: GROUP_HEADER_BG.api, textAlign: 'center' }
  if (key.startsWith('web')) return { background: GROUP_HEADER_BG.web, textAlign: 'center' }
  if (key.startsWith('app')) return { background: GROUP_HEADER_BG.app, textAlign: 'center' }
  if (key === 'perf') return { background: GROUP_HEADER_BG.perf, textAlign: 'center' }
  return { textAlign: 'center' }
}

const headerCellClassName = ({ column }) => {
  const key = column.columnKey || ''
  const g = highlightGroup.value
  if (!g) return ''
  if (g === 'api' && key.startsWith('api')) return 'col-highlight col-highlight--api'
  if (g === 'web' && key.startsWith('web')) return 'col-highlight col-highlight--web'
  if (g === 'app' && key.startsWith('app')) return 'col-highlight col-highlight--app'
  return ''
}

const expandSections = (row) => [
  {
    key: 'api',
    title: '接口',
    metrics: [
      { key: 'api', label: '接口', value: row.api_count ?? 0, group: 'api' },
      { key: 'case', label: '用例', value: row.case_count ?? 0, group: 'api' },
      { key: 'suite', label: '套件', value: row.suite_count ?? row.suites ?? 0, group: 'api' },
      { key: 'plan', label: '计划', value: row.api_plan_count ?? 0, group: 'api' },
    ],
  },
  {
    key: 'web',
    title: 'Web',
    metrics: [
      { key: 'case', label: '用例', value: row.web_case_count ?? row.ui_case_count ?? 0, group: 'web' },
      { key: 'suite', label: '套件', value: row.web_suite_count ?? row.ui_suites ?? 0, group: 'web' },
      { key: 'plan', label: '计划', value: row.web_task_count ?? row.ui_task_count ?? 0, group: 'web' },
    ],
  },
  {
    key: 'app',
    title: 'App',
    metrics: [
      { key: 'case', label: '用例', value: row.app_case_count ?? 0, group: 'app' },
      { key: 'suite', label: '套件', value: row.app_suite_count ?? 0, group: 'app' },
      { key: 'plan', label: '计划', value: row.app_plan_count ?? 0, group: 'app' },
    ],
  },
  {
    key: 'other',
    title: '其他',
    metrics: [
      { key: 'perf', label: '性能场景', value: row.perf_scene_count ?? 0, group: 'perf' },
    ],
  },
]

const showAssets = ref(false)
const assetList = ref([])
const filteredAssetList = ref([])
const currentCatalog = ref(null)
const assetGroupFilter = ref('all')
const assetsLoading = ref(false)

const assetCountByGroup = computed(() => ({
  web: assetList.value.filter(a => a.group === 'web').length,
  app: assetList.value.filter(a => a.group === 'app').length,
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

const openAssets = async (catalog, groupFilter = 'all') => {
  currentCatalog.value = catalog
  showAssets.value = true
  assetsLoading.value = true
  assetGroupFilter.value = groupFilter
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

const openAssetsByGroup = (catalog, group) => {
  openAssets(catalog, group)
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
    case 'app_case':
      router.push({ name: 'appCaseEdit', params: { id } })
      break
    case 'app_suite':
      router.push({ name: 'appSuiteEdit', params: { id } })
      break
    case 'app_plan':
      router.push({ name: 'appPlanEdit', params: { id } })
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
.page-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
}

.filter-tag {
  font-weight: normal;
}

.catalog-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

@media (max-width: 1200px) {
  .catalog-stats {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .catalog-stats {
    grid-template-columns: 1fr;
  }
}

.summary-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 18px;
  border-radius: 10px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;

  &:hover {
    border-color: var(--el-border-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  &.is-active {
    border-color: var(--el-color-primary-light-5);
    box-shadow: 0 0 0 1px var(--el-color-primary-light-7);
  }
}

.summary-card-icon {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--el-fill-color-light);
}

.summary-card-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--el-text-color-primary);
}

.summary-card-label {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-regular);
}

.summary-card-sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.catalog-page {
  display: flex;
  gap: 16px;
  min-height: calc(100vh - 300px);
  align-items: stretch;
}

.catalog-sidebar {
  width: 240px;
  min-width: 240px;
  display: flex;
  flex-direction: column;
}

.catalog-table-card {
  flex: 1;
  min-width: 0;
  border-radius: 10px;

  :deep(.el-card__body) {
    padding: 16px;
  }
}

.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 200px;
}

.toolbar-search {
  width: 240px;
  max-width: 100%;
}

.toolbar-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.column-settings {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.name-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}

.name-icon {
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.name-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.count-num {
  font-variant-numeric: tabular-nums;

  &.is-zero {
    color: #c0c4cc;
  }

  &.is-clickable {
    color: var(--el-color-primary);
    cursor: pointer;

    &:hover {
      text-decoration: underline;
    }
  }
}

.catalog-data-table {
  :deep(.el-table__row) {
    &:hover > td {
      background-color: #f5f7fa !important;
    }
  }

  :deep(th.col-highlight--api) {
    box-shadow: inset 0 -2px 0 #409eff;
  }

  :deep(th.col-highlight--web) {
    box-shadow: inset 0 -2px 0 #67c23a;
  }

  :deep(th.col-highlight--app) {
    box-shadow: inset 0 -2px 0 #9b59b6;
  }
}

.expand-detail {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  padding: 8px 12px 12px 48px;
}

.expand-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.expand-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.expand-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 56px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
  cursor: default;

  &:not(.is-zero) {
    cursor: pointer;

    &:hover {
      background: var(--el-fill-color);
    }
  }

  &.is-zero .expand-metric-value {
    color: #c0c4cc;
  }
}

.expand-section--api .expand-section-title { color: #409eff; }
.expand-section--web .expand-section-title { color: #67c23a; }
.expand-section--app .expand-section-title { color: #9b59b6; }

.expand-metric-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.expand-metric-value {
  font-size: 16px;
  font-weight: 600;
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}

.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 0 4px;

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
