<template>
  <el-dialog
    v-model="visible"
    title="插入步骤片段"
    width="720px"
    destroy-on-close
    @open="onOpen"
  >
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索片段名称"
        clearable
        style="width: 220px;"
        @keyup.enter="loadList"
      />
      <el-button type="primary" icon="Search" @click="loadList">搜索</el-button>
      <el-button link type="primary" @click="goManage">管理片段</el-button>
    </div>
    <el-alert
      class="insert-hint"
      type="info"
      :closable="false"
      show-icon
      :title="insertHintText"
    />
    <el-table
      ref="tableRef"
      :data="fragmentList"
      v-loading="loading"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      @current-change="onSelect"
      @row-click="onRowClick"
      max-height="360"
      border
      class="fragment-picker-table"
    >
      <el-table-column width="52" align="center">
        <template #default="{ row }">
          <el-radio
            class="row-radio"
            :model-value="selectedId"
            :value="row.id"
            @click.stop
            @change="selectRow(row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="name" label="片段名称" min-width="140" show-overflow-tooltip>
        <template #default="{ row }">
          <span :class="{ 'name-selected': isRowSelected(row) }">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="tags" label="分类" width="100" show-overflow-tooltip />
      <el-table-column label="步骤数" width="80" align="center">
        <template #default="{ row }">{{ row.step_count }}</template>
      </el-table-column>
      <el-table-column label="版本" width="70" align="center">
        <template #default="{ row }">v{{ row.version }}</template>
      </el-table-column>
      <el-table-column prop="description" label="说明" min-width="160" show-overflow-tooltip />
    </el-table>
    <div v-if="selected" class="selected-summary">
      已选片段：<strong>{{ selected.name }}</strong>
      <el-tag size="small" type="primary" effect="plain" class="selected-tag">v{{ selected.version }}</el-tag>
    </div>
    <div v-else class="selected-summary muted">
      请点击表格中的一行选中片段
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selected" @click="confirm">插入</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { uiFragmentApi } from '@/api/modules/ui'
import { appFragmentApi } from '@/api/modules/app'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { buildFragmentRefStep, resolveInsertAfterIndex } from '@/utils/stepHelper'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  excludeFragmentId: { type: [Number, String], default: null },
  domain: { type: String, default: 'ui' },
  /** 当前选中的步骤下标（0-based）；&lt;0 表示未选，追加到末尾 */
  selectedStepIndex: { type: Number, default: -1 },
  /** 当前步骤总数，用于提示插入位置 */
  stepsCount: { type: Number, default: 0 },
})
const emit = defineEmits(['update:modelValue', 'insert'])

const router = useRouter()
const proStore = ProjectStore()
const keyword = ref('')
const loading = ref(false)
const fragmentList = ref([])
const selected = ref(null)
const tableRef = ref(null)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const insertAt = computed(() => resolveInsertAfterIndex(props.stepsCount, props.selectedStepIndex))

const selectedId = computed(() => selected.value?.id ?? null)

const insertHintText = computed(() => {
  const count = Number(props.stepsCount) || 0
  const sel = Number(props.selectedStepIndex)
  if (count <= 0) return '当前无步骤，片段将作为第 1 步插入'
  if (Number.isFinite(sel) && sel >= 0 && sel < count) {
    return `将插入到第 ${sel + 1} 步之后（成为第 ${insertAt.value + 1} 步）`
  }
  return '未选中步骤：将追加到列表末尾。请先在步骤列表中点击要接续的那一步，再打开本弹窗'
})

function sameId(a, b) {
  if (a == null || b == null) return false
  return String(a) === String(b)
}

function isRowSelected(row) {
  return sameId(selected.value?.id, row?.id)
}

function rowClassName({ row }) {
  return isRowSelected(row) ? 'is-fragment-selected' : ''
}

function selectRow(row) {
  if (!row) return
  selected.value = row
  nextTick(() => tableRef.value?.setCurrentRow?.(row))
}

async function onOpen() {
  selected.value = null
  await loadList()
  await nextTick()
  tableRef.value?.setCurrentRow?.(null)
}

async function loadList() {
  const projectId = proStore.projectInfo?.id
  if (!projectId) return
  loading.value = true
  try {
    const api = props.domain === 'app' ? appFragmentApi : uiFragmentApi
    const res = await api.list({
      project_id: projectId,
      keyword: keyword.value || undefined,
      page: 1,
      size: 100,
    })
    fragmentList.value = (res.data?.data?.items || res.data?.items || []).filter(
      (row) => !props.excludeFragmentId || !sameId(row.id, props.excludeFragmentId)
    )
  } catch (e) {
    fragmentList.value = []
    console.error('加载步骤片段失败', e)
  } finally {
    loading.value = false
  }
}

function onSelect(row) {
  selected.value = row || null
}

function onRowClick(row) {
  selectRow(row)
}

function confirm() {
  if (!selected.value) {
    ElMessage.warning('请选择一个片段')
    return
  }
  const frag = selected.value
  emit('insert', {
    step: buildFragmentRefStep(frag),
    insertAt: insertAt.value,
  })
  visible.value = false
  selected.value = null
}

function goManage() {
  visible.value = false
  router.push(props.domain === 'app' ? '/app-fragments' : '/ui-fragments')
}
</script>

<style scoped lang="scss">
.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  align-items: center;
}

.insert-hint {
  margin-bottom: 12px;
}

.selected-summary {
  margin-top: 10px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;

  &.muted {
    color: var(--el-text-color-secondary);
  }
}

.selected-tag {
  margin-left: 0;
}

.name-selected {
  color: var(--el-color-primary);
  font-weight: 600;
}

.fragment-picker-table {
  :deep(.el-table__body tr) {
    cursor: pointer;
  }

  :deep(.el-table__body tr.current-row > td.el-table__cell),
  :deep(.el-table__body tr.is-fragment-selected > td.el-table__cell) {
    background-color: var(--el-color-primary-light-8) !important;
  }

  :deep(.el-table__body tr.is-fragment-selected > td.el-table__cell:first-child) {
    box-shadow: inset 3px 0 0 var(--el-color-primary);
  }

  :deep(.el-radio.row-radio) {
    height: auto;
    margin-right: 0;
  }

  :deep(.el-radio.row-radio .el-radio__label) {
    display: none;
  }
}
</style>
