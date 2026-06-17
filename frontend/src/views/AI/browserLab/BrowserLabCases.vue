<template>
  <div>
    <div class="toolbar">
      <el-input
        v-model="filters.keyword"
        placeholder="模糊搜索：名称 / 任务 / URL / 标签"
        clearable
        style="width: 280px;"
        @keyup.enter="loadList"
      />
      <el-button type="primary" @click="loadList">查询</el-button>
      <el-button v-if="canExecute" type="success" @click="openEdit()">新建用例</el-button>
    </div>

    <el-table :data="list" v-loading="loading" stripe @row-dblclick="(row) => openEdit(row)">
      <el-table-column prop="name" label="用例名称" min-width="120">
        <template #default="{ row }">
          <span class="bl-case-name" :title="row.name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="start_url" label="起始 URL" min-width="180" show-overflow-tooltip />
      <el-table-column prop="task_text" label="任务描述" min-width="220" show-overflow-tooltip />
      <el-table-column prop="tags" label="标签" width="120" show-overflow-tooltip />
      <el-table-column prop="run_count" label="执行次数" width="88" align="center" />
      <el-table-column label="最近状态" width="96" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.last_status" :type="statusTag(row.last_status)" size="small">{{ statusLabel(row.last_status) }}</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="update_time" label="更新时间" width="160">
        <template #default="{ row }">{{ formatTime(row.update_time) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canExecute" link type="primary" @click="runCase(row)">执行</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="primary" @click="viewRecords(row)">记录</el-button>
          <el-button v-if="canExecute" link type="danger" @click="removeCase(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="size"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadList"
      />
    </div>

    <el-dialog v-model="editDialog.visible" :title="editDialog.id ? '编辑用例' : '新建用例'" width="640px" destroy-on-close>
      <el-form :model="editDialog.form" label-width="96px">
        <el-form-item label="用例名称" required>
          <el-input v-model="editDialog.form.name" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editDialog.form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="起始 URL" required>
          <el-input v-model="editDialog.form.start_url" />
        </el-form-item>
        <BrowserLabTaskTextField
          v-model="editDialog.form.task_text"
          required
          :rows="5"
          :start-url="editDialog.form.start_url"
          :case-name="editDialog.form.name"
          :ai-config-id="editDialog.aiConfigId"
          :project-id="projectId"
        />
        <el-form-item label="标签">
          <el-input v-model="editDialog.form.tags" placeholder="逗号分隔" />
        </el-form-item>
        <el-form-item label="AI 模型">
          <el-select v-model="editDialog.aiConfigId" style="width: 100%;" clearable>
            <el-option v-for="c in enabledConfigs" :key="c.id" :label="`${c.name} (${c.model})`" :value="c.id" />
          </el-select>
        </el-form-item>
        <BrowserLabExecOptionsFields :form="editDialog.form" />
      </el-form>
      <template #footer>
        <el-button @click="editDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="editDialog.saving" @click="saveCase">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { browserLabApi } from '@/api/modules/ai.js'
import { useAiConfigSelect } from '@/composables/useAiConfigSelect.js'
import BrowserLabExecOptionsFields from './BrowserLabExecOptionsFields.vue'
import BrowserLabTaskTextField from './BrowserLabTaskTextField.vue'
import { mergeBrowserLabExecForm, browserLabExecConfigPayload } from './browserLabExecOptions.js'
import { ProjectStore } from '@/stores/module/ProjectStore.js'
import { UserStore } from '@/stores/module/UserStore.js'

const router = useRouter()
const projectId = computed(() => ProjectStore().projectInfo?.id)
const canExecute = computed(() => UserStore().hasPermission('ai_test:execute'))
const { aiConfigId, enabledConfigs, loadConfigs } = useAiConfigSelect({ scene: 'browser_lab' })

const loading = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(20)
const total = ref(0)
const filters = ref({ keyword: '' })
const editDialog = ref({
  visible: false,
  id: null,
  saving: false,
  aiConfigId: null,
  form: mergeBrowserLabExecForm({
    name: '',
    description: '',
    start_url: '',
    task_text: '',
    tags: ''
  })
})

function statusLabel(s) {
  return { done: '完成', running: '执行中', failed: '失败', stopped: '已停止', pending: '等待' }[s] || s
}
function statusTag(s) {
  return { done: 'success', running: 'warning', failed: 'danger', stopped: 'info' }[s] || 'info'
}
function formatTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 19) : '-'
}

async function loadList() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await browserLabApi.listCases(projectId.value, { page: page.value, size: size.value, keyword: filters.value.keyword })
    if (res.data?.code === 200) {
      list.value = res.data.data?.list || []
      total.value = res.data.data?.total || 0
    }
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  editDialog.value.id = row?.id || null
  editDialog.value.aiConfigId = row?.ai_config_id || aiConfigId.value || null
  editDialog.value.form = row ? {
    name: row.name,
    description: row.description || '',
    start_url: row.start_url,
    task_text: row.task_text,
    tags: row.tags || '',
    ...mergeBrowserLabExecForm(row)
  } : mergeBrowserLabExecForm({
    name: '', description: '', start_url: '', task_text: '', tags: ''
  })
  editDialog.value.visible = true
}

async function saveCase() {
  const f = editDialog.value.form
  if (!f.name?.trim() || !f.task_text?.trim() || !f.start_url?.trim()) {
    return ElMessage.warning('请填写必填项')
  }
  editDialog.value.saving = true
  const payload = {
    name: f.name.trim(),
    description: f.description,
    task_text: f.task_text,
    start_url: f.start_url,
    tags: f.tags,
    config: {
      ai_config_id: editDialog.value.aiConfigId || null,
      ...browserLabExecConfigPayload(f)
    }
  }
  try {
    const res = editDialog.value.id
      ? await browserLabApi.updateCase(editDialog.value.id, payload, projectId.value)
      : await browserLabApi.createCase(payload, projectId.value)
    if (res.data?.code === 200) {
      ElMessage.success('保存成功')
      editDialog.value.visible = false
      loadList()
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message)
  } finally {
    editDialog.value.saving = false
  }
}

async function runCase(row) {
  router.push({ path: '/browser-lab/run', query: { caseId: row.id, run: '1' } })
}

function viewRecords(row) {
  router.push({ path: '/browser-lab/records', query: { caseId: row.id } })
}

async function removeCase(row) {
  await ElMessageBox.confirm(
    `确定永久删除用例「${row.name}」？\n将同时删除该用例下全部执行记录及截图/GIF，不可恢复。`,
    '永久删除',
    { type: 'warning' }
  )
  const res = await browserLabApi.deleteCases([row.id], projectId.value)
  if (res.data?.code === 200) {
    ElMessage.success('已删除')
    loadList()
  }
}

onMounted(async () => {
  await loadConfigs()
  loadList()
})
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
.bl-case-name {
  display: inline-block;
  min-width: 1em;
  line-height: 1.4;
  word-break: break-all;
  vertical-align: middle;
}
</style>
