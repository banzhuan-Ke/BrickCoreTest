<template>
  <div class="case-set">
    <div class="filter-bar">
      <el-input
        v-model="searchName"
        placeholder="标题"
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
        <el-option label="P0" value="P0" />
        <el-option label="P1" value="P1" />
        <el-option label="P2" value="P2" />
        <el-option label="P3" value="P3" />
      </el-select>
      <el-button size="small" type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
    </div>

    <div class="case-list-container" v-infinite-scroll="loadMore" :infinite-scroll-disabled="disabled">
      <div class="case-list">
        <div
          v-for="item in caseList"
          :key="item.id"
          class="case-item"
          draggable="true"
          @dragstart="handleDragStart($event, item)"
        >
          <div class="case-info">
            <el-icon><Document /></el-icon>
            <span class="case-name" :title="item.name">{{ item.name }}</span>
            <el-tag v-if="item.level" size="small" :type="levelTagType(item.level)" class="level-tag">
              {{ item.level }}
            </el-tag>
          </div>
          <el-button
            @click="editCase(item.id)"
            :icon="Edit"
            circle
            size="small"
            type="primary"
            plain
          />
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
        <el-empty description="暂无数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Document, Edit, Loading, Search } from '@element-plus/icons-vue'
import http from '@/api/index'
import { ProjectStore } from '@/stores/module/ProjectStore'

defineProps({
  suiteId: {
    type: [String, Number],
    default: null,
  },
})

const router = useRouter()
const proStore = ProjectStore()

const caseList = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const searchName = ref('')
const searchLevel = ref('')
const noMore = computed(() => caseList.value.length >= total.value)
const disabled = computed(() => loading.value || noMore.value)

const levelTagType = (level) => {
  const map = { P0: 'danger', P1: 'warning', P2: 'primary', P3: 'info' }
  return map[level] || 'info'
}

const resetAndLoad = () => {
  page.value = 1
  caseList.value = []
  total.value = 0
  getCaseList()
}

const getCaseList = async () => {
  if (loading.value) return
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

    const res = await http.caseApi.getList(params)
    if (res.status === 200) {
      caseList.value.push(...res.data.data)
      total.value = res.data.total
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

let searchTimer = null
const handleSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(resetAndLoad, 200)
}

const loadMore = () => {
  page.value++
  getCaseList()
}

const handleDragStart = (e, item) => {
  e.dataTransfer.setData('application/json', JSON.stringify(item))
  e.dataTransfer.effectAllowed = 'copy'
}

const editCase = (caseId) => {
  router.push({ name: 'editCase', params: { id: caseId } })
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
  transition: all 0.2s;

  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  &:active {
    cursor: grabbing;
  }
}

.case-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  min-width: 0;

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

.level-tag {
  flex-shrink: 0;
}

.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.no-more {
  padding: 16px;
}

.empty-tip {
  padding: 20px 0;
}
</style>
