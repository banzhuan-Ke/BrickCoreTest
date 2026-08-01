<template>
  <div class="step-editor">
    <div v-if="selectionMode" class="selection-toolbar">
      <span class="selection-summary">已选 <strong>{{ selectedCount }}</strong> 步</span>
      <el-button link type="primary" @click="selectAll">全选</el-button>
      <el-button link @click="clearSelection">清空</el-button>
      <el-tooltip content="仅执行勾选的步骤（不连续也会按序号依次跑；需先打开交互调试）" placement="top">
        <el-button
          type="success"
          size="small"
          :icon="VideoPlay"
          :disabled="selectedCount === 0"
          @click="runDebugSelectedSteps"
        >
          执行勾选步骤
        </el-button>
      </el-tooltip>
      <el-button
        type="primary"
        size="small"
        :disabled="selectedCount === 0"
        @click="openCreateFragmentDialog"
      >
        生成片段
      </el-button>
      <el-button link @click="exitSelectionMode">退出多选</el-button>
    </div>
    <div v-else-if="localSteps.length > 0" class="selection-toolbar is-compact">
      <el-button link type="primary" @click="enterSelectionMode">多选步骤</el-button>
      <el-button
        v-if="module !== 'app'"
        link
        type="warning"
        @click="insertSmartStep()"
      >
        插入智能步骤
      </el-button>
      <el-text type="info" size="small">勾选后点「执行勾选步骤」；卡片/工具条的「执行本步」只跑当前一步</el-text>
    </div>

    <!-- 步骤列表 -->
    <div class="step-list" :class="{ 'is-empty': steps.length === 0 }">
      <VueDraggable
        v-model="localSteps"
        :group="{ name: 'steps', pull: false, put: true }"
        :animation="200"
        :ghost-class="'ghost'"
        :drag-class="'dragging'"
        :chosen-class="'chosen'"
        :empty-insert-threshold="80"
        handle=".step-drag-handle"
        filter=".btn, button, .el-button, .step-select-box, a, input, textarea"
        :prevent-on-filter="true"
        target=".draggable-content"
        @add="onStepAdd"
        @end="onDragEnd"
        class="draggable-container"
      >
        <div class="draggable-content" :class="{ 'is-drop-empty': localSteps.length === 0 }">
          <StepItem
            v-for="(step, index) in localSteps"
            :key="step.id || `step_${index}`"
            :step="step"
            :index="index"
            :parent-path="[]"
            :selectable="selectionMode"
            :selected="selectedIndices.has(index)"
            :selected-count="selectedCount"
            :debug-enabled="debugEnabled"
            :execution-hint="stepExecutionHint(index)"
            :debug-selected="isDebugHighlighted(index)"
            :debug-run-result="stepDebugRunResult(index)"
            @toggle-select="toggleStepSelection(index)"
            @run-selected="runDebugSelectedSteps"
            @edit="openEditDialog(step, index)"
            @debug="onDebugStep"
            @record-from-step="onRecordFromStep"
            @debug-select="onDebugSelectStep(index)"
            @copy="copyStep(index)"
            @update:step="updateStep(index, $event)"
            @delete="deleteStep(index)"
            @add-branch="addBranch(index)"
            @delete-branch="deleteBranch(index, $event)"
            @expand-fragment="onExpandFragment"
          />
        </div>
      </VueDraggable>
      
      <!-- 空状态提示（pointer-events: none，不阻挡拖放） -->
      <div v-if="steps.length === 0" class="empty-tip">
        <el-icon :size="40" color="#909399"><Plus /></el-icon>
        <p>暂无步骤，请从左侧拖拽到此处添加</p>
        <p class="empty-tip-sub">也可双击左侧操作项快速添加</p>
        <el-button
          v-if="module !== 'app'"
          link
          type="warning"
          class="empty-tip-action"
          @click="insertSmartStep(0)"
        >
          插入智能步骤
        </el-button>
      </div>
    </div>

    <!-- 步骤编辑弹窗 -->
    <StepEditDialog
      v-model:visible="dialogVisible"
      :step="editingStep"
      :all-steps="localSteps"
      :step-index="editingIndex"
      :step-path="editingPath"
      :module="module"
      :driver-mode="driverMode"
      @save="handleStepSave"
      @save-multiple="handleStepSaveMultiple"
      @cancel="handleStepCancel"
    />

    <FragmentRefEditDialog
      v-model="fragmentDialogVisible"
      :step="editingFragmentStep"
      :domain="module === 'app' ? 'app' : 'ui'"
      @save="handleFragmentSave"
    />

    <CreateFragmentFromStepsDialog
      v-model="createFragmentVisible"
      :selected-count="selectedCount"
      :steps="pendingFragmentSteps"
      :domain="module === 'app' ? 'app' : 'ui'"
      @created="handleFragmentCreated"
    />
  </div>
