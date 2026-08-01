<template>
  <div>
    <div class="toolbar">
      <el-button v-if="canExecute" type="success" @click="openCreate">新建文件夹</el-button>
      <el-button @click="loadList">刷新</el-button>
    </div>

    <el-empty
      v-if="!loading && !list.length"
      description="还没有迭代文件夹"
      class="folder-empty"
    >
      <template #default>
        <p class="empty-hint">创建文件夹后上传需求、Bug 清单、测试计划等文档，供报告生成与 AI 检索引用。</p>
        <div class="empty-actions">
          <el-button v-if="canExecute" type="primary" @click="openCreate">新建文件夹</el-button>
          <el-button @click="router.push('/ai-knowledge/reports')">前往报告向导</el-button>
        </div>
      </template>
    </el-empty>

    <el-table v-else :data="list" v-loading="loading" stripe @row-dblclick="openFolder">
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="iteration_label" label="迭代标签" width="120" />
      <el-table-column label="日期范围" width="200">
        <template #default="{ row }">
          <span v-if="row.date_start || row.date_end">
            {{ row.date_start || '?' }} ~ {{ row.date_end || '?' }}
          </span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="doc_count" label="文档数" width="88" align="center" />
      <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
      <el-table-column prop="update_time" label="更新时间" width="168">
        <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openFolder(row)">进入</el-button>
          <el-button v-if="canExecute" link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="canExecute" link type="danger" @click="removeFolder(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog.visible" :title="dialog.id ? '编辑文件夹' : '新建文件夹'" width="520px" destroy-on-close>
      <el-form :model="dialog.form" label-width="96px">
        <el-form-item label="名称" required>
          <el-input v-model="dialog.form.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="迭代标签">
          <el-input v-model="dialog.form.iteration_label" placeholder="如 2026S4" maxlength="50" />
        </el-form-item>
        <el-form-item label="开始日期">
          <el-date-picker v-model="dialog.form.date_start" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="结束日期">
          <el-date-picker v-model="dialog.form.date_end" type="date" value-format="YYYY-MM-DD" style="width: 100%;" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="dialog.form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="saveFolder">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeApi } from '@/api/modules/knowledge.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { useKnowledgePermissions } from '@/modules/knowledge/composables/useKnowledgePermissions.js'

const router = useRouter()
const projectId = computed(() => ProjectStore().projectInfo?.id)
const { canEdit: canExecute } = useKnowledgePermissions()

const loading = ref(false)
const deleteMode = ref('logical')
const list = ref([])
const dialog = ref({
  visible: false,
  id: null,
  saving: false,
  form: { name: '', description: '', iteration_label: '', date_start: null, date_end: null }
})

function formatTime(v) {
  if (!v) return '-'
  return String(v).replace('T', ' ').slice(0, 19)
}

async function loadList() {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  loading.value = true
  try {
    const [folderRes, metaRes] = await Promise.all([
      knowledgeApi.listFolders(projectId.value),
      knowledgeApi.getMeta()
    ])
    list.value = folderRes.data?.items || []
    if (metaRes.data?.knowledge_delete_mode) {
      deleteMode.value = metaRes.data.knowledge_delete_mode
    }
  } catch (e) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  dialog.value = {
    visible: true,
    id: null,
    saving: false,
    form: { name: '', description: '', iteration_label: '', date_start: null, date_end: null }
  }
}

function openEdit(row) {
  dialog.value = {
    visible: true,
    id: row.id,
    saving: false,
    form: {
      name: row.name,
      description: row.description || '',
      iteration_label: row.iteration_label || '',
      date_start: row.date_start,
      date_end: row.date_end
    }
  }
}

async function saveFolder() {
  const name = (dialog.value.form.name || '').trim()
  if (!name) {
    ElMessage.warning('请填写名称')
    return
  }
  dialog.value.saving = true
  try {
    const payload = { ...dialog.value.form, name }
    if (dialog.value.id) {
      await knowledgeApi.updateFolder(dialog.value.id, payload, projectId.value)
      ElMessage.success('已更新')
    } else {
      await knowledgeApi.createFolder(payload, projectId.value)
      ElMessage.success('已创建')
    }
    dialog.value.visible = false
    await loadList()
  } catch (e) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    dialog.value.saving = false
  }
}

function openFolder(row) {
  router.push(`/ai-knowledge/folders/${row.id}`)
}

async function removeFolder(row) {
  try {
    const msg = deleteMode.value === 'physical'
      ? `将永久删除文件夹「${row.name}」及其内全部文档、源文件与索引，此操作不可恢复，确定继续吗？`
      : `将从列表中隐藏文件夹「${row.name}」及其文档（逻辑删除，源文件仍保留），确定继续吗？`
    await ElMessageBox.confirm(msg, '确认', { type: 'warning' })
    await knowledgeApi.deleteFolder(row.id, projectId.value)
    ElMessage.success('已删除')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

watch(projectId, loadList)

onMounted(loadList)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.folder-empty {
  margin: 48px 0;
}
.empty-hint {
  margin: 0 0 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  max-width: 420px;
  line-height: 1.5;
}
.empty-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
