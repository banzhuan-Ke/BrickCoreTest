<template>
  <div class="step-item-wrapper" :style="{marginLeft: depth > 0 ? '20px' : '0'}">
    <div class="step" :class="stepClasses" @click="handleSelectForDebug">
      <div class="line1">
        <span
          class="step-drag-handle"
          title="拖拽排序"
          @click.stop
        >⋮⋮</span>
        <el-checkbox
          v-if="selectable"
          :model-value="selected"
          class="step-select-box"
          @click.stop
          @change="handleToggleSelect"
        />
        <!--步骤序号-->
        <span class="step-index" @click.stop="handleSelectForDebug">步骤 {{ index + 1 }}</span>
        <!--图标-->
        <el-icon class="header-icon" size="18px" :color="stepIconColor">
          <Collection v-if="step.method === 'fragment_ref'" />
          <Share v-else-if="step.method === 'condition_branch'" />
          <Operation v-else />
        </el-icon>
        <!--名称-->
        <div class="name">
          <span class="keyword">{{ step.keyword }}</span>
          <span v-if="step.desc && step.desc !== step.keyword" class="desc"> - {{ step.desc }}</span>
        </div>
        <!--标签显示-->
        <div class="tags" v-if="step.method === 'condition_branch'">
          <el-tag size="small" type="warning">{{ step.branches?.length || 0 }} 个分支</el-tag>
        </div>
        <div class="tags" v-if="step.method === 'fragment_ref'">
          <el-tag size="small" type="success">片段引用</el-tag>
          <el-tag v-if="step.params?.fragment_version" size="small" type="info">v{{ step.params.fragment_version }}</el-tag>
          <el-tag v-if="fragmentOutdated" size="small" type="warning">有新版本</el-tag>
        </div>
        <div v-if="recoveryHint && !executionHint" class="tags recovery-tags">
          <el-tag v-if="recoveryKinds.includes('heal')" size="small" type="warning">自愈救过</el-tag>
          <el-tag v-if="recoveryKinds.includes('act')" size="small" type="success">AI Act 救过</el-tag>
        </div>
        <!--按钮-->
        <div class="btn">
          <el-tooltip
            v-if="depth === 0 && interactiveReady && showRunSelectedBtn"
            :content="`按勾选顺序执行已选的 ${selectedCount} 步（不连续也会依次跑）`"
            placement="top"
          >
            <el-button
              plain
              size="small"
              type="success"
              :icon="VideoPlay"
              @click.stop="handleRunSelected"
            >执行勾选({{ selectedCount }})</el-button>
          </el-tooltip>
          <el-tooltip
            v-if="depth === 0 && interactiveReady"
            content="在已打开的交互调试浏览器中只执行本步；勾选多步请用顶部「执行勾选步骤」"
            placement="top"
          >
            <el-button
              plain
              size="small"
              type="warning"
              :icon="VideoPlay"
              :loading="debugRunResult?.status === 'running'"
              @click.stop="handleInteractiveRun"
            >执行本步</el-button>
          </el-tooltip>
          <el-tooltip
            v-if="depth === 0"
            :content="recordFromStepTooltip"
            placement="top"
          >
            <span>
              <el-button
                plain
                size="small"
                type="warning"
                :icon="VideoCamera"
                :disabled="!allowInteractiveActions"
                @click.stop="handleRecordFromStep"
              >从这里开始录制</el-button>
            </span>
          </el-tooltip>
          <el-tooltip
            v-if="depth === 0"
            :content="debugThroughTooltip"
            placement="top"
          >
            <span>
              <el-button
                v-if="depth === 0"
                plain
                size="small"
                type="success"
                :icon="VideoPlay"
                :disabled="!debugEnabled || !allowInteractiveActions"
                @click.stop="handleDebug"
              >调试到此步</el-button>
            </span>
          </el-tooltip>
          <el-button plain size="small" type="primary" :icon="Edit" @click.stop="handleEdit">
            {{ step.method === 'fragment_ref' ? '配置' : '编辑' }}
          </el-button>
          <el-button
            v-if="canConvertSmart"
            plain
            size="small"
            type="warning"
            @click.stop="handleConvertToSmart"
          >转为智能</el-button>
          <el-button plain size="small" type="info" :icon="CopyDocument" @click.stop="handleCopy">复制</el-button>
          <el-button plain size="small" type="danger" :icon="Delete" @click.stop="handleDelete">删除</el-button>
        </div>
      </div>
      
      <!-- 片段引用展示 -->
      <div v-if="step.method === 'fragment_ref'" class="fragment-ref-box">
        <p>引用片段：<strong>{{ step.params?.fragment_name || step.desc }}</strong></p>
        <p v-if="step.params?.fragment_id" class="muted">ID: {{ step.params.fragment_id }} · 锁定版本 v{{ step.params?.fragment_version || '?' }}</p>
        <div v-if="fragmentVarEntries.length" class="fragment-vars">
          <span class="muted">入参：</span>
          <el-tag v-for="item in fragmentVarEntries" :key="item.key" size="small" type="info">
            {{ item.key }}={{ item.value || '（空）' }}
          </el-tag>
        </div>
        <p class="hint">执行时将自动展开为片段内步骤；修改片段后引用处自动生效（版本号仅作提示）。</p>
        <div class="fragment-actions">
          <el-button v-if="fragmentOutdated" link type="warning" size="small" @click="syncFragmentVersion">同步至最新版本号</el-button>
          <el-button link type="primary" size="small" @click="handleExpandFragment">展开为普通步骤</el-button>
        </div>
      </div>

      <!-- 条件分支展示 -->
      <div v-if="step.method === 'condition_branch'" class="branches-container">
        <div 
          v-for="(branch, bIndex) in step.branches" 
          :key="branch.id || `branch_${bIndex}_${step.id || '0'}`"
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
          <el-button link size="small" type="primary" :icon="Plus" @click="handleAddBranch">
            添加条件分支
          </el-button>
        </div>
      </div>
      
      <!-- 步骤参数预览（非条件分支、非片段引用） -->
      <div class="line2" v-if="step.method !== 'condition_branch' && step.method !== 'fragment_ref' && hasParams">
        <p>{{ getParamsDisplay(step.params) }}</p>
      </div>

      <!-- 最近一次执行失败信息（默认收起） -->
      <div v-if="executionHint" class="execution-error-box">
        <div class="execution-error-header" @click="errorExpanded = !errorExpanded">
          <el-tag :type="executionHint.status === 'error' ? 'danger' : 'warning'" size="small">
            {{ executionHintLabel }}
          </el-tag>
          <el-tag
            v-if="executionHint.failure_code"
            size="small"
            :type="failureCodeTagType(executionHint.failure_code)"
            effect="plain"
          >
            {{ formatFailureCode(executionHint.failure_code) }}
          </el-tag>
          <span class="execution-error-toggle">{{ errorExpanded ? '收起' : '展开' }}详情</span>
          <el-icon class="execution-error-arrow">
            <ArrowDown v-if="!errorExpanded" />
            <ArrowUp v-else />
          </el-icon>
        </div>
        <div v-show="errorExpanded" class="execution-error-body">
          <p v-if="executionHint.message" class="execution-error-message">{{ executionHint.message }}</p>
          <el-image
            v-if="executionHint.screenshot"
            :src="executionHint.screenshot"
            :preview-src-list="[executionHint.screenshot]"
            fit="contain"
            class="execution-error-shot"
            preview-teleported
          />
        </div>
      </div>

      <!-- 最近一次执行：自愈 / AI Act 救回（默认收起） -->
      <div v-else-if="recoveryHint" class="execution-recovery-box">
        <div class="execution-recovery-header" @click="recoveryExpanded = !recoveryExpanded">
          <el-tag v-if="recoveryKinds.includes('heal')" size="small" type="warning">自愈救过</el-tag>
          <el-tag v-if="recoveryKinds.includes('act')" size="small" type="success">AI Act 救过</el-tag>
          <span class="execution-error-toggle">{{ recoveryExpanded ? '收起' : '展开' }}详情</span>
          <el-icon class="execution-error-arrow">
            <ArrowDown v-if="!recoveryExpanded" />
            <ArrowUp v-else />
          </el-icon>
        </div>
        <div v-show="recoveryExpanded" class="execution-error-body">
          <p v-if="recoveryHint.message" class="execution-recovery-message">{{ recoveryHint.message }}</p>
          <p v-if="recoveryHint.heal?.new" class="execution-recovery-meta">
            自愈定位：<code>{{ recoveryHint.heal.original || '—' }}</code>
            →
            <code>{{ recoveryHint.heal.new }}</code>
          </p>
          <p v-if="recoveryHint.ai_act?.reason || recoveryHint.ai_act?.act_desc" class="execution-recovery-meta">
            Act 规划：{{ recoveryHint.ai_act.act_desc || recoveryHint.ai_act.reason }}
          </p>
        </div>
      </div>

      <div v-else-if="debugRunResult?.status === 'running'" class="execution-running-box">
        <el-tag type="primary" size="small">调试执行中</el-tag>
        <span v-if="debugRunResult.message" class="execution-running-msg">{{ debugRunResult.message }}</span>
      </div>

      <div v-else-if="debugRunResult && debugRunResult.status === 'success'" class="execution-success-box">
        <el-tag type="success" size="small">调试成功</el-tag>
        <div v-if="debugOutcomeVars.length" class="execution-success-vars">
          <div
            v-for="(item, vi) in debugOutcomeVars"
            :key="`${item.name}-${vi}`"
            class="execution-success-var-row"
          >
            <code class="var-name">{{ item.name }}</code>
            <span class="var-eq">=</span>
            <code class="var-value" :title="formatOutcomeValue(item.value)">{{ formatOutcomeValue(item.value) }}</code>
          </div>
        </div>
        <p
          v-else-if="debugOutcomeText"
          class="execution-success-msg"
        >{{ debugOutcomeText }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, inject } from 'vue'
