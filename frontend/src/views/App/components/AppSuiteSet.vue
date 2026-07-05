<template>
  <PageCard>
    <template #title>
      <span>App 套件列表</span>
    </template>
    <template #main>
      <div class="suite-toolbar">
        <el-input
          v-model="searchName"
          placeholder="按套件名称搜索"
          clearable
          @clear="handleSearch"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button icon="Search" @click="handleSearch" />
          </template>
        </el-input>
        <div class="suite-toolbar-hint">已加入当前计划的套件会标记为「已加入」</div>
      </div>
      <div class="main_box" v-infinite-scroll="loadNextPage">
        <draggable
          v-model="suiteList"
          item-key="id"
          :sort="false"
          :clone="customClone"
          :group="{ name: 'suite', pull: 'clone', put: false }"
          chosen-class="chosen"
          drag-class="dragging"
          ghost-class="ghost"
        >
          <template #item="{ element }">
            <div class="line" :class="{ 'line--added': isSuiteInPlan(element.id) }">
              <div class="name">
                {{ element.name }}
                <el-tag
                  v-if="isSuiteInPlan(element.id)"
                  type="success"
                  size="small"
                  effect="plain"
                  class="added-tag"
                >
                  已加入
                </el-tag>
              </div>
              <div class="create_time">{{ formatTime(element.create_time) }}</div>
              <el-tooltip content="编辑套件" placement="bottom">
                <el-button
                  icon="Edit"
                  circle
                  plain
                  type="primary"
                  @click="router.push({ name: 'appSuiteEdit', params: { id: element.id } })"
                />
              </el-tooltip>
            </div>
          </template>
        </draggable>
        <div v-if="!loading && suiteList.length === 0" class="empty-tip">
          {{ searchName.trim() ? '未找到匹配的套件' : '暂无套件' }}
        </div>
        <div v-loading="loading" element-loading-text="加载中..." class="loading" />
      </div>
    </template>
  </PageCard>
</template>

<script setup>
import { reactive, ref, onMounted, inject, computed } from 'vue'
import { useRouter } from 'vue-router'
import PageCard from '@/components/PageCard.vue'
import { appSuiteApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'
import draggable from 'vuedraggable'
import dateTools from '@/tools/dateTools'

const router = useRouter()
const proStore = ProjectStore()
const suiteList = ref([])
const loading = ref(false)
const searchName = ref('')

const taskAddedSuiteIds = inject('taskAddedSuiteIds', computed(() => new Set()))
const isSuiteInPlan = (suiteId) => taskAddedSuiteIds.value.has(suiteId)

const pageConfig = reactive({
  page: 1,
  size: 10,
  total: 0,
})

function formatTime(v) {
  return v ? dateTools.rTime(v) : '—'
}

function customClone(data) {
  return {
    suite_id: data.id,
    suite_name: data.name,
    create_time: data.create_time,
  }
}

async function getSuiteList() {
  if (!proStore.projectInfo?.id) return
  loading.value = true
  try {
    const params = {
      page: pageConfig.page,
      size: pageConfig.size,
      project_id: proStore.projectInfo.id,
    }
    if (searchName.value.trim()) params.name = searchName.value.trim()
    const res = await appSuiteApi.list(params)
    suiteList.value.push(...(res.data?.data || []))
    pageConfig.total = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

async function resetAndLoad() {
  pageConfig.page = 1
  pageConfig.total = 0
  suiteList.value = []
  await getSuiteList()
}

function handleSearch() {
  resetAndLoad()
}

function loadNextPage() {
  if (loading.value) return
  if (pageConfig.page * pageConfig.size < pageConfig.total) {
    pageConfig.page += 1
    getSuiteList()
  }
}

onMounted(resetAndLoad)
</script>

<style scoped lang="scss">
@use '../../Task/componets/SuiteSet.scss';

.suite-toolbar {
  margin-bottom: 8px;
}

.suite-toolbar-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.line--added {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}

.added-tag {
  margin-left: 6px;
}

.empty-tip {
  text-align: center;
  padding: 24px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.loading {
  min-height: 40px;
}
</style>
