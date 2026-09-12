<template>
  <PageCard>
    <template #title>
      <div style="font-size: 18px; font-weight: bold;">CSV 数据集</div>
    </template>
    <template #main>
      <el-alert type="info" :closable="false" show-icon style="margin-bottom: 14px">
        项目级 CSV，可被多个压测场景绑定。用例里写
        <code v-pre>${{csv.列名}}</code>
        ；编辑用例可用「插入变量」快速插入。旧场景内联 CSV 可点「迁出历史数据」转为数据集。
      </el-alert>

      <div class="toolbar">
        <el-input
          v-model="keyword"
          placeholder="搜索名称"
          clearable
          style="width: 220px"
          @keyup.enter="fetchList"
        />
        <el-button type="primary" @click="fetchList">搜索</el-button>
        <el-button v-permission="'perf_scene:edit'" type="success" @click="openCreate">新建数据集</el-button>
        <el-button v-permission="'perf_scene:edit'" plain @click="migrateLegacy" :loading="migrating">
          迁出历史数据
        </el-button>
      </div>

      <el-table :data="tableData" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="file_name" label="文件" min-width="140" show-overflow-tooltip />
        <el-table-column prop="row_count" label="行数" width="80" align="center" />
        <el-table-column label="列" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ (row.columns || []).join(', ') }}
          </template>
        </el-table-column>
        <el-table-column prop="bound_scene_count" label="绑定场景" width="90" align="center" />
        <el-table-column prop="update_time" label="更新时间" width="170" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openPreview(row)">预览</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="primary"
              size="small"
              @click="triggerUpload(row)"
            >上传 CSV</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="primary"
              size="small"
              @click="openEdit(row)"
            >改名</el-button>
            <el-button
              v-permission="'perf_scene:edit'"
              link
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <input
        ref="fileInputRef"
        type="file"
        accept=".csv"
        style="display: none"
        @change="onFileChosen"
      />

      <el-dialog v-model="formVisible" :title="form.id ? '编辑数据集' : '新建数据集'" width="480px" destroy-on-close>
        <el-form :model="form" label-width="88px">
          <el-form-item label="名称" required>
            <el-input v-model="form.name" maxlength="100" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="2" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="formVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveForm">确定</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="previewVisible" title="CSV 预览" width="720px" destroy-on-close>
        <div v-if="previewMeta" class="preview-meta">
          <el-tag size="small">{{ previewMeta.name }}</el-tag>
          <span>{{ previewMeta.file_name }} · {{ previewMeta.row_count }} 行</span>
        </div>
        <el-table v-if="previewRows.length" :data="previewRows" size="small" border max-height="400">
          <el-table-column
            v-for="col in previewColumns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="120"
            show-overflow-tooltip
          />
        </el-table>
        <el-empty v-else description="暂无数据，请先上传 CSV" />
      </el-dialog>
    </template>
  </PageCard>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PageCard from '@/components/PageCard.vue'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { perfCsvDatasetApi } from '@/api/modules/perf'

const proStore = ProjectStore()
const loading = ref(false)
const migrating = ref(false)
const saving = ref(false)
const keyword = ref('')
const tableData = ref([])
const formVisible = ref(false)
const form = reactive({ id: null, name: '', description: '' })
const fileInputRef = ref(null)
const uploadTargetId = ref(null)

const previewVisible = ref(false)
const previewMeta = ref(null)
const previewRows = ref([])
const previewColumns = ref([])

async function fetchList() {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  loading.value = true
  try {
    const res = await perfCsvDatasetApi.getList({
      project_id: pid,
      keyword: keyword.value || undefined,
    })
    const data = res?.data || res || {}
    tableData.value = data.data || data || []
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  form.id = null
  form.name = ''
  form.description = ''
  formVisible.value = true
}

function openEdit(row) {
  form.id = row.id
  form.name = row.name
  form.description = row.description || ''
  formVisible.value = true
}

async function saveForm() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  const pid = proStore.projectInfo?.id
  saving.value = true
  try {
    if (form.id) {
      await perfCsvDatasetApi.update(form.id, {
        name: form.name.trim(),
        description: form.description,
      })
    } else {
      await perfCsvDatasetApi.create({
        project_id: pid,
        name: form.name.trim(),
        description: form.description,
      })
    }
    ElMessage.success('已保存')
    formVisible.value = false
    fetchList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function triggerUpload(row) {
  uploadTargetId.value = row.id
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

async function onFileChosen(ev) {
  const file = ev.target?.files?.[0]
  const id = uploadTargetId.value
  if (!file || !id) return
  if (!file.name.toLowerCase().endsWith('.csv')) {
    ElMessage.error('请选择 CSV 文件')
    return
  }
  const fd = new FormData()
  fd.append('file', file)
  try {
    await perfCsvDatasetApi.upload(id, fd)
    ElMessage.success('上传成功')
    fetchList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  }
}

async function openPreview(row) {
  try {
    const res = await perfCsvDatasetApi.preview(row.id, { limit: 50 })
    const data = res?.data || res || {}
    previewMeta.value = data
    previewRows.value = data.preview || []
    previewColumns.value = data.columns || (previewRows.value[0] ? Object.keys(previewRows.value[0]) : [])
    previewVisible.value = true
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '预览失败')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除数据集「${row.name}」？已绑定场景需先解绑。`,
      '删除确认',
      { type: 'warning' }
    )
    await perfCsvDatasetApi.remove(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function migrateLegacy() {
  const pid = proStore.projectInfo?.id
  if (!pid) return
  migrating.value = true
  try {
    const res = await perfCsvDatasetApi.migrateLegacy(pid)
    const data = res?.data || res || {}
    ElMessage.success(`已迁出 ${data.migrated_count || 0} 个场景的历史 CSV`)
    fetchList()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '迁出失败')
  } finally {
    migrating.value = false
  }
}

onMounted(fetchList)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.preview-meta {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