import { Operation, Share, ArrowDown, ArrowRight, ArrowUp, Edit, Delete, Plus, VideoPlay, Collection, CopyDocument, VideoCamera } from '@element-plus/icons-vue'
import { uiFragmentApi } from '@/api/modules/ui'
import { appFragmentApi } from '@/api/modules/app'
import { ProjectStore } from '@/stores/module/ProjectStore'
import BranchStepList from './BranchStepList.vue'
import { formatStepParamValue, canConvertToSmart, convertStepToSmart } from '@/utils/stepHelper'
import { formatExecutionHintStatus } from '@/utils/caseExecutionHints'
import { formatFailureCode, failureCodeTagType } from '@/utils/uiFailureCode'
import { formatOutcomeValue, formatStepOutcomeText } from '@/utils/debugSession.js'
import { ElMessage } from 'element-plus'

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
  },
  selectable: {
    type: Boolean,
    default: false
  },
  selected: {
    type: Boolean,
    default: false
  },
  selectedCount: {
    type: Number,
    default: 0
  },
  executionHint: {
    type: Object,
    default: null
  },
  recoveryHint: {
    type: Object,
    default: null,
  },
  debugSelected: {
    type: Boolean,
    default: false,
  },
  debugRunResult: {
    type: Object,
    default: null,
  },
  debugEnabled: {
    type: Boolean,
    default: true,
  },
  allowInteractiveActions: {
    type: Boolean,
    default: true,
  },
})

