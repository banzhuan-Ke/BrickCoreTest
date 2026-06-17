<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>测试文件</span>
        <div class="title-actions">
          <el-upload
            :show-file-list="false"
            :auto-upload="false"
            :on-change="onUploadChange"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.gif,.webp,.zip,.json,.pem,.p12,.pfx,.cer,.crt,.key"
          >
            <el-button type="primary" size="small" icon="Upload" :loading="uploading">上传文件</el-button>
          </el-upload>
        </div>
      </div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #title>
          接口 form-data 文件字段可在此集中上传（存 MinIO <code>api-test-files</code>，按当前项目隔离），多个接口/用例可复用同一文件。
        </template>
      </el-alert>

      <div class="search-bar">
        <el-input v-model="keyword" placeholder="搜索文件名" clearable style="width: 220px;" @keyup.enter="loadList" />
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
        <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
      </div>

      <el-table :data="list" stripe v-loading="loading" border>
        <el-table-column prop="file_name" label="文件名" min-width="160" show-overflow-tooltip />
        <el-table-column label="关联引用" min-width="240">
          <template #default="{ row }">
            <TestFileRefTags :refs="row.references" mode="api" @detail="showRefs(row)" />
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
              :fetch-url="apiTestFileApi.getDownloadUrl"
              :fetch-preview="apiTestFileApi.getPreviewContent"
            />
            <el-tooltip
              v-if="row.references?.total"
              content="存在关联引用，请先在接口/用例中解除绑定后再删除"
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

      <el-dialog v-model="refsVisible" :title="`关联引用：${refsRow?.file_name || ''}`" width="640px">
        <p v-if="!refsData.total">暂无接口或用例引用此文件。</p>
        <template v-else>
          <p class="refs-summary">共 {{ refsData.total }} 处引用（接口 {{ refsData.api_count }}，用例 {{ refsData.case_count }}）</p>
          <el-table v-if="refsData.apis?.length" :data="refsData.apis" size="small" border style="margin-bottom: 12px;">
            <el-table-column label="接口" min-width="200">
              <template #default="{ row }">
                <router-link :to="{ path: '/api-module', query: { api_id: String(row.id) } }" class="ref-link">{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
          <el-table v-if="refsData.cases?.length" :data="refsData.cases" size="small" border>
            <el-table-column label="用例" min-width="200">
              <template #default="{ row }">
                <router-link
                  :to="{ path: '/api-case', query: { api_id: String(row.api_id || ''), edit_case_id: String(row.id) } }"
                  class="ref-link"
                >{{ row.name }} (#{{ row.id }})</router-link>
              </template>
            </el-table-column>
          </el-table>
        </template>
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
import { apiTestFileApi } from '@/api/modules/apiTestFile'
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
const loading = ref(false)
const uploading = ref(false)
const list = ref([])
const keyword = ref('')
const pagination = reactive({ page: 1, size: 20, total: 0 })
const refsVisible = ref(false)
const refsRow = ref(null)
const refsData = ref({ total: 0, api_count: 0, case_count: 0, apis: [], cases: [] })

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const res = await apiTestFileApi.getList({
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
    const res = await apiTestFileApi.getReferences(row.id, projectId)
    refsData.value = res.data?.data || { total: 0, apis: [], cases: [] }
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
    await apiTestFileApi.upload(projectId, raw)
    ElMessage.success('上传成功')
    await loadList()
  } catch (e) {
    const data = e?.response?.data ?? e?.data
    const detail = data?.detail
    const msg = typeof detail === 'string' ? detail : detail?.message || data?.message
    if (msg && e?.status !== 403) {
      // 403 已由全局拦截器提示权限不足
      ElMessage.error(msg)
    }
  } finally {
    uploading.value = false
  }
}

async function handleDelete(row) {
  const refs = row.references || { total: 0 }
  if (refs.total > 0) {
    ElMessage.warning(`文件「${row.file_name}」仍被 ${refs.total} 处引用，请先在关联接口/用例中解除绑定`)
    showRefs(row)
    return
  }
  try {
    await ElMessageBox.confirm(`确定删除文件「${row.file_name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await apiTestFileApi.delete(row.id, proStore.projectInfo.id, false)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : detail?.message || '删除失败')
  }
}

onMounted(loadList)
onActivated(loadList)
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
</style>
