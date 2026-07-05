<template>
  <div class="case-set">
    <div class="filter-bar">
      <el-input
        v-model="searchName"
        placeholder="按用例名称搜索"
        clearable
        size="small"
        class="filter-title"
        @keyup.enter="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select
        v-model="searchLevel"
        placeholder="优先级"
        clearable
        size="small"
        class="filter-level"
        @change="handleSearch"
      >
        <el-option v-for="lv in ['P0', 'P1', 'P2', 'P3']" :key="lv" :label="lv" :value="lv" />
      </el-select>
      <el-button size="small" type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
    </div>
    <div class="filter-hint">已加入当前套件的用例会标记为「已加入」</div>

    <div class="case-list-container" v-infinite-scroll="loadMore" :infinite-scroll-disabled="disabled">
      <div class="case-list">
        <div
          v-for="item in caseList"
          :key="item.id"
          class="case-item"
          :class="{ 'case-item--added': isCaseInSuite(item.id) }"
          draggable="true"
          @dragstart="handleDragStart($event, item)"
        >
          <div class="case-info">
            <el-icon><Document /></el-icon>
            <span class="case-name" :title="item.name">{{ item.name }}</span>
            <el-tag v-if="isCaseInSuite(item.id)" type="success" size="small" effect="plain" class="added-tag">
              已加入
            </el-tag>
            <el-tag v-if="item.level" size="small" :type="levelTagType(item.level)" class="level-tag">
              {{ item.level }}
            </el-tag>
          </div>
          <el-button :icon="Edit" circle size="small" type="primary" plain @click="editCase(item.id)" />
        </div>
      </div>

      <div v-if="loading" class="loading-more">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
      <div v-if="!loading && noMore && caseList.length > 0" class="no-more">
        <el-divider>没有更多了</el-divider>
      </div>
      <div v-if="!loading && caseList.length === 0" class="empty-tip">
        <el-empty :description="searchName.trim() || searchLevel ? '未找到匹配的用例' : '暂无数据'" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject } from 'vue'
import { useRouter } from 'vue-router'
import { Document, Edit, Loading, Search } from '@element-plus/icons-vue'
import { appCaseApi } from '@/api'
import { ProjectStore } from '@/stores/module/ProjectStore'

defineProps({
  suiteId: { type: [String, Number], default: null },
})

const router = useRouter()
const proStore = ProjectStore()
const suiteAddedCaseIds = inject('suiteAddedCaseIds', ref(new Set()))
const isCaseInSuite = (caseId) => suiteAddedCaseIds.value.has(caseId)

const caseList = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const searchName = ref('')
const searchLevel = ref('')
const noMore = computed(() => caseList.value.length >= total.value)
const disabled = computed(() => loading.value || noMore.value)

function levelTagType(level) {
  const map = { P0: 'danger', P1: 'warning', P2: 'primary', P3: 'info' }
  return map[level] || 'info'
}

function resetAndLoad() {
  page.value = 1
  caseList.value = []
  total.value = 0
  getCaseList()
}

async function getCaseList() {
  if (loading.value || !proStore.projectInfo?.id) return
  loading.value = true
  try {
    const params = {
      page: page.value,
      size: size.value,
      project_id: proStore.projectInfo.id,
    }
    const name = searchName.value.trim()
    if (name) params.name = name
    if (searchLevel.value) params.level = searchLevel.value
    const res = await appCaseApi.list(params)
    caseList.value.push(...(res.data?.data || []))
    total.value = res.data?.total || 0
  } finally {
    loading.value = false
  }
}

let searchTimer = null
function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(resetAndLoad, 200)
}

function loadMore() {
  page.value += 1
  getCaseList()
}

function handleDragStart(e, item) {
  e.dataTransfer.setData('application/json', JSON.stringify(item))
  e.dataTransfer.effectAllowed = 'copy'
}

function editCase(caseId) {
  router.push({ name: 'appCaseEdit', params: { id: caseId } })
}

watch(
  () => proStore.projectInfo.id,
  (id) => {
    if (id) resetAndLoad()
  }
)

resetAndLoad()
</script>

<style scoped lang="scss">
.case-set {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.filter-bar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.filter-title {
  flex: 1;
  min-width: 0;
}

.filter-level {
  width: 88px;
  flex-shrink: 0;
}

.filter-hint {
  padding: 0 12px 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-bottom: 1px solid var(--el-border-color-light);
}

.case-list-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}

.case-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.case-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: grab;

  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  &.case-item--added {
    border-color: var(--el-color-success-light-5);
    background: var(--el-color-success-light-9);
  }
}

.case-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow: hidden;

  .el-icon {
    color: var(--el-color-primary);
    flex-shrink: 0;
  }
}

.case-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.added-tag,
.level-tag {
  flex-shrink: 0;
}

.loading-more,
.empty-tip {
  padding: 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
}

.no-more {
  padding: 8px;
}
</style>
