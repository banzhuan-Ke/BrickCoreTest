<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>测试文件</span>
        <div class="title-actions">
          <template v-if="activeTab === 'files'">
            <el-upload
              :show-file-list="false"
              :auto-upload="false"
              :on-change="onUploadChange"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,.zip,.xmind,.json"
            >
              <el-button type="primary" size="small" icon="Upload" :loading="uploading">上传文件</el-button>
            </el-upload>
            <el-button size="small" icon="Search" @click="scanLegacy">扫描本地路径步骤</el-button>
          </template>
          <template v-else>
            <input
              ref="folderInputRef"
              type="file"
              webkitdirectory
              directory
              multiple
              class="hidden-folder-input"
              @change="onFolderUploadChange"
            />
            <el-button type="primary" size="small" icon="Upload" :loading="folderUploading" @click="triggerFolderUpload">
              上传文件夹
            </el-button>
          </template>
        </div>
      </div>
    </template>
    <template #main>
      <el-tabs v-model="activeTab" class="resource-tabs" @tab-change="onTabChange">
        <el-tab-pane label="单文件" name="files" />
        <el-tab-pane label="文件夹" name="folders" />
      </el-tabs>

      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #title>
          <template v-if="activeTab === 'files'">
            Web 自动化「input 文件上传」步骤可在此上传测试素材（存 MinIO <code>ui-test-files</code>），任意 Runner 执行前会自动下载到本地。
            仍可使用环境变量 <code v-pre>${{files_path}}</code> 指向 Runner 本机目录（单机兼容模式）。
          </template>
          <template v-else>
            文件夹上传保留相对路径，适用于 <code>webkitdirectory</code> 目录选择场景；步骤编辑器中选择「文件夹」模式并绑定此处资源。
          </template>
        </template>
      </el-alert>

      <!-- 单文件列表 -->
      <template v-if="activeTab === 'files'">
        <div class="search-bar">
          <el-input v-model="keyword" placeholder="搜索文件名" clearable style="width: 220px;" @keyup.enter="loadList" />
          <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
          <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
        </div>

        <el-table :data="list" stripe v-loading="loading" border>
          <el-table-column prop="file_name" label="文件名" min-width="160" show-overflow-tooltip />
          <el-table-column label="关联引用" min-width="240">
            <template #default="{ row }">
              <TestFileRefTags :refs="row.references" mode="ui" @detail="showRefs(row)" />
            </template>
          </el-table-column>
          <el-table-column label="大小" width="100" align="right">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column prop="mime_type" label="类型" width="140" show-overflow-tooltip />
          <el-table-column prop="username" label="上传人" width="100" />
          <el-table-column label="上传时间" width="168">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right" align="center">
            <template #default="{ row }">
              <TestFileActions
                :file-id="row.id"
                :project-id="proStore.projectInfo?.id"
                :file-name="row.file_name"
                :mime-type="row.mime_type"
                :fetch-url="uiTestFileApi.getDownloadUrl"
                :fetch-preview="uiTestFileApi.getPreviewContent"
              />
              <el-tooltip
                v-if="row.references?.total"
                content="存在关联引用，请先在用例/套件/片段中解除绑定后再删除"
                placement="top"
              >
                <el-button size="small" type="danger" link disabled>删除</el-button>
              </el-tooltip>
              <el-button v-else size="small" type="danger" link @click="handleDelete(row)">删除</el-button>
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

      <!-- 文件夹列表 -->
      <template v-else>
        <div class="search-bar">
          <el-input v-model="folderKeyword" placeholder="搜索文件夹名" clearable style="width: 220px;" @keyup.enter="loadFolderList" />
          <el-button type="primary" icon="Search" @click="loadFolderList">搜索</el-button>
          <el-button icon="RefreshRight" @click="resetFolderSearch">重置</el-button>
        </div>

        <el-table :data="folderList" stripe v-loading="folderLoading" border>
          <el-table-column prop="folder_name" label="文件夹名" min-width="160" show-overflow-tooltip />
          <el-table-column label="关联引用" min-width="240">
            <template #default="{ row }">
              <TestFileRefTags :refs="row.references" mode="ui" @detail="showFolderRefs(row)" />
            </template>
          </el-table-column>
          <el-table-column label="文件数" width="80" align="center" prop="file_count" />
          <el-table-column label="总大小" width="100" align="right">
            <template #default="{ row }">{{ formatSize(row.total_size) }}</template>
          </el-table-column>
          <el-table-column prop="username" label="上传人" width="100" />
          <el-table-column label="上传时间" width="168">
            <template #default="{ row }">{{ formatTime(row.create_time) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="showFolderEntries(row)">文件清单</el-button>
              <el-tooltip
                v-if="row.references?.total"
                content="存在关联引用，请先在用例/套件/片段中解除绑定后再删除"
                placement="top"
              >
                <el-button size="small" type="danger" link disabled>删除</el-button>
              </el-tooltip>
              <el-button v-else size="small" type="danger" link @click="handleFolderDelete(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="folderPagination.page"
          v-model:page-size="folderPagination.size"
          :total="folderPagination.total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          class="pagination"
          @size-change="loadFolderList"
          @current-change="loadFolderList"
        />
      </template>

      <el-dialog v-model="refsVisible" :title="`关联引用：${refsRow?.file_name || ''}`" width="680px">
        <p v-if="!refsData.total">暂无用例、套件或片段引用此文件。</p>
        <template v-else>
          <p class="refs-summary">
            共 {{ refsData.total }} 处引用（用例 {{ refsData.case_count }}，套件 {{ refsData.suite_count }}，片段 {{ refsData.fragment_count }}）
          </p>
          <el-table v-if="refsData.cases?.length" :data="refsData.cases" size="small" border style="margin-bottom: 12px;">
            <el-table-column label="用例" min-width="200">
              <template #default="{ row }">
                <router-link :to="`/case/edit/${row.id}`" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
          <el-table v-if="refsData.suites?.length" :data="refsData.suites" size="small" border style="margin-bottom: 12px;">
            <el-table-column label="套件" min-width="200">
              <template #default="{ row }">
                <router-link :to="`/suite/edit/${row.id}`" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
          <el-table v-if="refsData.fragments?.length" :data="refsData.fragments" size="small" border>
            <el-table-column label="片段" min-width="200">
              <template #default="{ row }">
                <router-link :to="`/ui-fragments/edit/${row.id}`" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-dialog>

      <el-dialog v-model="legacyVisible" title="仍使用 Runner 本地 files_path 的上传步骤" width="820px">
        <el-alert
          v-if="legacyScan.unique_filenames?.length"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
        >
          请在上方上传同名文件后，到用例步骤编辑器中为「input 文件上传」步骤重新选择平台文件。
        </el-alert>
        <p v-if="!legacyScan.total">未发现 legacy 步骤，或已全部迁移到 MinIO。</p>
        <el-table v-else :data="legacyScan.items" size="small" border max-height="420">
          <el-table-column prop="source_type" label="来源" width="90">
            <template #default="{ row }">{{ sourceLabel(row.source_type) }}</template>
          </el-table-column>
          <el-table-column prop="source_name" label="名称" min-width="120" show-overflow-tooltip />
          <el-table-column prop="step_desc" label="步骤" min-width="140" show-overflow-tooltip />
          <el-table-column prop="suggested_filename" label="建议上传文件名" min-width="160" show-overflow-tooltip />
          <el-table-column prop="file_path" label="当前路径表达式" min-width="200" show-overflow-tooltip />
        </el-table>
      </el-dialog>

      <el-dialog v-model="folderRefsVisible" :title="`关联引用：${folderRefsRow?.folder_name || ''}`" width="680px">
        <p v-if="!folderRefsData.total">暂无用例、套件或片段引用此文件夹。</p>
        <template v-else>
          <p class="refs-summary">
            共 {{ folderRefsData.total }} 处引用（用例 {{ folderRefsData.case_count }}，套件 {{ folderRefsData.suite_count }}，片段 {{ folderRefsData.fragment_count }}）
          </p>
          <el-table v-if="folderRefsData.cases?.length" :data="folderRefsData.cases" size="small" border style="margin-bottom: 12px;">
            <el-table-column label="用例" min-width="200">
              <template #default="{ row }">
                <router-link :to="`/case/edit/${row.id}`" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
          <el-table v-if="folderRefsData.suites?.length" :data="folderRefsData.suites" size="small" border style="margin-bottom: 12px;">
            <el-table-column label="套件" min-width="200">
              <template #default="{ row }">
                <router-link :to="`/suite/edit/${row.id}`" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
          <el-table v-if="folderRefsData.fragments?.length" :data="folderRefsData.fragments" size="small" border>
            <el-table-column label="片段" min-width="200">
              <template #default="{ row }">
                <router-link :to="`/ui-fragments/edit/${row.id}`" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-dialog>

      <el-dialog v-model="folderEntriesVisible" :title="`文件清单：${folderEntriesRow?.folder_name || ''}`" width="720px">
        <el-table :data="folderEntriesRow?.entries || []" size="small" border max-height="420">
          <el-table-column prop="relative_path" label="相对路径" min-width="280" show-overflow-tooltip />
          <el-table-column label="大小" width="100" align="right">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column prop="mime_type" label="类型" width="160" show-overflow-tooltip />
        </el-table>
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, onMounted, onActivated } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import TestFileRefTags from '@/components/TestFileRefTags.vue'
import TestFileActions from '@/components/TestFileActions.vue'
import { uiTestFileApi } from '@/api/modules/uiTestFile'
import { uiTestFolderApi } from '@/api/modules/uiTestFolder'
import { ProjectStore } from '@/stores/module/ProjectStore'
import dateTools from '@/tools/dateTools'