</template>

<script setup>
import { ref, computed, provide, watch, nextTick } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { Plus, VideoPlay } from '@element-plus/icons-vue'
import StepItem from './StepItem.vue'
import StepEditDialog from './StepEditDialog.vue'
import FragmentRefEditDialog from './FragmentRefEditDialog.vue'
import CreateFragmentFromStepsDialog from './CreateFragmentFromStepsDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  normalizeExpandedFragmentSteps,
  duplicateStepWithNewIds,
  extractStepsWithNewIds,
  buildFragmentRefStep,
  ensureStepsHaveIds,
  applyKeywordDragStep,
  stepsMissingIds,
  updateStepAtPath,
  isValidStepPath,
  replaceStepAtPathWithMultiple,
  generateStepId,
} from '@/utils/stepHelper'
import { uiFragmentApi } from '@/api/modules/ui'
import { appFragmentApi } from '@/api/modules/app'
import { ProjectStore } from '@/stores/module/ProjectStore'
import { getStepExecutionHint } from '@/utils/caseExecutionHints'
import { getDebugStepResult } from '@/utils/debugSession'

const proStore = ProjectStore()

const props = defineProps({
  steps: {
    type: Array,
    default: () => []
  },
  executionHints: {
    type: Object,
    default: null
  },
  debugExecutionHints: {
    type: Object,
    default: null,
  },
  debugSelectedIndex: {
    type: Number,
    default: -1,
  },
  debugSelectedIndices: {
    type: Array,
    default: () => [],
  },
  /** web | app — App 用例编辑传 app */
  module: {
    type: String,
    default: 'web'
  },
  /** App 用例 driver_mode，用于步骤编辑 H5 说明 */
  driverMode: {
    type: String,
    default: '',
  },
  debugEnabled: {
    type: Boolean,
    default: true,
  },
})

provide('stepEditorModule', computed(() => props.module))

function stepExecutionHint(index) {
  const fromDebug = getStepExecutionHint(props.debugExecutionHints, index, localSteps.value[index])
  if (fromDebug) return fromDebug
  return getStepExecutionHint(props.executionHints, index, localSteps.value[index])
}

function stepDebugRunResult(index) {
  return getDebugStepResult(props.debugExecutionHints, index)
}

function isDebugHighlighted(index) {
  if (props.debugSelectedIndices?.length) {
    return props.debugSelectedIndices.includes(index)
  }
  return props.debugSelectedIndex === index
}

function onDebugSelectStep(index) {
  emit('debug-select-step', index)
}

const emit = defineEmits(['update:steps', 'debug-step', 'debug-select-step', 'debug-selected-steps', 'record-from-step'])

// 本地步骤数据
const localSteps = computed({
  get: () => props.steps,
  set: (val) => emit('update:steps', val)
})

// 加载的历史步骤可能无 id，补全后避免拖拽时误删已有步骤
watch(
  () => props.steps,
  (steps) => {
    if (!Array.isArray(steps) || steps.length === 0) return
    if (!stepsMissingIds(steps)) return
    emit('update:steps', ensureStepsHaveIds(steps))
  },
  { immediate: true },
)

