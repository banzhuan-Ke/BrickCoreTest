<template>
  <div class="step-editor">
    <!-- 步骤列表 -->
    <div class="step-list" :class="{ 'is-empty': steps.length === 0 }">
      <VueDraggable
        v-model="localSteps"
        :group="{ name: 'steps', pull: false, put: true }"
        :animation="200"
        :ghost-class="'ghost'"
        :drag-class="'dragging'"
        :chosen-class="'chosen'"
        target=".draggable-content"
        @add="onStepAdd"
        @end="onDragEnd"
        class="draggable-container"
      >
        <div class="draggable-content">
          <StepItem
            v-for="(step, index) in localSteps"
            :key="step.id || `step_${index}`"
            :step="step"
            :index="index"
            :parent-path="[]"
            @edit="openEditDialog(step, index)"
            @debug="onDebugStep"
            @update:step="updateStep(index, $event)"
            @delete="deleteStep(index)"
            @add-branch="addBranch(index)"
            @delete-branch="deleteBranch(index, $event)"
          />
        </div>
      </VueDraggable>
      
      <!-- 空状态提示 -->
      <div v-if="steps.length === 0" class="empty-tip">
        <el-icon :size="40" color="#909399"><Plus /></el-icon>
        <p>暂无步骤，请从左侧拖拽添加</p>
      </div>
    </div>

    <!-- 步骤编辑弹窗 -->
    <StepEditDialog
      v-model:visible="dialogVisible"
      :step="editingStep"
      :all-steps="localSteps"
      :step-index="editingIndex"
      @save="handleStepSave"
      @cancel="handleStepCancel"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { Plus } from '@element-plus/icons-vue'
import StepItem from './StepItem.vue'
import StepEditDialog from './StepEditDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { generateStepId } from '@/utils/stepHelper'

const props = defineProps({
  steps: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:steps', 'debug-step'])

// 本地步骤数据
const localSteps = computed({
  get: () => props.steps,
  set: (val) => emit('update:steps', val)
})

// 弹窗控制
const dialogVisible = ref(false)
const editingStep = ref(null)
const editingIndex = ref(-1)
const isNewStep = ref(false) // 标记是否是新增步骤

// 打开编辑弹窗
function openEditDialog(step, index) {
  editingStep.value = { ...step }
  editingIndex.value = index
  isNewStep.value = false
  dialogVisible.value = true
}

function onDebugStep(index) {
  emit('debug-step', index)
}

// 处理拖拽添加（从左侧关键字面板拖入）
function onStepAdd(evt) {
  const { item, newIndex } = evt
  
  // 获取拖拽的原始数据
  const rawData = JSON.parse(item.dataset.step || '{}')
  
  // 创建新步骤
  // name: 显示名称，keyword: 执行时用的关键字
  const newStep = {
    id: generateStepId(),
    keyword: rawData.keyword || rawData.name || '未知操作',
    desc: rawData.name || rawData.keyword || '未知操作',
    method: rawData.method || '',
    params: rawData.params ? JSON.parse(JSON.stringify(rawData.params)) : {},
    children: [], // 支持嵌套
    config: { timeout: 30000, retry: false }
  }
  
  // 如果是条件分支步骤，添加branches字段
  if (rawData.method === 'condition_branch' || rawData.is_container) {
    newStep.is_container = true
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
  
  // VueDraggable 在 v-model 模式下会自动添加占位元素
  // 我们需要替换它
  const steps = [...localSteps.value]
  
  // 检查新位置是否有占位元素（没有 id 的对象）
  if (newIndex < steps.length && steps[newIndex] && !steps[newIndex].id) {
    // 删除占位元素
    steps.splice(newIndex, 1)
  }
  
  // 插入新步骤
  steps.splice(newIndex, 0, newStep)
  localSteps.value = steps
  
  // 打开编辑弹窗
  editingStep.value = newStep
  editingIndex.value = newIndex
  isNewStep.value = true
  dialogVisible.value = true
}

// 处理拖拽排序结束
function onDragEnd() {
  // 可以在这里添加排序后的处理逻辑
}

// 更新步骤
function updateStep(index, newStep) {
  const steps = [...localSteps.value]
  steps[index] = { ...steps[index], ...newStep }
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

// 处理步骤保存
function handleStepSave(savedStep) {
  if (editingIndex.value >= 0 && editingIndex.value < localSteps.value.length) {
    // 更新现有步骤
    updateStep(editingIndex.value, savedStep)
  }
  
  dialogVisible.value = false
  editingStep.value = null
  editingIndex.value = -1
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
  isNewStep.value = false
}
</script>

<style scoped lang="scss">
.step-editor {
  min-height: 300px;
}

.step-list {
  min-height: 200px;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  
  &.is-empty {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}

.draggable-container {
  min-height: 100px;
}

.draggable-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.empty-tip {
  text-align: center;
  color: var(--el-text-color-secondary);
  padding: 40px;
  
  p {
    margin-top: 10px;
  }
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
