<template>
  <div>
    <div class="toolbar">
      <el-dropdown split-button type="primary" @click="uploadVisible = true">
        新增需求
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="uploadVisible = true">上传需求文档（PDF/Word…）</el-dropdown-item>
            <el-dropdown-item @click="openXmindCreate">从 XMind 导入测试点</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button @click="loadList" icon="Refresh">刷新</el-button>
    </div>

    <el-table :data="reqList" v-loading="listLoading" stripe border style="margin-top: 12px;">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="需求名称" min-width="180">
        <template #default="{ row }">
          <div class="name-cell">
            <span class="name-text" :title="row.name">{{ row.name }}</span>
            <el-button
              v-if="canEdit"
              link
              type="primary"
              class="name-edit-btn"
              :icon="EditPen"
              @click="openRename(row)"
            />
          </div>
        </template>
      </el-table-column>
      <el-table-column label="关联文档" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">
          <template v-if="row.source_type === 'xmind'">
            <el-tag size="small" type="warning">XMind</el-tag>
            <span class="muted">{{ row.file_name || '思维导图导入' }}</span>
          </template>
          <template v-else-if="row.file_name">
            <el-tag size="small" type="info" style="margin-right: 6px;">文档</el-tag>
            {{ row.file_name }}
          </template>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="test_point_count" label="测试点" width="80" align="center" />
      <el-table-column prop="scheme_count" label="方案" width="70" align="center" />
      <el-table-column prop="case_count" label="用例" width="70" align="center" />
      <el-table-column prop="section_count" label="章节" width="70" align="center" />
      <el-table-column prop="update_time" label="更新时间" width="170" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openWorkspace(row)">进入工作台</el-button>
          <el-button link type="primary" @click="openXmindImportForRow(row)">导入 XMind</el-button>
          <el-button v-if="canDelete" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <input ref="xmindFileInput" type="file" accept=".xmind" style="display: none;" @change="onXmindFileSelected" />

    <el-dialog v-model="renameVisible" title="编辑需求名称" width="460px" destroy-on-close @closed="resetRenameForm">
      <el-form label-width="90px" @submit.prevent="handleRename">
        <el-form-item label="需求名称" required>
          <el-input
            v-model="renameForm.name"
            maxlength="200"
            show-word-limit
            placeholder="请输入需求名称"
            @keyup.enter="handleRename"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" :loading="renaming" @click="handleRename">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadVisible" title="上传需求文档" width="520px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="需求名称">
          <el-input v-model="uploadForm.name" placeholder="可选，默认取文件名" />
        </el-form-item>
        <el-form-item label="文档文件" required>
          <el-upload
            ref="uploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".pdf,.docx,.txt,.md"
            :on-change="onFileChange"
            :on-remove="() => uploadForm.file = null"
          >
            <el-button type="primary" icon="Upload">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">支持 PDF、Word(.docx)、TXT、Markdown；含图文档需配置 Vision 模型</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'
import { aiTestAnalysisApi } from '@/api/modules/ai.js'
import { aiRequirementApi } from '@/api/modules/ai.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const router = useRouter()
const proStore = ProjectStore()
const uStore = UserStore()
const canDelete = computed(() => uStore.hasPermission('ai_test:execute'))
const canEdit = computed(() => uStore.hasPermission('ai_test:execute'))
const reqList = ref([])
const listLoading = ref(false)
const uploadVisible = ref(false)
const uploading = ref(false)
const renameVisible = ref(false)
const renaming = ref(false)
const uploadRef = ref(null)
const uploadForm = reactive({ name: '', file: null })
const renameForm = reactive({ id: null, name: '' })
const xmindFileInput = ref(null)
const xmindTargetReqId = ref(null)

const ensureProject = () => {
  if (!proStore.projectInfo?.id) {
    ElMessage.warning('请先在顶部导航栏选择项目')
    return false
  }
  return true
}

const loadList = async () => {
  if (!ensureProject()) return
  listLoading.value = true
  try {
    const res = await aiTestAnalysisApi.getRequirements({
      project_id: proStore.projectInfo.id,
      page: 1,
      size: 200
    })
    if (res.data?.code === 200) {
      reqList.value = res.data.data?.list || []
    }
  } finally {
    listLoading.value = false
  }
}

const openWorkspace = (row, tab = 'overview') => {
  router.push({ name: 'aiTestingWorkspace', params: { reqId: row.id }, query: { tab } })
}

const openRename = (row) => {
  renameForm.id = row.id
  renameForm.name = row.name || ''
  renameVisible.value = true
}