// 弹窗控制
const dialogVisible = ref(false)
const editingStep = ref(null)
const editingIndex = ref(-1)
const editingPath = ref([])
const isNewStep = ref(false) // 标记是否是新增步骤
const fragmentDialogVisible = ref(false)
const editingFragmentStep = ref(null)
const editingFragmentIndex = ref(-1)
const fragmentOnSave = ref(null)
const selectionMode = ref(false)
const selectedIndices = ref(new Set())
const createFragmentVisible = ref(false)
const pendingFragmentSteps = ref([])

const selectedCount = computed(() => selectedIndices.value.size)

provide('fragmentRefEdit', (step, onSave) => {
  editingFragmentStep.value = JSON.parse(JSON.stringify(step))
  editingFragmentIndex.value = -1
  fragmentOnSave.value = onSave
  fragmentDialogVisible.value = true
})

provide('expandFragmentStep', async (refStep, onReplace) => {
  const fid = refStep?.params?.fragment_id
  const projectId = proStore.projectInfo?.id
  const name = refStep?.params?.fragment_name || refStep?.desc || '片段'
  if (!fid || !projectId) {
    ElMessage.warning('片段信息不完整，无法展开')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定将片段「${name}」展开为普通步骤吗？\n\n展开后此处将变为可独立编辑的步骤，且无法恢复为片段引用类型。`,
      '展开为普通步骤',
      {
        confirmButtonText: '确定展开',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  try {
    const api = props.module === 'app' ? appFragmentApi : uiFragmentApi
    const res = await api.previewExpand(fid, {
      project_id: projectId,
      variables: refStep.params?.variables || {},
      steps: [refStep],
    })
    const expanded = normalizeExpandedFragmentSteps(res.data?.data?.expanded_steps || [])
    if (!expanded.length) {
      ElMessage.warning('片段内没有可展开的步骤')
      return
    }
    onReplace(expanded)
    ElMessage.success(`已展开为 ${expanded.length} 个普通步骤`)
  } catch (e) {
    const detail = e?.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : detail?.message || '展开失败')
  }
})

// 打开编辑弹窗
function openEditAtPath(step, path) {
  if (step?.method === 'fragment_ref') {
    editingFragmentStep.value = JSON.parse(JSON.stringify(step))
    editingFragmentIndex.value = path?.[0] ?? -1
    fragmentOnSave.value = null
    fragmentDialogVisible.value = true
    return
  }
  editingStep.value = JSON.parse(JSON.stringify(step))
  editingPath.value = Array.isArray(path) && path.length ? [...path] : []
  editingIndex.value = editingPath.value.length ? editingPath.value[editingPath.value.length - 1] : -1
  isNewStep.value = false
  dialogVisible.value = true
}

function openEditDialog(step, index) {
  openEditAtPath(step, [index])
}

provide('editStepMethod', (step, path) => {
  openEditAtPath(step, path)
})

function handleFragmentSave(updatedStep) {
  if (fragmentOnSave.value) {
    fragmentOnSave.value(updatedStep)
    fragmentOnSave.value = null
  } else if (editingFragmentIndex.value >= 0) {
    updateStep(editingFragmentIndex.value, updatedStep)
  }
  fragmentDialogVisible.value = false
}

function enterSelectionMode() {
  selectionMode.value = true
  selectedIndices.value = new Set()
}

function exitSelectionMode() {
  selectionMode.value = false
  selectedIndices.value = new Set()
}

function toggleStepSelection(index) {
  const next = new Set(selectedIndices.value)
  if (next.has(index)) {
    next.delete(index)
  } else {
    next.add(index)
  }
  selectedIndices.value = next
}

function selectAll() {
  selectedIndices.value = new Set(localSteps.value.map((_, index) => index))
}

function clearSelection() {
  selectedIndices.value = new Set()
}

function openCreateFragmentDialog() {
  if (selectedCount.value === 0) {
    ElMessage.warning('请先勾选要生成片段的步骤')
    return
  }
  pendingFragmentSteps.value = extractStepsWithNewIds(
    localSteps.value,
    [...selectedIndices.value],
  )
  createFragmentVisible.value = true
}

function runDebugSelectedSteps() {
  if (selectedCount.value === 0) {
    ElMessage.warning('请先勾选要调试的步骤')
    return
  }
  const indices = [...selectedIndices.value].sort((a, b) => a - b)
  emit('debug-selected-steps', indices)
  exitSelectionMode()
}

function handleFragmentCreated({ fragment, replaceWithRef }) {
  if (!fragment?.id) return

  if (replaceWithRef) {
    const indices = [...selectedIndices.value].sort((a, b) => a - b)
    const insertAt = indices[0]
    const steps = [...localSteps.value]
    for (let i = indices.length - 1; i >= 0; i -= 1) {
      steps.splice(indices[i], 1)
    }
    steps.splice(insertAt, 0, buildFragmentRefStep(fragment))
    localSteps.value = steps
  }

  exitSelectionMode()
}

function onDebugStep(index) {
  emit('debug-step', index)
}

function onRecordFromStep(index) {
  emit('record-from-step', index)
}

function copyStep(index) {
  const steps = [...localSteps.value]
  const duplicated = duplicateStepWithNewIds(steps[index])
  steps.splice(index + 1, 0, duplicated)
  localSteps.value = steps
  if (selectionMode.value) {
    exitSelectionMode()
  }
  ElMessage.success('步骤已复制')
}

// 处理拖拽添加（从左侧关键字面板拖入）
function onStepAdd(evt) {
  const { item, newIndex } = evt
  const rawData = JSON.parse(item.dataset.step || '{}')
  const { steps, insertIndex } = applyKeywordDragStep(localSteps.value, rawData, newIndex)
  localSteps.value = steps
  if (selectionMode.value) {
    exitSelectionMode()
  }
  nextTick(() => {
    editingStep.value = steps[insertIndex]
    editingIndex.value = insertIndex
    editingPath.value = [insertIndex]
    isNewStep.value = true
    dialogVisible.value = true
  })
}

// 处理拖拽排序结束
function onDragEnd() {
  if (selectionMode.value) {
    exitSelectionMode()
  }
}

// 更新步骤
function updateStep(index, newStep) {
  const steps = [...localSteps.value]
  steps[index] = { ...steps[index], ...newStep }
  localSteps.value = steps
}

function onExpandFragment({ index, expanded }) {
  const steps = [...localSteps.value]
  steps.splice(index, 1, ...expanded)
  localSteps.value = steps
}

// 删除步骤
async function deleteStep(index) {
  try {
    await ElMessageBox.confirm('确定删除该步骤吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const steps = [...localSteps.value]
    steps.splice(index, 1)
    localSteps.value = steps
    if (selectionMode.value) {
      exitSelectionMode()
    }
    ElMessage.success('删除成功')
  } catch {
    // 取消删除
  }
}

// 添加分支到条件分支步骤
function addBranch(stepIndex) {
  const steps = [...localSteps.value]
  const step = steps[stepIndex]
  
  // 确保 branches 存在
  const branches = step.branches ? [...step.branches] : []
  
  // 找到ELSE分支的位置
  const elseIndex = branches.findIndex(b => b.condition?.type === 'else')
  
  const newBranch = {
    id: `branch_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    name: `分支${branches.length}`,
    condition: {
      type: 'element_visible',
      locator: '',
      operator: 'is_true'
    },
    steps: []
  }
  
  // 在ELSE分支之前插入
  if (elseIndex >= 0) {
    branches.splice(elseIndex, 0, newBranch)
  } else {
    branches.push(newBranch)
  }
  
  // 创建新的步骤对象，确保触发响应式更新
  steps[stepIndex] = { ...step, branches }
  localSteps.value = steps
  ElMessage.success('分支已添加')
}

// 删除条件分支步骤中的分支
function deleteBranch(stepIndex, branchIndex) {
  const steps = [...localSteps.value]
  const step = steps[stepIndex]
  const branch = step.branches[branchIndex]
  
  if (branch.condition?.type === 'else') {
    ElMessage.warning('ELSE分支不能删除')
    return
  }
  
  // 创建新的 branches 数组
  const branches = step.branches.filter((_, i) => i !== branchIndex)
  
  // 创建新的步骤对象
  steps[stepIndex] = { ...step, branches }
  localSteps.value = steps
  ElMessage.success('分支已删除')
}

function insertSmartStep(atIndex = null) {
  const idx = atIndex != null
    ? Math.max(0, Math.min(atIndex, localSteps.value.length))
    : localSteps.value.length
  const step = {
    id: generateStepId(),
    keyword: '智能步骤',
    method: 'smart_step',
    desc: '智能步骤',
    params: { intent: '' },
    children: [],
    config: { timeout: 30000, retry: false, pre_wait_ms: 0 },
  }
  const list = [...localSteps.value]
  list.splice(idx, 0, step)
  localSteps.value = list
  nextTick(() => {
    editingStep.value = list[idx]
    editingIndex.value = idx
    editingPath.value = [idx]
    isNewStep.value = true
    dialogVisible.value = true
  })
}

// 处理步骤保存
function handleStepSave(savedStep) {
  const path = editingPath.value
  if (isValidStepPath(path)) {
    if (path.length === 1) {
      updateStep(path[0], savedStep)
    } else {
      localSteps.value = updateStepAtPath(localSteps.value, path, savedStep)
    }
  } else if (isNewStep.value && editingIndex.value >= 0 && editingIndex.value < localSteps.value.length) {
    updateStep(editingIndex.value, savedStep)
  } else {
    ElMessage.error('步骤保存失败：路径无效')
    return
  }

  dialogVisible.value = false
  editingStep.value = null
  editingIndex.value = -1
  editingPath.value = []
  isNewStep.value = false
}

function handleStepSaveMultiple(steps) {
  if (!Array.isArray(steps) || steps.length === 0) {
    ElMessage.error('步骤保存失败：无有效步骤')
    return
  }
  const path = editingPath.value
  if (isValidStepPath(path)) {
    localSteps.value = replaceStepAtPathWithMultiple(localSteps.value, path, steps)
  } else if (isNewStep.value && editingIndex.value >= 0 && editingIndex.value < localSteps.value.length) {
    const list = [...localSteps.value]
    list.splice(editingIndex.value, 1, ...steps)
    localSteps.value = list
  } else {
    ElMessage.error('步骤保存失败：路径无效')
    return
  }
  ElMessage.success(`已拆分为 ${steps.length} 条智能步骤`)

  dialogVisible.value = false
  editingStep.value = null
  editingIndex.value = -1
  editingPath.value = []
  isNewStep.value = false
}

// 处理取消 - 如果是新增步骤则删除
function handleStepCancel() {
  if (isNewStep.value && editingIndex.value >= 0) {
    const steps = [...localSteps.value]
    steps.splice(editingIndex.value, 1)
    localSteps.value = steps
  }
  
  dialogVisible.value = false
  editingStep.value = null
  editingIndex.value = -1
  editingPath.value = []
  isNewStep.value = false
}

function getSelectedIndices() {
  return [...selectedIndices.value].sort((a, b) => a - b)
}

defineExpose({ insertSmartStep, getSelectedIndices })
</script>

<style scoped lang="scss">
.step-editor {
  min-height: 300px;
}

.selection-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding: 8px 12px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;

  &.is-compact {
    background: transparent;
    border-style: dashed;
    border-color: var(--el-border-color);
  }
}

.selection-summary {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.step-list {
  min-height: 200px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  position: relative;
  
  &.is-empty {
    .draggable-container {
      min-height: 200px;
      width: 100%;
    }

    .empty-tip {
      position: absolute;
      inset: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      pointer-events: none;
    }
  }
}

.draggable-container {
  min-height: 100px;
}

.draggable-content {
  display: flex;
  flex-direction: column;
  gap: 8px;

  &.is-drop-empty {
    min-height: 180px;
    width: 100%;
  }
}

.empty-tip {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 40px;
  
  p {
    margin-top: 10px;
  }
}

.empty-tip-sub {
  margin-top: 4px !important;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.empty-tip-action {
  margin-top: 8px;
  pointer-events: auto;
}

// 拖拽样式
.ghost {
  opacity: 0.5;
  background: var(--el-color-primary-light-9);
  border: 2px dashed var(--el-color-primary);
}

.chosen {
  border: 2px solid var(--el-color-primary);
}

.dragging {
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
</style>
