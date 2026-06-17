<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>步骤片段</span>
        <el-button type="primary" size="small" icon="Plus" @click="goCreate">新建片段</el-button>
      </div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #title>
          步骤片段是可复用的步骤序列（如登录、导航）。用例/套件中「插入片段」后保存引用，执行时由平台自动展开。
        </template>
      </el-alert>

      <div class="search-bar">
        <el-input v-model="keyword" placeholder="搜索片段名称" clearable style="width: 220px;" @keyup.enter="loadList" />
        <el-input v-model="tagFilter" placeholder="分类标签" clearable style="width: 140px;" @keyup.enter="loadList" />
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
        <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
      </div>

      <el-table :data="list" stripe v-loading="loading" border>
        <el-table-column prop="name" label="片段名称" min-width="140" show-overflow-tooltip />
        <el-table-column prop="tags" label="分类" width="100" show-overflow-tooltip />
        <el-table-column label="步骤数" width="90" align="center">
          <template #default="{ row }">{{ row.step_count }}</template>
        </el-table-column>
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }">v{{ row.version }}</template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column prop="update_by" label="更新人" width="100" />
        <el-table-column label="更新时间" width="168">
          <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
        </el-table-column>
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
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        class="pagination"
        @size-change="loadList"
        @current-change="loadList"
      />
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { uiFragmentApi } from '@/api/modules/ui'
import { ProjectStore } from '@/stores/module/ProjectStore'
import dateTools from '@/tools/dateTools'

const formatTime = (val) => (val ? dateTools.rTime(val) : '—')

const router = useRouter()
const proStore = ProjectStore()
const loading = ref(false)
const list = ref([])
const keyword = ref('')
const tagFilter = ref('')
const pagination = reactive({ page: 1, size: 20, total: 0 })

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await uiFragmentApi.getList({
      project_id: projectId,
      keyword: keyword.value || undefined,
      tag: tagFilter.value || undefined,
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
  tagFilter.value = ''
  pagination.page = 1
  loadList()
}

function goCreate() {
  router.push('/ui-fragments/new')
}

function goEdit(id) {
  router.push(`/ui-fragments/edit/${id}`)
}

async function handleDelete(row) {
  const projectId = proStore.projectInfo.id
  let refs = { total: 0, case_count: 0, suite_count: 0, cases: [] }
  try {
    const refRes = await uiFragmentApi.getReferences(row.id, projectId)
    refs = refRes.data?.data || refs
  } catch {
    /* 引用统计失败时不阻断 */
  }

  let refHint = ''
  if (refs.total > 0) {
    const parts = []
    if (refs.case_count) parts.push(`${refs.case_count} 条用例`)
    if (refs.suite_count) parts.push(`${refs.suite_count} 个套件前置`)
    refHint = `\n\n该片段正被 ${parts.join('、')} 引用，删除后这些位置执行会失败。`
    if (refs.cases?.length) {
      refHint += `\n用例：${refs.cases.slice(0, 5).map((c) => c.name).join('、')}${refs.case_count > 5 ? '…' : ''}`
    }
  }

  try {
    await ElMessageBox.confirm(`确定删除片段「${row.name}」？${refHint}`, '提示', { type: 'warning' })
  } catch {
    return
  }

  if (refs.total > 0) {
    try {
      await ElMessageBox.confirm('仍要删除该片段吗？引用处执行时将报错。', '存在引用', {
        type: 'error',
        confirmButtonText: '强制删除',
        cancelButtonText: '取消',
      })
    } catch {
      return
    }
    await uiFragmentApi.delete(row.id, projectId, true)
  } else {
    await uiFragmentApi.delete(row.id, projectId)
  }
  ElMessage.success('已删除')
  loadList()
}

onMounted(loadList)
onActivated(loadList)
</script>

<style scoped>
.page-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.search-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
