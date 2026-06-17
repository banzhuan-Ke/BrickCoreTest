<template>
  <PageCard>
    <template #title>
      <div style="display: flex; gap: 10px;">
        <el-button type="primary" size="small" @click="handleAdd" icon="Plus">接口</el-button>
        <el-button type="success" size="small" @click="handleImport" icon="Upload">导入</el-button>
      </div>
    </template>
    
    <template #main>
      <div class="api-list-container">
        <!-- 左侧测试目录 -->
        <div class="category-tree">
          <CatalogTree
            :project-id="proStore.projectInfo.id"
            v-model="currentCatalogId"
            :show-manage="true"
            all-node-label="全部接口"
            @change="handleCatalogFilter"
          />
        </div>
        
        <!-- 右侧接口列表 -->
        <div class="api-table">
          <div class="search-bar">
            <el-input
              v-model="searchForm.keyword"
              placeholder="搜索接口名称/路径"
              clearable
              style="width: 250px;"
              @keyup.enter="getApiList"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-select v-model="searchForm.method" placeholder="请求方法" clearable style="width: 120px;">
              <el-option label="WS" value="WS"/>
              <el-option label="GET" value="GET"/>
              <el-option label="POST" value="POST"/>
              <el-option label="PUT" value="PUT"/>
              <el-option label="DELETE" value="DELETE"/>
              <el-option label="PATCH" value="PATCH"/>
            </el-select>
            <el-button type="primary" @click="getApiList" icon="Search">搜索</el-button>
            <el-button @click="resetSearch" icon="RefreshRight">重置</el-button>
            <el-checkbox v-model="showFavoritesOnly" @change="getApiList">只看收藏</el-checkbox>
            <el-button
              v-if="selectedApis.length > 0"
              type="warning"
              @click="handleBatchAiGenerate"
              icon="MagicStick"
            >批量AI生成({{ selectedApis.length }})</el-button>
            <el-button
              v-if="selectedApis.length > 0"
              type="danger"
              @click="handleBatchDelete"
              icon="Delete"
            >批量删除({{ selectedApis.length }})</el-button>
          </div>
          
          <el-table :data="apiList" stripe v-loading="loading" @selection-change="handleSelectionChange">
            <el-table-column type="selection" width="50" align="center" />
            <el-table-column label="收藏" width="52" align="center">
              <template #default="{ row }">
                <el-button link :type="isFavorite(row.id) ? 'warning' : 'info'" @click.stop="toggleFavorite(row.id)">
                  <el-icon><StarFilled v-if="isFavorite(row.id)" /><Star v-else /></el-icon>
                </el-button>
              </template>
            </el-table-column>
            <el-table-column type="index" :index="tableRowIndex" width="50"/>
            <el-table-column label="请求方法" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.protocol === 'websocket'" type="warning" size="small">WS</el-tag>
                <el-tag v-else :type="getMethodType(row.method)" size="small">{{ row.method }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="接口名称" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="api-name-text">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="接口路径" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <code class="api-path-code">{{ row.path }}</code>
              </template>
            </el-table-column>
            <el-table-column label="所属目录" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.catalog_name || row.category_name" type="info" size="small">
                  {{ row.catalog_name || row.category_name }}
                </el-tag>
                <span v-else style="color: #999;">-</span>
              </template>
            </el-table-column>
            <el-table-column label="关联用例" width="100" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="(row.case_count ?? 0) > 0"
                  type="primary"
                  link
                  @click="openLinkedCases(row)"
                >
                  {{ row.case_count }} 个
                </el-button>
                <span v-else class="muted-text">0</span>
              </template>
            </el-table-column>
            <el-table-column label="创建人" width="100">
              <template #default="{ row }">
                {{ row.create_by || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="修改人" width="100">
              <template #default="{ row }">
                {{ row.update_by || row.create_by || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="更新时间" width="150">
              <template #default="{ row }">
                {{ formatTime(row.update_time) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="248" fixed="right">
              <template #default="{ row }">
                <el-button-group>
                  <el-button size="small" type="primary" @click="handleDebug(row)" icon="Promotion" title="调试"/>
                  <el-button size="small" type="warning" @click="handleAiGenerate(row)" icon="MagicStick" title="AI生成"/>
                  <el-button size="small" type="success" @click="handleEdit(row)" icon="Edit" title="编辑"/>
                  <el-button size="small" type="info" @click="openCopyDialog(row)" icon="CopyDocument" title="复制到其他项目"/>
                  <el-button size="small" type="danger" @click="handleDelete(row)" icon="Delete" title="删除"/>
                </el-button-group>
              </template>
            </el-table-column>
          </el-table>
          
          <el-pagination
            v-model:current-page="pagination.page"
            v-model:page-size="pagination.size"
            :total="pagination.total"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            @size-change="getApiList"
            @current-change="getApiList"
            class="pagination"
          />
        </div>
      </div>
    </template>
  </PageCard>
  
  <!-- 同步差异对比弹窗 -->
  <ApiSyncDiffDialog
    v-model="syncDiffDialog.visible"
    :api-data="syncDiffDialog.apiData"
    :diff-data="syncDiffDialog.diffData"
  />
  
  <!-- 接口编辑弹窗 -->
  <ApiEdit
    v-model="editDialog.visible"
    :data="editDialog.data"
    @success="handleEditSuccess"
  />
  
  <!-- 导入弹窗 -->
  <ApiImport
    v-model="importDialog.visible"
    @success="getApiList"
  />
  
  <!-- 调试弹窗 -->
  <ApiDebug
    v-model="debugDialog.visible"
    :api="debugDialog.data"
  />
  
  <!-- AI 生成用例弹窗 -->
  <ApiCaseGenerator
    v-model="aiDialog.visible"
    :api-data="aiDialog.data"
    @success="handleAiSuccess"
  />

  <!-- 批量 AI 生成 -->
  <ApiBatchCaseGenerator
    v-model="batchAiDialog.visible"
    :apis="selectedApis"
    @success="handleAiSuccess"
  />

  <!-- 关联用例 -->
  <el-drawer
    v-model="linkedDrawer.visible"
    :title="`关联用例 - ${linkedDrawer.api?.name || ''}`"
    size="520px"
    destroy-on-close
  >
    <el-table :data="linkedDrawer.list" v-loading="linkedDrawer.loading" stripe size="small">
      <el-table-column type="index" width="50" />
      <el-table-column label="用例名称" prop="name" min-width="160" show-overflow-tooltip />
      <el-table-column label="优先级" width="72" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="getPriorityType(row.priority)">{{ row.priority }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="editLinkedCase(row)">编辑</el-button>
          <el-button type="info" link size="small" @click="goCaseList(row)">列表</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="linked-drawer-footer">
      <el-button type="primary" @click="goCaseList()">前往用例管理</el-button>
    </div>
  </el-drawer>

  <CaseEdit
    v-model="linkedCaseEdit.visible"
    :data="linkedCaseEdit.data"
    @success="onLinkedCaseSaved"
  />

  <CopyToProjectDialog
    v-model="copyDialog.visible"
    title="复制接口到其他项目"
    :asset-name="copyDialog.row?.name"
    :submit-fn="submitCopyApi"
    @success="getApiList"
  />
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Star, StarFilled } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { ProjectStore } from '@/stores/module/ProjectStore'
import http from '@/api/index'
import { httpApi } from '@/api/modules/http'
import dateTools from '@/tools/dateTools'
import PageCard from '@/components/PageCard.vue'
import CatalogTree from '@/components/CatalogTree.vue'
import ApiEdit from './components/ApiEdit.vue'
import ApiImport from './components/ApiImport.vue'
import ApiDebug from './components/ApiDebug.vue'
import ApiCaseGenerator from '@/views/AI/components/ApiCaseGenerator.vue'
import ApiBatchCaseGenerator from '@/views/AI/components/ApiBatchCaseGenerator.vue'
import ApiSyncDiffDialog from './components/ApiSyncDiffDialog.vue'
import CaseEdit from './components/CaseEdit.vue'
import CopyToProjectDialog from '@/components/CopyToProjectDialog.vue'
import { useAssetFavorites } from '@/composables/useAssetFavorites'
import { makeTableRowIndex } from '@/utils/tableIndex'

const route = useRoute()
const router = useRouter()
const proStore = ProjectStore()
const { loadFavorites, isFavorite, toggleFavorite, sortByFavorites } = useAssetFavorites('api')
const showFavoritesOnly = ref(false)
const copyDialog = reactive({ visible: false, row: null })

const currentCatalogId = ref(null)

// 搜索表单
const searchForm = reactive({
  keyword: '',
  method: ''
})

// 分页
const pagination = reactive({
  page: 1,
  size: 20,
  total: 0
})

const tableRowIndex = makeTableRowIndex(pagination)

// 接口列表
const apiList = ref([])
const loading = ref(false)

// 弹窗控制
const editDialog = reactive({ visible: false, data: null })
const importDialog = reactive({ visible: false })
const debugDialog = reactive({ visible: false, data: null })
const aiDialog = reactive({ visible: false, data: null })
const batchAiDialog = reactive({ visible: false })
const syncDiffDialog = reactive({ visible: false, apiData: null, diffData: null })
const selectedApis = ref([])
const linkedDrawer = reactive({ visible: false, api: null, list: [], loading: false })
const linkedCaseEdit = reactive({ visible: false, data: null })

const getPriorityType = (priority) => {
  const map = { P0: 'danger', P1: 'warning', P2: '', P3: 'info' }
  return map[priority] || ''
}

const openLinkedCases = async (row) => {
  linkedDrawer.api = row
  linkedDrawer.visible = true
  linkedDrawer.loading = true
  linkedDrawer.list = []
  try {
    const res = await httpApi.getLinkedCases(row.id, { page: 1, size: 200 })
    linkedDrawer.list = res.data?.data || []
  } catch {
    ElMessage.error('加载关联用例失败')
  } finally {
    linkedDrawer.loading = false
  }
}

const editLinkedCase = async (caseRow) => {
  try {
    const res = await http.apiModuleApi.getTestCaseDetail(caseRow.id)
    const detail = res.data?.data ?? res.data
    if (detail) {
      linkedCaseEdit.data = detail
      linkedCaseEdit.visible = true
    }
  } catch {
    ElMessage.error('加载用例详情失败')
  }
}

const goCaseList = (caseRow = null) => {
  const query = { api_id: String(linkedDrawer.api?.id || '') }
  if (caseRow?.id) query.edit_case_id = String(caseRow.id)
  router.push({ path: '/api-case', query })
  linkedDrawer.visible = false
}

const onLinkedCaseSaved = () => {
  if (linkedDrawer.api?.id) openLinkedCases(linkedDrawer.api)
  getApiList()
}

const handleCatalogFilter = () => {
  pagination.page = 1
  getApiList()
}

// 获取接口列表
const handleEditSuccess = async () => {
  getApiList()
  // 编辑模式下检测关联用例同步状态
  if (editDialog.data?.id) {
    try {
      const res = await http.apiModuleApi.syncCheck(editDialog.data.id)
      const data = res.data
      const totalIssues = (data.diff_count || 0) + (data.warning_count || 0)
      if (totalIssues > 0) {
        const issueType = (data.diff_count || 0) > 0 ? '存在不一致' : '未完全覆盖'
        syncDiffDialog.apiData = editDialog.data
        syncDiffDialog.diffData = data
        syncDiffDialog.visible = true
      }
    } catch (e) {
      // 忽略 sync-check 错误，不影响主流程
    }
  }
}

const getApiList = async () => {
  loading.value = true
  try {
    await loadFavorites()
    const params = {
      project_id: proStore.projectInfo.id,
      page: pagination.page,
      size: pagination.size,
      keyword: searchForm.keyword || undefined,
      method: searchForm.method || undefined
    }
    if (currentCatalogId.value) {
      params.catalog_id = currentCatalogId.value
    }
    const res = await http.apiModuleApi.getApiList(params)
    if (res.status === 200) {
      let rows = res.data.data || []
      rows = sortByFavorites(rows)
      if (showFavoritesOnly.value) {
        rows = rows.filter((r) => isFavorite(r.id))
      }
      apiList.value = rows
      pagination.total = showFavoritesOnly.value ? rows.length : res.data.total
    }
  } catch (error) {
    ElMessage.error('获取接口列表失败')
  } finally {
    loading.value = false
  }
}

// 获取方法样式
const getMethodType = (method) => {
  const map = {
    'GET': 'success',
    'POST': 'primary',
    'PUT': 'warning',
    'DELETE': 'danger',
    'PATCH': 'info'
  }
  return map[method] || ''
}

// 格式化时间
const formatTime = (time) => {
  return time ? dateTools.rTime(time) : '-'
}

// 搜索重置
const resetSearch = () => {
  searchForm.keyword = ''
  searchForm.method = ''
  getApiList()
}

// 新增接口
const handleAdd = () => {
  editDialog.data = null
  editDialog.visible = true
}

// 编辑接口
const handleEdit = (row) => {
  // 深拷贝确保引用变化，触发子组件 watch
  editDialog.data = JSON.parse(JSON.stringify(row))
  editDialog.visible = true
}

// 删除接口
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该接口吗？', '提示', { type: 'warning' })
    const res = await http.apiModuleApi.deleteApi(row.id)
    if (res.status === 200 || res.status === 204) {
      ElMessage.success('删除成功')
      getApiList()
    }
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleSelectionChange = (selection) => {
  selectedApis.value = selection
}

const handleBatchDelete = async () => {
  if (selectedApis.value.length === 0) {
    ElMessage.warning('请选择要删除的接口')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedApis.value.length} 个接口吗？`,
      '警告',
      { type: 'warning' }
    )
    const ids = selectedApis.value.map(r => r.id)
    await http.apiModuleApi.batchDeleteApis(ids)
    ElMessage.success('批量删除成功')
    selectedApis.value = []
    getApiList()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error('批量删除失败')
    }
  }
}

// 导入
const handleImport = () => {
  importDialog.visible = true
}

// 调试
const handleDebug = (row) => {
  debugDialog.data = row
  debugDialog.visible = true
}

// AI 生成用例
const handleAiGenerate = (row) => {
  aiDialog.data = row
  aiDialog.visible = true
}

const handleBatchAiGenerate = () => {
  if (selectedApis.value.length === 0) {
    ElMessage.warning('请先选择接口')
    return
  }
  batchAiDialog.visible = true
}

const handleAiSuccess = () => {
  ElMessage.success('用例已导入，请前往接口用例页面查看')
}

const openCopyDialog = (row) => {
  copyDialog.row = row
  copyDialog.visible = true
}

const submitCopyApi = (payload) => httpApi.copyToProject(copyDialog.row.id, payload)

const applyRouteQuery = async () => {
  const apiId = route.query.api_id
  if (!apiId) return
  const id = Number(apiId)
  let row = apiList.value.find((a) => a.id === id)
  if (!row) {
    try {
      const res = await httpApi.getDetail(id)
      row = res.data?.data ?? res.data
    } catch {
      return
    }
  }
  if (row) handleEdit(row)
}

onMounted(async () => {
  await getApiList()
  await applyRouteQuery()
})

watch(
  () => route.query.api_id,
  async (apiId) => {
    if (!apiId) return
    await applyRouteQuery()
  },
)
</script>

<style scoped lang="scss">
.api-list-container {
  display: flex;
  gap: 20px;
  height: calc(100vh - 250px);
}

.category-tree {
  width: 250px;
  min-width: 250px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 15px;
  overflow-y: auto;
  
  .tree-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    
    .tree-title {
      font-weight: 600;
      font-size: 14px;
    }
  }
  
  .tree-node {
    display: flex;
    align-items: center;
    flex: 1;
    
    .el-icon {
      margin-right: 5px;
      color: var(--el-color-primary);
    }
    
    .node-label {
      flex: 1;
    }
    
    .node-actions {
      display: none;
    }
    
    &:hover .node-actions {
      display: flex;
    }
  }
}

.api-table {
  flex: 1;
  display: flex;
  flex-direction: column;
  
  .search-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 15px;
  }
  
  .api-path-code {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 13px;
    color: var(--el-color-primary);
    background: var(--el-fill-color-light);
    padding: 2px 6px;
    border-radius: 4px;
  }
  
  .api-name-text {
    font-weight: 500;
    color: var(--el-text-color-primary);
  }
  
  .pagination {
    margin-top: 15px;
    display: flex;
    justify-content: flex-end;
  }
}

.muted-text {
  color: var(--el-text-color-secondary);
}

.linked-drawer-footer {
  margin-top: 16px;
  text-align: right;
}
</style>
