<template>
  <div class="branch-step-list" :class="{ 'is-empty': localSteps.length === 0 }">
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
      class="draggable-container"
    >
      <div class="draggable-content" :class="{ 'is-drop-empty': localSteps.length === 0 }">
        <StepItem
          v-for="(subStep, sIndex) in localSteps"
          :key="subStep.id || `step_${sIndex}_${Date.now()}`"
          :step="subStep"
          :index="sIndex"
          :depth="parentPath.length"
          :parent-path="parentPath"
          @update:step="(newStep) => updateSubStep(sIndex, newStep)"
          @edit="() => openSubStepEdit(sIndex)"
          @copy="copySubStep(sIndex)"
          @delete="deleteSubStep(sIndex)"
          @add-branch="() => handleAddBranch(sIndex)"
          @delete-branch="(bIndex) => handleDeleteBranch(sIndex, bIndex)"
          @expand-fragment="(payload) => onExpandFragment(sIndex, payload)"
        />
      </div>
    </VueDraggable>

    <!-- 空态仅作视觉提示，不拦截拖放（与主步骤列表一致） -->
    <div v-if="localSteps.length === 0" class="empty-hint">
      <el-text type="info" size="small">
        <el-icon><Plus /></el-icon>
        拖拽步骤到此处
      </el-text>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, inject, nextTick } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { Plus } from '@element-plus/icons-vue'
import StepItem from './StepItem.vue'
import { ElMessage } from 'element-plus'
import { duplicateStepWithNewIds, ensureStepsHaveIds, applyKeywordDragStep } from '@/utils/stepHelper'

const props = defineProps({
  branch: { type: Object, required: true },
  branchIndex: { type: Number, required: true },
  parentStep: { type: Object, required: true },
  parentPath: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:branch'])

const editStepMethod = inject('editStepMethod', null)
const localSteps = ref([])
const isUpdating = ref(false)

watch(() => props.branch.steps, (newSteps) => {
  if (!isUpdating.value) {
    localSteps.value = newSteps ? ensureStepsHaveIds(JSON.parse(JSON.stringify(newSteps))) : []
  }
}, { immediate: true, deep: true })

function updateParent(steps) {
  isUpdating.value = true
  localSteps.value = steps
  emit('update:branch', { ...props.branch, steps: JSON.parse(JSON.stringify(steps)) })
  nextTick(() => {
    isUpdating.value = false
  })
}

function onExpandFragment(stepIndex, { expanded }) {
  const steps = [...localSteps.value]
  steps.splice(stepIndex, 1, ...expanded)
  updateParent(steps)
}

function resolveDragPayload(item) {
  const rawAttr = item?.dataset?.step || item?.getAttribute?.('data-step') || ''
  if (rawAttr) {
    try {
      return JSON.parse(rawAttr)
    } catch {
      /* fall through */
    }
  }
  // 兼容 clone 后丢失 data-step：从 Sortable 临时节点上的绑定数据兜底
  if (item && typeof item === 'object') {
    const fallback = {
      keyword: item.keyword || item.name || '',
      name: item.name || item.keyword || '',
      method: item.method || '',
      params: item.params || {},
      is_container: item.is_container,
      branches: item.branches,
    }
    if (fallback.method) return fallback
  }
  return {}
}

function onStepAdd(evt) {
  const { item, newIndex } = evt
  let rawData = resolveDragPayload(item)
  if (!rawData?.method) {
    const placeholder = localSteps.value.find((s) => s && s._keywordDragPlaceholder)
    if (placeholder) {
      rawData = placeholder
    }
  }
  if (!rawData?.method) {
    ElMessage.warning('未能识别拖入的步骤，请重试')
    return
  }
  const { steps } = applyKeywordDragStep(localSteps.value, rawData, newIndex)
  updateParent(steps)
  ElMessage.success('步骤已添加')
}

function updateSubStep(index, newStep) {
  const steps = [...localSteps.value]
  steps[index] = newStep
  updateParent(steps)
}

function deleteSubStep(index) {
  updateParent(localSteps.value.filter((_, i) => i !== index))
}

function copySubStep(index) {
  const steps = [...localSteps.value]
  const duplicated = duplicateStepWithNewIds(steps[index])
  steps.splice(index + 1, 0, duplicated)
  updateParent(steps)
  ElMessage.success('步骤已复制')
}

function openSubStepEdit(index) {
  const step = localSteps.value[index]
  if (!step) return
  const path = [...props.parentPath, index]
  if (editStepMethod) {
    editStepMethod(step, path)
    return
  }
  const editEvent = new CustomEvent('edit-step-request', {
    detail: { step, path },
  })
  window.dispatchEvent(editEvent)
}

function handleAddBranch(stepIndex) {
  const step = localSteps.value[stepIndex]
  const branches = step.branches ? [...step.branches] : []
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
  if (elseIndex >= 0) {
    branches.splice(elseIndex, 0, newBranch)
  } else {
    branches.push(newBranch)
  }
  updateSubStep(stepIndex, { ...step, branches })
  ElMessage.success('分支已添加')
}

function handleDeleteBranch(stepIndex, branchIndex) {
  const step = localSteps.value[stepIndex]
  const branch = step.branches[branchIndex]
  if (branch.condition?.type === 'else') {
    ElMessage.warning('ELSE分支不能删除')
    return
  }
  const branches = step.branches.filter((_, i) => i !== branchIndex)
  updateSubStep(stepIndex, { ...step, branches })
  ElMessage.success('分支已删除')
}
</script>

<style scoped lang="scss">
.branch-step-list {
  position: relative;
  min-height: 56px;

  &.is-empty {
    .draggable-container {
      min-height: 72px;
      width: 100%;
    }

    .empty-hint {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      pointer-events: none;
      z-index: 1;
    }
  }
}

.draggable-container {
  min-height: 40px;
}

.draggable-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;

  &.is-drop-empty {
    min-height: 72px;
    width: 100%;
  }
}

.empty-hint {
  padding: 16px;
  text-align: center;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  border: 2px dashed var(--el-border-color);
  color: var(--el-text-color-secondary);

  .el-icon {
    margin-right: 4px;
  }
}

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