const resetRenameForm = () => {
  renameForm.id = null
  renameForm.name = ''
}

const handleRename = async () => {
  if (!ensureProject() || !renameForm.id) return
  const name = renameForm.name?.trim()
  if (!name) {
    ElMessage.warning('请输入需求名称')
    return
  }
  renaming.value = true
  try {
    const res = await aiRequirementApi.update(
      renameForm.id,
      { name },
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '已更新')
      renameVisible.value = false
      const idx = reqList.value.findIndex(r => r.id === renameForm.id)
      if (idx >= 0) {
        reqList.value[idx] = { ...reqList.value[idx], ...(res.data.data || {}), name }
      }
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '更新失败')
  } finally {
    renaming.value = false
  }
}

const onFileChange = (file) => {
  uploadForm.file = file?.raw || null
}

const handleUpload = async () => {
  if (!ensureProject()) return
  if (!uploadForm.file) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const res = await aiRequirementApi.upload(
      uploadForm.file,
      uploadForm.name?.trim() || undefined,
      proStore.projectInfo.id
    )
    if (res.data?.code === 200) {
      ElMessage.success('上传成功')
      uploadVisible.value = false
      uploadForm.name = ''
      uploadForm.file = null
      uploadRef.value?.clearFiles?.()
      await loadList()
      const row = res.data.data
      if (row?.id) openWorkspace(row, 'document')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

const openXmindCreate = () => {
  if (!ensureProject()) return
  xmindTargetReqId.value = null
  xmindFileInput.value?.click()
}

const openXmindImportForRow = (row) => {
  if (!ensureProject()) return
  xmindTargetReqId.value = row.id
  xmindFileInput.value?.click()
}

const handleDelete = async (row) => {
  if (!ensureProject()) return
  try {
    await ElMessageBox.confirm(
      `确定删除需求「${row.name}」？将同时删除其测试点、测试方案与工作区用例；已复制到功能用例库的用例不受影响。`,
      '删除需求',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  listLoading.value = true
  try {
    const res = await aiRequirementApi.delete(row.id, proStore.projectInfo.id)
    if (res.data?.code === 200) {
      ElMessage.success(res.data.message || '删除成功')
      await loadList()
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    listLoading.value = false
  }
}

const onXmindFileSelected = async (e) => {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file || !ensureProject()) return

  let batchName = ''
  let reqName = ''
  try {
    if (xmindTargetReqId.value) {
      const { value } = await ElMessageBox.prompt('导入批次名（可选）', '导入 XMind 测试点', {
        confirmButtonText: '导入',
        cancelButtonText: '取消',
        inputPlaceholder: '留空则不分批'
      })
      batchName = value || ''
    } else {
      const { value } = await ElMessageBox.prompt('需求名称（可选，默认取文件名）', '从 XMind 新建需求', {
        confirmButtonText: '下一步',
        cancelButtonText: '取消',
        inputPlaceholder: '如：非经营性事件'
      })
      reqName = value || ''
      const batchRes = await ElMessageBox.prompt('导入批次名（可选）', '从 XMind 新建需求', {
        confirmButtonText: '导入',
        cancelButtonText: '取消',
        inputPlaceholder: '留空则不分批'
      })
      batchName = batchRes.value || ''
    }
  } catch {
    return
  }

  listLoading.value = true
  try {
    if (xmindTargetReqId.value) {
      const res = await aiTestAnalysisApi.importTestPointsXmind(
        xmindTargetReqId.value,
        file,
        { batch_name: batchName },
        proStore.projectInfo.id
      )
      if (res.data?.code === 200) {
        ElMessage.success(res.data.message || '导入成功')
        await loadList()
        openWorkspace({ id: xmindTargetReqId.value }, 'points')
      }
    } else {
      const res = await aiTestAnalysisApi.createFromXmind(
        file,
        { name: reqName, batch_name: batchName },
        proStore.projectInfo.id
      )
      if (res.data?.code === 200) {
        ElMessage.success(res.data.message || '创建成功')
        await loadList()
        const req = res.data.data?.requirement
        if (req?.id) openWorkspace(req, 'points')
      }
    }
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || err?.message || '导入失败')
  } finally {
    listLoading.value = false
    xmindTargetReqId.value = null
  }
}

onMounted(loadList)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
.muted {
  color: #909399;
  font-size: 13px;
}
.name-cell {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.name-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name-edit-btn {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.name-cell:hover .name-edit-btn,
.name-edit-btn:focus-visible {
  opacity: 1;
}
</style>
