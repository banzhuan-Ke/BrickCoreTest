<template>
  <div class="plan-item-selector">
    <el-tabs v-model="activeTab">
      <!-- Tab 1：按套件添加 -->
      <el-tab-pane label="按套件添加" name="suite">
        <div class="tab-search">
          <CatalogTreeSelect
            v-model="filterSuiteCatalog"
            :project-id="proStore.projectInfo.id"
            placeholder="目录"
            width="140px"
            @change="fetchSuites"
          />
          <el-input
            v-model="suiteKeyword"
            placeholder="搜索套件"
            clearable
            @input="fetchSuites"
            @clear="fetchSuites"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>
        <div class="item-list" v-loading="suiteLoading">
          <div
            v-for="suite in suiteList"
            :key="suite.id"
            class="item-row"
            :class="{ 'is-added': addedSuiteIds.has(suite.id) }"
          >
            <div class="item-info">
              <el-icon class="item-icon suite-icon"><Folder /></el-icon>
              <span class="item-name" :title="suite.name">{{ suite.name }}</span>
              <el-tag size="small" type="info" style="margin-left: 6px">
                {{ suite.case_count ?? 0 }} 用例
              </el-tag>
            </div>
            <el-button
              v-if="!addedSuiteIds.has(suite.id)"
              link
              type="primary"
              size="small"
              @click="addSuite(suite)"
            >
              <el-icon><Plus /></el-icon>添加
            </el-button>
            <el-tag v-else size="small" type="success">已添加</el-tag>
          </div>
          <el-empty v-if="!suiteLoading && suiteList.length === 0" description="暂无套件" :image-size="60" />
        </div>
      </el-tab-pane>

      <!-- Tab 2：按用例筛选添加 -->
      <el-tab-pane label="按用例添加" name="case">
        <div class="tab-search">
          <el-select
            v-model="filterPriority"
            placeholder="优先级"
            clearable
            style="width: 90px; margin-right: 6px"
            @change="fetchCases"
          >
            <el-option v-for="p in ['P0','P1','P2','P3']" :key="p" :label="p" :value="p" />
          </el-select>
          <CatalogTreeSelect
            v-model="filterCatalog"
            :project-id="proStore.projectInfo.id"
            placeholder="目录"
            width="140px"
            @change="fetchCases"
          />
          <el-input
            v-model="caseKeyword"
            placeholder="搜索用例"
            clearable
            style="flex: 1"
            @input="fetchCases"
            @clear="fetchCases"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
        </div>

        <div class="item-list" v-loading="caseLoading">
          <div
            v-for="c in caseList"
            :key="c.id"
            class="item-row"
            :class="{ 'is-added': addedCaseIds.has(c.id) }"
          >
            <el-checkbox
              v-model="selectedCaseIds"
              :label="c.id"
              :disabled="addedCaseIds.has(c.id)"
              style="margin-right: 6px"
            />
            <div class="item-info">
              <el-tag size="small" :type="priorityType(c.priority)" style="margin-right: 4px">
                {{ c.priority }}
              </el-tag>
              <el-tag size="small" :type="methodType(c.api_method)" style="margin-right: 4px">
                {{ c.api_method || 'GET' }}
              </el-tag>
              <span class="item-name" :title="c.name">{{ c.name }}</span>
            </div>
            <el-tag v-if="addedCaseIds.has(c.id)" size="small" type="success" style="flex-shrink:0">已添加</el-tag>
          </div>
          <el-empty v-if="!caseLoading && caseList.length === 0" description="暂无用例" :image-size="60" />
        </div>

        <div class="case-footer">
          <span class="selected-count">已选 {{ selectedCaseIds.length }} 个</span>
          <el-button
            type="primary"
            size="small"
            :disabled="selectedCaseIds.length === 0"
            @click="addSelectedCases"
          >
            加入计划
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { Search, Plus, Folder } from '@element-plus/icons-vue'
import { httpSuiteApi, httpCaseApi } from '@/api/modules/http'
import { ProjectStore } from '@/stores/module/ProjectStore'
import CatalogTreeSelect from '@/components/CatalogTreeSelect.vue'

