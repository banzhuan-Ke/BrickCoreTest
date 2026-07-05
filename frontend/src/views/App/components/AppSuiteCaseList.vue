<template>
  <div class="suite-case-list" @dragover.prevent @drop="handleDrop">
    <div class="case-list">
      <div
        v-for="(element, index) in suiteCaseList"
        :key="element.step_id || element.case_id || element.id"
        class="case-item"
        draggable="true"
        @dragstart="handleDragStart($event, index)"
        @dragover.prevent
        @drop="handleItemDrop($event, index)"
      >
        <div class="drag-handle">
          <el-icon><Rank /></el-icon>
        </div>
        <div class="case-info">
          <span class="case-index">{{ index + 1 }}</span>
          <span class="case-name" :title="element.name">{{ element.name }}</span>
          <el-tag v-if="element.level" size="small" type="info">{{ element.level }}</el-tag>
        </div>
        <div class="case-actions">
          <el-tooltip content="跳过执行" placement="top">
            <el-switch v-model="element.skip" size="small" @click.stop />
          </el-tooltip>
          <el-tooltip content="编辑用例" placement="top">
            <el-button
              :icon="Edit"
              circle
              size="small"
              type="primary"
              plain
              @click="editCase(element.case_id)"
            />
          </el-tooltip>
          <el-tooltip content="移除" placement="top">
            <el-button
              :icon="Delete"
              circle
              size="small"
              type="danger"
              plain
              @click="removeCase(index)"
            />
          </el-tooltip>
        </div>
      </div>
    </div>
    <div v-if="suiteCaseList.length === 0" class="empty-tip">
      <el-empty description="暂无套件用例，请从下方拖拽添加" :image-size="60" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Rank, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { appSuiteApi } from '@/api'

const props = defineProps({
  suiteId: {
    type: [String, Number],
    default: null,
  },
})

const emit = defineEmits(['cases-change'])

const router = useRouter()
const suiteCaseList = ref([])
const dragIndex = ref(-1)

function emitChange() {
  emit(
    'cases-change',
    suiteCaseList.value.map((item) => item.case_id).filter(Boolean)
  )
}

async function loadCases() {
  if (!props.suiteId) {
    suiteCaseList.value = []
    emitChange()
    return
  }
  try {
    const res = await appSuiteApi.listCases(props.suiteId)
    suiteCaseList.value = (res.data || []).map((item) => ({
      step_id: item.step_id,
      case_id: item.case_id,
      name: item.name,
      sort: item.sort,
      skip: !!item.skip,
      level: item.level,
    }))
    emitChange()
  } catch {
    suiteCaseList.value = []
    emitChange()
  }
}

function removeCase(index) {
  suiteCaseList.value.splice(index, 1)
  suiteCaseList.value.forEach((item, idx) => {
    item.sort = idx
  })
  emitChange()
  ElMessage.success('已移除')
}

function editCase(caseId) {
  router.push({ name: 'appCaseEdit', params: { id: caseId } })
}

function handleDragStart(e, index) {
  dragIndex.value = index
  e.dataTransfer.effectAllowed = 'move'
}

function handleItemDrop(e, dropIndex) {
  e.preventDefault()
  if (dragIndex.value === -1 || dragIndex.value === dropIndex) return
  const item = suiteCaseList.value.splice(dragIndex.value, 1)[0]
  suiteCaseList.value.splice(dropIndex, 0, item)
  suiteCaseList.value.forEach((row, idx) => {
    row.sort = idx
  })
  dragIndex.value = -1
  emitChange()
}

function handleDrop(e) {
  e.preventDefault()
  const data = e.dataTransfer.getData('application/json')
  if (!data) return
  try {
    const caseItem = JSON.parse(data)
    if (suiteCaseList.value.some((item) => item.case_id === caseItem.id)) {
      ElMessage.warning('该用例已在套件中')
      return
    }
    suiteCaseList.value.push({
      case_id: caseItem.id,
      name: caseItem.name,
      level: caseItem.level,
      sort: suiteCaseList.value.length,
      skip: false,
    })
    emitChange()
    ElMessage.success('已添加用例，请保存套件')
  } catch {
    ElMessage.error('添加用例失败')
  }
}

function getCasePayload() {
  return suiteCaseList.value.map((row, i) => ({
    case_id: row.case_id,
    sort: i,
    skip: !!row.skip,
  }))
}

async function saveSuiteCases(suiteId) {
  const id = suiteId || props.suiteId
  if (!id) return true
  try {
    await appSuiteApi.replaceCases(id, getCasePayload())
    await loadCases()
    return true
  } catch {
    ElMessage.error('保存套件用例失败')
    return false
  }
}

defineExpose({ saveSuiteCases, getCasePayload, loadCases })

watch(
  () => props.suiteId,
  () => {
    loadCases()
  },
  { immediate: true }
)

onMounted(loadCases)
</script>

<style scoped lang="scss">
.suite-case-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 100px;
}

.case-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.case-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: grab;

  &:hover {
    border-color: var(--el-color-primary);
    background: var(--el-color-primary-light-9);
  }

  &:active {
    cursor: grabbing;
  }
}

.drag-handle {
  color: var(--el-text-color-secondary);
  cursor: grab;
}

.case-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.case-index {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.case-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.case-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.empty-tip {
  padding: 12px 0;
}
</style>
