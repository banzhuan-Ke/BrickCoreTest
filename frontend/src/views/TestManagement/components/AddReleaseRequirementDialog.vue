<template>
  <el-dialog
    :model-value="modelValue"
    title="关联迭代需求"
    width="640px"
    destroy-on-close
    @close="emit('update:modelValue', false)"
  >
    <el-tabs v-model="mode">
      <el-tab-pane label="从项目需求选择" name="pick">
        <div class="toolbar">
          <el-input
            v-model="keyword"
            clearable
            placeholder="搜索需求名称"
            style="width: 220px"
            @keyup.enter="search"
          />
          <el-button type="primary" @click="search">查询</el-button>
        </div>
        <el-table
          v-loading="loading"
          :data="requirements"
          border
          height="320"
          @selection-change="onSelect"
        >
          <el-table-column type="selection" width="45" :selectable="rowSelectable" />
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">{{ row.review_status || row.parse_status || '—' }}</template>
          </el-table-column>
        </el-table>
        <p class="hint">已关联的需求不可重复选择；选中后写入版本需求列表并链到需求工作台。</p>
      </el-tab-pane>
      <el-tab-pane label="手工填写" name="manual">
        <el-form :model="manualForm" label-width="90px">
          <el-form-item label="编号" required>
            <el-input v-model="manualForm.requirement_key" placeholder="如 JIRA-123" />
          </el-form-item>
          <el-form-item label="标题">
            <el-input v-model="manualForm.title" />
          </el-form-item>
          <el-form-item label="链接">
            <el-input v-model="manualForm.url" placeholder="http(s)://..." />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="manualForm.note" type="textarea" :rows="3" placeholder="需求摘要或说明" />
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        v-if="mode === 'pick'"
        type="primary"
        :disabled="!selected.length"
        :loading="saving"
        @click="submitPick"
      >
        关联选中 ({{ selected.length }})
      </el-button>
      <el-button v-else type="primary" :loading="saving" @click="submitManual">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { aiRequirementApi } from '@/api/modules/ai'
import { testReleaseApi } from '@/api/testManagement'

const props = defineProps({
  modelValue: Boolean,
  releaseId: { type: Number, required: true },
  projectId: { type: Number, required: true },
  existingKeys: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue', 'done'])

const mode = ref('pick')
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const requirements = ref([])
const selected = ref([])
const manualForm = ref({ requirement_key: '', title: '', url: '', note: '' })

const existingSet = () => new Set((props.existingKeys || []).map((k) => String(k).toLowerCase()))

const rowSelectable = (row) => {
  const key = `REQ-${row.id}`.toLowerCase()
  return !existingSet().has(key) && !existingSet().has(String(row.id))
}

const search = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await aiRequirementApi.getList({
      project_id: props.projectId,
      page: 1,
      size: 200
    })
    const data = res.data?.data
    let list = Array.isArray(data) ? data : data?.items || data?.list || []
    const kw = keyword.value.trim().toLowerCase()
    if (kw) {
      list = list.filter((r) => {
        const name = String(r.name || '').toLowerCase()
        const id = String(r.id || '')
        return name.includes(kw) || id.includes(kw)
      })
    }
    requirements.value = list
  } finally {
    loading.value = false
  }
}

const onSelect = (rows) => {
  selected.value = rows
}

const submitPick = async () => {
  if (!selected.value.length) return
  saving.value = true
  try {
    let added = 0
    for (const r of selected.value) {
      const key = `REQ-${r.id}`
      if (existingSet().has(key.toLowerCase())) continue
      await testReleaseApi.addRequirement(props.releaseId, props.projectId, {
        requirement_key: key,
        title: r.name || `需求 #${r.id}`,
        url: null
      })
      added += 1
    }
    ElMessage.success(added ? `已关联 ${added} 条需求` : '所选需求均已关联')
    emit('update:modelValue', false)
    emit('done')
  } finally {
    saving.value = false
  }
}

const submitManual = async () => {
  const key = manualForm.value.requirement_key?.trim()
  if (!key) {
    ElMessage.warning('请填写编号')
    return
  }
  saving.value = true
  try {
    await testReleaseApi.addRequirement(props.releaseId, props.projectId, {
      requirement_key: key,
      title: manualForm.value.title || null,
      url: manualForm.value.url || null,
      note: manualForm.value.note || null
    })
    ElMessage.success('已添加')
    emit('update:modelValue', false)
    emit('done')
  } finally {
    saving.value = false
  }
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      mode.value = 'pick'
      selected.value = []
      manualForm.value = { requirement_key: '', title: '', url: '', note: '' }
      search()
    }
  }
)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.hint {
  margin: 10px 0 0;
  color: #909399;
  font-size: 12px;
}
</style>
