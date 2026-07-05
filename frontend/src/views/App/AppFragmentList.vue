<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>App 步骤片段</span>
        <el-button type="primary" size="small" icon="Plus" @click="goCreate">新建片段</el-button>
      </div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        App 片段可在用例/套件前置中引用，执行时由平台自动展开。
      </el-alert>
      <div class="search-bar">
        <el-input v-model="keyword" placeholder="搜索片段名称" clearable style="width: 220px;" @keyup.enter="loadList" />
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
        <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
      </div>
      <el-table :data="list" stripe v-loading="loading" border>
        <el-table-column prop="name" label="片段名称" min-width="140" />
        <el-table-column prop="tags" label="分类" width="100" />
        <el-table-column label="步骤数" width="90" align="center">
          <template #default="{ row }">{{ row.step_count }}</template>
        </el-table-column>
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }">v{{ row.version }}</template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="160" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="goEdit(row.id)">编辑</el-button>
            <el-button size="small" type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.size"
        :total="pagination.total"
        layout="total, prev, pager, next"
        class="pagination"
        @current-change="loadList"
      />
    </template>
  </PageCard>
</template>

<script setup>
import { reactive, ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { appFragmentApi } from '@/api/modules/app'
import { ProjectStore } from '@/stores/module/ProjectStore'

const router = useRouter()
const proStore = ProjectStore()
const loading = ref(false)
const list = ref([])
const keyword = ref('')
const pagination = reactive({ page: 1, size: 20, total: 0 })

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await appFragmentApi.list({
      project_id: projectId,
      keyword: keyword.value || undefined,
      page: pagination.page,
      size: pagination.size,
    })
    list.value = res.data?.data?.items || []
    pagination.total = res.data?.data?.total || 0
  } finally {
    loading.value = false
  }
}

function resetSearch() {
  keyword.value = ''
  pagination.page = 1
  loadList()
}

function goCreate() {
  router.push({ name: 'appFragmentNew' })
}

function goEdit(id) {
  router.push({ name: 'appFragmentEdit', params: { id } })
}

async function handleDelete(row) {
  const projectId = proStore.projectInfo.id
  try {
    await ElMessageBox.confirm(`确定删除片段「${row.name}」？`, '提示', { type: 'warning' })
    await appFragmentApi.remove(row.id, projectId)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
    const detail = e?.response?.data?.detail
    if (detail?.message) {
      ElMessage.error(detail.message)
    }
  }
}

onMounted(loadList)
onActivated(loadList)
</script>

<style scoped>
.page-title-row { display: flex; justify-content: space-between; width: 100%; }
.search-bar { display: flex; gap: 8px; margin-bottom: 16px; }
.pagination { margin-top: 16px; justify-content: flex-end; }
</style>
