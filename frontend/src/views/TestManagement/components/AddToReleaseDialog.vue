<template>
  <el-dialog
    :model-value="modelValue"
    title="纳入版本测试范围"
    width="720px"
    destroy-on-close
    @close="emit('update:modelValue', false)"
  >
    <div class="toolbar">
      <el-input v-model="keyword" clearable placeholder="搜索标题" style="width: 200px" @keyup.enter="search" />
      <el-input v-model="module" clearable placeholder="模块" style="width: 140px" />
      <el-button type="primary" @click="search">查询</el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="cases"
      border
      height="360"
      @selection-change="onSelect"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column prop="module" label="模块" width="120" show-overflow-tooltip />
      <el-table-column prop="priority" label="优先级" width="80" />
    </el-table>
    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next, sizes"
        :page-sizes="[50, 100, 200]"
        @current-change="search"
        @size-change="onSizeChange"
      />
    </div>
    <div class="risk-row">
      <span class="risk-label">纳入后风险等级</span>
      <el-select v-model="riskLevel" style="width: 140px">
        <el-option label="低风险" value="low" />
        <el-option label="中风险" value="medium" />
        <el-option label="高风险" value="high" />
        <el-option label="严重" value="critical" />
      </el-select>
      <span class="risk-hint">用于质量门禁与范围列表展示，纳入后可在范围中单独调整</span>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="!selected.length" :loading="saving" @click="submit">
        纳入选中 ({{ selected.length }})
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { aiFunctionalCaseApi } from '@/api/modules/ai'
import { testReleaseApi } from '@/api/testManagement'

const props = defineProps({
  modelValue: Boolean,
  releaseId: { type: Number, required: true },
  projectId: { type: Number, required: true }
})
const emit = defineEmits(['update:modelValue', 'done'])

const loading = ref(false)
const saving = ref(false)
const cases = ref([])
const selected = ref([])
const keyword = ref('')
const module = ref('')
const riskLevel = ref('medium')
const page = ref(1)
const pageSize = ref(100)
const total = ref(0)

const search = async () => {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await aiFunctionalCaseApi.getList({
      project_id: props.projectId,
      keyword: keyword.value || undefined,
      module: module.value || undefined,
      page: page.value,
      size: pageSize.value
    })
    const data = res.data?.data || {}
    cases.value = data.list || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

const onSizeChange = () => {
  page.value = 1
  search()
}

const onSelect = (rows) => {
  selected.value = rows
}

const submit = async () => {
  saving.value = true
  try {
    const res = await testReleaseApi.addScopes(props.releaseId, props.projectId, {
      functional_case_ids: selected.value.map((r) => r.id),
      risk_level: riskLevel.value
    })
    const d = res.data?.data || {}
    ElMessage.success(`新增 ${d.created_count || 0}，已存在 ${d.existing_count || 0}`)
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
      selected.value = []
      page.value = 1
      search()
    }
  }
)
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.pager {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}
.risk-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.risk-label {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.risk-hint {
  color: #909399;
  font-size: 12px;
}
</style>