const formatTime = (val) => (val ? dateTools.rTime(val) : '—')
const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const proStore = ProjectStore()
const activeTab = ref('files')
const loading = ref(false)
const uploading = ref(false)
const list = ref([])
const keyword = ref('')
const pagination = reactive({ page: 1, size: 20, total: 0 })
const folderLoading = ref(false)
const folderUploading = ref(false)
const folderList = ref([])
const folderKeyword = ref('')
const folderPagination = reactive({ page: 1, size: 20, total: 0 })
const folderInputRef = ref(null)
const legacyVisible = ref(false)
const legacyScan = ref({ total: 0, items: [], unique_filenames: [] })
const refsVisible = ref(false)
const refsRow = ref(null)
const refsData = ref({
  total: 0,
  case_count: 0,
  suite_count: 0,
  fragment_count: 0,
  cases: [],
  suites: [],
  fragments: [],
})
const folderRefsVisible = ref(false)
const folderRefsRow = ref(null)
const folderRefsData = ref({
  total: 0,
  case_count: 0,
  suite_count: 0,
  fragment_count: 0,
  cases: [],
  suites: [],
  fragments: [],
})
const folderEntriesVisible = ref(false)
const folderEntriesRow = ref(null)

function sourceLabel(type) {
  return { case: '用例', suite: '套件', fragment: '片段' }[type] || type
}

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await uiTestFileApi.getList({
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

async function showRefs(row) {
  refsRow.value = row
  if (row.references) {
    refsData.value = row.references
    refsVisible.value = true
    return
  }
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  try {
    const res = await uiTestFileApi.getReferences(row.id, projectId)
    refsData.value = res.data?.data || { total: 0, cases: [], suites: [], fragments: [] }
    refsVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '查询引用失败')
  }
}

async function onUploadChange(uploadFile) {
  const projectId = proStore.projectInfo?.id
  const raw = uploadFile?.raw
  if (!projectId || !raw) return
  uploading.value = true
  try {
    const res = await uiTestFileApi.upload(projectId, raw)
    if (res.data?.code !== 200) {
      ElMessage.error(res.data?.message || '上传失败')
      return
    }
    ElMessage.success('上传成功')
    await loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleDelete(row) {
  const refs = row.references || { total: 0 }
  if (refs.total > 0) {
    ElMessage.warning(`文件「${row.file_name}」仍被 ${refs.total} 处引用，请先在关联用例/套件/片段中解除绑定`)
    showRefs(row)
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除文件「${row.file_name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await uiTestFileApi.delete(row.id, proStore.projectInfo.id, false)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : detail?.message || '删除失败')
  }
}

async function scanLegacy() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  try {
    const res = await uiTestFileApi.migrationScan(projectId)
    legacyScan.value = res.data?.data || { total: 0, items: [], unique_filenames: [] }
    legacyVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '扫描失败')
  }
}

function onTabChange(name) {
  if (name === 'folders') loadFolderList()
  else loadList()
}

async function loadFolderList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  folderLoading.value = true
  try {
    const res = await uiTestFolderApi.getList({
      project_id: projectId,
      keyword: folderKeyword.value || undefined,
      page: folderPagination.page,
      size: folderPagination.size,
    })
    folderList.value = res.data?.data?.items || []
    folderPagination.total = res.data?.data?.total || 0
  } finally {
    folderLoading.value = false
  }
}

