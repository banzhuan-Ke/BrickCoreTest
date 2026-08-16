<template>
  <div class="step-item-wrapper" :style="{marginLeft: depth > 0 ? '20px' : '0'}">
    <div class="step" :class="{'is-nested': depth > 0, 'is-condition': step.method === 'condition_branch'}">
      <div class="line1">
        <!--图标-->
        <el-icon class="header-icon" size="18px" :color="step.method === 'condition_branch' ? '#e6a23c' : 'var(--el-color-primary)'">
          <Operation v-if="step.method !== 'condition_branch'" />
          <Share v-else />
        </el-icon>
        <!--名称-->
        <div class="name">
          <span class="keyword">{{ step.keyword }}</span>
          <span v-if="step.desc" class="desc"> - {{ step.desc }}</span>
        </div>
        <!--标签显示-->
        <div class="tags" v-if="step.method === 'condition_branch'">
          <el-tag size="small" type="warning">{{ step.branches?.length || 0 }} 个分支</el-tag>
        </div>
        <!--按钮-->
        <div class="btn">
          <el-button plain size="small" type="primary" icon="Edit" @click='handleEdit'>编辑</el-button>
          <el-button plain size="small" type="danger" icon="Delete" @click='handleDelete'>删除</el-button>
        </div>
      </div>
      
      <!-- 条件分支展示 -->
      <div v-if="step.method === 'condition_branch'" class="branches-container">
        <div 
          v-for="(branch, bIndex) in step.branches" 
          :key="branch.id || bIndex"
          class="branch-item"
        >
          <div class="branch-header" @click="toggleBranch(bIndex)">
            <el-icon size="14">
              <ArrowDown v-if="!collapsedBranches[bIndex]" />
              <ArrowRight v-else />
            </el-icon>
            <el-tag size="small" :type="branch.condition?.type === 'else' ? 'info' : 'success'" effect="dark">
              {{ branch.condition?.type === 'else' ? 'ELSE' : `IF ${bIndex + 1}` }}
            </el-tag>
            <span class="branch-name">{{ branch.name || '未命名分支' }}</span>
            <span class="branch-condition" v-if="branch.condition?.type !== 'else'">
              {{ getConditionDisplay(branch.condition) }}
            </span>
            <span class="step-count">({{ branch.steps?.length || 0 }} 步)</span>
            
            <div class="branch-actions" @click.stop>
              <el-button 
                v-if="branch.condition?.type !== 'else'" 
                link size="small" type="danger" 
                @click="handleDeleteBranch(bIndex)"
              >
                删除
              </el-button>
            </div>
          </div>
          
          <!-- 分支内的步骤 - 支持拖拽 -->
          <div v-show="!collapsedBranches[bIndex]" class="branch-steps-wrapper">
            <BranchStepList
              :branch="branch"
              :branch-index="bIndex"
              :parent-step="step"
              :parent-path="[...currentPath, bIndex]"
              @update:branch="(newBranch) => updateBranch(bIndex, newBranch)"
            />
          </div>
        </div>
        
        <!-- 添加分支按钮 -->
        <div class="add-branch-btn">
          <el-button link size="small" type="primary" icon="Plus" @click="handleAddBranch">
            添加条件分支
          </el-button>
        </div>
      </div>
      
      <div class="line2" v-if="step.method !== 'condition_branch'">
        <p>{{ getParamsDisplay(step.params) }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject } from 'vue'
import { Operation, Share, ArrowDown, ArrowRight, Plus } from '@element-plus/icons-vue'
import BranchStepList from './BranchStepList.vue'

