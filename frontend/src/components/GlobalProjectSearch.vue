<template>
  <el-dialog
    v-model="visible"
    title="项目内搜索"
    width="640px"
    destroy-on-close
    append-to-body
    align-center
    :z-index="4000"
    class="global-search-dialog"
    @opened="onOpened"
  >
    <el-input
      ref="inputRef"
      v-model="keyword"
      placeholder="搜索 Web / 接口 / App 用例、套件、计划、元素…"
      clearable
      :prefix-icon="Search"
      @input="onSearch"
      @keyup.enter="pickFirst"
    />
    <div v-loading="loading" class="search-results">
      <template v-if="groups.length">
        <div v-for="group in groups" :key="group.key" class="search-group">
          <div class="group-title">{{ group.label }}</div>
          <div
            v-for="item in group.items"
            :key="`${group.key}-${item.id}`"
            class="search-item"
            @click="goItem(group, item)"
          >
            <span class="item-name">{{ item.name }}</span>
            <span v-if="item.subtitle" class="item-sub">{{ item.subtitle }}</span>
          </div>
        </div>
      </template>
      <el-empty v-else-if="keyword && !loading" description="无匹配结果" :image-size="64" />
      <p v-else class="search-hint">输入关键词搜索当前项目下的 Web / 接口 / App 资产</p>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter, isNavigationFailure, NavigationFailureType } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { searchApi } from '@/api/modules/sys'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const props = defineProps({
  modelValue: Boolean,
})

const emit = defineEmits(['update:modelValue'])

const router = useRouter()
const proStore = ProjectStore()
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const keyword = ref('')
const groups = ref([])
const loading = ref(false)
const inputRef = ref(null)
let debounceTimer = null

function onOpened() {
  keyword.value = ''
  groups.value = []
  setTimeout(() => inputRef.value?.focus?.(), 50)
}

async function doSearch() {
  const q = keyword.value.trim()
  const projectId = proStore.projectInfo?.id
  if (!q || !projectId) {
    groups.value = []
    return
  }
  loading.value = true
  try {
    const res = await searchApi.search(projectId, q)
    groups.value = res.data?.data?.groups || []
  } finally {
    loading.value = false
  }
}

function onSearch() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(doSearch, 280)
}

function buildRouteTarget(group, item) {
  const uStore = UserStore()
  const id = String(item.id)
  const name = item.name || ''

  switch (group.key) {
    case 'ui_case':
      if (uStore.hasPermission('ui_case:edit')) {
        return { name: 'editCase', params: { id } }
      }
      return { name: 'caseList', query: { name } }
    case 'ui_suite':
      if (uStore.hasPermission('ui_suite:edit')) {
        return { name: 'editSuite', params: { id } }
      }
      return { name: 'suiteList', query: { name } }
    case 'ui_task':
      if (uStore.hasPermission('ui_task:edit')) {
        return { name: 'editTask', params: { id } }
      }
      return { name: 'taskList', query: { name } }
    case 'api':
      return { name: 'apiModule', query: { api_id: id } }
    case 'api_case': {
      const query = { api_id: String(item.api_id || '') }
      if (uStore.hasPermission('api_case:edit')) {
        query.edit_case_id = id
      } else if (name) {
        query.keyword = name
      }
      return { name: 'apiCase', query }
    }
    case 'api_suite':
      return { name: 'apiSuiteDetail', params: { suiteId: id } }
    case 'api_plan':
      if (uStore.hasPermission('api_plan:view')) {
        return { name: 'apiPlanEdit', params: { planId: id } }
      }
      return { name: 'apiPlan', query: { keyword: name } }
    case 'app_case':
      if (uStore.hasPermission('app_case:edit')) {
        return { name: 'appCaseEdit', params: { id } }
      }
      return { name: 'appCaseList', query: { name } }
    case 'app_suite':
      if (uStore.hasPermission('app_suite:edit')) {
        return { name: 'appSuiteEdit', params: { id } }
      }
      return { name: 'appSuiteList', query: { name } }
    case 'app_plan':
      if (uStore.hasPermission('app_plan:edit')) {
        return { name: 'appPlanEdit', params: { id } }
      }
      return { name: 'appPlanList', query: { name } }
    case 'app_element':
      return { name: 'appElements', query: name ? { name } : {} }
    default:
      return group.route ? { path: group.route } : null
  }
}

function isBenignNavigationFailure(err) {
  if (!isNavigationFailure(err)) return false
  return (
    err.type === NavigationFailureType.duplicated
    || err.type === NavigationFailureType.cancelled
    || err.type === NavigationFailureType.redirected
  )
}

async function goItem(group, item) {
  const target = buildRouteTarget(group, item)
  if (!target) {
    ElMessage.warning('暂不支持跳转到该类型')
    return
  }
  visible.value = false
  try {
    await router.push(target)
  } catch (err) {
    if (isBenignNavigationFailure(err)) return
    console.error('[GlobalProjectSearch] navigate failed', err)
    ElMessage.error('页面跳转失败，请刷新后重试')
  }
}

function pickFirst() {
  const first = groups.value[0]?.items?.[0]
  if (first && groups.value[0]) {
    goItem(groups.value[0], first)
  }
}

watch(visible, (v) => {
  if (!v) {
    keyword.value = ''
    groups.value = []
  }
})
</script>

<style scoped lang="scss">
.search-results {
  margin-top: 12px;
  min-height: 200px;
  max-height: 420px;
  overflow-y: auto;
}

.search-group {
  margin-bottom: 14px;
}

.group-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}

.search-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  &:hover {
    background: var(--el-fill-color-light);
  }
}

.item-name {
  font-weight: 500;
}

.item-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-hint {
  margin: 24px 0 0;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}
</style>
