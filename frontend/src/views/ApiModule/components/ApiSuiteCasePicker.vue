<template>
  <div class="api-suite-case-picker">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="order-tip"
    >
      套件按<strong>执行序号</strong>从上到下依次运行；前置用例提取的变量（如 token）可在后续用例中通过
      <code v-pre>${{变量名}}</code> 引用。请把登录、取 token 等用例排在前面。
    </el-alert>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="order-tip auth-priority-tip"
    >
      若已在 <strong>Token 授权</strong> 中启用登录并提取同名变量（如 <code v-pre>token</code>），
      授权会在每条用例执行前<strong>覆盖</strong>套件传递的值，前序登录用例 extract 的 token 对后续用例通常<strong>不生效</strong>。
      请与 Token 授权<strong>二选一</strong>：要么关闭授权、用套件链式登录；要么用授权、不必在套件里放登录用例。
    </el-alert>

    <div class="picker-panels">
      <div class="panel available-panel">
        <div class="panel-header">
          <span>可选用例</span>
          <el-select
            v-model="filterPriority"
            placeholder="优先级"
            clearable
            size="small"
            class="filter-priority"
          >
            <el-option label="P0" value="P0" />
            <el-option label="P1" value="P1" />
            <el-option label="P2" value="P2" />
            <el-option label="P3" value="P3" />
          </el-select>
          <el-input
            v-model="filterKeyword"
            placeholder="搜索用例"
            clearable
            size="small"
            class="filter-input"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div class="panel-body">
          <div
            v-for="item in filteredAvailable"
            :key="item.id"
            class="case-row available-row"
            @click="addCase(item)"
          >
            <el-tag v-if="item.priority" size="small" :type="priorityType(item.priority)" class="prio-tag">
              {{ item.priority }}
            </el-tag>
            <span class="case-name" :title="item.name">{{ item.name }}</span>
            <span class="api-name">{{ item.api_name || '-' }}</span>
            <el-button type="primary" link size="small" @click.stop="addCase(item)">
              添加
            </el-button>
          </div>
          <el-empty v-if="filteredAvailable.length === 0" description="无匹配用例" :image-size="48" />
        </div>
      </div>

      <div class="panel selected-panel">
        <div class="panel-header">
          <span>已选用例（{{ selectedList.length }}）</span>
          <span class="sub-title">拖拽或使用箭头调整执行顺序</span>
        </div>
        <div class="panel-body selected-body">
          <VueDraggable
            v-model="selectedList"
            :animation="200"
            handle=".drag-handle"
            class="selected-list"
            @end="emitOrder"
          >
            <div
              v-for="(item, index) in selectedList"
              :key="item.id"
              class="case-row selected-row"
            >
              <span class="exec-order" :title="`执行序号 ${index + 1}`">{{ index + 1 }}</span>
              <el-icon class="drag-handle"><Rank /></el-icon>
              <div class="case-main">
                <span class="case-name" :title="item.name">{{ item.name }}</span>
                <span class="api-name">{{ item.api_name || '-' }}</span>
              </div>
              <div class="row-actions">
                <el-button
                  link
                  size="small"
                  :disabled="index === 0"
                  @click="moveUp(index)"
                >
                  <el-icon><ArrowUp /></el-icon>
                </el-button>
                <el-button
                  link
                  size="small"
                  :disabled="index === selectedList.length - 1"
                  @click="moveDown(index)"
                >
                  <el-icon><ArrowDown /></el-icon>
                </el-button>
                <el-button link type="danger" size="small" @click="removeAt(index)">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </VueDraggable>
          <el-empty
            v-if="selectedList.length === 0"
            description="请从左侧添加用例"
            :image-size="48"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import { Search, Rank, ArrowUp, ArrowDown, Close } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  caseOptions: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue'])

const filterKeyword = ref('')
const filterPriority = ref(null)
const selectedList = ref([])
const syncingFromParent = ref(false)

const optionMap = computed(() => {
  const map = new Map()
  for (const c of props.caseOptions) {
    map.set(c.id, c)
  }
  return map
})

const syncFromModelValue = (ids) => {
  syncingFromParent.value = true
  selectedList.value = (ids || [])
    .map((id) => optionMap.value.get(id))
    .filter(Boolean)
  syncingFromParent.value = false
}

watch(
  () => props.modelValue,
  (ids) => syncFromModelValue(ids),
  { immediate: true, deep: true }
)

watch(
  () => props.caseOptions,
  () => syncFromModelValue(props.modelValue),
  { deep: true }
)

const priorityType = (p) => {
  const map = { P0: 'danger', P1: 'warning', P2: '', P3: 'info' }
  return map[p] || ''
}

const filteredAvailable = computed(() => {
  const selectedIds = new Set(selectedList.value.map((c) => c.id))
  const kw = filterKeyword.value.trim().toLowerCase()
  const prio = filterPriority.value
  return props.caseOptions.filter((c) => {
    if (selectedIds.has(c.id)) return false
    if (prio && c.priority !== prio) return false
    if (!kw) return true
    const text = `${c.name} ${c.api_name || ''} ${c.priority || ''}`.toLowerCase()
    return text.includes(kw)
  })
})

const emitOrder = () => {
  if (syncingFromParent.value) return
  emit(
    'update:modelValue',
    selectedList.value.map((c) => c.id)
  )
}

const addCase = (item) => {
  if (selectedList.value.some((c) => c.id === item.id)) return
  selectedList.value.push({ ...item })
  emitOrder()
}

const removeAt = (index) => {
  selectedList.value.splice(index, 1)
  emitOrder()
}

const moveUp = (index) => {
  if (index <= 0) return
  const list = selectedList.value
  ;[list[index - 1], list[index]] = [list[index], list[index - 1]]
  emitOrder()
}

const moveDown = (index) => {
  if (index >= selectedList.value.length - 1) return
  const list = selectedList.value
  ;[list[index], list[index + 1]] = [list[index + 1], list[index]]
  emitOrder()
}
</script>

<style lang="scss" scoped>
.api-suite-case-picker {
  width: 100%;
}

.order-tip {
  margin-bottom: 12px;

  code {
    padding: 0 4px;
    font-size: 12px;
  }
}

.picker-panels {
  display: flex;
  gap: 16px;
  min-height: 320px;

  @media (max-width: 900px) {
    flex-direction: column;
  }
}

.panel {
  flex: 1;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.panel-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 500;
  font-size: 14px;

  .sub-title {
    font-weight: normal;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    margin-left: auto;
  }

  .filter-priority {
    width: 88px;
    margin-left: auto;
  }

  .filter-input {
    width: 140px;
  }
}

.prio-tag {
  flex-shrink: 0;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  max-height: 360px;
  padding: 8px;
}

.case-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 4px;
  margin-bottom: 6px;
  font-size: 13px;
}

.available-row {
  cursor: pointer;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);

  &:hover {
    border-color: var(--el-color-primary-light-5);
    background: var(--el-color-primary-light-9);
  }
}

.selected-row {
  border: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-light);

  .drag-handle {
    cursor: grab;
    color: var(--el-text-color-secondary);
    flex-shrink: 0;

    &:active {
      cursor: grabbing;
    }
  }
}

.exec-order {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  line-height: 26px;
  text-align: center;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.case-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.case-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.api-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.available-row .case-name {
  flex: 1;
}

.available-row .api-name {
  max-width: 120px;
  flex-shrink: 0;
}

.row-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.selected-list {
  min-height: 40px;
}
</style>
