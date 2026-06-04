<template>
  <div class="branch-step-list">
    <draggable
      :list="localSteps"
      item-key="id"
      :group="{ name: 'steps', pull: false, put: true }"
      class="step-list-container"
      @change="onChange"
      chosen-class="chosen"
      drag-class="dragging"
      ghost-class="ghost"
      :move="onMove"
    >
      <template #item="{ element: subStep, index: sIndex }">
        <StepItem
          :step="subStep"
          :index="sIndex"
          :depth="parentPath.length"
          :parent-path="parentPath"
          @update:step="(newStep) => updateSubStep(sIndex, newStep)"
          @delete="deleteSubStep(sIndex)"
        />
      </template>
      <template #footer>
        <div v-if="localSteps.length === 0" class="empty-hint">
          <el-text type="info" size="small">
            <el-icon><Plus /></el-icon>
            拖拽步骤到此处
          </el-text>
        </div>
      </template>
    </draggable>
  </div>
</template>

<script setup>
import { computed, inject, ref, nextTick, watch } from 'vue'
import draggable from 'vuedraggable'
import { Plus } from '@element-plus/icons-vue'
import StepItem from './StepItem.vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  branch: { type: Object, required: true },
  branchIndex: { type: Number, required: true },
  parentStep: { type: Object, required: true },
  parentPath: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:branch'])
const editStepMethod = inject('editStepMethod')

const localSteps = ref([])
const isProcessing = ref(false)

watch(() => props.branch.steps, (newSteps) => {
  localSteps.value = newSteps || []
}, { immediate: true, deep: true })

function updateParent(steps) {
  localSteps.value = steps
  emit('update:branch', { ...props.branch, steps })
}

function onMove(evt) {
  return true
}

async function onChange(evt) {
  console.log('[BranchStepList] Change event:', evt)
  
  if (!evt.added) return
  
  if (isProcessing.value) {
    console.warn('[BranchStepList] Already processing, skip')
    return
  }
  
  const element = evt.added.element
  const newIndex = evt.added.newIndex
  
  if (!element) {
    console.error('[BranchStepList] No element')
    return
  }
  
  const tempId = element.id || element._dragSessionId
  if (!tempId) {
    console.error('[BranchStepList] No tempId')
    return
  }
  
  isProcessing.value = true
  
  try {
    await nextTick()
    
    const cleaned = localSteps.value.filter(s => s.id !== tempId)
    if (cleaned.length < localSteps.value.length) {
      updateParent(cleaned)
      console.log('[BranchStepList] Auto-added item removed')
    }
    
    let cloned = JSON.parse(JSON.stringify(element))
    cloned.desc = cloned.desc || cloned.keyword || ''
    if (cloned.params) cloned.params = JSON.parse(JSON.stringify(cloned.params))
    if (cloned.method === 'condition_branch' && !cloned.branches) {
      cloned.branches = []
    }
    
    editStepMethod(
      cloned,
      [...props.parentPath],
      (savedStep) => {
        console.log('[BranchStepList] Save callback')
        if (savedStep) {
          const newSteps = [...localSteps.value]
          const finalStep = {
            ...savedStep,
            id: `step_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            _pending: false
          }
          if (newIndex <= newSteps.length) {
            newSteps.splice(newIndex, 0, finalStep)
          } else {
            newSteps.push(finalStep)
          }
          updateParent(newSteps)
          ElMessage.success('步骤已添加')
        }
        isProcessing.value = false
      },
      () => {
        console.log('[BranchStepList] Cancel callback')
        const finalClean = localSteps.value.filter(s => s.id !== tempId)
        if (finalClean.length !== localSteps.value.length) {
          updateParent(finalClean)
        }
        ElMessage.info('已取消添加')
        isProcessing.value = false
      }
    )
  } catch (error) {
    console.error('[BranchStepList] Error:', error)
    isProcessing.value = false
  }
}

function updateSubStep(index, newStep) {
  const steps = [...localSteps.value]
  steps[index] = newStep
  updateParent(steps)
}

function deleteSubStep(index) {
  updateParent(localSteps.value.filter((_, i) => i !== index))
}
</script>

<style scoped lang="scss">
.branch-step-list { min-height: 50px; }
.step-list-container { min-height: 50px; padding: 8px; background: #fff; border-radius: 4px; border: 2px dashed transparent; transition: all 0.3s; }
.step-list-container:hover { border-color: var(--el-color-primary-light-5); }
.empty-hint { padding: 20px; text-align: center; background: var(--el-fill-color-light); border-radius: 4px; border: 2px dashed var(--el-border-color); color: var(--el-text-color-secondary); }
.empty-hint .el-icon { margin-right: 4px; }
.dragging { border: 2px dashed var(--el-color-primary); transform: scale(1.02); opacity: 0.8; }
.chosen { border: 2px solid var(--el-color-primary); }
.ghost { border: 2px dashed var(--el-color-primary); background: var(--el-color-primary-light-9); opacity: 0.5; }
.step-list-container:has(.sortable-ghost) { border-color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
</style>