<template>
  <div>
    <div class="filter-bar">
      <el-input v-model="filters.keyword" placeholder="方案标题关键词" clearable style="width: 200px;" @keyup.enter="loadList" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 100px;" @change="loadList">
        <el-option label="草稿" value="draft" />
        <el-option label="已确认" value="confirmed" />
      </el-select>
      <el-button @click="loadList" icon="Search">筛选</el-button>
      <el-button @click="resetFilters">重置</el-button>
      <span class="list-hint">共 {{ total }} 条</span>
    </div>

    <el-table :data="rows" v-loading="loading" stripe border style="margin-top: 12px;">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="requirement_name" label="需求" min-width="160" show-overflow-tooltip />
      <el-table-column prop="title" label="方案标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="version" label="版本" width="70" align="center" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'confirmed' ? 'success' : 'info'" size="small">
            {{ row.status === 'confirmed' ? '已确认' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="update_time" label="更新时间" width="170" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="goRequirement(row)">打开</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      class="pager"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="p => { page = p; loadList() }"
    />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { aiTestAnalysisApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'

const router = useRouter()
const proStore = ProjectStore()
const rows = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filters = reactive({ keyword: '', status: '' })

const loadList = async () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先在顶部导航栏选择项目')
    return
  }
  loading.value = true
  try {
    const params = {
      project_id: proStore.projectInfo.id,
      page: page.value,
      size: pageSize
    }
    if (filters.keyword?.trim()) params.keyword = filters.keyword.trim()
    if (filters.status) params.status = filters.status
    const res = await aiTestAnalysisApi.listProjectSchemes(params)
    if (res.data?.code === 200) {
      rows.value = res.data.data?.list || []
      total.value = res.data.data?.total || 0
    }
  } finally {
    loading.value = false
  }
}

const resetFilters = () => {
  filters.keyword = ''
  filters.status = ''
  page.value = 1
  loadList()
}

const goRequirement = (row) => {
  router.push({
    name: 'aiTestingWorkspace',
    params: { reqId: row.requirement_id },
    query: { tab: 'schemes' }
  })
}

onMounted(loadList)
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.list-hint {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
