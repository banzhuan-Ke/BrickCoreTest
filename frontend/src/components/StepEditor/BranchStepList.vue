<template>
  <div class="branch-step-list">
    <VueDraggable
      v-model="localSteps"
      :group="{ name: 'steps', pull: false, put: true }"
      :animation="200"
      :ghost-class="'ghost'"
      :drag-class="'dragging'"
      :chosen-class="'chosen'"
      target=".draggable-content"
      @add="onStepAdd"
      class="draggable-container"
    >
      <div class="draggable-content">
        <StepItem
          v-for="(subStep, sIndex) in localSteps"
          :key="subStep.id || `step_${sIndex}_${Date.now()}`"
          :step="subStep"
          :index="sIndex"
          :depth="parentPath.length"
          :parent-path="parentPath"
          @update:step="(newStep) => updateSubStep(sIndex, newStep)"
          @delete="deleteSubStep(sIndex)"
          @add-branch="() => handleAddBranch(sIndex)"
          @delete-branch="(bIndex) => handleDeleteBranch(sIndex, bIndex)"
          @expand-fragment="(payload) => onExpandFragment(sIndex, payload)"
        />
      </div>
    </VueDraggable>
    
    <!-- 空状态提示 -->
    <div v-if="localSteps.length === 0" class="empty-hint">
      <el-text type="info" size="small">
        <el-icon><Plus /></el-icon>
        拖拽步骤到此处
      </el-text>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, provide, nextTick } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { Plus } from '@element-plus/icons-vue'
import StepItem from './StepItem.vue'
import { ElMessage } from 'element-plus'
import { generateStepId } from '@/utils/stepHelper'

const props = defineProps({
  branch: { type: Object, required: true },
  branchIndex: { type: Number, required: true },
  parentStep: { type: Object, required: true },
  parentPath: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:branch'])

const localSteps = ref([])
const isUpdating = ref(false)

watch(() => props.branch.steps, (newSteps) => {
  if (!isUpdating.value) {
    localSteps.value = newSteps ? JSON.parse(JSON.stringify(newSteps)) : []
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

// 处理拖拽添加步骤
function onStepAdd(evt) {
  const { item, newIndex } = evt
  
  // 获取拖拽的原始数据
  const rawData = JSON.parse(item.dataset.step || '{}')
  
  // 创建新步骤
  const newStep = {
    id: generateStepId(),
    keyword: rawData.keyword || rawData.name || '未知操作',
    desc: rawData.name || rawData.keyword || '未知操作',
    method: rawData.method || '',
    params: rawData.params ? JSON.parse(JSON.stringify(rawData.params)) : {},
    children: [],
    config: { timeout: 30000, retry: false }
  }
  
  // 如果是条件分支，添加branches
  if (rawData.method === 'condition_branch' || rawData.is_container) {
    newStep.branches = rawData.branches ? JSON.parse(JSON.stringify(rawData.branches)) : [
      {
        id: `branch_${Date.now()}`,
        name: '分支1',
        condition: { type: 'element_visible', locator: '', operator: 'is_true' },
        steps: []
      },
      {
        id: `else_branch_${Date.now()}`,
        name: '默认分支',
        condition: { type: 'else' },
        steps: []
      }
    ]
  }
  
  // 使用 nextTick 确保 VueDraggable 完成内部状态更新
  nextTick(() => {
    // 创建新的步骤数组，替换占位元素
    const currentSteps = localSteps.value
    const steps = [...currentSteps]
    
    // 检查并移除占位元素（如果存在）
    if (newIndex < steps.length && steps[newIndex] && !steps[newIndex].id) {
      steps.splice(newIndex, 1)
    }
    
    // 在正确的位置插入新步骤
    steps.splice(newIndex, 0, newStep)
    updateParent(steps)
    ElMessage.success('步骤已添加')
  })
}

function updateSubStep(index, newStep) {
  const steps = [...localSteps.value]
  steps[index] = newStep
  updateParent(steps)
}

function deleteSubStep(index) {
  updateParent(localSteps.value.filter((_, i) => i !== index))
}

function handleAddBranch(stepIndex) {
  const step = localSteps.value[stepIndex]
  
  // 创建新的 branches 数组
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
  
  // 创建新的 branches 数组
  const branches = step.branches.filter((_, i) => i !== branchIndex)
  
  updateSubStep(stepIndex, { ...step, branches })
  ElMessage.success('分支已删除')
}

// 提供编辑方法给子组件
provide('editStepMethod', (step, path, onSave, onCancel) => {
  // 向上冒泡编辑事件
  const editEvent = new CustomEvent('edit-step-request', {
    detail: { step, path, onSave, onCancel }
  })
  window.dispatchEvent(editEvent)
})
</script>

<style scoped lang="scss">
.branch-step-list {
  min-height: 50px;
}

.draggable-container {
  min-height: 50px;
}

.draggable-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-hint {
  padding: 20px;
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
