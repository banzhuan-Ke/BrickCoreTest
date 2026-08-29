<template>
  <div class="tm-review-templates" v-loading="loading">
    <div class="header">
      <h2>评审模板</h2>
      <el-button v-if="canManage" type="primary" @click="openCreate">新建模板</el-button>
    </div>

    <el-table :data="rows" border stripe>
      <el-table-column prop="name" label="名称" min-width="160" />
      <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
      <el-table-column label="检查项" min-width="220">
        <template #default="{ row }">
          {{ (row.checklist || []).map((c) => c.label || c.key).join('、') || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="默认" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.is_default" type="success" size="small">是</el-tag>
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right" v-if="canManage">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="visible" :title="editing ? '编辑模板' : '新建模板'" width="560px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" maxlength="200" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="默认模板">
          <el-switch v-model="form.is_default" />
        </el-form-item>
        <el-form-item label="检查项">
          <div class="checklist">
            <div v-for="(item, idx) in form.checklist" :key="idx" class="check-row">
              <el-input v-model="item.label" placeholder="检查项名称" />
              <el-checkbox v-model="item.required">必填</el-checkbox>
              <el-button link type="danger" @click="form.checklist.splice(idx, 1)">删</el-button>
            </div>
            <el-button size="small" @click="addCheckItem">添加检查项</el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { testReviewApi } from '@/api/testManagement'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { UserStore } from '@/stores/module/UserStore'

const proStore = ProjectStore()
const uStore = UserStore()
const projectId = computed(() => proStore.projectInfo?.id)
const canManage = computed(() => uStore.hasPermission('test_review:manage'))

const loading = ref(false)
const saving = ref(false)
const rows = ref([])
const visible = ref(false)
const editing = ref(null)
const form = reactive({
  name: '',
  description: '',
  is_default: false,
  checklist: []
})

const load = async () => {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await testReviewApi.listTemplates(projectId.value)
    rows.value = res.data?.data || []
  } finally {
    loading.value = false
  }
}

const addCheckItem = () => {
  form.checklist.push({
    key: `item_${form.checklist.length + 1}`,
    label: '',
    required: false
  })
}

const openCreate = () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  editing.value = null
  form.name = ''
  form.description = ''
  form.is_default = false
  form.checklist = [
    { key: 'item_1', label: '步骤清晰可执行', required: true },
    { key: 'item_2', label: '预期结果明确', required: true },
  ]
  visible.value = true
}

const openEdit = (row) => {
  editing.value = row
  form.name = row.name || ''
  form.description = row.description || ''
  form.is_default = !!row.is_default
  form.checklist = (row.checklist || []).map((c, i) => ({
    key: c.key || `item_${i + 1}`,
    label: c.label || '',
    required: !!c.required
  }))
  visible.value = true
}

const submit = async () => {
  if (!projectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  const checklist = form.checklist
    .filter((c) => (c.label || '').trim())
    .map((c, i) => ({
      key: c.key || `item_${i + 1}`,
      label: c.label.trim(),
      required: !!c.required
    }))
  saving.value = true
  try {
    if (editing.value) {
      await testReviewApi.updateTemplate(editing.value.id, projectId.value, {
        name: form.name.trim(),
        description: form.description || null,
        is_default: form.is_default,
        checklist
      })
      ElMessage.success('已更新')
    } else {
      await testReviewApi.createTemplate({
        project_id: projectId.value,
        name: form.name.trim(),
        description: form.description || null,
        is_default: form.is_default,
        checklist
      })
      ElMessage.success('已创建')
    }
    visible.value = false
    await load()
  } finally {
    saving.value = false
  }
}

const remove = async (row) => {
  await ElMessageBox.confirm(`删除模板「${row.name}」？`, '确认', { type: 'warning' })
  await testReviewApi.removeTemplate(row.id, projectId.value)
  ElMessage.success('已删除')
  await load()
}

watch(projectId, () => load())
onMounted(load)
</script>

<style scoped>
.tm-review-templates { padding: 16px; }
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.header h2 { margin: 0; font-size: 20px; }
.checklist { width: 100%; }
.check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
</style>