const emit = defineEmits(['update:step', 'delete', 'add-branch', 'delete-branch', 'edit', 'debug', 'record-from-step', 'copy', 'expand-fragment', 'toggle-select', 'debug-select', 'run-selected'])

const fragmentRefEdit = inject('fragmentRefEdit', null)
const expandFragmentStep = inject('expandFragmentStep', null)
const editStepMethod = inject('editStepMethod', null)
const interactiveDebugSession = inject('interactiveDebugSession', ref(null))
const runInteractiveDebugStep = inject('runInteractiveDebugStep', null)
const interactiveReady = computed(() => interactiveDebugSession.value?.status === 'ready')
const recordFromStepTooltip = computed(() => (
  props.allowInteractiveActions
    ? '调试已开时可二选一：直接在当前浏览器接录，或先回放前置步再接录'
    : '请先保存用例后再使用交互调试 / 从这里录制'
))
const debugThroughTooltip = computed(() => {
  if (!props.allowInteractiveActions) {
    return '请先保存用例后再使用交互调试 / 从这里录制'
  }
  return interactiveReady.value
    ? '交互调试已就绪：将执行第 1 步到本步'
    : '推荐先打开「交互调试」；也可使用旧版一次性调试'
})
const showRunSelectedBtn = computed(
  () => props.selectable && props.selected && props.selectedCount > 0,
)
const proStore = ProjectStore()
const stepModule = inject('stepEditorModule', computed(() => 'web'))
const canConvertSmart = computed(
  () => stepModule.value === 'web' && canConvertToSmart(props.step),
)
const latestFragmentVersion = ref(null)
const fragmentOutdated = ref(false)
const errorExpanded = ref(false)
const recoveryExpanded = ref(false)

