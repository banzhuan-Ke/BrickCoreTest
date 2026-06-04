<template>
  <div class="case-set">
    <!-- 搜索框 -->
    <div class="search-box">
      <el-input
        v-model="searchName"
        placeholder="搜索用例名称"
        clearable
        size="small"
        @input="handleSearch"
        @clear="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>
    
    <div class="case-list-container" v-infinite-scroll="loadMore" :infinite-scroll-disabled="disabled">
      <!-- 用例列表 - 使用普通列表渲染 -->
      <div class="case-list">
        <div 
          v-for="item in displayList" 
          :key="item.id"
          class="case-item"
          draggable="true"
          @dragstart="handleDragStart($event, item)"
        >
          <div class="case-info">
            <el-icon><Document /></el-icon>
            <span class="case-name" :title="item.name">{{ item.name }}</span>
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
      
      <div v-if="!loading && noMore && displayList.length > 0" class="no-more">
        <el-divider>没有更多了</el-divider>
      </div>
      
      <div v-if="!loading && displayList.length === 0" class="empty-tip">
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

const props = defineProps({
  suiteId: {
    type: [String, Number],
    required: true
  }
})

const router = useRouter()
const proStore = ProjectStore()

const caseList = ref([])
const loading = ref(false)
const page = ref(1)
const size = ref(20)
const total = ref(0)
const searchName = ref('')
const noMore = computed(() => caseList.value.length >= total.value)
const disabled = computed(() => loading.value || noMore.value)

// 显示的用例列表（根据搜索条件过滤）
const displayList = computed(() => {
  console.log('caseList changed:', caseList.value.length, caseList.value)
  if (!searchName.value.trim()) {
    return caseList.value
  }
  const keyword = searchName.value.trim().toLowerCase()
  return caseList.value.filter(item => item.name.toLowerCase().includes(keyword))
})

// 监听 caseList 变化
watch(caseList, (newVal) => {
  console.log('caseList watch:', newVal.length, newVal)
}, { deep: true })

// 获取用例列表
const getCaseList = async () => {
  console.log('getCaseList called, page:', page.value)
  if (loading.value) return
  loading.value = true
  try {
    const params = {
      page: page.value,
      size: size.value,
      project_id: proStore.projectInfo.id,
    }
    if (searchName.value.trim()) {
      params.name = searchName.value.trim()
    }
    console.log('request params:', params)
    const res = await http.caseApi.getList(params)
    console.log('response:', res.status, res.data)
    if (res.status === 200) {
      caseList.value.push(...res.data.data)
      total.value = res.data.total
      console.log('after push, caseList:', caseList.value.length)
    }
  } catch (error) {
    console.error('获取用例列表失败:', error)
  } finally {
    loading.value = false
  }
}

// 搜索处理（防抖）
let searchTimer = null
const handleSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    caseList.value = []
    getCaseList()
  }, 300)
}

// 加载更多
const loadMore = () => {
  page.value++
  getCaseList()
}

// 拖拽开始
const handleDragStart = (e, item) => {
  e.dataTransfer.setData('application/json', JSON.stringify(item))
  e.dataTransfer.effectAllowed = 'copy'
}

// 编辑用例
const editCase = (caseId) => {
  router.push({ name: 'editCase', params: { id: caseId } })
}

// 初始加载
console.log('CaseSet init, project_id:', proStore.projectInfo.id)
getCaseList()
</script>

<style scoped lang="scss">
.case-set {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.search-box {
  padding: 12px 12px 0 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.case-list-container {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
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
  gap: 8px;
  overflow: hidden;
  
  .el-icon {
    color: var(--el-color-primary);
    flex-shrink: 0;
  }
}

.case-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