const props = defineProps({
  // 已添加的 items，用于去重标记（由父组件传入）
  addedItems: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['add-items'])

const proStore = ProjectStore()
const activeTab = ref('suite')

// ===== 套件 Tab =====
const suiteList = ref([])
const suiteLoading = ref(false)
const suiteKeyword = ref('')
const filterSuiteCatalog = ref(null)

const addedSuiteIds = computed(() => {
  return new Set(
    props.addedItems
      .filter(i => i.item_type === 'suite')
      .map(i => i.suite_id)
  )
})

const fetchSuites = async () => {
  if (!proStore.projectInfo?.id) return
  suiteLoading.value = true
  try {
    const res = await httpSuiteApi.getList({
      project_id: proStore.projectInfo.id,
      keyword: suiteKeyword.value || undefined,
      catalog_id: filterSuiteCatalog.value || undefined,
      page: 1,
      size: 100,
    })
    suiteList.value = res.data?.data || []
  } catch (e) {
    suiteList.value = []
  } finally {
    suiteLoading.value = false
  }
}

const addSuite = (suite) => {
  emit('add-items', [{
    item_type: 'suite',
    suite_id: suite.id,
    suite_name: suite.name,
    sort: 0,
  }])
}

// ===== 用例 Tab =====
const caseList = ref([])
const caseLoading = ref(false)
const caseKeyword = ref('')
const filterPriority = ref(null)
const filterCatalog = ref(null)
const selectedCaseIds = ref([])

const addedCaseIds = computed(() => {
  return new Set(
    props.addedItems
      .filter(i => i.item_type === 'case')
      .map(i => i.case_id)
  )
})

const fetchCases = async () => {
  if (!proStore.projectInfo?.id) return
  caseLoading.value = true
  try {
    const params = {
      project_id: proStore.projectInfo.id,
      keyword: caseKeyword.value || undefined,
      priority: filterPriority.value || undefined,
      catalog_id: filterCatalog.value || undefined,
      page: 1,
      size: 100,
    }
    const res = await httpCaseApi.getList(params)
    caseList.value = res.data?.data || []
  } catch (e) {
    caseList.value = []
  } finally {
    caseLoading.value = false
  }
}

const addSelectedCases = () => {
  const items = selectedCaseIds.value
    .filter(id => !addedCaseIds.value.has(id))
    .map(id => {
      const c = caseList.value.find(x => x.id === id)
      return {
        item_type: 'case',
        case_id: id,
        case_name: c?.name || '',
        api_name: c?.api_name || '',
        api_method: c?.api_method || '',
        sort: 0,
      }
    })
  if (items.length > 0) {
    emit('add-items', items)
    selectedCaseIds.value = []
  }
}

// 优先级颜色
const priorityType = (p) => {
  const map = { P0: 'danger', P1: 'warning', P2: '', P3: 'info' }
  return map[p] || ''
}

// 请求方法颜色
const methodType = (m) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'warning' }
  return map[m] || 'info'
}

// 切换 Tab 时加载数据
watch(activeTab, (val) => {
  if (val === 'suite') fetchSuites()
  else if (val === 'case') fetchCases()
})

onMounted(() => {
  fetchSuites()
})
</script>

<style scoped>
.plan-item-selector {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.tab-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.item-list {
  flex: 1;
  overflow-y: auto;
  max-height: 420px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  transition: background 0.15s;
}
.item-row:last-child {
  border-bottom: none;
}
.item-row:hover {
  background: var(--el-fill-color-light);
}
.item-row.is-added {
  background: var(--el-color-success-light-9);
}
.item-info {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  margin-right: 8px;
}
.item-icon {
  margin-right: 6px;
  flex-shrink: 0;
}
.suite-icon {
  color: var(--el-color-warning);
}
.item-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.case-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.selected-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
