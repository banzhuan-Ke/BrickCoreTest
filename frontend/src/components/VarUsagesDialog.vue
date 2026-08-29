<template>
  <el-drawer
    v-model="visible"
    size="88%"
    destroy-on-close
    class="var-usages-drawer"
    @open="onOpen"
  >
    <template #header>
      <div class="drawer-header">
        <div class="title-block">
          <div class="title">变量引用</div>
          <div class="sub">扫描用例 / 套件 / 计划等中的 <code v-pre>${{变量名}}</code> 明文引用</div>
        </div>
        <div class="toolbar">
          <el-input
            v-model="queryName"
            placeholder="输入变量名后查询"
            clearable
            style="width: 240px"
            @keyup.enter="load"
          />
          <el-button type="primary" :loading="loading" @click="load">查询</el-button>
          <el-tag v-if="result" type="info" effect="plain">共 {{ result.total }} 处</el-tag>
          <el-tag v-if="result?.truncated" type="warning" effect="plain">结果已截断</el-tag>
        </div>
      </div>
    </template>

    <div v-if="quickNames.length" class="quick-row">
      <span class="quick-label">快捷查看：</span>
      <el-button
        v-for="n in quickNames"
        :key="n"
        size="small"
        round
        :type="queryName === n ? 'primary' : 'default'"
        @click="quickSearch(n)"
      >
        {{ n }}
      </el-button>
    </div>

    <el-skeleton v-if="loading" :rows="10" animated />
    <template v-else-if="result">
      <el-empty v-if="!result.total" description="未找到引用（仅扫描 ${变量名} 明文）" />
      <template v-else>
        <el-tabs v-model="activeCategory" class="usage-tabs">
          <el-tab-pane
            v-for="cat in categories"
            :key="cat.key"
            :name="cat.key"
            :label="`${cat.label}（${cat.rows.length}）`"
            :disabled="!cat.rows.length"
          />
        </el-tabs>

        <el-table
          :data="pagedRows"
          stripe
          border
          size="small"
          height="calc(100vh - 280px)"
          empty-text="该类暂无引用"
        >
          <el-table-column type="index" label="#" width="56" :index="indexMethod" />
          <el-table-column prop="name" label="名称" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              <el-button type="primary" link @click="jumpCurrent(row)">{{ row.name || `#${row.id}` }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="位置 / 备注" min-width="280" show-overflow-tooltip>
            <template #default="{ row }">
              {{ rowMetaText(row) || '—' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="center" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link size="small" @click="jumpCurrent(row)">打开</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="currentRows.length"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next"
            background
          />
        </div>

        <el-alert
          v-if="result.truncated"
          type="warning"
          :closable="false"
          show-icon
          class="truncate-tip"
          :title="`服务端每类最多返回 ${result.limit || 200} 条；若仍不够可缩小范围后分次查询`"
        />
      </template>
    </template>
    <el-empty v-else description="输入变量名并查询，或点上方快捷查看" />
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/api/index'
import { UserStore } from '@/stores/module/UserStore.js'

const CATEGORY_DEFS = [
  { key: 'api_definitions', label: '接口定义' },
  { key: 'api_cases', label: '接口用例' },
  { key: 'api_suites', label: '接口套件' },
  { key: 'api_plans', label: '接口计划' },
  { key: 'ui_cases', label: 'Web 用例' },
  { key: 'ui_suites', label: 'Web 套件' },
  { key: 'ui_plans', label: 'Web 计划' },
  { key: 'app_cases', label: 'App 用例' },
  { key: 'app_suites', label: 'App 套件' },
  { key: 'sql_templates', label: 'SQL 模板' },
  { key: 'perf_scenes', label: '压测场景' },
]

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  projectId: { type: [Number, String], default: null },
  varName: { type: String, default: '' },
  /** 快捷变量名候选（项目/环境变量名） */
  quickVarNames: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const router = useRouter()
const uStore = UserStore()
const loading = ref(false)
const result = ref(null)
const queryName = ref('')
const activeCategory = ref('ui_cases')
const page = ref(1)
const pageSize = ref(20)

watch(
  () => props.varName,
  (v) => {
    queryName.value = v || ''
  },
  { immediate: true }
)

const quickNames = computed(() => {
  const fromProp = (props.quickVarNames || []).map((x) => String(x || '').trim()).filter(Boolean)
  return [...new Set(fromProp)].slice(0, 24)
})

const categories = computed(() =>
  CATEGORY_DEFS.map((d) => ({
    ...d,
    rows: Array.isArray(result.value?.[d.key]) ? result.value[d.key] : [],
  }))
)

const currentRows = computed(() => {
  const hit = categories.value.find((c) => c.key === activeCategory.value)
  return hit?.rows || []
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return currentRows.value.slice(start, start + pageSize.value)
})

watch(activeCategory, () => {
  page.value = 1
})
watch(pageSize, () => {
  page.value = 1
})

function indexMethod(i) {
  return (page.value - 1) * pageSize.value + i + 1
}

function rowMetaText(row) {
  const parts = []
  if (row.via) parts.push(String(row.via))
  else if (row.location) parts.push(String(row.location))
  if (row.api_name) parts.push(String(row.api_name))
  if (Array.isArray(row.via_case_ids) && row.via_case_ids.length) {
    parts.push(`关联用例 ${row.via_case_ids.slice(0, 5).join(',')}`)
  }
  return parts.join(' · ')
}

function onOpen() {
  queryName.value = props.varName || queryName.value || ''
  if (queryName.value.trim()) load()
}

function quickSearch(name) {
  queryName.value = name
  load()
}

async function load() {
  const name = (queryName.value || '').trim()
  if (!props.projectId) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!name) {
    ElMessage.warning('请输入变量名')
    return
  }
  loading.value = true
  result.value = null
  page.value = 1
  try {
    const res = await http.projectApi.getVariableUsages(props.projectId, name)
    result.value = res.data?.data ?? res.data
    const first = CATEGORY_DEFS.find((d) => (result.value?.[d.key] || []).length)
    activeCategory.value = first?.key || 'ui_cases'
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '查询失败')
  } finally {
    loading.value = false
  }
}

function closeAndGo(to) {
  visible.value = false
  router.push(to)
}

function jumpEditOrList({ editPerm, editTo, listTo, hintName }) {
  if (editPerm && uStore.hasPermission(editPerm)) {
    closeAndGo(editTo)
    return
  }
  closeAndGo(listTo)
  if (hintName) {
    ElMessage.info(`当前无编辑权限，已打开列表；可搜索：${hintName}`)
  }
}

function jumpCurrent(row) {
  const key = activeCategory.value
  const map = {
    api_definitions: () => closeAndGo({ path: '/api-case', query: { api_id: row.id } }),
    api_cases: () => closeAndGo({ path: '/api-case', query: { edit_case_id: row.id } }),
    api_suites: () => closeAndGo({ path: `/api-suite/${row.id}` }),
    api_plans: () => closeAndGo({ path: `/api-plan/${row.id}` }),
    ui_cases: () =>
      jumpEditOrList({
        editPerm: 'ui_case:edit',
        editTo: { path: `/case/edit/${row.id}` },
        listTo: { path: '/case', query: { name: row.name || '' } },
        hintName: row.name,
      }),
    ui_suites: () =>
      jumpEditOrList({
        editPerm: 'ui_suite:edit',
        editTo: { path: `/suite/edit/${row.id}` },
        listTo: { path: '/suite', query: { name: row.name || '' } },
        hintName: row.name,
      }),
    ui_plans: () =>
      jumpEditOrList({
        editPerm: 'ui_task:edit',
        editTo: { path: `/task/edit/${row.id}` },
        listTo: { path: '/task', query: { name: row.name || '' } },
        hintName: row.name,
      }),
    app_cases: () =>
      jumpEditOrList({
        editPerm: 'app_case:edit',
        editTo: { path: `/app-case/edit/${row.id}` },
        listTo: { path: '/app-case', query: { name: row.name || '' } },
        hintName: row.name,
      }),
    app_suites: () =>
      jumpEditOrList({
        editPerm: 'app_suite:edit',
        editTo: { path: `/app-suite/edit/${row.id}` },
        listTo: { path: '/app-suite', query: { name: row.name || '' } },
        hintName: row.name,
      }),
    sql_templates: () => closeAndGo({ path: '/api-data-factory' }),
    perf_scenes: () =>
      jumpEditOrList({
        editPerm: 'perf_scene:edit',
        editTo: { path: `/perf-scene/edit/${row.id}` },
        listTo: { path: '/perf-scenes', query: { keyword: row.name || '' } },
        hintName: row.name,
      }),
  }
  map[key]?.()
}
</script>

<style scoped>
.drawer-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  padding-right: 28px;
}
.title-block .title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.3;
}
.title-block .sub {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.quick-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}
.quick-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.usage-tabs {
  margin-bottom: 8px;
}
.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.truncate-tip {
  margin-top: 12px;
}
</style>