const fragmentVarEntries = computed(() => {
  const vars = props.step.params?.variables
  if (!vars || typeof vars !== 'object') return []
  return Object.entries(vars).map(([key, value]) => ({ key, value: value ?? '' }))
})

const stepIconColor = computed(() => {
  if (props.step.method === 'fragment_ref') return '#67c23a'
  if (props.step.method === 'condition_branch') return '#e6a23c'
  return 'var(--el-color-primary)'
})

const stepClasses = computed(() => ({
  'is-nested': props.depth > 0,
  'is-condition': props.step.method === 'condition_branch',
  'is-fragment': props.step.method === 'fragment_ref',
  'is-selected': props.selectable && props.selected,
  'is-failed': !!props.executionHint,
  'is-recovered': !!props.recoveryHint && !props.executionHint,
  'is-debug-selected': props.debugSelected,
  'is-debug-running': props.debugRunResult?.status === 'running',
  'is-debug-success': props.debugRunResult?.status === 'success' && !props.executionHint,
  'is-debug-failed': props.executionHint && props.debugSelected,
}))

const executionHintLabel = computed(() => formatExecutionHintStatus(props.executionHint?.status))

const debugOutcomeVars = computed(() => {
  const list = props.debugRunResult?.variables
  return Array.isArray(list) ? list.filter((v) => v && v.name) : []
})

const debugOutcomeText = computed(() => formatStepOutcomeText(props.debugRunResult))
const recoveryKinds = computed(() => {
  const kinds = props.recoveryHint?.kinds
  return Array.isArray(kinds) ? kinds : []
})

async function checkFragmentVersion() {
  if (props.step.method !== 'fragment_ref') return
  const fid = props.step.params?.fragment_id
  const projectId = proStore.projectInfo?.id
  if (!fid || !projectId) return
  try {
    const api = stepModule.value === 'app' ? appFragmentApi : uiFragmentApi
    const res = await api.getDetail(fid, projectId)
    latestFragmentVersion.value = res.data?.data?.version
    const pinned = props.step.params?.fragment_version
    fragmentOutdated.value = pinned != null && latestFragmentVersion.value != null && pinned < latestFragmentVersion.value
  } catch {
    fragmentOutdated.value = false
  }
}

function syncFragmentVersion() {
  if (!latestFragmentVersion.value) return
  const updated = {
    ...props.step,
    params: {
      ...props.step.params,
      fragment_version: latestFragmentVersion.value,
    },
  }
  emit('update:step', updated)
  fragmentOutdated.value = false
}

async function handleExpandFragment() {
  if (!expandFragmentStep) return
  await expandFragmentStep(props.step, (expanded) => {
    emit('expand-fragment', { index: props.index, expanded })
  })
}

onMounted(checkFragmentVersion)
watch(() => props.step.params?.fragment_id, checkFragmentVersion)

// 当前路径
const currentPath = computed(() => [...props.parentPath, props.index])

// 折叠状态
const collapsedBranches = ref({})

