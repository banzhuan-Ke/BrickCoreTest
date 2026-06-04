<template>
  <PageCard>
    <template #title>
      <div class="page-title-row">
        <span>Header 模板</span>
        <el-button type="primary" size="small" icon="Plus" @click="openDialog()">新建模板</el-button>
      </div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 16px;">
        <template #title>
          Header 模板是编辑时的公共 Header 库，在接口/用例编辑页手动导入；执行时只使用接口/用例本地 Header，并通过
          <code v-pre>${{变量名}}</code> 引用环境变量。
        </template>
      </el-alert>

      <div class="search-bar">
        <el-input
          v-model="keyword"
          placeholder="搜索模板名称"
          clearable
          style="width: 220px;"
          @keyup.enter="loadList"
        />
        <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
        <el-button icon="RefreshRight" @click="resetSearch">重置</el-button>
      </div>

      <el-table :data="templateList" stripe v-loading="loading" border>
        <el-table-column prop="name" label="模板名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="默认" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" size="small" type="success">默认</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="Header 数" width="100" align="center">
          <template #default="{ row }">{{ (row.headers || []).length }}</template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column prop="update_by" label="更新人" width="100" show-overflow-tooltip />
        <el-table-column label="更新时间" width="168" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="time-cell">{{ formatTime(row.update_time) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
            <el-button
              v-if="!row.is_default"
              size="small"
              type="success"
              link
              @click="handleSetDefault(row)"
            >
              设为默认
            </el-button>
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

  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="760px"
    destroy-on-close
    @closed="resetForm"
  >
    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
      <el-form-item label="模板名称" prop="name">
        <el-input v-model="form.name" maxlength="100" show-word-limit placeholder="如：通用 JSON 请求头" />
      </el-form-item>
      <el-form-item label="说明">
        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
      </el-form-item>
      <el-form-item label="设为默认">
        <el-switch v-model="form.is_default" />
      </el-form-item>
      <el-form-item label="Header 列表" required>
        <HeaderTemplateEditor ref="editorRef" v-model="form.headers" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import HeaderTemplateEditor from '@/components/HeaderTemplateEditor.vue'
import { httpHeaderTemplatesApi } from '@/api/modules/httpHeaderTemplates.js'
import { ProjectStore } from '@/stores/module/ProjectStore'
import dateTools from '@/tools/dateTools'

const proStore = ProjectStore()
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const templateList = ref([])
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const editorRef = ref(null)

const pagination = reactive({
  page: 1,
  size: 20,
  total: 0,
})

const form = reactive({
  name: '',
  description: '',
  headers: [],
  is_default: false,
})

const rules = {
  name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
}

const dialogTitle = computed(() => (editingId.value ? '编辑 Header 模板' : '新建 Header 模板'))
const projectId = computed(() => proStore.projectInfo?.id)

const formatTime = (val) => (val ? dateTools.rTime(val) : '—')

const loadList = async () => {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await httpHeaderTemplatesApi.getList({
      project_id: projectId.value,
      keyword: keyword.value || undefined,
      page: pagination.page,
      size: pagination.size,
    })
    if (res.data?.code === 200) {
      templateList.value = res.data.data?.list || []
      pagination.total = res.data.data?.total || 0
    }
  } catch {
    ElMessage.error('加载 Header 模板失败')
  } finally {
    loading.value = false
  }
}

const resetSearch = () => {
  keyword.value = ''
  pagination.page = 1
  loadList()
}

const resetForm = () => {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.headers = []
  form.is_default = false
}

const openDialog = (row = null) => {
  if (row) {
    editingId.value = row.id
    form.name = row.name
    form.description = row.description || ''
    form.headers = Array.isArray(row.headers) ? row.headers.map((h) => ({ ...h })) : []
    form.is_default = !!row.is_default
  } else {
    resetForm()
  }
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const headers = editorRef.value?.validateAndGet?.()
  if (headers === null) return

  saving.value = true
  try {
    const payload = {
      name: form.name,
      description: form.description,
      headers,
      is_default: form.is_default,
    }
    if (editingId.value) {
      await httpHeaderTemplatesApi.update(editingId.value, payload, projectId.value)
      ElMessage.success('模板已更新')
    } else {
      await httpHeaderTemplatesApi.create({ ...payload, project_id: projectId.value })
      ElMessage.success('模板已创建')
    }
    dialogVisible.value = false
    loadList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const handleSetDefault = async (row) => {
  try {
    await httpHeaderTemplatesApi.setDefault(row.id, projectId.value)
    ElMessage.success('已设为默认模板')
    loadList()
  } catch {
    ElMessage.error('设置默认模板失败')
  }
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除模板「${row.name}」？`, '删除确认', { type: 'warning' })
    await httpHeaderTemplatesApi.delete(row.id, projectId.value)
    ElMessage.success('已删除')
    loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

onMounted(loadList)
</script>

<style scoped lang="scss">
.page-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.search-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.muted {
  color: var(--el-text-color-secondary);
}
</style>