function resetFolderSearch() {
  folderKeyword.value = ''
  folderPagination.page = 1
  loadFolderList()
}

function triggerFolderUpload() {
  folderInputRef.value?.click()
}

async function onFolderUploadChange(event) {
  const projectId = proStore.projectInfo?.id
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!projectId || !files.length) return
  const rootName = (files[0].webkitRelativePath || files[0].name || '').split('/')[0]
  folderUploading.value = true
  try {
    const res = await uiTestFolderApi.upload(projectId, files, rootName)
    if (res.data?.code !== 200) {
      ElMessage.error(res.data?.message || '上传失败')
      return
    }
    ElMessage.success(`文件夹上传成功（${res.data?.data?.file_count || files.length} 个文件）`)
    await loadFolderList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || '上传失败')
  } finally {
    folderUploading.value = false
  }
}

async function showFolderRefs(row) {
  folderRefsRow.value = row
  if (row.references) {
    folderRefsData.value = row.references
    folderRefsVisible.value = true
    return
  }
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  try {
    const res = await uiTestFolderApi.getReferences(row.id, projectId)
    folderRefsData.value = res.data?.data || { total: 0, cases: [], suites: [], fragments: [] }
    folderRefsVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '查询引用失败')
  }
}

function showFolderEntries(row) {
  folderEntriesRow.value = row
  folderEntriesVisible.value = true
}

async function handleFolderDelete(row) {
  const refs = row.references || { total: 0 }
  if (refs.total > 0) {
    ElMessage.warning(`文件夹「${row.folder_name}」仍被 ${refs.total} 处引用，请先在关联用例/套件/片段中解除绑定`)
    showFolderRefs(row)
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除文件夹「${row.folder_name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await uiTestFolderApi.delete(row.id, proStore.projectInfo.id, false)
    ElMessage.success('已删除')
    loadFolderList()
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : detail?.message || '删除失败')
  }
}

onMounted(loadList)
onActivated(() => {
  if (activeTab.value === 'folders') loadFolderList()
  else loadList()
})
</script>

<style scoped lang="scss">
.page-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.title-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.search-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
.refs-summary {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.ref-link {
  color: var(--el-color-primary);
  text-decoration: none;
  &:hover {
    text-decoration: underline;
  }
}
.hidden-folder-input {
  display: none;
}
.resource-tabs {
  margin-bottom: 8px;
}
</style>