const props = defineProps({
  step: {
    type: Object,
    required: true
  },
  index: {
    type: Number,
    required: true
  },
  depth: {
    type: Number,
    default: 0
  },
  parentPath: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:step', 'delete', 'add-branch', 'delete-branch'])

const editStepMethod = inject('editStepMethod')

// 当前路径
const currentPath = computed(() => [...props.parentPath, props.index])

// 折叠状态
const collapsedBranches = ref({})

// 切换分支折叠
function toggleBranch(bIndex) {
  collapsedBranches.value[bIndex] = !collapsedBranches.value[bIndex]
}

// 更新整个分支
function updateBranch(bIndex, newBranch) {
  const newStepData = JSON.parse(JSON.stringify(props.step))
  newStepData.branches[bIndex] = newBranch
  emit('update:step', newStepData)
}

// 编辑
function handleEdit() {
  editStepMethod(props.step, currentPath.value)
}

// 删除
function handleDelete() {
  emit('delete')
}

// 添加分支
function handleAddBranch() {
  emit('add-branch')
}

// 删除分支
function handleDeleteBranch(bIndex) {
  emit('delete-branch', bIndex)
}

// 获取条件显示文本（含定位摘要，便于发现未配置）
function getConditionDisplay(condition) {
  if (!condition) return ''

  const typeMap = {
    element_visible: '元素可见',
    element_exist: '元素存在',
    element_text_equals: '文本等于',
    element_text_contains: '文本包含',
    page_title_equals: '标题等于',
    page_url_contains: 'URL包含',
    custom_js: 'JS表达式',
  }

  if (condition.type === 'else') return '默认分支'

  const typeName = typeMap[condition.type] || condition.type
  const operator = condition.operator === 'is_true' ? '为真' : '为假'
  const needsLocator = ['element_visible', 'element_exist', 'element_text_equals', 'element_text_contains'].includes(
    condition.type,
  )
  let locatorText = ''
  const loc = condition.locator
  if (typeof loc === 'string') locatorText = loc.trim()
  else if (loc && typeof loc === 'object') {
    const value = String(loc.value || '').trim()
    locatorText = value ? (loc.by ? `${loc.by}=${value}` : value) : ''
  }
  if (needsLocator) {
    if (!locatorText) return `${typeName} ${operator} · 未配置定位`
    const short = locatorText.length > 40 ? `${locatorText.slice(0, 40)}…` : locatorText
    return `${typeName} ${operator} · ${short}`
  }
  return `${typeName} ${operator}`
}

// 获取参数显示
function getParamsDisplay(params) {
  if (!params) return ''
  
  const display = []
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value !== null && value !== undefined) {
      display.push(`${key}: ${value}`)
    }
  }
  
  return display.length > 0 ? display.join(', ') : '无参数'
}
</script>

<style scoped lang="scss">
.step-item-wrapper {
  margin-bottom: 8px;
}

.step {
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  transition: all 0.3s;
  
  &:hover {
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  }
  
  &.is-nested {
    background: #fafafa;
    border-style: dashed;
  }
  
  &.is-condition {
    border-color: #e6a23c;
    background: #fdf6ec;
  }
}

.line1 {
  display: flex;
  align-items: center;
  gap: 8px;
  
  .header-icon {
    flex-shrink: 0;
  }
  
  .name {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 4px;
    min-width: 0;
    
    .keyword {
      font-weight: 500;
      color: var(--el-text-color-primary);
    }
    
    .desc {
      color: var(--el-text-color-secondary);
      font-size: 13px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
  
  .tags {
    flex-shrink: 0;
  }
  
  .btn {
    flex-shrink: 0;
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.3s;
  }
}

.step:hover .btn {
  opacity: 1;
}

.line2 {
  margin-top: 8px;
  padding-left: 26px;
  
  p {
    margin: 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.branches-container {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--el-border-color);
}

.branch-item {
  margin-bottom: 8px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}

.branch-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.3s;
  background: var(--el-fill-color-light);
  
  &:hover {
    background: var(--el-fill-color);
  }
  
  .branch-name {
    font-weight: 500;
    font-size: 13px;
  }
  
  .branch-condition {
    flex: 1;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  .step-count {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
  
  .branch-actions {
    opacity: 0;
    transition: opacity 0.3s;
  }
  
  &:hover .branch-actions {
    opacity: 1;
  }
}

.branch-steps-wrapper {
  padding: 8px;
  background: #f5f7fa;
  border-top: 1px solid var(--el-border-color-lighter);
}

.add-branch-btn {
  padding: 8px 12px;
  text-align: center;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>