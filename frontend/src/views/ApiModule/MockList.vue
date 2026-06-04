<template>
  <PageCard>
    <template #title>
      <el-button type="primary" size="small" icon="Plus" @click="handleAdd">新建 Mock</el-button>
    </template>
    <template #main>
      <div class="mock-list">
        <!-- 搜索栏 -->
        <div class="search-bar">
          <el-input
            v-model="keyword"
            placeholder="搜索名称"
            clearable
            style="width: 200px;"
            @keyup.enter="getMockList"
          />
          <el-button type="primary" icon="Search" @click="getMockList">搜索</el-button>
          <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
        </div>

        <!-- 列表 -->
        <el-table :data="mockList" stripe v-loading="loading">
          <el-table-column type="index" label="序号" width="60" />
          <el-table-column label="名称" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span>{{ row.name }}</span>
              <el-tag v-if="!row.is_enabled" type="info" size="small" style="margin-left:6px">已禁用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="方法" width="90">
            <template #default="{ row }">
              <el-tag :type="getMethodType(row.method)" size="small">{{ row.method }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="匹配路径" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <code style="font-size:12px">{{ row.path }}</code>
            </template>
          </el-table-column>
          <el-table-column label="状态码" width="85" align="center">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.response_status)" size="small">{{ row.response_status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="延迟(ms)" width="90" align="center" prop="response_delay" />
          <el-table-column label="调用次数" width="90" align="center" prop="call_count" />
          <el-table-column label="最后调用" width="150">
            <template #default="{ row }">
              {{ row.last_call_time ? formatTime(row.last_call_time) : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="启用" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.is_enabled"
                @change="handleToggle(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" icon="Edit" @click="handleEdit(row)" />
              <el-button size="small" type="danger" icon="Delete" @click="handleDelete(row)" />
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="getMockList"
          @current-change="getMockList"
          class="pagination"
        />
      </div>
    </template>
  </PageCard>

  <MockDialog
    v-model="dialog.visible"
    :data="dialog.data"
    :project-id="proStore.projectInfo.id"
    @success="getMockList"
  />
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { httpMockApi } from '@/api/modules/http'
import dateTools from '@/tools/dateTools'
import PageCard from '@/components/PageCard.vue'
import MockDialog from './components/MockDialog.vue'

const proStore = ProjectStore()

const keyword = ref('')
const loading = ref(false)
const mockList = ref([])
const dialog = reactive({ visible: false, data: null })
const pagination = reactive({ page: 1, size: 20, total: 0 })

const getMockList = async () => {
  loading.value = true
  try {
    const params = {
      project_id: proStore.projectInfo.id,
      page: pagination.page,
      size: pagination.size
    }
    if (keyword.value) params.keyword = keyword.value
    const res = await httpMockApi.getList(params)
    if (res.status === 200) {
      mockList.value = res.data.data || []
      pagination.total = res.data.total
    }
  } catch (err) {
    ElMessage.error('获取 Mock 列表失败')
  } finally {
    loading.value = false
  }
}

const resetSearch = () => {
  keyword.value = ''
  pagination.page = 1
  getMockList()
}

const handleAdd = () => {
  dialog.data = null
  dialog.visible = true
}

const handleEdit = (row) => {
  dialog.data = row
  dialog.visible = true
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除 Mock「${row.name}」吗？`, '提示', { type: 'warning' })
    await httpMockApi.delete(row.id)
    ElMessage.success('删除成功')
    getMockList()
  } catch (err) {
    if (err !== 'cancel') ElMessage.error('删除失败')
  }
}

const handleToggle = async (row) => {
  try {
    const res = await httpMockApi.toggle(row.id)
    if (res.status === 200) {
      row.is_enabled = res.data.is_enabled
      ElMessage.success(res.data.is_enabled ? '已启用' : '已禁用')
    }
  } catch (err) {
    ElMessage.error('切换失败')
  }
}

const getMethodType = (method) => {
  const map = { GET: 'success', POST: 'primary', PUT: 'warning', DELETE: 'danger', PATCH: 'info' }
  return map[method] || ''
}

const getStatusType = (code) => {
  if (code >= 500) return 'danger'
  if (code >= 400) return 'warning'
  if (code >= 300) return 'info'
  return 'success'
}

const formatTime = (t) => dateTools.rTime(t)

onMounted(() => getMockList())
</script>

<style scoped lang="scss">
.mock-list {
  .search-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 15px;
  }
  .pagination {
    margin-top: 15px;
    display: flex;
    justify-content: flex-end;
  }
}
</style>
