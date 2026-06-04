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
            <el-table-column label="接口数" width="90">
              <template #default="{ row }">{{ row.api_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="用例数" width="90">
              <template #default="{ row }">{{ row.case_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="套件数" width="90">
              <template #default="{ row }">{{ row.suite_count ?? row.suites ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="UI用例" width="90">
              <template #default="{ row }">{{ row.ui_case_count ?? 0 }}</template>
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

  <el-drawer v-model="showAssets" :with-header="false" size="80%">
    <div class="drawer-header">
      <div class="title">{{ currentCatalog?.name }} — 关联套件</div>
    </div>
    <div class="filter-bar">
      <el-radio-group v-model="suiteTypeFilter" size="small" @change="filterSuites">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="web">Web</el-radio-button>
        <el-radio-button label="api">接口</el-radio-button>
      </el-radio-group>
    </div>
    <el-table
      :data="filteredSuiteList"
      style="width: calc(100% - 40px)"
      :header-cell-style="{'text-align':'center'}"
      :cell-style="{'text-align':'center'}"
      stripe
    >
      <template #empty>
        <el-empty description="暂无套件" />
      </template>
      <el-table-column label="序号" type="index" width="70"/>
      <el-table-column prop="name" label="套件名称"/>
      <el-table-column prop="suite_type" label="套件类型" width="120">
        <template #default="scope">
          <el-tag v-if='scope.row.suite_type==="1" || scope.row.suite_type==="web"' type="success">Web</el-tag>
          <el-tag v-else-if='scope.row.suite_type==="2" || scope.row.suite_type==="api"' type="primary">接口</el-tag>
          <el-tag v-else type="info">未分类</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="创建人"/>
      <el-table-column prop="create_time" label="创建时间" min-width="160">
        <template #default="scope">
          {{ dateTools.rTime(scope.row.create_time) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="scope">
          <el-button @click="handleEditSuite(scope.row)" size="small" icon="Edit" plain type="primary">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Grid } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import http from '@/api/index'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import dateTools from '@/tools/dateTools'
import PageCard from '@/components/PageCard.vue'
import CatalogTree from '@/components/CatalogTree.vue'
import { collectCatalogSubtreeIds } from '@/api/modules/catalog'

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
  }
})

const handleCatalogChange = () => {
  // 筛选由 filteredCatalogRows 计算完成，无需重复拉取列表
}

const showAssets = ref(false)
const suiteList = ref([])
const filteredSuiteList = ref([])
const currentCatalog = ref(null)
const suiteTypeFilter = ref('all')

const filterSuites = () => {
  if (suiteTypeFilter.value === 'all') {
    filteredSuiteList.value = suiteList.value
  } else {
    filteredSuiteList.value = suiteList.value.filter(suite => suite.suite_type === suiteTypeFilter.value)
  }
}

const openAssets = async (catalog) => {
  currentCatalog.value = catalog
  const response = await http.catalogApi.getDetail(catalog.id)
  suiteList.value = response.data?.suites || []
  suiteTypeFilter.value = 'all'
  filterSuites()
  showAssets.value = true
}

const handleEditSuite = (suite) => {
  if (suite.suite_type === 'api') {
    router.push(`/api-suite/${suite.id}`)
  } else {
    router.push({ name: 'editSuite', params: { id: suite.id } })
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
  min-width: 120px;
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