// 是否有参数
const hasParams = computed(() => {
  return props.step.params && Object.keys(props.step.params).length > 0
})

// 切换分支折叠
function toggleBranch(bIndex) {
  collapsedBranches.value[bIndex] = !collapsedBranches.value[bIndex]
}

// 更新整个分支
function updateBranch(bIndex, newBranch) {
  // 创建新的步骤对象，确保触发响应式更新
  // 使用深拷贝避免引用问题
  const currentBranches = props.step.branches || []
  const newBranches = currentBranches.map((b, i) => {
    if (i === bIndex) {
      // 深拷贝新分支数据
      return JSON.parse(JSON.stringify(newBranch))
    }
    return { ...b }
  })
  
  const newStepData = {
    ...props.step,
    branches: newBranches
  }
  emit('update:step', newStepData)
}

// 编辑
function handleEdit() {
  if (props.step.method === 'fragment_ref' && fragmentRefEdit) {
    fragmentRefEdit(props.step, (updated) => emit('update:step', updated))
    return
  }
  if (editStepMethod && props.depth > 0) {
    editStepMethod(props.step, currentPath.value)
    return
  }
  emit('edit')
}

/** SMART-1：普通点击/输入 → 智能步骤 */
function handleConvertToSmart() {
  const next = convertStepToSmart(props.step)
  if (!next) return
  emit('update:step', next)
  ElMessage.success(`已转为「${next.keyword}」，请编辑补全 target / intent`)
}

function handleDebug() {
  if (!props.allowInteractiveActions || !props.debugEnabled) return
  emit('debug', props.index)
}

function handleRecordFromStep() {
  if (!props.allowInteractiveActions) return
  emit('record-from-step', props.index)
}

function handleInteractiveRun() {
  if (typeof runInteractiveDebugStep === 'function') {
    runInteractiveDebugStep(props.index)
  }
}

function handleRunSelected() {
  emit('run-selected')
}

function handleSelectForDebug() {
  if (props.depth === 0) {
    emit('debug-select', props.index)
  }
}

function handleCopy() {
  emit('copy')
}

function handleToggleSelect() {
  emit('toggle-select')
}

// 删除
function handleDelete() {
  emit('delete')
}

// 添加分支
function handleAddBranch() {
  // 确保分支数据存在
  if (!props.step.branches) {
    const newStep = { 
      ...props.step, 
      branches: [
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
    emit('update:step', newStep)
  }
  emit('add-branch')
}

// 删除分支
function handleDeleteBranch(bIndex) {
  emit('delete-branch', bIndex)
}

function formatConditionLocator(locator) {
  if (locator == null || locator === '') return ''
  if (typeof locator === 'string') return locator.trim()
  if (typeof locator === 'object') {
    const by = locator.by || ''
    const value = String(locator.value || '').trim()
    if (!value) return ''
    return by ? `${by}=${value}` : value
  }
  return String(locator)
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
  const locatorText = formatConditionLocator(condition.locator)
  if (needsLocator) {
    if (!locatorText) return `${typeName} ${operator} · 未配置定位`
    const short = locatorText.length > 40 ? `${locatorText.slice(0, 40)}…` : locatorText
    return `${typeName} ${operator} · ${short}`
  }
  const expected = String(condition.expected_value || condition.script || '').trim()
  if (expected) {
    const short = expected.length > 24 ? `${expected.slice(0, 24)}…` : expected
    return `${typeName} ${operator} · ${short}`
  }
  return `${typeName} ${operator}`
}

// 获取参数显示
function getParamsDisplay(params) {
  if (!params) return ''

  const display = []
  for (const [key, value] of Object.entries(params)) {
    const formatted = formatStepParamValue(value)
    if (formatted !== null) {
      display.push(`${key}: ${formatted}`)
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

  &.is-selected {
    border-color: var(--el-color-primary);
    box-shadow: 0 0 0 1px var(--el-color-primary-light-7);
  }

  &.is-failed {
    border-color: var(--el-color-danger);
    background: var(--el-color-danger-light-9);

    .step-index {
      color: var(--el-color-danger);
      background: var(--el-color-danger-light-7);
    }
  }

  &.is-debug-selected {
    box-shadow: 0 0 0 2px var(--el-color-primary-light-5);
    border-color: var(--el-color-primary);
  }

  &.is-debug-running {
    border-left: 3px solid var(--el-color-primary);
    animation: debug-running-pulse 1.2s ease-in-out infinite;
  }

  &.is-debug-success {
    border-left: 3px solid var(--el-color-success);
  }
}

@keyframes debug-running-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(64, 158, 255, 0.15); }
  50% { box-shadow: 0 0 0 4px rgba(64, 158, 255, 0.08); }
}

.line1 {
  display: flex;
  align-items: center;
  gap: 8px;

  .step-drag-handle {
    flex-shrink: 0;
    width: 18px;
    text-align: center;
    color: var(--el-text-color-placeholder);
    cursor: grab;
    user-select: none;
    font-size: 12px;
    line-height: 1;
    letter-spacing: -2px;

    &:active {
      cursor: grabbing;
    }
  }

  .step-select-box {
    flex-shrink: 0;
    margin-right: -4px;
  }
  
  .step-index {
    flex-shrink: 0;
    font-size: 12px;
    font-weight: bold;
    color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
    padding: 2px 8px;
    border-radius: 4px;
    min-width: 50px;
    text-align: center;
    cursor: pointer;
  }
  
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

.execution-error-box {
  margin-top: 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid var(--el-color-danger-light-5);
  overflow: hidden;
}

.execution-recovery-box {
  margin-top: 10px;
  border-radius: 6px;
  background: #fff;
  border: 1px solid var(--el-color-warning-light-5);
  overflow: hidden;
}

.execution-recovery-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}

.execution-recovery-box .execution-error-body {
  border-top: 1px dashed var(--el-color-warning-light-5);
}

.execution-recovery-message,
.execution-recovery-meta {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
}

.execution-recovery-meta code {
  font-size: 11px;
  padding: 0 4px;
  background: var(--el-fill-color);
  border-radius: 3px;
}

.recovery-tags {
  display: inline-flex;
  gap: 4px;
  margin-left: 6px;
  flex-shrink: 0;
}

.step.is-recovered {
  border-color: var(--el-color-warning-light-5);
}

.execution-error-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}

.execution-error-toggle {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.execution-error-arrow {
  color: var(--el-text-color-secondary);
}

.execution-error-body {
  padding: 0 12px 10px;
  border-top: 1px dashed var(--el-color-danger-light-7);
}

.execution-error-message {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-color-danger);
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.execution-error-shot {
  margin-top: 8px;
  max-width: 320px;
  max-height: 180px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
}

.execution-success-box {
  margin-top: 8px;
  padding: 8px 12px;
  border-top: 1px dashed var(--el-color-success-light-7);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.execution-success-msg {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

.execution-success-vars {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.execution-success-var-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  line-height: 1.45;
}

.execution-success-var-row .var-name {
  flex: 0 0 auto;
  max-width: 140px;
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  padding: 1px 6px;
  border-radius: 3px;
  word-break: break-all;
}

.execution-success-var-row .var-eq {
  color: var(--el-text-color-secondary);
  flex: 0 0 auto;
}

.execution-success-var-row .var-value {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 3px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow: auto;
}

.execution-running-box {
  margin-top: 8px;
  padding: 8px 12px;
  border-top: 1px dashed var(--el-color-primary-light-7);
  display: flex;
  align-items: center;
  gap: 8px;
}

.execution-running-msg {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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

.step.is-fragment {
  border-color: var(--el-color-success-light-5);
  background: var(--el-color-success-light-9);
}

.fragment-ref-box {
  margin-top: 10px;
  padding: 10px 12px;
  background: #fff;
  border-radius: 6px;
  border: 1px dashed var(--el-color-success-light-5);
  font-size: 13px;

  p {
    margin: 0 0 6px;
  }

  .muted {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  .hint {
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  .fragment-vars {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
  }

  .fragment-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
}
</style>
